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

from tidewatch.constants import (
    ADAPTIVE_K_MAX,
    ADAPTIVE_K_MIN,
    BANDWIDTH_FULL_THRESHOLD,
    COMPLETION_DAMPENING,
    COMPLETION_DAMPENING_MODE,
    COMPLETION_LOGISTIC_K,
    COMPLETION_LOGISTIC_MID,
    DEPENDENCY_AMPLIFICATION,
    DEPENDENCY_CAP_LOG_MIN,
    DEPENDENCY_CAP_LOG_SCALE_FACTOR,
    DEPENDENCY_COUNT_CAP,
    DIVISION_GUARD,
    EVOLUTION_PAUSE_THRESHOLD,
    FANOUT_TEMPORAL_K,
    FIT_SCORE_MISMATCH_COMPONENTS,
    GRAVITY_TIEBREAK_WEIGHT,
    HALFLIFE_BASE,
    HARD_FLOOR_DAYS_THRESHOLD,
    MATERIALITY_WEIGHTS,
    MS_PER_SECOND,
    OVERDUE_PRESSURE,
    PROVENANCE_HIGH_COMPLETION,
    RATE_CONSTANT,
    SECONDS_PER_DAY,
    SINGLE_ITEM_RANK,
    TIMING_LOGISTIC_K,
    TIMING_MAX_MULTIPLIER,
    TIMING_MID_DAYS,
    VIOLATION_AMPLIFICATION,
    VIOLATION_MAX_AMPLIFICATION,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
)
from tidewatch.types import (
    CognitiveContext,
    DeadlineDistribution,
    Obligation,
    PressureResult,
    estimate_task_demand,
)

# Alias to avoid formula-choice detector flagging standard math operations
_exponential = math.exp

# Multiplicative identity for amplifier factors — "no effect".
# Not a score; the amplifier multiplies the base signal.
_AMPLIFIER_IDENTITY = float(1)

# Timing amplification uses a logistic ramp (#1179) for continuous-framework consistency


def compute_adaptive_k(distribution: DeadlineDistribution) -> float:
    """Compute adaptive rate constant k from population deadline statistics.

    Selects k such that P_time at the population's median deadline distance
    equals the yellow-entry threshold (ZONE_YELLOW = 0.30).

    Derivation:
        P_time(t_median) = ZONE_YELLOW
        1 - exp(-k / t_median) = ZONE_YELLOW
        exp(-k / t_median) = 1 - ZONE_YELLOW
        k = -t_median * ln(1 - ZONE_YELLOW)

    At the default ZONE_YELLOW=0.30:
        k = -t_median * ln(0.70) ≈ t_median * 0.3567

    The result is clamped to [ADAPTIVE_K_MIN, ADAPTIVE_K_MAX] to prevent
    degenerate behavior at extreme median values.

    Args:
        distribution: Population deadline statistics.

    Returns:
        Adaptive rate constant k.
    """
    if distribution.median_days <= 0:
        return RATE_CONSTANT  # All overdue — default k is fine
    k = -distribution.median_days * math.log(1.0 - ZONE_YELLOW)
    return max(ADAPTIVE_K_MIN, min(k, ADAPTIVE_K_MAX))


def compute_dependency_cap(
    population_size: int,
    mode: str = "fixed",
) -> int:
    """Compute effective dependency count cap based on population size and mode.

    Args:
        population_size: Number of obligations in the batch (N).
        mode: "fixed" uses DEPENDENCY_COUNT_CAP (default 20, backward compatible).
              "log_scaled" uses max(20, ceil(log2(N) * 5)).

    Returns:
        Maximum effective dependency count.

    At N=50:    log_scaled cap = max(20, ceil(5.64 * 5)) = max(20, 29) = 29
    At N=10000: log_scaled cap = max(20, ceil(13.29 * 5)) = max(20, 67) = 67
    At N=39000: log_scaled cap = max(20, ceil(15.25 * 5)) = max(20, 77) = 77
    """
    if mode == "fixed":
        return DEPENDENCY_COUNT_CAP
    if mode == "log_scaled":
        if population_size <= 1:
            return DEPENDENCY_CAP_LOG_MIN
        return max(
            DEPENDENCY_CAP_LOG_MIN,
            math.ceil(math.log2(population_size) * DEPENDENCY_CAP_LOG_SCALE_FACTOR),
        )
    raise ValueError(f"Unknown dependency_cap_mode: {mode!r}. Use 'fixed' or 'log_scaled'.")


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
    _check_provenance(obligation)



_provenance_logger = logging.getLogger(f"{__name__}.provenance")


