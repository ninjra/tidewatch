"""Tidewatch: Continuous obligation pressure with proactive planning."""

from tidewatch.pressure import calculate_pressure, pressure_zone, recalculate_batch
from tidewatch.planner import SpeculativePlanner
from tidewatch.triage import TriageQueue
from tidewatch.types import (
    Obligation, PressureResult, PlanRequest, PlanResult,
    Zone, TriageCandidate,
)

__version__ = "0.1.0"
__all__ = [
    "calculate_pressure", "pressure_zone", "recalculate_batch",
    "SpeculativePlanner", "TriageQueue",
    "Obligation", "PressureResult", "PlanRequest", "PlanResult",
    "Zone", "TriageCandidate",
]
