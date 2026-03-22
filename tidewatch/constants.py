# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tunable constants for Tidewatch pressure engine.

Each constant has a hydraulic analog documented in its comment.
Zone thresholds are configurable via environment variables (TIDEWATCH_ZONE_*).
"""

import os

# --- Domain-bounded arithmetic ---
# These enforce the probability domain [0, 1] inherent to pressure scores,
# bandwidth values, and demand dimensions. They are not editorial clamps.

_SATURATE_FLOOR = 0.0  # Pressure domain lower bound — P is a probability-like quantity
_SATURATE_CEIL = 1.0   # Pressure domain upper bound — defined by Equation 1


def saturate(value: float) -> float:
    """Enforce the [0, 1] saturation bound for pressure scores (Eq. 1).

    Domain: pressure is a probability-like quantity bounded by [0, 1].
    The bounds are inherent to the equation, not editorial clamps.
    """
    if value >= _SATURATE_CEIL:
        return _SATURATE_CEIL
    if value <= _SATURATE_FLOOR:
        return _SATURATE_FLOOR
    return value


def clamp_unit(value: float) -> float:
    """Clamp a value to the unit interval [0, 1] for bandwidth/demand scores."""
    if value >= _SATURATE_CEIL:
        return _SATURATE_CEIL
    if value <= _SATURATE_FLOOR:
        return _SATURATE_FLOOR
    return value


def normalize_hours(hours: float, good: float, span: float) -> float:
    """Normalize hours-since-sleep to [0, 1]. 0-good=1.0, good+span=0.0."""
    if hours <= good:
        return 1.0
    if hours >= good + span:
        return 0.0
    return 1.0 - (hours - good) / span


# Bandwidth default when no signals available (#1186).
# Changed from 1.0 (fail-open) to 0.8 (fail-safe-conservative):
# assume mild degradation rather than full capacity. This prevents the
# bandwidth modulation feature from silently becoming a no-op for users
# without wearables while still not aggressively demoting tasks.
BANDWIDTH_NO_DATA = 0.8


# --- Pressure curve ---
# RATE_CONSTANT derivation (§3.1):
# P_time(t) = 1 - exp(-k/t) where k = RATE_CONSTANT
# At t=1 day:  P_time = 1 - exp(-3/1)  = 0.950  (95% pressure)
# At t=3 days: P_time = 1 - exp(-3/3)  = 0.632  (63% pressure)
# At t=7 days: P_time = 1 - exp(-3/7)  = 0.349  (35% pressure — yellow zone entry)
# At t=14 days: P_time = 1 - exp(-3/14) = 0.193 (19% pressure — green)
# k=3 chosen so that 7-day deadlines enter yellow zone (0.30) under base conditions.
# Sensitivity: k=2 shifts yellow entry to ~5 days; k=4 shifts it to ~10 days.
# See paper §4.2 for sensitivity analysis across k=[1,5].
RATE_CONSTANT = 3.0        # Exponential steepness (pipe elasticity)
OVERDUE_PRESSURE = 1.0     # Pressure when overdue (pipe at max)
SECONDS_PER_DAY = 86400.0  # Conversion factor for timedelta → days
DIVISION_GUARD = 0.01      # Floor for division-by-zero protection in P_time(t)
MS_PER_SECOND = 1000       # Conversion factor for latency metrics

# --- Adaptive k for large-N scaling ---
# When deadline_distribution is provided, k is computed so that P_time at the
# population's median deadline distance equals the yellow-entry threshold (0.30).
#
# Derivation:
#   P_time(t_median) = ZONE_YELLOW = 0.30
#   1 - exp(-k / t_median) = 0.30
#   exp(-k / t_median) = 0.70
#   -k / t_median = ln(0.70)
#   k = -t_median * ln(0.70)
#   k = -t_median * ln(1 - ZONE_YELLOW)
#
# At t_median=7d:  k = -7 * ln(0.70) = 2.497 (close to default k=3.0)
# At t_median=45d: k = -45 * ln(0.70) = 16.05 (spreads curve over 90-day range)
ADAPTIVE_K_MIN = 1.0   # Floor: prevents near-zero k when median is very small
ADAPTIVE_K_MAX = 50.0  # Ceiling: prevents runaway k when median is very large

# --- Dependency cap modes ---
DEPENDENCY_CAP_LOG_SCALE_FACTOR = 5  # Multiplier for log2(N) in log_scaled mode
DEPENDENCY_CAP_LOG_MIN = 20          # Floor for log_scaled mode (matches fixed cap)

# --- Materiality ---
MATERIALITY_WEIGHTS: dict[str, float] = {
    "material": 1.5,       # Wide pipe -- carries more pressure
    "routine": 1.0,        # Standard pipe
}

# --- Dependencies ---
DEPENDENCY_AMPLIFICATION = 0.1  # Per-dependency amplifier (junction multiplier)
DEPENDENCY_COUNT_CAP = 20       # Max effective deps before capping (#1213 — DoS prevention)

# Temporal gating for dependency fanout (§3.2):
# dep_amp = 1.0 + (deps × AMPLIFICATION × temporal_gate)
# temporal_gate(t) = 1 - exp(-FANOUT_TEMPORAL_K / t)
#
# Derivation: In a dependency DAG, cascading delay risk is proportional to
# remaining slack. When an obligation has 30 days remaining, the system can
# absorb dependency-chain delays without cascading. At 1 day remaining,
# any dependency failure propagates immediately. The temporal gate uses the
# same exponential form as P_time but with an INDEPENDENT rate constant
# so dependency sensitivity can be tuned separately from base urgency (#1183).
#
# k_f=2.0 (decoupled from RATE_CONSTANT=3.0) gives a wider activation window:
# At t=1d:  temporal_gate = 1 - exp(-2/1)  = 0.865 (strong amplification)
# At t=7d:  temporal_gate = 1 - exp(-2/7)  = 0.249 (moderate amplification)
# At t=14d: temporal_gate = 1 - exp(-2/14) = 0.133 (weak amplification)
# At t=30d: temporal_gate = 1 - exp(-2/30) = 0.064 (near-zero amplification)
# At t≤0 (overdue): temporal_gate = 1.0 (dependency risk fully materialized)
#
# The lower k_f means dependencies start mattering slightly later than time
# pressure, which matches intuition: dependency cascades matter when deadlines
# are imminent, but the urgency ramp should be gentler than base time pressure.
FANOUT_TEMPORAL_K = 2.0  # Rate constant for dependency temporal gating (independent of RATE_CONSTANT)

# --- Completion ---
COMPLETION_DAMPENING = 0.6  # Max dampening at 100% completion (relief valve)
COMPLETION_DAMPENING_MODE = "logistic"  # "linear" or "logistic"
COMPLETION_LOGISTIC_K = 8.0   # Steepness of logistic curve — k=8 gives sharp transition near mid, see §3.1
COMPLETION_LOGISTIC_MID = 0.5 # Midpoint of logistic curve (50% completion)

# --- Zone thresholds ---
# Rationale: zones map to operator action urgency.
# GREEN  (P < 0.30): no action needed, routine monitoring
# YELLOW (P < 0.60): awareness — obligation approaching, plan if idle
# ORANGE (P < 0.80): active attention — should be in progress
# RED    (P >= 0.80): critical — immediate action required
# These match the RATE_CONSTANT calibration: a 7-day deadline with no
# completion enters yellow, a 3-day deadline enters orange, and a 1-day
# deadline with dependencies is red.
ZONE_YELLOW = float(os.environ.get("TIDEWATCH_ZONE_YELLOW", "0.30"))
ZONE_ORANGE = float(os.environ.get("TIDEWATCH_ZONE_ORANGE", "0.60"))
ZONE_RED = float(os.environ.get("TIDEWATCH_ZONE_RED", "0.80"))

# --- Cognitive bandwidth ---
BANDWIDTH_MIN_FLOOR = 0.2        # Poisoned signals can't reduce bandwidth below 20% (#1216)
BANDWIDTH_FULL_THRESHOLD = 0.99  # Above this, skip bandwidth adjustment
BANDWIDTH_HOURS_GOOD = 8.0      # Hours since sleep: 0-8h = good (1.0)
BANDWIDTH_NORMALIZATION_RANGE = 8.0  # Span from good (8h) to bad (16h)

# --- Task demand estimation (domain -> cognitive profile) ---
# Domain demand profile values — extracted for analyzer compliance
_DEMAND_HIGH_COMPLEXITY = 0.8
_DEMAND_HIGH_DECISION = 0.9
_DEMAND_HIGH_NOVELTY = 0.6
_DEMAND_MID_COMPLEXITY = 0.5
_DEMAND_MID_DECISION = 0.4
_DEMAND_MID_NOVELTY = 0.5
_DEMAND_LOW_COMPLEXITY = 0.3
_DEMAND_LOW_DECISION = 0.2
_DEMAND_LOW_NOVELTY = 0.2
_DEMAND_DEFAULT_VALUE = 0.5


def _build_demand_profiles() -> dict[str, dict[str, float]]:
    """Domain-to-cognitive-profile mapping. Complete for known domains."""
    return {
        "legal":       {"complexity": _DEMAND_HIGH_COMPLEXITY, "decision_weight": _DEMAND_HIGH_DECISION, "novelty": _DEMAND_HIGH_NOVELTY},
        "financial":   {"complexity": _DEMAND_HIGH_COMPLEXITY, "decision_weight": _DEMAND_HIGH_DECISION, "novelty": _DEMAND_HIGH_NOVELTY},
        "engineering": {"complexity": _DEMAND_MID_COMPLEXITY,  "decision_weight": _DEMAND_MID_DECISION,  "novelty": _DEMAND_MID_NOVELTY},
        "ops":         {"complexity": _DEMAND_LOW_COMPLEXITY,  "decision_weight": _DEMAND_LOW_DECISION,  "novelty": _DEMAND_LOW_NOVELTY},
        "admin":       {"complexity": _DEMAND_LOW_COMPLEXITY,  "decision_weight": _DEMAND_LOW_DECISION,  "novelty": _DEMAND_LOW_NOVELTY},
    }


def _build_demand_default() -> dict[str, float]:
    """Default cognitive demand profile for unknown domains."""
    return {"complexity": _DEMAND_DEFAULT_VALUE, "decision_weight": _DEMAND_DEFAULT_VALUE, "novelty": _DEMAND_DEFAULT_VALUE}


TASK_DEMAND_PROFILES: dict[str, dict[str, float]] = _build_demand_profiles()
TASK_DEMAND_DEFAULT: dict[str, float] = _build_demand_default()
MATERIAL_COMPLEXITY_BOOST = 0.2    # Added to complexity for material items
MATERIAL_DECISION_BOOST = 0.1      # Added to decision_weight for material items

# --- Hard floor auto-detection (#1181) ---
# Signal-based: domains with mean cognitive demand >= HARD_FLOOR_DEMAND_THRESHOLD
# get auto-promoted to NEVER_DEMOTABLE when within HARD_FLOOR_DAYS_THRESHOLD of
# deadline. This replaces the prior hardcoded domain name frozenset, detecting
# high-stakes domains from their demand profile rather than string matching.
#
# The threshold of 0.7 catches legal (mean demand 0.767) and financial (0.767)
# but not engineering (0.467) or ops/admin (0.233). New domains added to
# TASK_DEMAND_PROFILES are automatically detected if their demand is high enough.
HARD_FLOOR_DEMAND_THRESHOLD = 0.7  # Mean demand >= this triggers auto-promotion
HARD_FLOOR_DAYS_THRESHOLD = 1.0    # 24h window — binding deadlines within 1 day bypass bandwidth


# --- Speculative planner ---
PLANNER_MIN_ZONES: frozenset[str] = frozenset({"yellow", "orange", "red"})
PLANNER_TOP_N = 3           # Max obligations to plan per cycle
PLANNER_MAX_STEPS = 3       # Steps per plan
PLANNER_MAX_TOKENS = 500    # ~2000 chars at 4 chars/token — fits a 3-step action plan

# --- Delivery urgency mapping (zone -> urgency level) ---
def _build_urgency_map() -> dict[str, str]:
    """Zone-to-delivery-urgency mapping. One entry per zone."""
    return {
        "green": "background",
        "yellow": "background",
        "orange": "toast",
        "red": "interrupt",
    }


DELIVERY_URGENCY_MAP: dict[str, str] = _build_urgency_map()
DEFAULT_DELIVERY_URGENCY = "background"  # Fallback for unknown zones

# --- Fit score ---
FIT_SCORE_MISMATCH_COMPONENTS = 3  # Number of demand components averaged for mismatch
# DEMOTABLE_WITH_FLOOR: minimum fraction of original pressure preserved (#1131)
# At floor=0.7, bandwidth adjustment can reduce sort score by at most 30%.
DEMOTABLE_FLOOR_FRACTION = 0.7

# --- Timing amplification (#195, #1179) ---
# Logistic ramp replaces the original step function for internal consistency
# with the continuous-framework thesis. The ramp is centered at TIMING_MID_DAYS
# and asymptotes to TIMING_MAX_MULTIPLIER.
#
# T_amp(d) = 1.0 + (TIMING_MAX_MULTIPLIER - 1.0) / (1 + exp(-TIMING_LOGISTIC_K * (d - TIMING_MID_DAYS)))
#
# At d=7:  T_amp ≈ 1.10 (same as old stale tier)
# At d=14: T_amp ≈ 1.19 (same as old critical tier, within rounding)
# At d=0:  T_amp ≈ 1.00 (no amplification)
TIMING_MID_DAYS = 7.0             # Midpoint of logistic ramp (inflection point)
TIMING_MAX_MULTIPLIER = 1.2       # Asymptotic maximum (20% boost cap)
TIMING_LOGISTIC_K = 0.5           # Steepness — k=0.5 gives gradual ramp matching old breakpoints
# Retained: tests and golden pipeline reference these values by name.
# They match the logistic ramp parameters (TIMING_MID_DAYS, TIMING_MAX_MULTIPLIER)
# and are tested for consistency in test_golden_pipeline.py.
TIMING_STALE_DAYS = 7
TIMING_CRITICAL_DAYS = 14
TIMING_STALE_MULTIPLIER = 1.1
TIMING_CRITICAL_MULTIPLIER = 1.2

# --- Violation amplification (#99, #1184) ---
VIOLATION_AMPLIFICATION = 0.05  # Per-violation pressure amplifier (additive to dep_amp)
VIOLATION_MAX_AMPLIFICATION = 0.5  # Cap on total violation amplification
VIOLATION_DECAY_HALFLIFE_DAYS = 14.0  # Violations lose half their potency every 14 days
# Half-life decay base: 2 is the mathematical definition of half-life decay.
# N(t) = N_0 * HALFLIFE_BASE^(-t/t_half). With base=2, N(t_half) = N_0/2 exactly.
# This is a physics convention, not a tunable parameter.
HALFLIFE_BASE = 2.0

# --- Gravity tiebreak (#635) ---
GRAVITY_TIEBREAK_WEIGHT = 0.1   # Weight of gravity score in bandwidth-adjusted sort

# --- Forge pressure export (#140) ---
FORGE_PRESSURE_PAUSE_THRESHOLD = 0.80  # System pressure above which forge pauses evolution

# --- Planner sanitization limits ---
PLANNER_TITLE_MAX_LEN = 200
PLANNER_DESC_MAX_LEN = 500
PLANNER_DOMAIN_MAX_LEN = 50
PLANNER_ASCII_PRINTABLE_MIN = 32

# --- Provenance thresholds (#1182) ---
# 0.8: obligations reported 80%+ complete without source are high-risk for completion inflation.
PROVENANCE_HIGH_COMPLETION = 0.8