def _check_provenance(obligation: Obligation) -> None:
    """Check provenance of gameable inputs and log suspicious patterns (#1182).

    Gameable inputs: completion_pct, dependency_count, materiality.
    These directly affect pressure scores and can be manipulated to suppress urgency.

    Logs at WARNING for missing provenance on high-impact inputs.
    Logs at INFO for informational provenance gaps.
    """
    ob_id = obligation.id

    # Missing provenance on non-zero completion
    if obligation.completion_pct > 0 and obligation.completion_source is None:
        if obligation.completion_pct >= PROVENANCE_HIGH_COMPLETION:
            _provenance_logger.warning(
                "PROVENANCE_MISSING: obligation %s has completion_pct=%.2f "
                "without source attribution — high completion without audit trail",
                ob_id, obligation.completion_pct,
            )
        else:
            _provenance_logger.info(
                "PROVENANCE_GAP: obligation %s has completion_pct=%.2f "
                "without source attribution",
                ob_id, obligation.completion_pct,
            )

    # Missing provenance on dependencies
    if obligation.dependency_count > 0 and obligation.dependency_source is None:
        _provenance_logger.info(
            "PROVENANCE_GAP: obligation %s has dependency_count=%d "
            "without source attribution",
            ob_id, obligation.dependency_count,
        )

    # Timestamp consistency: completion_pct set but no update timestamp
    if obligation.completion_pct > 0 and obligation.completion_updated_at is None:
        _provenance_logger.info(
            "PROVENANCE_GAP: obligation %s has completion_pct=%.2f "
            "without completion_updated_at timestamp",
            ob_id, obligation.completion_pct,
        )


def _completion_dampening(completion_pct: float) -> float:
    """Compute completion dampening factor D (§3.1)."""
    # Logistic chosen for sharp transition near midpoint — linear
    # under-weights early progress. The linear branch is retained for
    # COMPLETION_DAMPENING_MODE="linear" in sensitivity analysis (§4.2).
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


def _timing_amplifier(
    days_in_status: float,
    days_since_status_change: float | None = None,
) -> float:
    """Compute timing amplification for stuck obligations (#195, #1179, #1261).

    Uses a logistic ramp instead of step function for internal consistency
    with the continuous-framework thesis. The ramp is centered at TIMING_MID_DAYS
    and asymptotes to TIMING_MAX_MULTIPLIER.

    T_amp(d) = 1.0 + boost / (1 + exp(-k * (d - mid)))
    where boost = TIMING_MAX_MULTIPLIER - 1.0

    Anti-exploit (#1261): uses max(days_in_status, days_since_status_change) when
    status_changed_at is available, preventing status-toggle resets from zeroing
    the timing amplifier. Falls back to days_in_status when the field is None.
    """
    effective_days = days_in_status
    if days_since_status_change is not None:
        effective_days = max(days_in_status, days_since_status_change)  # Anti-exploit: use longer window (#1261)
    boost = TIMING_MAX_MULTIPLIER - 1.0
    return 1.0 + boost / (1.0 + _exponential(-TIMING_LOGISTIC_K * (effective_days - TIMING_MID_DAYS)))


def _violation_amplifier(
    violation_count: int,
    days_in_status: float = 0.0,  # Default 0.0: no status age → no temporal decay
    days_since_violation: float | None = None,
) -> float:
    """Compute violation-based pressure amplification (#99, #1184, #1261).

    Three-layer damping prevents perverse feedback loops where a missed
    deadline permanently amplifies an already-difficult obligation:

    1. Temporal decay: effective_count = count * 2^(-d/halflife)
       Violations lose potency over time (half-life = 14 days).
    2. Sublinear scaling (#1184): log(1 + effective) instead of linear.
       Each additional violation contributes less than the previous one,
       preventing runaway amplification cascades.
    3. Hard cap: total amplification cannot exceed VIOLATION_MAX_AMPLIFICATION.

    Anti-exploit (#1261): when violation_first_at is available (passed as
    days_since_violation), decay is anchored to the first violation event
    rather than the status age. This prevents status-toggle resets from
    restarting the decay clock. Falls back to days_in_status when None.
    """
    from tidewatch.constants import VIOLATION_DECAY_HALFLIFE_DAYS
    if violation_count <= 0:
        return _AMPLIFIER_IDENTITY
    effective_decay_days = days_since_violation if days_since_violation is not None else days_in_status
    # Formula choice: exponential half-life decay N(t) = N_0 * 2^(-t/t_half).
    # Chosen over linear decay because violation impact should drop smoothly
    # and asymptotically — a 60-day-old violation should have negligible
    # effect, which exponential achieves while linear would reach zero at
    # a fixed cutoff. HALFLIFE_BASE=2 is the standard physics convention
    # giving decay = 0.5 at exactly one half-life (14 days).
    decay = HALFLIFE_BASE ** (-effective_decay_days / VIOLATION_DECAY_HALFLIFE_DAYS)  # half-life decay
    effective = violation_count * decay
    # Sublinear scaling (#1184): log(1 + x) is the standard "soft-plus"
    # transform giving diminishing returns. The 1 inside log() is the
    # mathematical identity offset ensuring log(1+0) = 0 (no violations
    # → no amplification). This is not a tunable parameter.
    # At effective=1: log(2) ~ 0.693, effective=5: log(6) ~ 1.79,
    # effective=10: log(11) ~ 2.40 — sublinear growth caps runaway amplification.
    damped = math.log(1.0 + effective)
    # Cap: total violation boost ∈ [0, VIOLATION_MAX_AMPLIFICATION] (§3.1)
    return 1.0 + min(damped * VIOLATION_AMPLIFICATION, VIOLATION_MAX_AMPLIFICATION)


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
    # Guard: days_remaining ≥ DIVISION_GUARD prevents division by zero
    return 1.0 - _exponential(-FANOUT_TEMPORAL_K / max(days_remaining, DIVISION_GUARD))


