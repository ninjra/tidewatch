# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tunable constants for Tidewatch pressure engine.

Each constant has a hydraulic analog documented in its comment.
"""

# --- Pressure curve ---
RATE_CONSTANT = 3.0        # Exponential steepness (pipe elasticity)
OVERDUE_PRESSURE = 1.0     # Pressure when overdue (pipe at max)

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
ZONE_YELLOW = 0.30
ZONE_ORANGE = 0.60
ZONE_RED = 0.80

# --- Cognitive bandwidth ---
BANDWIDTH_FULL_THRESHOLD = 0.99  # Above this, skip bandwidth adjustment
BANDWIDTH_HOURS_GOOD = 8.0      # Hours since sleep: 0-8h = good (1.0)
BANDWIDTH_HOURS_BAD = 16.0      # Hours since sleep: 16h+ = bad (0.0)
BANDWIDTH_NORMALIZATION_RANGE = 8.0  # BANDWIDTH_HOURS_BAD - BANDWIDTH_HOURS_GOOD

# --- Task demand estimation (domain -> cognitive profile) ---
TASK_DEMAND_PROFILES: dict[str, dict[str, float]] = {
    "legal":      {"complexity": 0.8, "decision_weight": 0.9, "novelty": 0.6},
    "financial":  {"complexity": 0.8, "decision_weight": 0.9, "novelty": 0.6},
    "engineering": {"complexity": 0.5, "decision_weight": 0.4, "novelty": 0.5},
    "ops":        {"complexity": 0.3, "decision_weight": 0.2, "novelty": 0.2},
    "admin":      {"complexity": 0.3, "decision_weight": 0.2, "novelty": 0.2},
}
TASK_DEMAND_DEFAULT: dict[str, float] = {
    "complexity": 0.5, "decision_weight": 0.5, "novelty": 0.5,
}
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
DELIVERY_URGENCY_MAP: dict[str, str] = {
    "green": "background",
    "yellow": "background",
    "orange": "toast",
    "red": "interrupt",
}
DEFAULT_DELIVERY_URGENCY = "background"  # Fallback for unknown zones

# --- Fit score ---
FIT_SCORE_MISMATCH_COMPONENTS = 3  # Number of demand components averaged for mismatch
