---
status: locked
version: 1
locked_date: 2026-03-20
source: Phase 2 Abstract Evolution (D7 synthesis)
measured_from: Monte Carlo 200-trial seed=42, pytest 537/537, wc -l 1599
---

# Tidewatch — Optimal Abstract (Locked Reference)

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
deadlines from being suppressed. We validate the framework with 537
deterministic and property-based tests—including 23 Hypothesis-driven
bounds-and-monotonicity checks—factor ablation, and Monte Carlo scheduling
simulations against earliest-deadline-first (EDF), FIFO, and random baselines.
Across workload scales (N=50, 200), Tidewatch eliminates queue inversions
entirely (0.0% vs. 10–13% for EDF) while maintaining comparable
missed-deadline rates; against naive baselines it reduces missed deadlines by
35–47%. The capacity-aware reranking stage is validated through property-based
tests and analytic checks; simulation-level evaluation remains future work. The
implementation comprises 1,599 lines of pure-stdlib Python with zero runtime
dependencies. All scoring functions ship with golden-value regression tests
verified to Delta < 10^-10, establishing deterministic reproducibility as a
first-class design constraint.

## Claim Provenance

| Claim | Source | Label |
|-------|--------|-------|
| 6 named factors | pressure.py:194-200, components.py:144-149 | VERIFIED |
| Late Collapse component space | components.py:33-63 | VERIFIED |
| Pareto-layered ranking | pressure.py:284-326 | VERIFIED |
| Weighted scalar aggregation | components.py collapsed property | VERIFIED |
| Physiological signals (sleep, pain, HRV) | types.py:157-216 | VERIFIED |
| Three-tier risk classification | types.py:15-29 (RiskTier enum) | VERIFIED |
| 537 tests | pytest --co → 537 collected | MEASURED |
| 23 property-based tests | pytest --co test_property_pressure.py → 23 | MEASURED |
| 0.0% vs 10-13% queue inversions | Monte Carlo N=50,200 seed=42 | MEASURED |
| 35-47% missed deadline reduction vs naive | Monte Carlo N=50,200 seed=42 | MEASURED |
| 1,599 lines | wc -l tidewatch/*.py | MEASURED |
| Delta < 10^-10 golden tests | test_golden_pipeline.py | VERIFIED |
| Zero runtime dependencies | stdlib-only in tidewatch/ | VERIFIED |