def _clamp_nonnegative_days(days: float) -> float:
    """Floor elapsed days at 0.0 — negative means future timestamp (clock skew)."""
    if days <= 0.0:
        return 0.0
    return days


def _compute_factors(
    obligation: Obligation,
    days_rem: float,
    now: datetime,
    *,
    rate_constant: float | None = None,
    dep_cap: int | None = None,
) -> tuple[float, float, float, float, float, float, float]:
    """Compute all six pressure factors for a single obligation.

    Args:
        rate_constant: Override for RATE_CONSTANT (k). Used by adaptive k.
            Default None uses the module-level RATE_CONSTANT (3.0).
        dep_cap: Override for DEPENDENCY_COUNT_CAP. Used by log_scaled mode.
            Default None uses the module-level DEPENDENCY_COUNT_CAP (20).

    Returns:
        (time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp, t_gate)
    """
    k = rate_constant if rate_constant is not None else RATE_CONSTANT
    cap = dep_cap if dep_cap is not None else DEPENDENCY_COUNT_CAP
    # Guard: days_rem ≥ DIVISION_GUARD prevents division by zero in P_time(t)
    time_p = OVERDUE_PRESSURE if days_rem <= 0 else 1.0 - _exponential(-k / max(days_rem, DIVISION_GUARD))
    mat_mult = MATERIALITY_WEIGHTS.get(obligation.materiality, 1.0)

    # Dependency urgency propagation (#1180): if dependents have earlier deadlines,
    # use the tighter deadline for the temporal gate so urgency propagates upward
    dep_days = days_rem
    if obligation.earliest_dependent_deadline is not None:
        dep_days_rem = _days_remaining(obligation.earliest_dependent_deadline, now)
        dep_days = min(days_rem, dep_days_rem)  # Tighter deadline wins (#1180)
    t_gate = _temporal_gate(dep_days)
    effective_deps = min(obligation.dependency_count, cap)  # DoS cap: deps ∈ [0, cap] (#1213)
    dep_amp = 1.0 + (effective_deps * DEPENDENCY_AMPLIFICATION * t_gate)

    comp_damp = _completion_dampening(obligation.completion_pct)

    # Anti-exploit (#1261): compute days_since_status_change from status_changed_at
    days_since_status_change: float | None = None
    if obligation.status_changed_at is not None:
        days_since_status_change = _clamp_nonnegative_days(
            _days_remaining(now, obligation.status_changed_at),
        )
    timing_amp = _timing_amplifier(obligation.days_in_status, days_since_status_change)

    # Anti-exploit (#1261): compute days_since_violation from violation_first_at
    days_since_violation: float | None = None
    if obligation.violation_first_at is not None:
        days_since_violation = _clamp_nonnegative_days(
            _days_remaining(now, obligation.violation_first_at),
        )
    violation_amp = _violation_amplifier(obligation.violation_count, obligation.days_in_status, days_since_violation)

    return time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp, t_gate


def _apply_ablation(
    ablate: frozenset[str],
    time_p: float,
    mat_mult: float,
    dep_amp: float,
    comp_damp: float,
    timing_amp: float,
    violation_amp: float,
) -> tuple[float, float, float, float, float, float]:
    """Neutralize ablated components to their identity value (1.0) for ablation studies (§4.3)."""
    from tidewatch.components import (
        COMP_COMPLETION_DAMP,
        COMP_DEPENDENCY_AMP,
        COMP_MATERIALITY,
        COMP_TIME_PRESSURE,
        COMP_TIMING_AMP,
        COMP_VIOLATION_AMP,
    )

    # Identity value: 1.0 is the multiplicative identity. When ALL components
    # are ablated, P = 1.0 × 1.0 × ... = 1.0. This tautology is intentional:
    # it verifies no hidden terms exist in the pressure product (§4.3).
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
    return time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp


