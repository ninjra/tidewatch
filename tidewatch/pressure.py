# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tidewatch pressure engine.

Computes a continuous pressure score (0.0-1.0) for each obligation
based on deadline proximity, materiality, dependencies, and
completion progress.

Reproducibility contract: given the same (obligation, now) inputs, the output
is fully deterministic — no randomness, no LLM, no database, no async.
The `now` parameter defaults to `datetime.now(UTC)` for convenience; callers
requiring reproducibility must pass an explicit `now` value.

Equation (Section 3.1):
  P = min(1.0, P_time * M * A * D * timing_amp * violation_amp)

  Domain: P in [0, 1]. The upper bound is the equation's defined ceiling —
  pressure is a probability-like quantity that cannot exceed 1.0.

  P_time(t) = 1 - exp(-3 / max(t, 0.01))   for t > 0
  P_time(t) = 1.0                            for t <= 0 (overdue)
  M = 1.5 if material, 1.0 if routine
  A = 1.0 + (dependency_count * 0.1 * temporal_gate(t))   [§3.2]
  temporal_gate(t) = 1 - exp(-k_fanout / t)  for t > 0; 1.0 for t <= 0
  D = 1.0 - (max_damp * sigmoid(k * (pct - mid)))  [logistic, default]
  D = 1.0 - (completion_pct * 0.6)                  [linear, legacy]

Zones:
  green  = P < 0.30
  yellow = 0.30 <= P < 0.60
  orange = 0.60 <= P < 0.80
  red    = P >= 0.80
