THREAD: Tidewatch abstract red team | D0: 2026-03-21

## Findings

1. EDF comparison framing is self-undermining — reporting a loss at N=200 and calling it a feature. Reframe: Tidewatch competes on operator sustainability and multi-objective scheduling, not deadline minimization.
2. "563 tests" is a process claim, not validity. Lead with what tests establish.
3. Monte Carlo methodology underspecified — no trial count, no CI, no distribution assumptions.
4. Physiological signal integration asserted but not validated — design contribution not result.
5. 35-47% against naive baselines is the wrong comparison — FIFO/Random not credible.
6. N=50 vs N=200 split unjustified mechanically.
7. "Operator" undefined.
8. Venue fit unresolvable — abstract spans scheduling, SE, HCI, and productivity.
9. Delta < 10^-10 unscoped to platform/environment.
10. "Logistic completion dampening" and "timing-sensitivity amplification" are invented terms without definition.
11. "Prevents perverse feedback loops" is informal and unsupported.

Highest risk: reviewer reads "loses to EDF at scale, physiological signals unvalidated" → rejection. Core contribution (interpretable, capacity-aware, multi-objective ranking with Late Collapse) is strong but buried.