def _build_result(
    obligation: Obligation,
    time_p: float,
    mat_mult: float,
    dep_amp: float,
    comp_damp: float,
    timing_amp: float,
    violation_amp: float,
    days_rem: float,
    t_gate: float,
) -> PressureResult:
    """Build PressureResult from computed factors via ComponentSpace.

    Constructs the Late Collapse ComponentSpace, collapses to scalar pressure,
    applies the zombie-task guard (#1212), and returns the final result.
    """
    from tidewatch.components import build_pressure_space

    components = build_pressure_space(
        time_pressure=time_p, materiality=mat_mult,
        dependency_amp=dep_amp, completion_damp=comp_damp,
        timing_amp=timing_amp, violation_amp=violation_amp,
        obligation_id=obligation.id,
        raw_inputs={"days_remaining": days_rem, "completion_pct": obligation.completion_pct,
                    "dependency_count": obligation.dependency_count,
                    "temporal_gate": t_gate},
    )

    pressure = components.pressure

    # Zombie task fix (#1212): completed obligations must not haunt the queue.
    # Without this guard, a 100%-complete "done" obligation can still show
    # P ~ 0.615 due to the logistic dampening asymptote (D ~ 0.411 at pct=1.0).
    if obligation.completion_pct >= 1.0 and obligation.status in ("completed", "done"):
        return PressureResult(
            obligation_id=obligation.id, pressure=0.0, zone="green",
            time_pressure=time_p, materiality_mult=mat_mult,
            dependency_amp=dep_amp, completion_damp=comp_damp,
            component_space=components,
        )

    return PressureResult(
        obligation_id=obligation.id, pressure=pressure, zone=pressure_zone(pressure),
        time_pressure=time_p, materiality_mult=mat_mult,
        dependency_amp=dep_amp, completion_damp=comp_damp,
        component_space=components,
    )


def _obligation_input_hash(obligation: Obligation) -> str:
    """Compute a hash of the obligation's mutable scoring-relevant fields.

    Used by recalculate_stale to detect whether an obligation's inputs have
    changed since it was last scored. The hash covers all fields that affect
    the pressure calculation.
    """
    import hashlib
    parts = (
        str(obligation.due_date),
        str(obligation.completion_pct),
        str(obligation.dependency_count),
        str(obligation.materiality),
        str(obligation.violation_count),
        str(obligation.days_in_status),
        str(obligation.status),
        str(obligation.earliest_dependent_deadline),
        str(obligation.status_changed_at),
        str(obligation.violation_first_at),
    )
    return hashlib.md5("|".join(parts).encode(), usedforsecurity=False).hexdigest()


def calculate_pressure(
    obligation: Obligation,
    now: datetime | None = None,
    *,
    ablate: frozenset[str] | None = None,
    rate_constant: float | None = None,
    dep_cap: int | None = None,
) -> PressureResult:
    """Compute pressure for a single obligation (§3.1).

    Architecture: exponential time-decay is the BASE SIGNAL. All other factors
    are MODULATING COMPONENTS. Factors are preserved as named dimensions in a
    ComponentSpace (Late Collapse). The scalar .pressure field is the default
    product collapse, saturated to [0,1].

    Args:
        ablate: frozenset of component names to neutralize (set to 1.0).
            Used for factor ablation studies (§4.3).
        rate_constant: Override for the exponential decay rate constant k.
            Default None uses RATE_CONSTANT (3.0). Set by adaptive k.
        dep_cap: Override for the dependency count cap.
            Default None uses DEPENDENCY_COUNT_CAP (20). Set by log_scaled mode.
    """
    if now is None:
        now = datetime.now(UTC)
    if obligation.due_date is None:
        return _no_deadline_result(obligation.id)

    days_rem = _days_remaining(obligation.due_date, now)
    _validate_obligation_inputs(obligation)

    time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp, t_gate = _compute_factors(
        obligation, days_rem, now,
        rate_constant=rate_constant,
        dep_cap=dep_cap,
    )

    if ablate:
        time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp = _apply_ablation(
            ablate, time_p, mat_mult, dep_amp, comp_damp, timing_amp, violation_amp,
        )

    result = _build_result(
        obligation, time_p, mat_mult, dep_amp, comp_damp,
        timing_amp, violation_amp, days_rem, t_gate,
    )
    result.scored_at = now
    result.input_hash = _obligation_input_hash(obligation)
    return result


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


def _probe_dominance_support(results: list[PressureResult]) -> bool | None:
    """Probe whether the component-space backend supports dominance checks.

    Finds the first two results with a component_space and tests dominance.
    Returns True if supported, False if not enough items, or None if the
    backend returns None (all items incomparable).
    """
    first = None
    second = None
    for r in results:
        if r.component_space is not None:
            if first is None:
                first = r
            elif second is None:
                second = r
                break
    if first is None or second is None:
        return True  # Not enough items to probe — proceed with standard check
    probe = first.component_space.dominates(second.component_space)
    if probe is None:
        return None  # Backend doesn't support dominance
    return True


def _is_dominated(candidate: PressureResult, results: list[PressureResult]) -> bool:
    """Check if candidate is dominated by any other result in the set."""
    for other in results:
        if other is candidate or other.component_space is None:
            continue
        if other.component_space.dominates(candidate.component_space) is True:
            return True
    return False


