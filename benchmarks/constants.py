# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Constants for benchmark metrics and runners.

Benchmark-specific constants. Domain-bounded and formula-specific values
that control metric computation and benchmark execution.
"""

# ── Spearman rank correlation (§4.1) ──
# Formula: ρ = 1 - 6Σd²/(n(n²-1))
# The coefficient 6 and exponent 2 are fixed by the mathematical definition
# of Spearman's rank correlation coefficient, not tunable parameters.
SPEARMAN_COEFFICIENT = 6.0
SPEARMAN_EXPONENT = 2
MIN_RANKS_FOR_CORRELATION = 2

# ── Eisenhower baseline ──
EISENHOWER_URGENT_THRESHOLD_DAYS = 7.0
EISENHOWER_Q2_SCORE = 0.5   # Not urgent + important
EISENHOWER_Q3_SCORE = 0.75  # Urgent + not important

# ── SOB generation defaults ──
DEFAULT_N = 1000
DEFAULT_SEED = 42
DEFAULT_OUTPUT = "sob.json"
JSON_INDENT = 2

# ── Monte Carlo simulation parameters ──
# Standard single-operator workday — models serial attention constraint
HOURS_PER_DAY = 8.0
# SI definition: 60 min × 60 sec — physical constant, NOT tunable
SECONDS_PER_HOUR = 3600.0
# Monte Carlo replications; convergence verified at N≥100 (§4.4)
DEFAULT_TRIALS = 200
# Numerical guard: prevents log(0) in lognormal when sigma→0
SIGMA_FLOOR = 1e-10

# ── Monte Carlo simulation thresholds ──
# Pressure ≥ this is effectively at the [0,1] ceiling after floating-point rounding
SATURATION_THRESHOLD = 0.999
# Floating-point epsilon for inversion detection — noise below this is not meaningful
INVERSION_EPSILON = 1e-10
# Bootstrap CI requires ≥ this many trials for stable percentile estimates
CI_MIN_TRIALS = 10

# ── Bootstrap CI ──
# Standard significance level for 95% confidence intervals (1 - alpha = 0.95)
# This is the universal default in frequentist statistics, not a tunable parameter.
BOOTSTRAP_CI_ALPHA = 0.05

# ── Display formatting ──
# Decimal places for metrics in JSON/table output — 4 digits matches paper table precision
METRIC_DISPLAY_PRECISION = 4

# ── Paper generation ──
# Fixed simulation start for reproducibility — all paper results reference this date
PAPER_SIM_START_YEAR = 2026
PAPER_SIM_START_MONTH = 6
PAPER_SIM_START_DAY = 1
PAPER_SIM_START_HOUR = 12
# Default N for paper results — small enough for quick iteration
PAPER_DEFAULT_N = 50
