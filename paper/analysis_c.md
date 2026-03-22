THREAD: tidewatch-abstract-redteam

## Claim Classification
- "Binary signals" → INFERENCE (not universally true)
- "Six factors" → QUOTE (descriptive)
- "Late Collapse" → INFERENCE (novel, requires formal definition)
- "Capacity-aware reranking" → INFERENCE (needs validation dataset)
- "563 tests" → MEASURED (internal, needs reproducibility artifacts)
- Performance numbers → MEASURED (internal, needs CIs and distribution spec)
- "35-47% vs naive" → MEASURED (high sensitivity to baseline definition)
- "Delta < 10^-10" → MEASURED (needs environment spec)

## Critical Risks
A. Baseline framing bias — underperforms EDF at scale, risks "inferior to optimal" reading.
B. Missing experimental determinism details — no float model, seed handling, environment.
C. Simulation validity gap — no task/deadline/dependency distributions disclosed.
D. Capacity signal integration weak evidence — no dataset, no validation metric.
E. "Late Collapse" ambiguity — not formally defined (vector space? complexity class?).
F. Overprecision without uncertainty — exact % without CIs.

## Required Fixes
1. Reframe: multi-objective prioritization under human constraints, not better scheduler.
2. Add experimental specification (distributions, trials, seeds).
3. Qualify capacity claims (synthetic vs real signals).
4. Replace point estimates with intervals.
5. Formalize Late Collapse (6D vector, Pareto dominance, deferred scalarization).
6. Temper determinism claim (specify environment or weaken).

## Proposed Tightened Abstract
Provided a rewritten version with: explicit Late Collapse definition as "six-dimensional component space," Monte Carlo qualified with "controlled task and dependency distributions," EDF tradeoff framed as "reflecting the tradeoff between multi-factor prioritization and deadline-optimal scheduling," determinism qualified with "under fixed execution conditions."

Bottom line: technically strong, positioning invites rejection. Fix framing and disclosure.