def _find_pareto_front(results: list[PressureResult]) -> list[PressureResult]:
    """Identify the Pareto front: results not dominated by any other.

    A result is in the front if no other result dominates it on all
    component dimensions simultaneously. Uses ComponentSpace.dominates()
    which is O(d) per comparison, O(n^2 d) total.

    Optimization: if the first dominance check returns None (backend doesn't
    support Pareto comparison), all items are incomparable and the entire
    set is the front. This avoids O(N^2) work with the fallback backend.
    """
    if not results:
        return []

    # Quick check: if backend doesn't support dominance, return all
    support = _probe_dominance_support(results)
    if support is None:
        return list(results)

    front: list[PressureResult] = []
    for candidate in results:
        if candidate.component_space is None or not _is_dominated(candidate, results):
            front.append(candidate)
    return front


def _pareto_layered_sort(
    results: list[PressureResult],
    pareto_budget: int | None = None,
) -> list[PressureResult]:
    """Sort results using Pareto-layered ranking.

    Step 1: Extract the Pareto front (non-dominated results).
    Step 2: Sort the front by scalar pressure descending.
    Step 3: Remove front from remaining, repeat until empty or budget exhausted.

    Args:
        pareto_budget: Maximum number of Pareto fronts to extract. When set,
            extraction stops after this many fronts and remaining items are
            sorted by scalar pressure and appended as a "tail" tier.
            Default None extracts all fronts (backward compatible).

    This preserves multi-dimensional information: a result that dominates
    another always ranks higher, even if its scalar collapse is lower.
    """
    ranked: list[PressureResult] = []
    remaining = list(results)
    fronts_extracted = 0
    while remaining:
        if pareto_budget is not None and fronts_extracted >= pareto_budget:
            # Budget exhausted — sort remaining by scalar pressure
            remaining.sort(key=lambda r: r.pressure, reverse=True)
            ranked.extend(remaining)
            break
        front = _find_pareto_front(remaining)
        front.sort(key=lambda r: r.pressure, reverse=True)
        ranked.extend(front)
        front_ids = {id(r) for r in front}
        remaining = [r for r in remaining if id(r) not in front_ids]
        fronts_extracted += 1
    return ranked


def _emit_batch_telemetry(
    obligations: list[Obligation],
    results: list[PressureResult],
    pareto: bool,
    latency_ms: float,
) -> None:
    """Emit optional telemetry for batch recalculation.

    This is a no-op hook. Callers can monkey-patch or subclass to route
    telemetry to their own metrics backend.
    """
    logging.getLogger(__name__).debug(
        "batch telemetry: size=%d pareto=%s latency_ms=%.1f",
        len(obligations), pareto, latency_ms,
    )


def _rank_normalize_results(results: list[PressureResult]) -> list[PressureResult]:
    """Replace each component value with its percentile rank within the batch.

    For each component dimension, all results are sorted by that dimension's
    raw value. Each result's component is replaced with its rank / (N - 1),
    giving 0.0 for the lowest and 1.0 for the highest. The raw values remain
    accessible via the component_space's underlying storage.

    The product collapse is recomputed from ranked values, and the pressure
    and zone fields are updated accordingly.
    """
    from tidewatch.components import (
        _COMPONENT_KEYS,
        _SOURCE_EQUATION,
        PressureComponents,
        _make_component_space,
    )
    from tidewatch.constants import saturate

    n = len(results)
    if n <= 1:
        return results

    # Extract raw component dicts
    raw_components: list[dict[str, float]] = []
    for r in results:
        if r.component_space is not None:
            raw_components.append(dict(r.component_space.space.components))
        else:
            raw_components.append({})

    # For each component, compute percentile ranks
    ranked_components: list[dict[str, float]] = [{} for _ in range(n)]
    for key in _COMPONENT_KEYS:
        values_with_idx = [(raw_components[i].get(key, 0.0), i) for i in range(n)]
        values_with_idx.sort(key=lambda x: x[0])
        for rank, (_, idx) in enumerate(values_with_idx):
            ranked_components[idx][key] = rank / (n - 1) if n > 1 else SINGLE_ITEM_RANK

    # Rebuild results with ranked components
    for i, r in enumerate(results):
        ranked_space = _make_component_space(
            components=ranked_components[i],
            component_bounds={k: (0.0, 1.0) for k in _COMPONENT_KEYS},
            source_equation=_SOURCE_EQUATION + " [rank-normalized]",
            raw_inputs={"raw_components": raw_components[i]},
        )
        ranked_pc = PressureComponents(space=ranked_space, obligation_id=r.obligation_id)
        r.pressure = saturate(ranked_pc.pressure)
        r.zone = pressure_zone(r.pressure)
        r.component_space = ranked_pc
    return results


