**THREAD: D1 — Tidewatch Red Team Review**

## Mathematical & Formal Issues

**1. Saturation ceiling destroys discriminability at the critical end.** The `min(1, ·)` bound is presented as a feature but it's an information-loss boundary that bites exactly when discrimination matters most. At N=200, 9% saturation rate means ~18 obligations are indistinguishable at the top. Late Collapse "preserves the raw product" escape hatch is noted but never evaluated — none of the MC runs use unclamped product ranking.

**2. Zero-propagation problem.** If any single factor approaches zero, the entire product collapses. A 51%-complete material obligation due tomorrow with 10 dependents gets D≈0.70, losing 30% of its pressure from a single factor. No ablation result addresses compound cross-factor interaction pathologies.

**3. Violation decay keyed to days-in-status, not days-since-violation.** If an obligation is violated then the operator changes its status (resetting d to 0), the full violation effect reactivates. Status changes reset the loop.

**4. kf=2.0 justification is intuitive, not empirical.** No sensitivity analysis for kf. The choice could be wrong by a factor of 2.

**5. Bandwidth floor of 0.2 is arbitrary and the fail-safe default of 0.8 is contradictory.** 0.8 is close to full capacity — "conservative" would mean lower b, not higher. b=0.2 floor: why 20%?

**6. MC structurally biased — inversion rate still in main table.** Paper acknowledges it's self-referential but still reports it as a comparison metric.

**7. Single-operator sequential model is unrealistic.** No context-switching cost, no partial progress.

**8. N=50 and N=200 are both small-scale.** No scaling analysis.

**9. Table 6 (N=50) has no CIs but Table 7 (N=200) does.** Inconsistent.

**10. 35-47% improvement is against straw-man baselines.** The meaningful comparison is Tidewatch vs EDF where Tidewatch loses at N=200.

**11. No real-world validation.** Zero user studies, zero deployment data.

**12. Cognitive bandwidth is aspirational, not validated.** Title claims it as co-equal contribution but evidence is a simulation with a single scalar.

**13. "Interpretable" factors — never tested for interpretability.**

**14. Determinism applies to pressure engine only**, not bandwidth (noisy signals) or planner (LLM outputs).

**15. Domain demand profiles (Table 2) have no sourcing.** Free parameters disguised as constants.

**16. Binary materiality multiplier contradicts continuous-framework thesis.**

**17. No multi-operator model.**

**18. Triage queue statelessness is a liability.**

**19. Speculative planner is underspecified.**

**20. Abstract buries key negative result.** EDF: 18.5% vs Tidewatch: 20.1% at N=200.

**21. Line count repeated 3 times.**

**22. Related work positions against LLM planners — asymmetric comparison.** Should compare against ICE/RICE, WSJF, Eisenhower.

**23. Gravity tiebreak term shouldn't be in the equation at all.** Placeholder that defaults to zero.

**24. Adversarial input gaming.** ndeps=20 cap, materiality=material, completion=0% = manufactured max pressure.

**25. Temporal gaming of bandwidth.** Underreport sleep/HRV to avoid complex work.

**26. No recalibration mechanism for drifting baselines.**
