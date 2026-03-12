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