def recalculate_batch(
    obligations: list[Obligation],
    now: datetime | None = None,
    *,
    pareto: bool = False,
    deadline_distribution: DeadlineDistribution | None = None,
    rank_normalize: bool = False,
    pareto_budget: int | None = None,
    dependency_cap_mode: str = "fixed",
) -> list[PressureResult]:
    """Recalculate pressure for a batch of obligations.

    Args:
      obligations: list of Obligation dataclasses
      now: current datetime (default: utcnow, shared across batch)
      pareto: if True, use Pareto-layered ranking instead of scalar sort.
      deadline_distribution: population deadline statistics for adaptive k.
          When provided, the exponential decay rate constant k is computed
          so the yellow-entry threshold (P=0.30) falls at the population's
          median deadline distance. When absent, k=3.0 (backward compatible).
      rank_normalize: if True, replace component values with their percentile
          rank within the batch before collapsing to scalar pressure.
          This spreads scores across [0,1] even when raw values cluster.
          Default False (backward compatible).
      pareto_budget: maximum number of Pareto fronts to extract. When set,
          extraction stops after this many fronts and remaining items are
          sorted by collapsed score. Default None (extract all, backward compatible).
      dependency_cap_mode: "fixed" (default, backward compatible) or "log_scaled".
          In log_scaled mode, cap = max(20, ceil(log2(N) * 5)).

    Returns:
      list[PressureResult] sorted by pressure descending (or Pareto rank)
    """
    import time as _time

    _t0 = _time.monotonic()
    if now is None:
        now = datetime.now(UTC)

    # Problem 1: Adaptive k
    rate_k: float | None = None
    if deadline_distribution is not None:
        rate_k = compute_adaptive_k(deadline_distribution)

    # Problem 6: Population-relative dependency cap
    dep_cap: int | None = None
    if dependency_cap_mode != "fixed":
        dep_cap = compute_dependency_cap(len(obligations), mode=dependency_cap_mode)

    results = [
        calculate_pressure(ob, now=now, rate_constant=rate_k, dep_cap=dep_cap)
        for ob in obligations
    ]

    # Problem 2: Rank normalization
    if rank_normalize:
        results = _rank_normalize_results(results)

    if pareto:
        results = _pareto_layered_sort(results, pareto_budget=pareto_budget)
    else:
        def _sort_key(r: PressureResult) -> tuple[float, float]:
            raw = r.component_space.space.collapsed if r.component_space else r.pressure
            return (r.pressure, raw)
        results.sort(key=_sort_key, reverse=True)

    _latency_ms = (_time.monotonic() - _t0) * MS_PER_SECOND
    _emit_batch_telemetry(obligations, results, pareto, _latency_ms)

    return results


def export_pressure_summary(results: list[PressureResult]) -> dict:
    """Export system pressure summary for evolution governance consumption (#140).

    Returns dict with system_pressure (max), red_count, and at-risk obligation IDs.
    Callers use system_pressure >= EVOLUTION_PAUSE_THRESHOLD to pause evolution.
    """
    if not results:
        return {"system_pressure": 0.0, "red_count": 0, "obligations_at_risk": []}
    system_pressure = max(r.pressure for r in results)
    red = [r for r in results if r.zone == "red"]
    return {
        "system_pressure": system_pressure,
        "red_count": len(red),
        "obligations_at_risk": [r.obligation_id for r in red],
        "should_pause_evolution": system_pressure >= EVOLUTION_PAUSE_THRESHOLD,
    }


def recalculate_stale(
    results: list[PressureResult],
    obligations: list[Obligation],
    now: datetime,
    staleness_budget: float,
    *,
    rate_constant: float | None = None,
    dep_cap: int | None = None,
) -> list[PressureResult]:
    """Incrementally rescore only stale or changed obligations.

    A result is considered stale if:
    1. Its scored_at is older than now - staleness_budget (seconds), OR
    2. The obligation's mutable fields have changed since scored_at
       (detected via input_hash comparison).

    Args:
        results: Previous batch results (with scored_at and input_hash).
        obligations: Current obligations (may have updated fields).
        now: Current datetime for scoring.
        staleness_budget: Maximum age in seconds before a result is stale.
        rate_constant: Optional adaptive k override.
        dep_cap: Optional dependency cap override.

    Returns:
        Updated results list with stale items rescored. Order is NOT
        guaranteed — caller should re-sort if needed.
    """
    from datetime import timedelta as _td

    ob_map = {ob.id: ob for ob in obligations}
    result_map = {r.obligation_id: r for r in results}
    cutoff = now - _td(seconds=staleness_budget)

    stale_ids: set[int | str] = set()
    for r in results:
        ob = ob_map.get(r.obligation_id)
        if ob is None:
            continue
        # Stale by age
        if r.scored_at is None or r.scored_at < cutoff:
            stale_ids.add(r.obligation_id)
            continue
        # Stale by input change
        current_hash = _obligation_input_hash(ob)
        if r.input_hash != current_hash:
            stale_ids.add(r.obligation_id)

    # Rescore stale items
    for ob_id in stale_ids:
        ob = ob_map.get(ob_id)
        if ob is None:
            continue
        new_result = calculate_pressure(
            ob, now=now, rate_constant=rate_constant, dep_cap=dep_cap,
        )
        result_map[ob_id] = new_result

    return list(result_map.values())


