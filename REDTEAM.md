# REDTEAM.md — Drop-in Red Team & Remediation Protocol

**Usage:** Copy this file to any repo root as `REDTEAM.md`. Start a Claude Code session and say:  
`read REDTEAM.md, then execute PHASE 1 against this repo`

Phases are sequential. Do not skip. Each phase produces artifacts before the next begins.

---

## CONTEXT

This repo is one project in a constellation being published together. The bar is not "does it work" — the bar is "does a skeptical reviewer with domain expertise agree this is novel or demonstrably better, and does the code support every claim the paper makes." Anything that doesn't clear that bar is a liability to the entire constellation.

---

## PHASE 1: RECONNAISSANCE

**Goal:** Build a complete mental model before judging anything.

```
1. Read every file in the repo root: README, CLAUDE.md, IMPLEMENTATION.md, 
   NEXT_SESSION.md, CHANGELOG, LICENSE, pyproject.toml / Cargo.toml / package.json
2. Map the module dependency graph (which modules import what)
3. Read every source file in the core library (not tests, not scripts)
4. Read the paper (if present: paper/, docs/, .tex, .md)
5. Read every test file
6. Read benchmark scripts and results files
7. Read CI configuration
```

**Output:** Write `REDTEAM_RECON.md` to repo root with:

```markdown
# Recon Summary

## Claimed Contributions
[List each novelty claim from the paper/README, numbered]

## Architecture
[One-paragraph description of the pipeline/dataflow]

## Dependency Graph
[Which modules depend on which — text or mermaid]

## Constants & Hyperparameters
[Every tunable constant, its value, and where it's defined]

## Public API Surface
[Every public class/function with signature]

## Test Inventory
[Test count, coverage map: which modules have tests, which don't]

## Benchmark Inventory
[Which benchmarks exist, which have results, which are TODO]

## Paper-Code Interface
[Every equation/algorithm in the paper mapped to its code location]
```

Do NOT judge anything in Phase 1. Only observe and record.

---

## PHASE 2: RED TEAM AUDIT

**Goal:** Find everything that would cause a rejection, a bug in production, or an embarrassment in peer review.

For each item, assign severity:
- **P0 — Blocker:** Paper claim unsupported by code, math bug, data loss risk, or result that doesn't reproduce.
- **P1 — Critical:** Will fail in production or get flagged by a reviewer. Must fix before submission.
- **P2 — Significant:** Informed reviewer will note it. Should fix.
- **P3 — Minor:** Polish. Fix when convenient.

### 2A: Novelty & Contribution Audit

For each claimed contribution from Phase 1:

```
1. PRIOR ART CHECK: Search the web for the closest existing work. 
   Is this actually novel, or is it a known technique with new terminology?
   - If novel: state what specifically is new and why it matters
   - If incremental: state what the delta is over prior art and whether 
     the delta justifies a publication
   - If already done: state who did it, when, and how this differs (if at all)

2. ABLATION EVIDENCE: Does the repo include an ablation that isolates 
   this contribution's effect? If yes, does the ablation actually show 
   improvement? If the ablation shows no improvement or regression, flag P0.

3. CLAIM-EVIDENCE ALIGNMENT: For each specific numerical claim in the 
   paper/README, trace it to the code that produced it. Can the result 
   be reproduced from the committed code + data? If not, flag P0.
```

### 2B: Paper-Code Consistency Audit

```
For every equation, algorithm, constant, and architectural claim in the paper:
1. Find the corresponding code
2. Verify they match EXACTLY (not approximately, not "in spirit")
3. For every mismatch: record paper value, code value, and which is correct
4. For every constant: verify paper value matches constants file
```

### 2C: Correctness Audit

```
For each core module:
1. EDGE CASES: What happens at boundary values? (zero, negative, inf, NaN, 
   empty input, single element, maximum size)
2. NUMERICAL STABILITY: Any division that can produce inf/NaN? Any 
   subtraction of nearly-equal floats? Any exp/log of extreme values?
3. DETERMINISM: Same input → same output? Any hidden state, global 
   mutation, or order-dependent behavior?
4. SILENT FAILURES: Any code path that silently produces wrong results 
   rather than raising an error?
```

### 2D: Test Audit

```
1. Which modules have zero test coverage?
2. Which edge cases from 2C are untested?
3. Are tests actually testing the right thing? (Look for tests that 
   always pass regardless of implementation — tautological tests)
4. Do tests match paper claims? (If paper says "F increases monotonically 
   with mass," is there a test for monotonicity?)
```

### 2E: Benchmark Audit

```
1. Is the benchmark synthetic or external? If synthetic, was it designed 
   to favor this system? (circular validation)
2. Are baselines implemented correctly? (Common flaw: strawman baselines 
   that are deliberately weakened)
3. Are baselines using the same embeddings, same preprocessing, same 
   evaluation protocol?
4. Are results statistically significant? (Variance, confidence intervals, 
   multiple runs)
5. What's the computational cost comparison? (A 2% improvement at 100x 
   cost is not publishable)
```

### 2F: Production Readiness Audit

```
1. Input validation: Can malformed input cause crashes or wrong results?
2. Logging: Is there any diagnostic output for debugging production issues?
3. Thread safety: Is concurrent use safe?
4. Error messages: Are failures diagnosable from the error alone?
5. API stability: Are public surfaces documented and versioned?
```

**Output:** Write `REDTEAM_AUDIT.md` to repo root with every finding, severity-tagged, organized by section. Include a priority matrix at the end.

---

## PHASE 3: HONEST ASSESSMENT

**Goal:** Answer the hard question before investing in fixes.

