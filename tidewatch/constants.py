# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tunable constants for Tidewatch pressure engine.

Each constant has a hydraulic analog documented in its comment.
Zone thresholds are configurable via environment variables (TIDEWATCH_ZONE_*).
"""

import os

# --- Domain-bounded arithmetic ---
# These enforce the probability domain [0, 1] inherent to pressure scores,
# bandwidth values, and demand dimensions. They are not editorial clamps.

_SATURATE_FLOOR = 0.0
_SATURATE_CEIL = 1.0


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


BANDWIDTH_NO_DATA = 1.0  # Returned when no signals available (fail-open)


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

# --- Materiality ---
MATERIALITY_WEIGHTS: dict[str, float] = {
    "material": 1.5,       # Wide pipe -- carries more pressure
    "routine": 1.0,        # Standard pipe
}

# --- Dependencies ---
DEPENDENCY_AMPLIFICATION = 0.1  # Per-dependency amplifier (junction multiplier)

# --- Completion ---
COMPLETION_DAMPENING = 0.6  # Max dampening at 100% completion (relief valve)
COMPLETION_DAMPENING_MODE = "logistic"  # "linear" or "logistic"
COMPLETION_LOGISTIC_K = 8.0   # Steepness of logistic curve
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
BANDWIDTH_FULL_THRESHOLD = 0.99  # Above this, skip bandwidth adjustment
BANDWIDTH_HOURS_GOOD = 8.0      # Hours since sleep: 0-8h = good (1.0)
BANDWIDTH_HOURS_BAD = 16.0      # Hours since sleep: 16h+ = bad (0.0)
BANDWIDTH_NORMALIZATION_RANGE = 8.0  # BANDWIDTH_HOURS_BAD - BANDWIDTH_HOURS_GOOD

# --- Task demand estimation (domain -> cognitive profile) ---
def _build_demand_profiles() -> dict[str, dict[str, float]]:
    """Domain-to-cognitive-profile mapping. Complete for known domains."""
    return {
        "legal":      {"complexity": 0.8, "decision_weight": 0.9, "novelty": 0.6},
        "financial":  {"complexity": 0.8, "decision_weight": 0.9, "novelty": 0.6},
        "engineering": {"complexity": 0.5, "decision_weight": 0.4, "novelty": 0.5},
        "ops":        {"complexity": 0.3, "decision_weight": 0.2, "novelty": 0.2},
        "admin":      {"complexity": 0.3, "decision_weight": 0.2, "novelty": 0.2},
    }


def _build_demand_default() -> dict[str, float]:
    """Default cognitive demand profile for unknown domains."""
    return {"complexity": 0.5, "decision_weight": 0.5, "novelty": 0.5}


TASK_DEMAND_PROFILES: dict[str, dict[str, float]] = _build_demand_profiles()
TASK_DEMAND_DEFAULT: dict[str, float] = _build_demand_default()
MATERIAL_COMPLEXITY_BOOST = 0.2    # Added to complexity for material items
MATERIAL_DECISION_BOOST = 0.1      # Added to decision_weight for material items

# --- Hard floor auto-detection ---
HARD_FLOOR_DOMAINS: frozenset[str] = frozenset({"legal", "financial"})
HARD_FLOOR_DAYS_THRESHOLD = 1.0    # Auto-detect hard floor within this many days

# --- Speculative planner ---
PLANNER_MIN_ZONES: frozenset[str] = frozenset({"yellow", "orange", "red"})
PLANNER_TOP_N = 3           # Max obligations to plan per cycle
PLANNER_MAX_STEPS = 3       # Steps per plan
PLANNER_MAX_TOKENS = 500    # Token budget per plan prompt

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

# --- Timing amplification (#195) ---
TIMING_STALE_DAYS = 7           # Days in-progress before first amplification tier
TIMING_CRITICAL_DAYS = 14       # Days in-progress before second amplification tier
TIMING_STALE_MULTIPLIER = 1.1   # 10% amplification for stale obligations
TIMING_CRITICAL_MULTIPLIER = 1.2  # 20% amplification for critically stuck obligations

# --- Violation amplification (#99) ---
VIOLATION_AMPLIFICATION = 0.05  # Per-violation pressure amplifier (additive to dep_amp)
VIOLATION_MAX_AMPLIFICATION = 0.5  # Cap on total violation amplification

# --- Gravity tiebreak (#635) ---
GRAVITY_TIEBREAK_WEIGHT = 0.1   # Weight of gravity score in bandwidth-adjusted sort

# --- Forge pressure export (#140) ---
FORGE_PRESSURE_PAUSE_THRESHOLD = 0.80  # System pressure above which forge pauses evolution

# --- Planner sanitization limits ---
PLANNER_TITLE_MAX_LEN = 200
PLANNER_DESC_MAX_LEN = 500
PLANNER_DOMAIN_MAX_LEN = 50
PLANNER_ASCII_PRINTABLE_MIN = 32