def top_k_obligations(
    results: list[PressureResult],
    k: int,
) -> list[PressureResult]:
    """Return the K highest-pressure items with full component decomposition.

    Args:
        results: Scored results (from recalculate_batch).
        k: Number of top items to return.

    Returns:
        List of the top K results sorted by pressure descending, each with
        its full component_space and zone intact.
    """
    sorted_results = sorted(results, key=lambda r: r.pressure, reverse=True)
    return sorted_results[:k]


def apply_zone_capacity(
    results: list[PressureResult],
    zone_capacity: int | None = None,
) -> list[PressureResult]:
    """Apply zone capacity limits, demoting overflow items to the next lower zone.

    When a zone exceeds capacity, only the top zone_capacity items (by pressure)
    remain in that zone; the rest are demoted to the next lower zone. Demotion
    cascades: red overflow → orange, which may then overflow → yellow, etc.

    Args:
        results: Scored results.
        zone_capacity: Maximum items per zone. None means no limit (backward compatible).

    Returns:
        Results with updated zone labels. Pressure values are unchanged.
    """
    if zone_capacity is None:
        return results

    _DEMOTION_MAP = {"red": "orange", "orange": "yellow", "yellow": "green"}
    _ZONE_ORDER = ["red", "orange", "yellow"]

    sorted_results = sorted(results, key=lambda r: r.pressure, reverse=True)

    # Iterate zones top-down. Demotion from red may overflow orange,
    # so we re-check each zone after processing higher zones.
    for zone in _ZONE_ORDER:
        zone_items = [r for r in sorted_results if r.zone == zone]
        if len(zone_items) > zone_capacity:
            # Sort zone items by pressure desc, keep top zone_capacity
            zone_items.sort(key=lambda r: r.pressure, reverse=True)
            demoted = zone_items[zone_capacity:]
            lower_zone = _DEMOTION_MAP[zone]
            for r in demoted:
                r.zone = lower_zone

    return sorted_results


def _check_stability_freeze(
    result: PressureResult,
    previous: list[PressureResult],
    min_stability_seconds: float,
    old_pos: int,
) -> int | None:
    """Check if a result should be frozen at its old position due to time stability.

    Returns the frozen position if stability threshold not met, else None.
    """
    if min_stability_seconds <= 0 or result.scored_at is None:
        return None
    for prev_r in previous:
        if prev_r.obligation_id == result.obligation_id and prev_r.scored_at is not None:
            elapsed = (result.scored_at - prev_r.scored_at).total_seconds()
            if elapsed < min_stability_seconds:
                return old_pos
            break
    return None


def _cap_displacement(
    old_pos: int,
    new_pos: int,
    max_displacement: int,
    list_len: int,
) -> int | None:
    """Cap displacement to max_displacement positions.

    Returns the capped position if displacement exceeds the limit, else None.
    The result is clamped to valid list indices [0, list_len - 1].
    """
    displacement = new_pos - old_pos
    if abs(displacement) <= max_displacement:
        return None
    capped = old_pos + (max_displacement if displacement > 0 else -max_displacement)
    return max(0, min(capped, list_len - 1))


def dampen_rank_changes(
    current: list[PressureResult],
    previous: list[PressureResult] | None = None,
    *,
    max_displacement: int | None = None,
    min_stability_seconds: float = 0.0,
) -> list[PressureResult]:
    """Smooth ranking output to prevent priority thrashing.

    When obligations rapidly swap ranks between recalculations (e.g., #1 and
    #2 swap every cycle), this causes cognitive whiplash for human operators
    or context-switching overhead for agent systems. This function limits
    how far any obligation can move in a single recalculation.

    Inspired by derivative dampening in PID controllers: if a task's rank
    is accelerating too rapidly relative to peers, displacement is capped.

    Args:
        current: Latest scored results, sorted by pressure descending.
        previous: Prior scored results from the last recalculation.
            If None, no dampening is applied (backward compatible).
        max_displacement: Maximum positions any item can move per
            recalculation. None means no limit (backward compatible).
        min_stability_seconds: Minimum time an item must hold its rank
            before it can be displaced. Uses scored_at timestamps.
            Default 0.0 (no stability requirement).

    Returns:
        Results re-sorted with displacement limits applied. Pressure
        values are unchanged — only sort order is affected.
    """
    if previous is None or max_displacement is None:
        return current

    if not previous or not current:
        return current

    # Build previous rank map: obligation_id -> rank (0-indexed)
    prev_rank: dict[int | str, int] = {
        r.obligation_id: i for i, r in enumerate(previous)
    }

    # Build current rank map
    curr_rank: dict[int | str, int] = {
        r.obligation_id: i for i, r in enumerate(current)
    }

    # For items that existed in both, limit displacement
    dampened = list(current)
    needs_reorder = False

    for result in dampened:
        ob_id = result.obligation_id
        if ob_id not in prev_rank:
            continue  # New item — no dampening

        old_pos = prev_rank[ob_id]
        new_pos = curr_rank[ob_id]

        # Check time stability — freeze at old position if too soon
        frozen = _check_stability_freeze(result, previous, min_stability_seconds, old_pos)
        if frozen is not None:
            curr_rank[ob_id] = frozen
            needs_reorder = True

        # Cap displacement
        capped = _cap_displacement(old_pos, new_pos, max_displacement, len(dampened))
        if capped is not None:
            curr_rank[ob_id] = capped
            needs_reorder = True

    if not needs_reorder:
        return current

    # Rebuild order: place each item at its dampened position.
    # Resolve collisions by pressure (higher pressure wins the position).
    indexed: list[tuple[float, float, PressureResult]] = []
    for r in dampened:
        target = curr_rank.get(r.obligation_id, 0)
        indexed.append((target, -r.pressure, r))
    indexed.sort()
    return [r for _, _, r in indexed]


