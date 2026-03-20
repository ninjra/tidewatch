---
status: locked
version: 2
locked_date: 2026-03-20
source: Phase 2 Abstract Evolution (D7 synthesis) + Gap resolution (D20)
measured_from: Monte Carlo 200-trial seed=42 (8 strategies), pytest 540/540, wc -l 1599
supersedes: abstract_optimal_v1.md
changes_from_v1:
  - "537 tests" → "540 tests" (3 golden 6-factor scenarios added)
  - "simulation-level evaluation remains future work" → replaced with measured bandwidth MC results
  - Added MCDM weighted-sum comparison result (product collapse wins by 23%)
---

# Tidewatch — Optimal Abstract v2 (Locked Reference)

Conventional task managers expose deadlines as binary signals—overdue or
not—discarding the continuous accumulation of risk as due dates approach and
ignoring whether the operator's current capacity permits execution of
high-demand work. We present Tidewatch, a task-prioritization framework that
decomposes urgency into six interpretable, multiplicative factors: exponential
time-decay, materiality weighting, temporally gated dependency fanout, logistic
completion dampening, timing-sensitivity amplification, and deadline-violation
amplification. Rather than collapsing these factors into a scalar immediately,
Tidewatch preserves them in a Late Collapse component space that supports both
weighted scalar aggregation and Pareto-layered ranking without premature
scalarization. An optional capacity-aware reranking stage integrates
self-reported or wearable-derived physiological signals (sleep quality, pain
level, HRV trend) to surface lower-demand tasks when operator bandwidth is
reduced, governed by a three-tier risk classification that prevents binding
deadlines from being suppressed. We validate the framework with 540
deterministic and property-based tests—including 23 Hypothesis-driven
bounds-and-monotonicity checks—factor ablation, and Monte Carlo scheduling
simulations against earliest-deadline-first (EDF), FIFO, and random baselines.
Across workload scales (N=50, 200), Tidewatch eliminates queue inversions
entirely (0.0% vs. 10–13% for EDF) while maintaining comparable
missed-deadline rates; against naive baselines it reduces missed deadlines by
35–47%. Under simulation, bandwidth reranking at reduced capacity (b=0.5)
slightly improves deadline compliance, and product collapse outperforms
weighted-sum MCDM by 23% on missed deadlines. The implementation comprises
1,599 lines of pure-stdlib Python with zero runtime dependencies. All scoring
functions ship with golden-value regression tests verified to
Delta < 10^-10, establishing deterministic reproducibility as a first-class
design constraint.

## Claim Provenance

| Claim | Source | Label |
|-------|--------|-------|
| 6 named factors | pressure.py:194-200, components.py:144-149 | VERIFIED |
| Late Collapse component space | components.py:33-63 | VERIFIED |
| Pareto-layered ranking | pressure.py:284-326 | VERIFIED |
| Weighted scalar aggregation | components.py collapsed property | VERIFIED |
| Physiological signals (sleep, pain, HRV) | types.py:157-216 | VERIFIED |
| Three-tier risk classification | types.py:15-29 (RiskTier enum) | VERIFIED |
| 540 tests | pytest -q → 540 passed | MEASURED |
| 23 property-based tests | pytest --co test_property_pressure.py → 23 | MEASURED |
| 0.0% vs 10-13% queue inversions | Monte Carlo N=50,200 seed=42 | MEASURED |
| 35-47% missed deadline reduction vs naive | Monte Carlo N=50,200 seed=42 | MEASURED |
| BW b=0.5 improves compliance | Monte Carlo N=50 seed=42 (0.064 vs 0.067) | MEASURED |
| Product collapse beats weighted-sum by 23% | Monte Carlo N=50 seed=42 (0.067 vs 0.082) | MEASURED |
| 1,599 lines | wc -l tidewatch/*.py | MEASURED |
| Delta < 10^-10 golden tests | test_golden_pipeline.py (14 scenarios) | VERIFIED |
| Zero runtime dependencies | stdlib-only in tidewatch/ | VERIFIED |
