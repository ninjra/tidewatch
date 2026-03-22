# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tidewatch: Continuous obligation pressure with Late Collapse architecture.

Scoring factors are preserved as named components (ComponentSpace) through the
entire pipeline. Collapse to scalar [0,1] happens only when a consumer needs it.
Backed by gravitas.types.ComponentSpace for Pareto-aware ranking; the dependency
is interface-based (ComponentSpaceProtocol) and substitutable.
"""

from tidewatch.components import (
    ComponentSpaceProtocol,
    PressureComponents,
    build_pressure_space,
)
from tidewatch.planner import PlanStubGenerator, SpeculativePlanner
from tidewatch.pressure import (
    apply_zone_capacity,
    bandwidth_adjusted_sort,
    calculate_pressure,
    compute_adaptive_k,
    compute_dependency_cap,
    export_pressure_summary,
    pressure_zone,
    recalculate_batch,
    recalculate_stale,
    top_k_obligations,
)
from tidewatch.triage import TriageQueue
from tidewatch.types import (
    CognitiveContext,
    DeadlineDistribution,
    Obligation,
    PlanRequest,
    PlanResult,
    PressureResult,
    RiskTier,
    TaskDemand,
    TriageCandidate,
    Zone,
    estimate_task_demand,
)

__version__ = "0.3.0"
__all__ = [
    "calculate_pressure", "pressure_zone", "recalculate_batch",
    "recalculate_stale", "top_k_obligations", "apply_zone_capacity",
    "compute_adaptive_k", "compute_dependency_cap",
    "bandwidth_adjusted_sort", "export_pressure_summary",
    "PlanStubGenerator", "SpeculativePlanner", "TriageQueue",
    "CognitiveContext", "TaskDemand", "estimate_task_demand",
    "Obligation", "PressureResult", "PlanRequest", "PlanResult",
    "DeadlineDistribution",
    "Zone", "RiskTier", "TriageCandidate",
    "ComponentSpaceProtocol", "PressureComponents", "build_pressure_space",
]
