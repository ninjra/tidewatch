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

# ── SOB generation defaults ──
DEFAULT_N = 1000
DEFAULT_SEED = 42
DEFAULT_OUTPUT = "sob.json"
JSON_INDENT = 2
