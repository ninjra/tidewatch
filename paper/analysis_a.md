## A

THREAD: redteam
CHAT_ID: not exposed
Source: uploaded PDF

## B

* **Verdict:** not ready as an empirical-superiority paper. It is closer to a deterministic systems/design note. The paper itself says Tidewatch does not beat EDF on raw deadline compliance and lists material limitations.
* **Primary attack:** the inversion headline is endogenous. Tidewatch sorts by pressure descending, and the discussion says zero inversions are a structural consequence of that ordering. That makes inversion reduction weak as independent validation.
* **External-validity gap:** the evidence is simulation-only, constants were tuned for one operator, demand estimation is heuristic, and intra-trial capacity variation is deferred to future work.
* **Consistency bug:** Eq. 10 is linear in bandwidth, but the rendered Figure 2 in the uploaded PDF shows a step near `b≈0.5`. As written, the paper does not explain that discontinuity.
* **Baseline weakness:** the collapse-method comparison is mostly against equal-weight weighted sum; Pareto ranking is presented as core, but not directly validated in the outcome results shown.
* **Safety gap:** physiological reranking is central to the pitch, but the paper shows no consent, audit, override, gaming, or harm analysis.

## C

**Key claim 1**
QUOTE: *"eliminates queue inversions entirely"*. CITE:
MEASURED: Table 6 shows Tidewatch at `0.000 ± 0.000` inversions versus EDF at `0.134 ± 0.000` for the displayed `N=50` results, and the discussion frames that as a structural consequence of pressure ordering.
INFERENCE: this is not a strong outcome win; it is mostly a property of the ranking rule.
NO EVIDENCE: the paper does not show that lower inversion rate predicts deadline success, operator value, or user satisfaction.

**Key claim 2**
QUOTE: *"trails by 9% at N=200"*. CITE:
MEASURED: the displayed table is labeled `N=50`, while the `N=200` result appears only in prose.
INFERENCE: the abstract's comparable-missed-deadline framing is weaker than it first appears because the paper does not show a full `N=200` table alongside the claim.
NO EVIDENCE: no visible `N=200` table, interval, or per-strategy breakdown is provided in the paper pages I inspected.

**Key claim 3**
QUOTE: none. CITE:
MEASURED: Eq. 10 implies linear dependence on bandwidth. Using the figure's own labels, the stated formula gives legal-brief fit scores of `0.10, 0.55, 1.00` and config-update scores of `0.624, 0.702, 0.78` at `b = 0, 0.5, 1.0`. The rendered Figure 2 shows a visible step near `b≈0.5` instead of a continuous line.
INFERENCE: either Figure 2 is wrong, Eq. 10 is incomplete, or an unstated piecewise rule exists.
NO EVIDENCE: Sec. 3.5 and the constants table do not state such a rule.

**Key claim 4**
QUOTE: none. CITE:
MEASURED: weighted-sum is reported at `0.082` missed deadlines versus `0.067` for product collapse, but the additive baseline uses equal weights only; Pareto-layered ranking is described yet not shown in the outcome table.
INFERENCE: the baseline suite is too weak to justify a broad claim that product collapse is the right reduction method.
NO EVIDENCE: there is no tuned weighted-sum baseline, learned weights, utility-based baseline, or direct Pareto-outcome comparison.

**Key claim 5**
QUOTE: *"541 deterministic and property-based tests"*. CITE:
MEASURED: the paper documents deterministic tests, property tests, and golden-value tolerances below `1e-10`.
INFERENCE: this is strong evidence of implementation correctness and reproducibility. It is not evidence of real-world prioritization quality.
NO EVIDENCE: no field trial, external task-trace evaluation, or human-subject study is presented.

**Key claim 6**
QUOTE: *"three-tier risk classification"*. CITE:
MEASURED: the reranker can use sleep quality, HRV trend, pain level, medication window, violation rate, constraint pressure, and session load, with fail-open behavior when no signals are present.
INFERENCE: the deployment risk is not just model quality; it is also safety, privacy, adversarial manipulation, and governance of overrides.
NO EVIDENCE: the paper provides no consent model, override audit design, false-negative analysis, or harm-case analysis.

## D

**R1**
improved: replace inversion as the headline metric with an external objective such as deadline loss, weighted lateness, regret, human choice agreement, or downstream utility.
risked: the current headline advantage may shrink or disappear.
enforcement_location: Abstract, Table 6, Sec. 5.3, Discussion.
regression_detection: if a headline metric can be guaranteed by construction under Tidewatch's own ordering rule, DO NOT SHIP that framing.

**R2**
improved: show full `N=200` results, multiple random seeds, and uncertainty for every strategy.
risked: exposes variance and possibly weaker performance.
enforcement_location: Table 6, Sec. 5.3, appendix.
regression_detection: if `N=200` remains prose-only or single-seed-only, DO NOT SHIP the across-workload-scale claim.

**R3**
improved: reconcile Eq. 10, the constants table, and Figure 2 so one deterministic implementation reproduces the plotted curves.
risked: the bandwidth narrative or thresholds may need to change.
enforcement_location: Sec. 3.5, Table 1, Figure 2.
regression_detection: recompute the plotted anchor points from the published formula; if the figure disagrees, DO NOT SHIP.

**R4**
improved: directly evaluate Pareto layering and stronger baselines, including tuned additive collapse and utility-based alternatives.
risked: the novelty story around Late Collapse may narrow.
enforcement_location: Sec. 3.2, Sec. 5.3, Conclusion.
regression_detection: if Late Collapse stays a core contribution without outcome evidence, DO NOT SHIP that claim.

**R5**
improved: add a deployment-safety section for physiological reranking: consent, override precedence, audit logging, calibration drift, and misuse/failure modes.
risked: may constrain where the system can be safely deployed.
enforcement_location: Sec. 3.5, Limitations, Conclusion.
regression_detection: absent opt-in, override, and failure analysis, DO NOT SHIP any production-readiness framing.

ANY_REGRESS => DO NOT SHIP.

## E

DETERMINISM: PARTIAL(scoped).
VERIFIED: the paper's stated formulas, constants, displayed `N=50` table, and deterministic-test counts are internally inspectable and reproducible from the document.
PARTIAL(scoped): the `N=200` performance claim is asserted in prose but not fully displayed, so the across-scale conclusion is only partially substantiated in the paper itself.
FAILED: external efficacy and safe physiological deployment are not validated by the current evidence package.

## F

TS: 2026-03-20

THREAD=redteam | CHAT_ID=not exposed | TS=2026-03-20
