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
  D = 1.0 - (completion_pct * 0.6)

Zones:
  green  = P < 0.30
  yellow = 0.30 <= P < 0.60
  orange = 0.60 <= P < 0.80
  red    = P >= 0.80
"""

import math
from datetime import datetime, timezone

from tidewatch.constants import (
    COMPLETION_DAMPENING,
    DEPENDENCY_AMPLIFICATION,
    MATERIALITY_WEIGHTS,
    OVERDUE_PRESSURE,
    RATE_CONSTANT,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
)
from tidewatch.types import (
    CognitiveContext,
    Obligation,
    PressureResult,
    TaskDemand,
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
        due_date = due_date.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
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
        now = datetime.now(timezone.utc)

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
    if days_rem <= 0:
        time_p = OVERDUE_PRESSURE
    else:
        time_p = 1.0 - math.exp(-RATE_CONSTANT / max(days_rem, 0.01))

    # 2. Materiality multiplier
    mat_mult = MATERIALITY_WEIGHTS.get(obligation.materiality, 1.0)

    # 3. Dependency amplifier
    dep_amp = 1.0 + (dependency_count * DEPENDENCY_AMPLIFICATION)

    # 4. Completion dampener
    comp_damp = 1.0 - (completion_pct * COMPLETION_DAMPENING)

    # Final pressure
    pressure = time_p * mat_mult * dep_amp * comp_damp
    # REMEDIATION: removed editorial floor max(0.0,...) — product of non-negative factors.
    # Was: min(1.0, max(0.0, pressure))
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
        now = datetime.now(timezone.utc)
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
    if bandwidth >= 0.99:
        return results

    ob_map = {ob.id: ob for ob in obligations}

    def fit_score(result: PressureResult) -> float:
        ob = ob_map.get(result.obligation_id)
        if ob is None:
            return result.pressure
        demand = estimate_task_demand(ob)
        mismatch = (demand.complexity + demand.novelty + demand.decision_weight) / 3.0
        return result.pressure * (1.0 - mismatch * (1.0 - bandwidth))

    sorted_results = sorted(results, key=fit_score, reverse=True)
    return sorted_results
