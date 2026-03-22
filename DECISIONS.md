# DECISIONS.md — Large-N Scaling Resolutions

Design choices made during implementation that were not fully specified in the task.

## Problem 1 — Adaptive k

**Decision**: k is clamped to [1.0, 50.0] (ADAPTIVE_K_MIN, ADAPTIVE_K_MAX).
**Rationale**: k < 1.0 produces a nearly flat curve (no discrimination), and
k > 50.0 produces an absurdly steep curve. The clamps prevent degenerate behavior
at extreme median deadline values without affecting normal use (median 1–140 days).

**Decision**: When median_days <= 0 (all overdue), adaptive k falls back to
RATE_CONSTANT (3.0) rather than computing from the formula.
**Rationale**: log(1 - 0.30) is negative, so negative median would yield a positive k
from the formula, but the semantic meaning is wrong — all-overdue populations don't
need k tuning.

## Problem 2 — Rank Normalization

**Decision**: Rank normalization replaces component values with rank/(N-1) and
rebuilds the ComponentSpace. Raw values are preserved in `raw_inputs["raw_components"]`.
**Rationale**: The product collapse of ranked values naturally spreads across [0,1]
because each component is uniformly distributed in [0,1] by construction. This is
simpler and more interpretable than alternatives like z-score normalization.

**Decision**: For N=1, all ranks default to 0.5.
**Rationale**: A single item has no ranking context. 0.5 is the neutral midpoint.

## Problem 3 — Incremental Recalculation

**Decision**: Input hash uses MD5 (usedforsecurity=False) of the concatenated string
representations of all mutable scoring fields.
**Rationale**: MD5 is fast and collision-resistant enough for change detection (not
security). Python's hashlib provides it in stdlib. The `usedforsecurity=False` flag
is required on FIPS-compliant systems.

**Decision**: Dependency graph propagation for staleness (rescoring items whose
dependencies changed) is not implemented.
**Rationale**: Tracking dependency graphs would require either a runtime dependency
(graph library) or maintaining adjacency lists in the scoring engine, which violates
the "zero runtime dependencies, pure math" constraint. The caller can achieve this
by including dependent obligations in the staleness check or by using full batch
recalculation when dependency structures change.

## Problem 4 — Pareto Budget

**Decision**: Added an optimization to `_find_pareto_front` that probes whether the
backend supports dominance comparison. If the first probe returns None (fallback
backend), all items are returned as the front without O(N^2) comparisons.
**Rationale**: The fallback ComponentSpace always returns None from dominates(),
making every item incomparable. Without this optimization, the probe loop still
runs O(N^2) comparisons that all return None. The probe detects this case in O(1).

## Problem 5 — Zone Capacity

**Decision**: Zone demotion cascades top-down (red → orange → yellow → green).
If red overflow pushes items to orange, and orange then exceeds capacity, those
items cascade to yellow.
**Rationale**: Without cascading, a single over-capacity zone could push all its
overflow into the next zone, making that zone meaninglessly large. Cascading
distributes the load evenly across zones.

**Decision**: Green zone has no demotion target and acts as a sink.
**Rationale**: Green is the lowest severity zone. Demoting below green is undefined
in the zone model.

## Problem 6 — Dependency Cap

**Decision**: The log_scaled formula is `cap = max(20, ceil(log2(N) * 5))`.
**Rationale**: log2 grows slowly enough to prevent unbounded caps while still
scaling with population size. The factor of 5 was chosen to produce reasonable
caps at key N values: N=50→29, N=10K→67, N=39K→77. The floor of 20 ensures
log_scaled mode is never less restrictive than fixed mode at small N.
