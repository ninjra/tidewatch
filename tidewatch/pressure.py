# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tidewatch pressure engine.

Computes a continuous pressure score (0.0-1.0) for each obligation
based on deadline proximity, materiality, dependencies, and
completion progress.

This is DETERMINISTIC MATH. No LLM. No inference. No database.
No async. Every score is reproducible and auditable.

Equation (Section 3.1):
  P = clamp_upper(1.0, P_time * M * A * D)  # MATH_GUARD

  The saturation bound is the equation's defined ceiling — pressure
  cannot exceed 1.0 by definition. This is NOT an editorial clamp.  # MATH_GUARD

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

import math
from datetime import UTC, datetime

from tidewatch.constants import (
    BANDWIDTH_FULL_THRESHOLD,
    COMPLETION_DAMPENING,
    COMPLETION_DAMPENING_MODE,
    COMPLETION_LOGISTIC_K,
    COMPLETION_LOGISTIC_MID,
    DEPENDENCY_AMPLIFICATION,
    FIT_SCORE_MISMATCH_COMPONENTS,
    FORGE_PRESSURE_PAUSE_THRESHOLD,
    GRAVITY_TIEBREAK_WEIGHT,
    HARD_FLOOR_DAYS_THRESHOLD,
    HARD_FLOOR_DOMAINS,
    MATERIALITY_WEIGHTS,
    OVERDUE_PRESSURE,
    RATE_CONSTANT,
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
    return delta / 86400.0


def calculate_pressure(
    obligation: Obligation,
    now: datetime | None = None,
) -> PressureResult:
    """Compute pressure for a single obligation.

    Pure function. No side effects. No DB. No LLM.

    Inputs:
      obligation: Obligation dataclass
      now: current datetime (default: utcnow)

    Logic:
      1. No deadline -> pressure = 0.0
      2. Time pressure: exponential approach as deadline nears
      3. Materiality: material items get 1.5x weight
      4. Dependencies: each adds 10% amplification
      5. Completion: progress dampens pressure (max 60%)
      6. Final pressure saturates at 1.0 (equation-defined bound, not editorial)

    Outputs:
      PressureResult with full factor decomposition

    Notes:
      This function is the ONLY place pressure is computed.
      Implements Section 3.1 of the Tidewatch paper.
    """
    if now is None:
        now = datetime.now(UTC)

    # No deadline = no pressure
    if obligation.due_date is None:
        return PressureResult(
            obligation_id=obligation.id,
            pressure=0.0,
            zone=pressure_zone(0.0),
            time_pressure=0.0,
            materiality_mult=1.0,
            dependency_amp=1.0,
            completion_damp=1.0,
        )

    days_rem = _days_remaining(obligation.due_date, now)

    # NaN/Inf guards — must precede range checks (NaN fails comparison silently)
    if math.isnan(obligation.completion_pct) or math.isinf(obligation.completion_pct):
        raise ValueError(f"completion_pct must be finite, got {obligation.completion_pct}")
    if math.isnan(float(obligation.dependency_count)) or math.isinf(float(obligation.dependency_count)):
        raise ValueError(f"dependency_count must be finite, got {obligation.dependency_count}")

    # REMEDIATION: replaced editorial clamp max(0.0, min(1.0, ...)) with input validation.
    # Was: completion_pct = max(0.0, min(1.0, obligation.completion_pct))
    if not (0.0 <= obligation.completion_pct <= 1.0):
        raise ValueError(
            f"completion_pct must be in [0,1], got {obligation.completion_pct}"
        )
    completion_pct = obligation.completion_pct

    # REMEDIATION: replaced editorial clamp max(0, ...) with input validation.
    # Was: dependency_count = max(0, obligation.dependency_count)
    if obligation.dependency_count < 0:
        raise ValueError(
            f"dependency_count must be >= 0, got {obligation.dependency_count}"
        )
    dependency_count = obligation.dependency_count

    # 1. Time pressure
    time_p = OVERDUE_PRESSURE if days_rem <= 0 else 1.0 - math.exp(-RATE_CONSTANT / max(days_rem, 0.01))

    # 2. Materiality multiplier
    mat_mult = MATERIALITY_WEIGHTS.get(obligation.materiality, 1.0)

    # 3. Dependency amplifier
    dep_amp = 1.0 + (dependency_count * DEPENDENCY_AMPLIFICATION)

    # 4. Completion dampener
    if COMPLETION_DAMPENING_MODE == "logistic":
        # Logistic: smooth S-curve, more dampening at high completion
        # D = 1 - max_damp * sigmoid(k * (pct - mid))
        sigmoid = 1.0 / (1.0 + math.exp(-COMPLETION_LOGISTIC_K * (completion_pct - COMPLETION_LOGISTIC_MID)))
        comp_damp = 1.0 - (COMPLETION_DAMPENING * sigmoid)
    else:
        # Linear: D = 1 - pct * max_damp (original §3.1)
        comp_damp = 1.0 - (completion_pct * COMPLETION_DAMPENING)

    # 5. Timing amplifier (#195) — stuck obligations get pressure boost
    if obligation.days_in_status >= TIMING_CRITICAL_DAYS:
        timing_amp = TIMING_CRITICAL_MULTIPLIER
    elif obligation.days_in_status >= TIMING_STALE_DAYS:
        timing_amp = TIMING_STALE_MULTIPLIER
    else:
        timing_amp = 1.0

    # 6. Violation amplifier (#99) — obligations with violations get pressure boost
    violation_amp = 1.0 + min(
        obligation.violation_count * VIOLATION_AMPLIFICATION,
        VIOLATION_MAX_AMPLIFICATION,
    )  # MATH_GUARD: capped amplification

    # Final pressure
    pressure = time_p * mat_mult * dep_amp * comp_damp * timing_amp * violation_amp
    pressure = min(1.0, pressure)  # MATH_GUARD: saturation bound per equation §3.1

    return PressureResult(
        obligation_id=obligation.id,
        pressure=pressure,
        zone=pressure_zone(pressure),
        time_pressure=time_p,
        materiality_mult=mat_mult,
        dependency_amp=dep_amp,
        completion_damp=comp_damp,
    )


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
    if pressure < ZONE_YELLOW:
        return "green"
    elif pressure < ZONE_ORANGE:
        return "yellow"
    elif pressure < ZONE_RED:
        return "orange"
    else:
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
    _latency_ms = (_time.monotonic() - _t0) * 1000

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
        pass

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

    def fit_score(result: PressureResult) -> tuple[int, float]:
        """Returns (tier, score). Tier 2 = hard floor (sorts first with reverse=True)."""
        ob = ob_map.get(result.obligation_id)
        if ob is None:
            return (1, result.pressure)
        if _is_hard_floor(ob):
            return (2, result.pressure)  # Hard floor: sorts above all bandwidth-adjusted items
        demand = estimate_task_demand(ob)
        mismatch = (demand.complexity + demand.novelty + demand.decision_weight) / FIT_SCORE_MISMATCH_COMPONENTS
        base = result.pressure * (1.0 - mismatch * (1.0 - bandwidth))
        gravity_bonus = (ob.gravity_score or 0.0) * GRAVITY_TIEBREAK_WEIGHT  # (#635)
        return (1, base + gravity_bonus)

    sorted_results = sorted(
        results,
        key=lambda r: fit_score(r),
        reverse=True,
    )
    return sorted_results
