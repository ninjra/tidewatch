## Verdict: DO NOT SHIP

### Claim 1 — Headline performance claim too strong
At N=200, Tidewatch: 0.201 missed vs EDF: 0.185 (+8.65% worse). Weighted-EDF: 0.186, also better. "Comparable" too aggressive at N=200. No equivalence margin, no hypothesis test.

### Claim 2 — Internal reporting failures
Table 5 lists 7 categories, text says "six." Strategy list names 8, tables show 7 rows (omit variable BW). Table 7 caption says "CIs in brackets" but no brackets rendered. Not cosmetic — erodes trust.

### Claim 3 — Evaluation confounded
Domain demand fixed by coarse profiles. Simulation durations domain-specific. Bandwidth benefit may be shorter/easier-task preference artifact. Weighted-EDF appears only at N=200, beats Tidewatch. Missing variable BW row means paper doesn't show full claimed strategy set.

### Claim 4 — Mathematical semantics underspecified
Paper criticizes additive MCDM, but weighted_collapse is explicitly a weighted sum. Saturation rate 9.0% identical across all strategies — not a discriminator. Ablation identity is algebraically true but semantically awkward.

### Claim 5 — Gameable formulas tied to wrong clock
Timing and violation decay use days-in-status, not days-since-event. Status change resets decay. Figure 2 crossover at b≈0.704 per Eq. 10, not ≈0.5 as plotted — figure mixes soft scoring with hard override.

### Claim 6 — Scope outruns validation
Paper includes Late Collapse, Pareto, bandwidth, planning, triage — evaluation covers only scalar pressure + MC ordering. Gravity term zeroed. Fallback backend is product-only. Should scope down to research note on heuristic pressure score.

### Recommendations
R1: Rewrite claims to match evidence
R2: Fix manuscript QA (counts, missing rows, CIs)
R3: Fairer baselines + real evidence
R4: Re-spec decay to event age, not status age
R5: Separate soft bandwidth from hard override in figures
R6: Add real task data or downgrade scope