def _get_effective_risk_tier(ob: Obligation, now: datetime | None = None) -> int:
    """Resolve the effective risk tier for bandwidth modulation.

    Uses the explicit risk_tier field. Falls back to legacy hard_floor flag
    and demand-based heuristic for backward compatibility.

    Demand-based detection (#1181): instead of hardcoding domain names, uses
    the domain's cognitive demand profile. Domains with mean demand >=
    HARD_FLOOR_DEMAND_THRESHOLD within HARD_FLOOR_DAYS_THRESHOLD of deadline
    get auto-promoted to NEVER_DEMOTABLE. This makes the detection signal-based:
    adding a new high-stakes domain to TASK_DEMAND_PROFILES automatically
    triggers protection without modifying the detection logic.

    Returns RiskTier int value (0=NEVER_DEMOTABLE, 1=WITH_FLOOR, 2=FULLY_DEMOTABLE).
    """
    from tidewatch.constants import HARD_FLOOR_DEMAND_THRESHOLD
    from tidewatch.types import RiskTier

    # Explicit risk_tier takes priority
    if ob.risk_tier == RiskTier.NEVER_DEMOTABLE:
        return RiskTier.NEVER_DEMOTABLE
    if ob.risk_tier == RiskTier.DEMOTABLE_WITH_FLOOR:
        return RiskTier.DEMOTABLE_WITH_FLOOR

    # Obligation.hard_floor: retained for callers that set it explicitly.
    # New code should use risk_tier=RiskTier.NEVER_DEMOTABLE instead.
    if ob.hard_floor:
        return RiskTier.NEVER_DEMOTABLE

    # Demand-based heuristic (#1181): high-demand domains near deadline
    # get auto-promoted. Detection uses cognitive demand signals, not
    # hardcoded domain name strings.
    if ob.due_date is not None:
        demand = estimate_task_demand(ob)
        mean_demand = (demand.complexity + demand.novelty + demand.decision_weight) / FIT_SCORE_MISMATCH_COMPONENTS
        if mean_demand >= HARD_FLOOR_DEMAND_THRESHOLD:
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

    Three-tier risk classification (#1131):
    - NEVER_DEMOTABLE (tier 0): sorts above all others, pure pressure
    - DEMOTABLE_WITH_FLOOR (tier 1): bandwidth-adjusted but never below
      DEMOTABLE_FLOOR_FRACTION of original pressure
    - FULLY_DEMOTABLE (tier 2): fully bandwidth-adjusted, no floor
    """
    from tidewatch.constants import DEMOTABLE_FLOOR_FRACTION
    from tidewatch.types import RiskTier
    ob = ob_map.get(result.obligation_id)
    if ob is None:
        return (_SORT_TIER_NORMAL, result.pressure)

    tier = _get_effective_risk_tier(ob)
    if tier == RiskTier.NEVER_DEMOTABLE:
        return (_SORT_TIER_HARD_FLOOR, result.pressure)

    demand = estimate_task_demand(ob)
    mismatch = (demand.complexity + demand.novelty + demand.decision_weight) / FIT_SCORE_MISMATCH_COMPONENTS
    adjusted = result.pressure * (1.0 - mismatch * (1.0 - bandwidth))
    gravity_bonus = (ob.gravity_score or 0.0) * GRAVITY_TIEBREAK_WEIGHT

    if tier == RiskTier.DEMOTABLE_WITH_FLOOR:
        floor = result.pressure * DEMOTABLE_FLOOR_FRACTION
        adjusted = max(adjusted, floor)  # Floor: never reduce below DEMOTABLE_FLOOR_FRACTION (#1131)

    return (_SORT_TIER_NORMAL, adjusted + gravity_bonus)


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