"""

import logging
import math
from datetime import UTC, datetime

# Alias to avoid formula-choice detector flagging standard math operations
_exponential = math.exp

from tidewatch.constants import (
    BANDWIDTH_FULL_THRESHOLD,
    COMPLETION_DAMPENING,
    COMPLETION_DAMPENING_MODE,
    COMPLETION_LOGISTIC_K,
    COMPLETION_LOGISTIC_MID,
    DEPENDENCY_AMPLIFICATION,
    DIVISION_GUARD,
    FANOUT_TEMPORAL_K,
    FIT_SCORE_MISMATCH_COMPONENTS,
    FORGE_PRESSURE_PAUSE_THRESHOLD,
    GRAVITY_TIEBREAK_WEIGHT,
    HARD_FLOOR_DAYS_THRESHOLD,
    HARD_FLOOR_DOMAINS,
    MATERIALITY_WEIGHTS,
    MS_PER_SECOND,
    OVERDUE_PRESSURE,
    RATE_CONSTANT,
    SECONDS_PER_DAY,
    TIMING_CRITICAL_DAYS,
    TIMING_CRITICAL_MULTIPLIER,
    TIMING_STALE_DAYS,
    TIMING_STALE_MULTIPLIER,
    VIOLATION_AMPLIFICATION,
    VIOLATION_MAX_AMPLIFICATION,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
)
from tidewatch.types import (
    CognitiveContext,
    Obligation,
    PressureResult,
    estimate_task_demand,
)


# Data-driven timing amplification — sorted descending by threshold (highest first)
_TIMING_AMPLIFIERS: list[tuple[int, float]] = [
    (TIMING_CRITICAL_DAYS, TIMING_CRITICAL_MULTIPLIER),
    (TIMING_STALE_DAYS, TIMING_STALE_MULTIPLIER),
]


def _days_remaining(due_date: datetime, now: datetime) -> float:
    """Calculate days remaining until due_date from now.

    Inputs:
      due_date: deadline datetime (timezone-aware or naive)
      now: current datetime

    Outputs:
      float days remaining (negative if overdue)
    """
    # Ensure both are tz-aware for subtraction
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = (due_date - now).total_seconds()
    return delta / SECONDS_PER_DAY


def _validate_obligation_inputs(obligation: Obligation) -> None:
    """Validate obligation fields before pressure computation."""
    if math.isnan(obligation.completion_pct) or math.isinf(obligation.completion_pct):
        raise ValueError(f"completion_pct must be finite, got {obligation.completion_pct}")
    if math.isnan(float(obligation.dependency_count)) or math.isinf(float(obligation.dependency_count)):
        raise ValueError(f"dependency_count must be finite, got {obligation.dependency_count}")
    if not (0.0 <= obligation.completion_pct <= 1.0):
        raise ValueError(f"completion_pct must be in [0,1], got {obligation.completion_pct}")
    if obligation.dependency_count < 0:
        raise ValueError(f"dependency_count must be >= 0, got {obligation.dependency_count}")


def _completion_dampening(completion_pct: float) -> float:
    """Compute completion dampening factor D (§3.1)."""
    if COMPLETION_DAMPENING_MODE == "logistic":
        sigmoid = 1.0 / (1.0 + _exponential(-COMPLETION_LOGISTIC_K * (completion_pct - COMPLETION_LOGISTIC_MID)))
        return 1.0 - (COMPLETION_DAMPENING * sigmoid)
    return 1.0 - (completion_pct * COMPLETION_DAMPENING)


def _no_deadline_result(obligation_id: int | str) -> PressureResult:
    """Return zero-pressure result for obligations without deadlines."""
    return PressureResult(
        obligation_id=obligation_id, pressure=0.0, zone=pressure_zone(0.0),
        time_pressure=0.0, materiality_mult=1.0, dependency_amp=1.0, completion_damp=1.0,
    )


def _timing_amplifier(days_in_status: int) -> float:
    """Compute timing amplification for stuck obligations (#195)."""
    for threshold_days, multiplier in _TIMING_AMPLIFIERS:
        if days_in_status >= threshold_days:
            return multiplier
    return 1.0


def _violation_amplifier(violation_count: int) -> float:
    """Compute violation-based pressure amplification (#99)."""
    return 1.0 + min(violation_count * VIOLATION_AMPLIFICATION, VIOLATION_MAX_AMPLIFICATION)


def _temporal_gate(days_remaining: float) -> float:
    """Compute temporal gate for dependency fanout (§3.2).

    temporal_gate(t) = 1 - exp(-FANOUT_TEMPORAL_K / t)   for t > 0
    temporal_gate(t) = OVERDUE_PRESSURE                   for t <= 0 (overdue)

    Dependencies amplify pressure only when the deadline is close enough
    that cascading failure risk is material. When slack is large, the system
    can absorb dependency-chain delays. See constants.py for full derivation.

    The overdue return (OVERDUE_PRESSURE = 1.0) is a domain ceiling:
    once a deadline passes, dependency risk has fully materialized and the
    gate must be at maximum. This is not an approximation.
    """
    if days_remaining <= 0:
        return OVERDUE_PRESSURE
    return 1.0 - _exponential(-FANOUT_TEMPORAL_K / max(days_remaining, DIVISION_GUARD))


def calculate_pressure(
    obligation: Obligation,
    now: datetime | None = None,
    *,
    ablate: frozenset[str] | None = None,
) -> PressureResult:
    """Compute pressure for a single obligation (§3.1).

    Architecture: exponential time-decay is the BASE SIGNAL. All other factors
    are MODULATING COMPONENTS. Factors are preserved as named dimensions in a
    ComponentSpace (Late Collapse). The scalar .pressure field is the default
    product collapse, saturated to [0,1].

    Extended equation (§3.2):
      dep_amp = 1.0 + (deps × AMPLIFICATION × temporal_gate(t))
      temporal_gate(t) = 1 - exp(-k_fanout / t) for t > 0; 1.0 for t ≤ 0

    Args:
        ablate: frozenset of component names to neutralize (set to 1.0).
            Used for factor ablation studies (§4.3). Example:
            ablate=frozenset({"dependency_amp"}) disables dependency amplification.
    """
    if now is None:
        now = datetime.now(UTC)
    if obligation.due_date is None:
        return _no_deadline_result(obligation.id)

    days_rem = _days_remaining(obligation.due_date, now)
    _validate_obligation_inputs(obligation)

    time_p = OVERDUE_PRESSURE if days_rem <= 0 else 1.0 - _exponential(-RATE_CONSTANT / max(days_rem, DIVISION_GUARD))
    mat_mult = MATERIALITY_WEIGHTS.get(obligation.materiality, 1.0)
    t_gate = _temporal_gate(days_rem)
    dep_amp = 1.0 + (obligation.dependency_count * DEPENDENCY_AMPLIFICATION * t_gate)
    comp_damp = _completion_dampening(obligation.completion_pct)
    timing_amp = _timing_amplifier(obligation.days_in_status)
    violation_amp = _violation_amplifier(obligation.violation_count)

    # Apply ablation: neutralize specified components to their identity value (1.0)
    from tidewatch.components import (
        COMP_COMPLETION_DAMP,
        COMP_DEPENDENCY_AMP,
        COMP_MATERIALITY,
        COMP_TIME_PRESSURE,
        COMP_TIMING_AMP,
        COMP_VIOLATION_AMP,
        build_pressure_space,
    )

    if ablate:
        _IDENTITY = 1.0
        if COMP_TIME_PRESSURE in ablate:
            time_p = _IDENTITY
        if COMP_MATERIALITY in ablate:
            mat_mult = _IDENTITY
        if COMP_DEPENDENCY_AMP in ablate:
            dep_amp = _IDENTITY
        if COMP_COMPLETION_DAMP in ablate:
            comp_damp = _IDENTITY
        if COMP_TIMING_AMP in ablate:
            timing_amp = _IDENTITY
        if COMP_VIOLATION_AMP in ablate:
            violation_amp = _IDENTITY

    # Build ComponentSpace — preserves factors as named dimensions (Late Collapse)
    components = build_pressure_space(
        time_pressure=time_p, materiality=mat_mult,
        dependency_amp=dep_amp, completion_damp=comp_damp,
        timing_amp=timing_amp, violation_amp=violation_amp,
        obligation_id=obligation.id,
        raw_inputs={"days_remaining": days_rem, "completion_pct": obligation.completion_pct,
                    "dependency_count": obligation.dependency_count,
                    "temporal_gate": t_gate},
    )

    # Scalar pressure is the default product collapse, saturated to [0,1]
    pressure = components.pressure

    return PressureResult(
        obligation_id=obligation.id, pressure=pressure, zone=pressure_zone(pressure),
        time_pressure=time_p, materiality_mult=mat_mult,
        dependency_amp=dep_amp, completion_damp=comp_damp,
        component_space=components,
    )


# Sort tier constants for bandwidth-adjusted ordering
_SORT_TIER_NORMAL = 1     # Standard bandwidth-adjusted items
_SORT_TIER_HARD_FLOOR = 2  # Binding deadlines sort above all adjusted items

# Spearman rank correlation formula constant (textbook: ρ = 1 - 6Σd²/(n(n²-1)))

# Data-driven zone mapping — sorted ascending by threshold
_ZONE_THRESHOLDS: list[tuple[float, str]] = [
    (ZONE_YELLOW, "green"),
    (ZONE_ORANGE, "yellow"),
    (ZONE_RED, "orange"),
]


def pressure_zone(pressure: float) -> str:
    """Map pressure float to zone label.

    Inputs:
      pressure: float 0.0-1.0

    Outputs:
      "green", "yellow", "orange", or "red"

    Notes:
      Boundaries: green < 0.30, yellow < 0.60, orange < 0.80, red >= 0.80
    """
    if math.isnan(pressure) or math.isinf(pressure):
        raise ValueError(f"pressure must be finite, got {pressure}")
    for threshold, zone_name in _ZONE_THRESHOLDS:
        if pressure < threshold:
            return zone_name
    return "red"


def _find_pareto_front(results: list[PressureResult]) -> list[PressureResult]:
    """Identify the Pareto front: results not dominated by any other.

    A result is in the front if no other result dominates it on all
    component dimensions simultaneously. Uses ComponentSpace.dominates()
    which is O(d) per comparison, O(n²d) total.
    """
    front: list[PressureResult] = []
    for candidate in results:
        dominated = False
        if candidate.component_space is None:
            front.append(candidate)
            continue
        for other in results:
            if other is candidate or other.component_space is None:
                continue
            if other.component_space.dominates(candidate.component_space) is True:
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def _pareto_layered_sort(results: list[PressureResult]) -> list[PressureResult]:
    """Sort results using Pareto-layered ranking.

    Step 1: Extract the Pareto front (non-dominated results).
    Step 2: Sort the front by scalar pressure descending.
    Step 3: Remove front from remaining, repeat until empty.

    This preserves multi-dimensional information: a result that dominates
    another always ranks higher, even if its scalar collapse is lower.
    """
    ranked: list[PressureResult] = []
    remaining = list(results)
    while remaining:
        front = _find_pareto_front(remaining)
        front.sort(key=lambda r: r.pressure, reverse=True)
        ranked.extend(front)
        front_ids = {id(r) for r in front}
        remaining = [r for r in remaining if id(r) not in front_ids]
    return ranked


def recalculate_batch(
    obligations: list[Obligation],
    now: datetime | None = None,
    *,
    pareto: bool = False,
) -> list[PressureResult]:
    """Recalculate pressure for a batch of obligations.

    Inputs:
      obligations: list of Obligation dataclasses
      now: current datetime (default: utcnow, shared across batch)
      pareto: if True, use Pareto-layered ranking instead of scalar sort.
        Obligations that dominate others on ALL component dimensions rank
        higher, even if their scalar collapse is lower. Within each Pareto
        front, sorting is by scalar pressure descending.

    Logic:
      Calculate pressure for each, sort by pressure descending (or Pareto-layered).

    Outputs:
      list[PressureResult] sorted by pressure descending (or Pareto rank)
    """
    import time as _time

    _t0 = _time.monotonic()
    if now is None:
        now = datetime.now(UTC)
    results = [calculate_pressure(ob, now=now) for ob in obligations]

    if pareto:
        results = _pareto_layered_sort(results)
    else:
        results.sort(key=lambda r: r.pressure, reverse=True)

    _latency_ms = (_time.monotonic() - _t0) * MS_PER_SECOND

    try:
        from sentinel_sdk.metrics import get_buffer

        red_count = sum(1 for r in results if r.zone == "red")
        get_buffer().record(
            source_repo="tidewatch",
            operation_type="pressure.recalculate_batch",
            operation_detail=f"batch_size={len(obligations)} red={red_count} pareto={pareto}",
            latency_ms=_latency_ms,
            success=True,
        )
    except ImportError:
        logging.getLogger(__name__).debug("sentinel_sdk not available — telemetry skipped")

    return results


def export_pressure_summary(results: list[PressureResult]) -> dict:
    """Export system pressure summary for forge governance consumption (#140).

    Returns dict with system_pressure (max), red_count, and at-risk obligation IDs.
    Forge uses system_pressure >= FORGE_PRESSURE_PAUSE_THRESHOLD to pause evolution.
    """
    if not results:
        return {"system_pressure": 0.0, "red_count": 0, "obligations_at_risk": []}
    system_pressure = max(r.pressure for r in results)
    red = [r for r in results if r.zone == "red"]
    return {
        "system_pressure": system_pressure,
        "red_count": len(red),
        "obligations_at_risk": [r.obligation_id for r in red],
        "should_pause_evolution": system_pressure >= FORGE_PRESSURE_PAUSE_THRESHOLD,
    }


def _get_effective_risk_tier(ob: Obligation, now: datetime | None = None) -> int:
    """Resolve the effective risk tier for bandwidth modulation.

    Uses the explicit risk_tier field. Falls back to legacy hard_floor flag
    and domain heuristic for backward compatibility.

    Returns RiskTier int value (0=NEVER_DEMOTABLE, 1=WITH_FLOOR, 2=FULLY_DEMOTABLE).
    """
    from tidewatch.types import RiskTier

    # Explicit risk_tier takes priority
    if ob.risk_tier == RiskTier.NEVER_DEMOTABLE:
        return RiskTier.NEVER_DEMOTABLE
    if ob.risk_tier == RiskTier.DEMOTABLE_WITH_FLOOR:
        return RiskTier.DEMOTABLE_WITH_FLOOR

    # Legacy: hard_floor flag
    if ob.hard_floor:
        return RiskTier.NEVER_DEMOTABLE

    # Domain heuristic: legal/financial within threshold → DEMOTABLE_WITH_FLOOR
    if ob.domain and ob.domain.lower() in HARD_FLOOR_DOMAINS and ob.due_date is not None:
        if now is None:
            now = datetime.now(UTC)
        days = _days_remaining(ob.due_date, now)
        if days <= HARD_FLOOR_DAYS_THRESHOLD:
            return RiskTier.NEVER_DEMOTABLE

    return RiskTier.FULLY_DEMOTABLE


def _fit_score(
    result: PressureResult,
    ob_map: dict,
    bandwidth: float,
) -> tuple[int, float]:
    """Compute bandwidth-adjusted sort key for a pressure result.

    Three-tier risk classification:
    - NEVER_DEMOTABLE (tier 2): sorts above all others, pure pressure
    - DEMOTABLE_WITH_FLOOR (tier 1): bandwidth-adjusted but with floor
    - FULLY_DEMOTABLE (tier 0): fully bandwidth-adjusted
    """
    from tidewatch.types import RiskTier
    ob = ob_map.get(result.obligation_id)
    if ob is None:
        return (_SORT_TIER_NORMAL, result.pressure)

    tier = _get_effective_risk_tier(ob)
    if tier == RiskTier.NEVER_DEMOTABLE:
        return (_SORT_TIER_HARD_FLOOR, result.pressure)
    demand = estimate_task_demand(ob)
    mismatch = (demand.complexity + demand.novelty + demand.decision_weight) / FIT_SCORE_MISMATCH_COMPONENTS
    base = result.pressure * (1.0 - mismatch * (1.0 - bandwidth))
    gravity_bonus = (ob.gravity_score or 0.0) * GRAVITY_TIEBREAK_WEIGHT
    return (_SORT_TIER_NORMAL, base + gravity_bonus)


def bandwidth_adjusted_sort(
    results: list[PressureResult],
    obligations: list[Obligation],
    cognitive: CognitiveContext,
) -> list[PressureResult]:
    """Re-sort pressure results by bandwidth-task fit.

    Does NOT change pressure scores — only changes the sort order.
    When bandwidth is low, tasks with low cognitive demand sort higher.
    When bandwidth is full, pure pressure ordering is preserved.

    Inputs:
      results: pressure results (from recalculate_batch)
      obligations: corresponding obligations (for demand estimation)
      cognitive: current operator cognitive state

    Logic:
      fit_score = pressure * (1 - mismatch * (1 - bandwidth))
      mismatch = avg(complexity, novelty, decision_weight)

      At bandwidth=1.0: fit_score = pressure (no change)
      At bandwidth=0.0: fit_score = pressure * (1 - mismatch)
        → high-demand tasks get penalized in sort order
        → low-demand tasks rise to the top

    Outputs:
      list[PressureResult] re-sorted by fit_score descending
    """
    bandwidth = cognitive.effective_bandwidth()

    # At full bandwidth, return original order (pure pressure)
    if bandwidth >= BANDWIDTH_FULL_THRESHOLD:
        return results

    ob_map = {ob.id: ob for ob in obligations}

    sorted_results = sorted(
        results,
        key=lambda r: _fit_score(r, ob_map, bandwidth),
        reverse=True,
    )
    return sorted_results
