"""Speculative planner -- idle-time plan generation for high-pressure obligations.

Returns prompt templates. The caller provides the LLM.
No inference calls, no database, no async.

Usage:
  planner = SpeculativePlanner()
  requests = planner.generate_plan_requests(pressure_results, obligations)
  for req in requests:
      llm_output = my_llm(req.prompt)
      result = planner.complete_plan(req, llm_output)
"""

from datetime import datetime, timezone

from tidewatch.constants import PLANNER_MIN_ZONES, PLANNER_TOP_N
from tidewatch.types import Obligation, PlanRequest, PlanResult, PressureResult


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

_DELIVERY_URGENCY_MAP: dict[str, str] = {
    "green": "background",
    "yellow": "background",
    "orange": "toast",
    "red": "interrupt",
}


class SpeculativePlanner:
    """Generates plan requests for high-pressure obligations.

    Inputs (constructor):
      min_zones: set of zone names that trigger planning
      top_n: max obligations to plan per cycle
      system_prompt: override default system prompt

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
    ) -> None:
        self.min_zones = frozenset(min_zones) if min_zones else PLANNER_MIN_ZONES
        self.top_n = top_n if top_n is not None else PLANNER_TOP_N
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    def _build_prompt(self, obligation: Obligation, result: PressureResult) -> str:
        """Build the LLM prompt for a single obligation."""
        return (
            f"Obligation: {obligation.title}\n"
            f"Description: {obligation.description or ''}\n"
            f"Due: {obligation.due_date}\n"
            f"Pressure zone: {result.zone} (score {result.pressure:.2f})\n"
            f"Domain: {obligation.domain or 'general'}\n\n"
            f"Produce 2-3 concrete next steps. Each step must be:\n"
            f"- Actionable (not \"think about\" or \"consider\")\n"
            f"- Completable in one sitting (under 2 hours)\n"
            f"- Specific enough to start immediately\n"
            f"Be concise. No preamble."
        )

    def generate_plan_requests(
        self,
        pressure_results: list[PressureResult],
        obligations: list[Obligation] | None = None,
        obligation_map: dict[int | str, Obligation] | None = None,
    ) -> list[PlanRequest]:
        """Generate plan requests for high-pressure obligations.

        Inputs:
          pressure_results: list of PressureResult (typically from recalculate_batch)
          obligations: optional list of Obligation (builds map internally)
          obligation_map: optional pre-built {id: Obligation} map

        Logic:
          1. Filter to results in min_zones
          2. Sort by pressure descending
          3. Take top_n
          4. Build prompt for each
          5. Determine delivery urgency by zone

        Outputs:
          list[PlanRequest] for caller to send to LLM
        """
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
            urgency = _DELIVERY_URGENCY_MAP.get(result.zone, "background")

            requests.append(PlanRequest(
                obligation=obligation,
                pressure_result=result,
                prompt=prompt,
                delivery_urgency=urgency,
            ))

        return requests

    def complete_plan(
        self,
        plan_request: PlanRequest,
        plan_text: str,
    ) -> PlanResult:
        """Wrap LLM output in a PlanResult.

        Inputs:
          plan_request: the PlanRequest that was sent to the LLM
          plan_text: the raw LLM output

        Outputs:
          PlanResult with obligation metadata and plan text
        """
        return PlanResult(
            obligation_id=plan_request.obligation.id,
            plan_text=plan_text,
            zone=plan_request.pressure_result.zone,
            pressure=plan_request.pressure_result.pressure,
            created_at=datetime.now(timezone.utc),
        )
