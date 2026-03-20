# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Core types for Tidewatch.

All types are plain dataclasses using only stdlib.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

# --- Zone enum ---

class Zone(enum.Enum):
    """Operational pressure zones.

    Ordered by severity: GREEN < YELLOW < ORANGE < RED.
    """
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        order = [Zone.GREEN, Zone.YELLOW, Zone.ORANGE, Zone.RED]
        return order.index(self) < order.index(other)

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        order = [Zone.GREEN, Zone.YELLOW, Zone.ORANGE, Zone.RED]
        return order.index(self) > order.index(other)

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        return self == other or self > other


# --- Obligation ---

@dataclass
class Obligation:
    """A tracked obligation with deadline and metadata.

    Inputs:
      id: unique identifier
      title: human-readable name
      due_date: deadline (None = no deadline = no pressure)
      materiality: "material" or "routine"
      dependency_count: number of obligations that depend on this one
      completion_pct: 0.0 to 1.0
      domain: optional domain tag (e.g., "legal", "financial")
      description: optional free-text description
      status: obligation lifecycle state

    Notes:
      Caller manages persistence. Tidewatch only computes on these.
    """
    id: int | str
    title: str
    due_date: datetime | None = None
    materiality: str = "routine"
    dependency_count: int = 0
    completion_pct: float = 0.0
    domain: str | None = None
    description: str | None = None
    status: str = "active"
    hard_floor: bool = False  # Binding deadline — ignores bandwidth sort
    days_in_status: float = 0.0  # Days in current status (#195 timing amplification)
    violation_count: int = 0     # Rule violations associated with this obligation (#99)
    gravity_score: float | None = None  # Gravitational attraction score from gravitas (#635)


# --- Pressure result ---

@dataclass
class PressureResult:
    """Full decomposition of a pressure calculation.

    Every factor is exposed for auditability.
    """
    obligation_id: int | str
    pressure: float
    zone: str
    time_pressure: float
    materiality_mult: float
    dependency_amp: float
    completion_damp: float


# --- Plan types ---

@dataclass
class PlanRequest:
    """A request to generate a speculative plan.

    Contains the obligation, its pressure result, a prompt template
    for the caller to send to their LLM, and the suggested delivery
    urgency.
    """
    obligation: Obligation
    pressure_result: PressureResult
    prompt: str
    delivery_urgency: str  # "background" | "toast" | "interrupt"


@dataclass
class PlanResult:
    """A completed speculative plan.

    Created by SpeculativePlanner.complete_plan() after the caller
    invokes their LLM with the PlanRequest prompt.
    """
    obligation_id: int | str
    plan_text: str
    zone: str
    pressure: float
    created_at: datetime = field(default_factory=datetime.now)


# --- Triage ---

# --- Cognitive bandwidth context ---

@dataclass
class CognitiveContext:
    """Operator's current cognitive state from health data.

    All fields are 0.0-1.0 normalized scores where 1.0 = optimal.
    None = data unavailable (field ignored in computation).

    This does NOT change pressure scores — pressure is pure deadline math.
    It modulates the SORT ORDER when presenting obligations to the operator,
    biasing toward tasks that match current capacity.
    """
    sleep_quality: float | None = None      # 0=terrible, 1=excellent
    hrv_trend: float | None = None          # 0=declining, 1=improving
    pain_level: float | None = None         # 0=severe pain, 1=no pain
    hours_since_sleep: float | None = None  # raw hours (not normalized)
    medication_window: bool | None = None   # True=within med effect window
    bandwidth_score: float | None = None    # Pre-computed composite (0-1)
    violation_rate: float | None = None     # 0=no violations, 1=critical (#279)
    constraint_pressure: float | None = None  # 0=all clear, 1=all breached (#279)
    session_load: float | None = None       # 0=idle, 1=saturated (#279)

    def effective_bandwidth(self) -> float:
        """Compute composite bandwidth score from available signals.

        Returns 0.0-1.0 where 1.0 = full capacity. If no signals
        available, returns 1.0 (assume full capacity — fail-open).
        """
        from tidewatch.constants import BANDWIDTH_HOURS_GOOD, BANDWIDTH_NORMALIZATION_RANGE

        # Domain: bandwidth in [0, 1] where 1.0 = full capacity
        if self.bandwidth_score is not None:
            return max(0.0, min(1.0, self.bandwidth_score))

        signals: list[float] = []
        if self.sleep_quality is not None:
            signals.append(self.sleep_quality)
        if self.hrv_trend is not None:
            signals.append(self.hrv_trend)
        if self.pain_level is not None:
            signals.append(self.pain_level)
        if self.hours_since_sleep is not None:
            # Domain: normalize hours to [0, 1] — 8h=1.0, 16h=0.0
            normalized = max(0.0, 1.0 - max(0.0, self.hours_since_sleep - BANDWIDTH_HOURS_GOOD) / BANDWIDTH_NORMALIZATION_RANGE)
            signals.append(normalized)
        if self.violation_rate is not None:
            signals.append(1.0 - self.violation_rate)
        if self.constraint_pressure is not None:
            signals.append(1.0 - self.constraint_pressure)
        if self.session_load is not None:
            signals.append(1.0 - self.session_load)

        if not signals:
            return 1.0  # Fail-open: no data = assume full capacity
        return sum(signals) / len(signals)


# --- Task cognitive demand ---

@dataclass
class TaskDemand:
    """Cognitive demand profile for an obligation.

    Maps obligation characteristics to cognitive load requirements.
    Used by bandwidth-aware sorting to match tasks to capacity.
    """
    complexity: float = 0.5      # 0=trivial, 1=deeply analytical
    novelty: float = 0.5         # 0=familiar/routine, 1=completely new
    decision_weight: float = 0.5 # 0=mechanical, 1=high-stakes judgment


def estimate_task_demand(obligation: Obligation) -> TaskDemand:
    """Estimate cognitive demand from obligation metadata.

    Heuristic — uses domain and materiality as proxies.
    Can be overridden per-obligation in the future.
    """
    from tidewatch.constants import (
        MATERIAL_COMPLEXITY_BOOST,
        MATERIAL_DECISION_BOOST,
        TASK_DEMAND_DEFAULT,
        TASK_DEMAND_PROFILES,
    )

    domain = (obligation.domain or "").lower()
    profile = TASK_DEMAND_PROFILES.get(domain, TASK_DEMAND_DEFAULT)
    complexity = profile["complexity"]
    decision_weight = profile["decision_weight"]
    novelty = profile["novelty"]

    # Domain: demand dimensions in [0, 1]
    if obligation.materiality == "material":
        complexity = min(1.0, complexity + MATERIAL_COMPLEXITY_BOOST)
        decision_weight = min(1.0, decision_weight + MATERIAL_DECISION_BOOST)

    return TaskDemand(
        complexity=complexity,
        novelty=novelty,
        decision_weight=decision_weight,
    )


# --- Triage ---

@dataclass
class TriageCandidate:
    """A candidate obligation staged for user review.

    Sources (email scanners, calendar parsers, etc.) emit these.
    The triage queue deduplicates and stages them.
    """
    title: str
    source: str = "unknown"
    source_ref: str | None = None
    due_date: datetime | None = None
    domain: str | None = None
    priority: int = 3
    context: str | None = None
    staged_at: datetime = field(default_factory=datetime.now)
