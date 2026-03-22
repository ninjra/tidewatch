## Red-Team Review (Paper-Level) — Analysis B

### 1) Core Model Validity
- Multiplicative structure fragile to calibration drift — no independence justification
- Saturation at P=1 creates information collapse, fallback is input-order tie-break
- Temporal functions (exponential, logistic, half-life) are unvalidated design choices — NO EVIDENCE

### 2) Deferred Scalarization
- System collapses via product for actual ranking in experiments — Pareto mode not evaluated
- Pareto ranking scalability unaddressed — NO EVIDENCE

### 3) Evaluation Weaknesses
- Simulation assumptions dominate (LogNormal, independent, single operator)
- Queue inversion rate defined relative to its own pressure function — biased metric
- Missing baselines: slack-based, LLF, critical-path-aware
- Capacity-aware improvement 20.1→19.5% (Δ=0.6%) — no significance test
- BW improvement could be noise at 200 trials

### 4) Internal Consistency
- "Objective pressure" contradicted by subjective inputs (materiality, completion%, deps)
- Factor independence assumed but violated (completion↔timing, deps↔deadlines)
- Ablation identity (all→P=1.0) semantically meaningless

### 5) Reproducibility vs Validity
- Strong determinism, weak external validity
- "Zero dependencies" limits integration — no scalability benchmark

### 6) Security
- Gaming vectors acknowledged but unresolved
- DoS via saturation flooding

### 7) Cognitive Bandwidth
- Unvalidated but used in simulation variants — inconsistent
- Arithmetic mean of heterogeneous signals naive — no weighting/calibration

### 8) Claims
- True contribution: interpretable multi-factor scoring, deterministic, auditable
- Overstated: "continuous obligation pressure" as novel (prior art exists), "deferred scalarization" as unique (standard in MCDM)

### Required Fixes
1. Anti-saturation ordering (preserve raw score above 1)
2. Statistical validation (CIs, significance tests)
3. Stronger baselines (LLF, slack-based)
4. Adversarial stress tests
5. Justify or learn parameters
