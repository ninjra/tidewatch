# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Plan stub generator — structured prompt templates for high-pressure obligations.

This is a TEMPLATE ENGINE, not an NLP system. It:
  1. Selects obligations that exceed pressure zone thresholds
  2. Fills structured prompt templates with obligation metadata
  3. Stages the result as a PlanRequest for the caller's LLM

The caller provides the LLM. Tidewatch never invokes inference directly.
When integrated with an orchestration layer, plan stubs can be enriched by the
caller's LLM — that is a caller capability, not a Tidewatch one.

Runs synchronously after ranking. No daemon, no event loop, no concurrency.
complete_plan() uses datetime.now(UTC) for timestamp — callers requiring
reproducibility should pass an explicit `now` value.

Usage:
  planner = PlanStubGenerator()
  requests = planner.generate_plan_requests(pressure_results, obligations)
  for req in requests:
      llm_output = my_llm(req.prompt)  # caller's LLM, not ours
      result = planner.complete_plan(req, llm_output)
"""

import logging
from datetime import UTC, datetime

from tidewatch.constants import (
    DEFAULT_DELIVERY_URGENCY,
    DELIVERY_URGENCY_MAP,
    PLANNER_ASCII_PRINTABLE_MIN,
    PLANNER_DESC_MAX_LEN,
    PLANNER_DOMAIN_MAX_LEN,
    PLANNER_MAX_TOKENS,
    PLANNER_MIN_ZONES,
    PLANNER_TITLE_MAX_LEN,
    PLANNER_TOP_N,
)
from tidewatch.types import Obligation, PlanRequest, PlanResult, PressureResult

logger = logging.getLogger(__name__)

# Approximate chars-per-token for prompt length estimation
_CHARS_PER_TOKEN = 4



_DEFAULT_SYSTEM_PROMPT = (
    "You are a task planning assistant. "
    "Given an obligation with its deadline and pressure level, "
    "produce 2-3 concrete next steps.\n"
    "Each step must be:\n"
    "- Actionable (not \"think about\" or \"consider\")\n"
    "- Completable in one sitting (under 2 hours)\n"
    "- Specific enough to start immediately\n"
    "Be concise. No preamble."
)

class PlanStubGenerator:
    """Generates structured prompt stubs for high-pressure obligations.

    This is a template engine: it selects obligations by zone threshold,
    fills prompt templates with obligation metadata, and stages results
    for the caller's LLM. No inference, no NLP, no generation.

    Inputs (constructor):
      min_zones: set of zone names that trigger stub generation
      top_n: max obligations to generate stubs for per cycle
      system_prompt: override default system prompt
      delivery_urgency_map: zone-to-urgency mapping (default from constants)
      default_delivery_urgency: fallback for unknown zones (default from constants)

    Notes:
      This class has no side effects. It produces PlanRequest objects
      that the caller sends to their LLM. After receiving the LLM
      output, the caller calls complete_plan() to wrap it in a
      PlanResult.
    """

    def __init__(
        self,
        min_zones: frozenset[str] | set[str] | None = None,
        top_n: int | None = None,
        system_prompt: str | None = None,
        delivery_urgency_map: dict[str, str] | None = None,
        default_delivery_urgency: str | None = None,
    ) -> None:
        self.min_zones = frozenset(min_zones) if min_zones else PLANNER_MIN_ZONES
        self.top_n = top_n if top_n is not None else PLANNER_TOP_N
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self.delivery_urgency_map = (
            delivery_urgency_map if delivery_urgency_map is not None
            else DELIVERY_URGENCY_MAP
        )
        self.default_delivery_urgency = (
            default_delivery_urgency if default_delivery_urgency is not None
            else DEFAULT_DELIVERY_URGENCY
        )

    # Prompt injection markers to strip (#1215).
    # These are common patterns used to hijack LLM context windows.
    _INJECTION_MARKERS: tuple[str, ...] = (
        "SYSTEM:",
        "```",
        "IGNORE PREVIOUS",
    )

    @staticmethod
    def _sanitize(text: str, max_len: int = PLANNER_DESC_MAX_LEN) -> str:
        """Sanitize user-provided text for LLM prompt inclusion.

        Strips control characters, truncates to max_len, and strips
        common prompt injection markers (#1215).
        """
        if not text:
            return ""
        # Strip control chars except newline/tab
        cleaned = "".join(c for c in text if c == "\n" or c == "\t" or (ord(c) >= PLANNER_ASCII_PRINTABLE_MIN))
        # Strip prompt injection markers (#1215)
        for marker in PlanStubGenerator._INJECTION_MARKERS:
            cleaned = cleaned.replace(marker, "")
        # Truncate
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len] + "..."
        return cleaned

    def _build_prompt(self, obligation: Obligation, result: PressureResult) -> str:
        """Build the LLM prompt for a single obligation."""
        title = self._sanitize(obligation.title, max_len=PLANNER_TITLE_MAX_LEN)
        desc = self._sanitize(obligation.description or "", max_len=PLANNER_DESC_MAX_LEN)
        domain = self._sanitize(obligation.domain or "general", max_len=PLANNER_DOMAIN_MAX_LEN)

        prompt = (
            f"Obligation: {title}\n"
            f"Description: {desc}\n"
            f"Due: {obligation.due_date}\n"
            f"Pressure zone: {result.zone} (score {result.pressure:.2f})\n"
            f"Domain: {domain}\n\n"
            f"Produce 2-3 concrete next steps. Each step must be:\n"
            f"- Actionable (not \"think about\" or \"consider\")\n"
            f"- Completable in one sitting (under 2 hours)\n"
            f"- Specific enough to start immediately\n"
            f"Be concise. No preamble."
        )

        # Enforce token budget
        max_chars = PLANNER_MAX_TOKENS * _CHARS_PER_TOKEN
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars]
        return prompt

    def generate_plan_requests(
        self,
        pressure_results: list[PressureResult],
        obligations: list[Obligation] | None = None,
        obligation_map: dict[int | str, Obligation] | None = None,
    ) -> list[PlanRequest]:
        """Generate plan requests for high-pressure obligations."""
        # Build obligation lookup
        ob_map: dict[int | str, Obligation] = {}
        if obligation_map is not None:
            ob_map = obligation_map
        elif obligations is not None:
            ob_map = {ob.id: ob for ob in obligations}

        # Filter and sort
        eligible = [
            r for r in pressure_results
            if r.zone in self.min_zones
        ]
        eligible.sort(key=lambda r: r.pressure, reverse=True)
        top = eligible[:self.top_n]

        requests: list[PlanRequest] = []
        for result in top:
            obligation = ob_map.get(result.obligation_id)
            if obligation is None:
                continue

            prompt = self._build_prompt(obligation, result)
            urgency = self._resolve_urgency(result)

            requests.append(PlanRequest(
                obligation=obligation,
                pressure_result=result,
                prompt=prompt,
                delivery_urgency=urgency,
            ))

        return requests

    def _resolve_urgency(self, result: PressureResult) -> str:
        """Map zone to delivery urgency, with fallback logging."""
        if result.zone in self.delivery_urgency_map:
            return self.delivery_urgency_map[result.zone]
        logger.warning(
            "Unknown zone %r for obligation %s — using default urgency %r",
            result.zone, result.obligation_id, self.default_delivery_urgency,
        )
        return self.default_delivery_urgency

    def complete_plan(
        self,
        plan_request: PlanRequest,
        plan_text: str,
        now: datetime | None = None,
    ) -> PlanResult:
        """Wrap LLM output in a PlanResult.

        Inputs:
          plan_request: the PlanRequest that was sent to the LLM
          plan_text: the raw LLM output
          now: timestamp for the plan (default: UTC now)

        Outputs:
          PlanResult with obligation metadata and plan text
        """
        if now is None:
            now = datetime.now(UTC)
        return PlanResult(
            obligation_id=plan_request.obligation.id,
            plan_text=plan_text,
            zone=plan_request.pressure_result.zone,
            pressure=plan_request.pressure_result.pressure,
            created_at=now,
        )


# Public API alias — tests and downstream callers use this name.
# Exported via tidewatch.__init__.__all__.
SpeculativePlanner = PlanStubGenerator
