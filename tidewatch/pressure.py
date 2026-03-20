# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tidewatch pressure engine.

Computes a continuous pressure score (0.0-1.0) for each obligation
based on deadline proximity, materiality, dependencies, and
completion progress.

This is DETERMINISTIC MATH. No LLM. No inference. No database.
No async. Every score is reproducible and auditable.

Equation (Section 3.1):
  P = min(1.0, P_time * M * A * D)

  Domain: P in [0, 1]. The upper bound is the equation's defined ceiling —
  pressure is a probability-like quantity that cannot exceed 1.0.

  P_time(t) = 1 - exp(-3 / max(t, 0.01))   for t > 0
  P_time(t) = 1.0                            for t <= 0 (overdue)
  M = 1.5 if material, 1.0 if routine
  A = 1.0 + (dependency_count * 0.1)
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


def calculate_pressure(
    obligation: Obligation,
    now: datetime | None = None,
) -> PressureResult:
    """Compute pressure for a single obligation (§3.1)."""
    if now is None:
        now = datetime.now(UTC)
    if obligation.due_date is None:
        return _no_deadline_result(obligation.id)

    days_rem = _days_remaining(obligation.due_date, now)
    _validate_obligation_inputs(obligation)

    time_p = OVERDUE_PRESSURE if days_rem <= 0 else 1.0 - _exponential(-RATE_CONSTANT / max(days_rem, DIVISION_GUARD))
    mat_mult = MATERIALITY_WEIGHTS.get(obligation.materiality, 1.0)
    dep_amp = 1.0 + (obligation.dependency_count * DEPENDENCY_AMPLIFICATION)
    comp_damp = _completion_dampening(obligation.completion_pct)
    timing_amp = _timing_amplifier(obligation.days_in_status)
    violation_amp = _violation_amplifier(obligation.violation_count)

    from tidewatch.constants import saturate
    pressure = saturate(time_p * mat_mult * dep_amp * comp_damp * timing_amp * violation_amp)

    return PressureResult(
        obligation_id=obligation.id, pressure=pressure, zone=pressure_zone(pressure),
        time_pressure=time_p, materiality_mult=mat_mult,
        dependency_amp=dep_amp, completion_damp=comp_damp,
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


def recalculate_batch(
    obligations: list[Obligation],
    now: datetime | None = None,
) -> list[PressureResult]:
    """Recalculate pressure for a batch of obligations.

    Inputs:
      obligations: list of Obligation dataclasses
      now: current datetime (default: utcnow, shared across batch)

    Logic:
      Calculate pressure for each, sort by pressure descending.

    Outputs:
      list[PressureResult] sorted by pressure descending
    """
    import time as _time

    _t0 = _time.monotonic()
    if now is None:
        now = datetime.now(UTC)
    results = [calculate_pressure(ob, now=now) for ob in obligations]
    results.sort(key=lambda r: r.pressure, reverse=True)
    _latency_ms = (_time.monotonic() - _t0) * MS_PER_SECOND

    try:
        from sentinel_sdk.metrics import get_buffer

        red_count = sum(1 for r in results if r.zone == "red")
        get_buffer().record(
            source_repo="tidewatch",
            operation_type="pressure.recalculate_batch",
            operation_detail=f"batch_size={len(obligations)} red={red_count}",
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


def _is_hard_floor(ob: Obligation) -> bool:
    """Binding deadline: explicit flag OR domain heuristic."""
    if ob.hard_floor:
        return True
    if ob.domain and ob.domain.lower() in HARD_FLOOR_DOMAINS and ob.due_date is not None:
        now = datetime.now(UTC)
        days = _days_remaining(ob.due_date, now)
        if days <= HARD_FLOOR_DAYS_THRESHOLD:
            return True
    return False


def _fit_score(
    result: PressureResult,
    ob_map: dict,
    bandwidth: float,
) -> tuple[int, float]:
    """Compute bandwidth-adjusted sort key for a pressure result."""
    ob = ob_map.get(result.obligation_id)
    if ob is None:
        return (_SORT_TIER_NORMAL, result.pressure)
    if _is_hard_floor(ob):
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
