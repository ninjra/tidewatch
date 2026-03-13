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

# --- Zone thresholds ---
ZONE_YELLOW = 0.30
ZONE_ORANGE = 0.60
ZONE_RED = 0.80

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