**Output:** Append to `REDTEAM_AUDIT.md` a section titled `## Publication Viability` that answers:

```
### For each claimed contribution:
- Is it novel? [YES / INCREMENTAL / NO]
- Is it empirically validated? [YES / PARTIAL / NO]  
- Does the code support the claim? [YES / MISMATCH / NO]
- Would removing this contribution weaken the constellation? [YES / NO]

### Overall verdict:
- PUBLISH AS-IS: Claims are supported, novel, and empirically validated.
- PUBLISH AFTER FIXES: Core contribution is sound but P0/P1 issues 
  must be resolved. List the fixes.
- RETHINK SCOPE: Some contributions are valid but others are not. 
  Recommend which to keep and which to cut.
- DO NOT PUBLISH: The core claim is not supported by evidence, or 
  the contribution is not novel enough to justify a paper.

### Constellation impact:
- Does this repo strengthen or weaken the constellation as a whole?
- Which other repos in the constellation does this one depend on or 
  support?
- If this repo were cut, what would be lost?
```

Be brutally honest. A weak paper in the constellation damages all papers in the constellation.

---

## PHASE 4: REMEDIATION

**Goal:** Fix every P0 and P1 issue. Implement, don't advise.

### Rules

1. **Fix code, not just comments.** If the paper and code disagree, fix one of them (prefer fixing the paper to match correct code; prefer fixing code to match correct paper equations).

2. **Every fix gets a test.** No fix is complete without a test that would have caught the original issue. Add tests to existing test files following existing patterns.

3. **Paper fixes go in a diff block.** For LaTeX/markdown paper changes, output the complete replacement text for the affected section. Not a description of what to change — the actual text.

4. **Constants audit produces a reconciliation table.** Output a markdown table: `| Name | Paper Value | Code Value | Correct Value | Action |`

5. **Run tests after every fix batch.** `python -m pytest tests/ -q --tb=short` (or equivalent). If tests fail, fix them before proceeding.

6. **Run linter after every fix batch.** `ruff check` / `cargo clippy` / `eslint` as appropriate.

7. **Do not change public API signatures** unless the fix requires it and you document the breaking change.

8. **Commit message format:** `fix(redteam): P{severity} {section}.{number} — {one-line description}`

### Execution Order

```
1. Fix all P0 items (blockers)
2. Run full test suite — must pass
3. Fix all P1 items (critical)
4. Run full test suite — must pass
5. Write new tests for all edge cases identified in 2C/2D
6. Run full test suite — must pass
7. Update IMPLEMENTATION.md / frozen surfaces if any API changed
8. Update paper sections affected by fixes
9. Re-run benchmarks if any scoring logic changed
10. Write REDTEAM_REMEDIATION.md summarizing all changes
```

---

## PHASE 5: VALIDATION

**Goal:** Confirm the repo is release-ready.

```
1. Re-run Phase 2 sections A, B, C against the fixed codebase
2. Verify all P0 findings are resolved
3. Verify all P1 findings are resolved
4. Run full test suite one final time
5. Run full benchmark suite and compare results to pre-fix baselines
6. If any benchmark result changed by more than 1%, document why
```

**Output:** Write `REDTEAM_VALIDATION.md` with:

```markdown
# Validation Report

## P0 Resolution
[For each P0: original finding → fix applied → test added → status RESOLVED/OPEN]

## P1 Resolution  
[Same format]

## Test Suite
- Tests before: N
- Tests after: M
- All passing: YES/NO

## Benchmark Comparison
| Metric | Before | After | Delta | Explanation |
|--------|--------|-------|-------|-------------|

## Remaining P2/P3
[List with recommended priority for next session]

## Final Verdict
[READY FOR PUBLICATION / NEEDS ANOTHER PASS / see specific items]
```

---

## ANTI-PATTERNS — DO NOT DO THESE

- **Do not rubber-stamp.** "Looks good" is not a finding. Every module gets scrutinized.
- **Do not soften findings.** If the core contribution isn't novel, say so. Intellectual honesty is the entire point.
- **Do not defer research.** If you need to check whether a technique is novel, search the web now. Do not say "the author should verify."
- **Do not fix P2/P3 before all P0/P1 are resolved.** Severity order is strict.
- **Do not change the architecture.** Red team finds bugs and mismatches. It does not redesign the system. If the architecture is fundamentally flawed, say so in Phase 3 and stop.
- **Do not generate partial fixes.** Every code change is complete and paste-ready. Every paper change is the full replacement text. No "change X to Y" instructions.
- **Do not skip the test.** Every fix gets a test. No exceptions.
- **Do not conflate "I don't understand it" with "it's wrong."** Physics metaphors, unusual algorithms, and domain-specific patterns are not bugs. Only flag things that are actually incorrect, unsupported, or misleading.

---

## SESSION MANAGEMENT

At session start:
```
Read REDTEAM.md. State which phase you are beginning and which repo this is.
```

At session end (or if context is getting long):
```
Write REDTEAM_CHECKPOINT.md with:
- Current phase and step
- Findings so far
- Files modified
- What remains
```

Next session picks up from the checkpoint.

---

## CALIBRATION

This prompt was developed against the Gravitas repo (physics-inspired memory retrieval) where it identified:
- 3 P0 blockers (paper-code constant mismatches, light cone edge case, equation disagreement)
- 11 P1 criticals (missing benchmark, NaN propagation, duplicated logic, no input validation, no logging)
- Multiple P2/P3 items

The bar is: **would a senior researcher reviewing this for a top venue accept it?** If no, the finding is at least P1.
