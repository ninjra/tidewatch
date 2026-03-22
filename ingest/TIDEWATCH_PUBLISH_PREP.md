# TIDEWATCH PUBLISH PREP — Repo Analysis & Claude Code Prompt

**Generated:** 2026-03-21
**Ingested:** 2026-03-22 — loaded as 15 obligations (#1358–#1372)
**Purpose:** Analyze top GitHub repos for visibility/monetization patterns, synthesize into actionable Claude Code prompt for Tidewatch public release.

**Current state (post-ingest):**
- Tests: 659 (not 563 as doc says)
- Version: 0.4.4 (not 0.1.0)
- Framing: agent orchestration substrate (not task manager)
- Terminology: deferred scalarization (not Late Collapse)
- LICENSE: exists (Apache-2.0 dual, not MIT as doc suggests)
- .gitignore: exists (needs completeness check)
- CI: remediation-gates.yml exists (needs matrix + coverage)
- GitHub org: ninjra (not infoil as doc suggests)

---

## TOP 10 REPO ANALYSIS

Selected for excellence across different dimensions of repo presentation relevant to a mid-scale Python library with an academic paper.

| # | Repo | Stars | Key Strength | What Tidewatch Should Steal |
|---|------|-------|--------------|---------------------------|
| 1 | **astral-sh/ruff** | 46.6k | Speed benchmarks + social proof quotes from named devs at named companies. Terminal GIF. One-liner description. | Benchmark table (vs EDF/FIFO). Named testimonial pattern. "Ruff is so fast I thought it wasn't running" → adapt for Tidewatch's determinism story. |
| 2 | **fastapi/fastapi** | 80k+ | Badge row → one-liner → bullet feature list → 5-line quick start → social proof from Netflix/Uber/Microsoft. Docs site link prominent. | Feature bullet pattern: ✅ emoji + bold problem + brief explanation. Quick-start code block. "Used by" section (even if self-use initially — cite the paper). |
| 3 | **pydantic/pydantic** | 22k+ | Minimal README: badges → one paragraph → code example → install → done. Lets the code speak. Ecosystem cross-links (Logfire, pydantic-ai). | Brevity. Tidewatch README is currently overwritten from red-team iterations. Strip to essentials. Cross-link Sentinel/Gravitas constellation. |
| 4 | **fastapi/typer** | 16k+ | Family branding ("FastAPI's little sibling"). Terminal session GIF showing actual CLI interaction. Minimal deps highlighted. | "Part of the Sentinel constellation" branding. Show actual `tidewatch score` or `tidewatch rank` CLI output if applicable. |
| 5 | **Textualize/rich** | 50k+ | Visual-first: README is a gallery of screenshots showing what Rich renders. Every feature has a visual. | Tidewatch needs at least ONE visual — a scoring heatmap, a ranked obligation list, or a factor decomposition chart. SVG or PNG in README. |
| 6 | **pola-rs/polars** | 30k+ | Performance comparison table with exact numbers and methodology. Clear "Getting Started" across multiple languages. API reference link. | Monte Carlo results table directly in README. Methodology footnote. Link to paper for full evaluation. |
| 7 | **ollama/ollama** | 120k+ | Extreme simplicity: `ollama run llama3` in 3 lines. Model table. Zero friction install. | Tidewatch install must be `pip install tidewatch` → `from tidewatch import score_obligation` → done. If it's not this simple, simplify. |
| 8 | **maybe-finance/maybe** | 35k+ | Niche clarity: "The OS for your personal finances." Problem statement is the first thing you see. Self-hosting focused. | Tidewatch one-liner needs to be this clear. Not "multi-objective task-prioritization framework" — something a human would say. |
| 9 | **ScrapeGraphAI** | 15k+ | Explicit monetization strategy: open core → sponsors → premium features. FUNDING.yml + GitHub Sponsors + sponsor tier design. Blog post documenting the journey. | FUNDING.yml from day one. GitHub Sponsors profile. "Sponsorware" pattern for future premium features (e.g., Sentinel integration). |
| 10 | **calcom/cal.com** | 34k+ | Open core exemplar: fully functional OSS + hosted version for revenue. CITATION-like attribution. Sponsor logos in README. Contributing guide. | Open core model: Tidewatch OSS + "Tidewatch Cloud" or "Sentinel-integrated Tidewatch" as premium. Sponsor display section in README even if empty initially. |

---

## SYNTHESIZED PATTERNS — What the Top Repos All Share

### README Structure (in order)

1. **Badge row** (4-7 badges max): CI status, coverage %, PyPI version, Python versions, license, paper DOI
2. **One-liner** (≤15 words): What it does, not what it is
3. **Hero visual**: GIF, screenshot, or diagram — NOT a wall of text
4. **"Why This?" bullets** (3-5): ✅ emoji + bold problem + one sentence
5. **Quick Start**: ≤5 lines from install to first result
6. **Benchmark/Comparison table**: Numbers with methodology citation
7. **Architecture diagram or factor decomposition** (for technical repos)
8. **Documentation links**: API docs, paper, tutorials
9. **Contributing guide link**
10. **License + Citation + Sponsors**

### Monetization Infrastructure

- `.github/FUNDING.yml` — enables the Sponsor button on day one
- `CITATION.cff` — machine-readable citation for the paper (required for academic impact)
- GitHub Sponsors profile with tiered sponsorship
- "Sponsors" section in README (even if empty — signals intent)
- Open core licensing consideration (MIT core + commercial add-ons)

### CI/CD & Quality Signals

- GitHub Actions CI badge that actually runs tests
- Coverage badge (actual %, not placeholder)
- Pre-commit hooks documented
- `pyproject.toml` as single source of truth (no setup.py/setup.cfg)
- Reproducible install: `pip install tidewatch` or `uv add tidewatch`

### Repo Hygiene

- `LICENSE` (MIT for maximum adoption)
- `CHANGELOG.md` (keep-a-changelog format)
- `CONTRIBUTING.md`
- `.gitignore` (Python template)
- `py.typed` marker (PEP 561)
- Properly scoped `pyproject.toml` with `[project]`, `[project.optional-dependencies]`, `[tool.pytest]`, `[tool.ruff]`

---

## CURRENT TIDEWATCH STATE (INTERNAL — post-remediation)

Based on the 3 red-team sessions (D0: 2026-03-20 through D0: 2026-03-21):

- 6-factor Late Collapse scoring with Pareto-layered ranking
- Monte Carlo evaluation vs EDF, weighted-EDF, FIFO, Random baselines
- 563 deterministic + property-based tests (23 Hypothesis)
- 3-tier bandwidth risk classification
- Factor ablation analysis
- Python 3.11+ stdlib-only dependencies
- Paper abstract iterated through 3 adversarial red-team passes

**Gaps for public release** (INFERENCE — not verified against actual repo):
- README likely still in internal/development state
- No CI/CD pipeline (GitHub Actions)
- No FUNDING.yml or CITATION.cff
- No PyPI packaging (`pyproject.toml` may need `[build-system]` and `[project]` sections)
- No badges
- No visual/diagram in README
- No CHANGELOG.md or CONTRIBUTING.md
- No pre-commit configuration
- No `py.typed` marker
- Paper-repo alignment not verified post-remediation

---

## CLAUDE CODE PROMPT

```
TASK: Prepare the Tidewatch repository for public release and paper publication.
All work in ~/projects/tidewatch.

CONTEXT: Tidewatch is a multi-objective task-prioritization framework with a
Late Collapse scoring architecture, Monte Carlo evaluation, and an academic
paper. The repo has been through a major remediation pass (15 findings from 3
red-team sessions). It now needs to be publication-ready: polished for public
GitHub visibility, monetization infrastructure, and paper-repo alignment.

This prompt has FOUR PHASES. Execute them in order. Do not skip phases.

========================================================================
PHASE 1 — RECON (read-only, no changes)
========================================================================

Before touching anything, measure the current state:

1. Read the current README.md completely. Note its length, structure, and
   whether it matches the post-remediation abstract.

2. Inventory all top-level files: LICENSE, CHANGELOG, CONTRIBUTING, CITATION,
   pyproject.toml, .github/ directory, .pre-commit-config.yaml, py.typed,
   setup.py, setup.cfg, Makefile, etc.

3. Read pyproject.toml completely. Note:
   - Does [build-system] exist?
   - Does [project] exist with name, version, description, authors, license,
     requires-python, classifiers, urls?
   - Does [project.optional-dependencies] exist?
   - Are tool configs ([tool.pytest.ini_options], [tool.ruff], etc.) present?

4. Check if .github/workflows/ exists. List any CI files.

5. Run the test suite: python -m pytest --tb=short -q
   Record: total tests, pass/fail count, warnings.

6. Run: python -m pytest --co -q | tail -1
   Record: total test count for badge.

7. If coverage tooling is available:
   python -m pytest --cov=tidewatch --cov-report=term-missing -q
   Record: coverage percentage for badge.

8. Check for any existing GIF, PNG, SVG, or diagram files in the repo.

9. Read the paper source (look for .tex, .md, or doc files in the repo).
   Note the abstract text for alignment checking.

10. Produce a STATE_REPORT.md in the repo root summarizing all findings from
    steps 1-9. This is the baseline for all subsequent phases.

========================================================================
PHASE 2 — REPO INFRASTRUCTURE
========================================================================

Create or update the following files. Do NOT modify any Python source code
in this phase.

### 2a. pyproject.toml — ensure publication-ready metadata

If [build-system] is missing, add:
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

If [project] is missing or incomplete, add/update:
  [project]
  name = "tidewatch"
  version = "<read from existing code or __init__.py>"
  description = "Multi-objective task prioritization with capacity-aware reranking"
  readme = "README.md"
  license = "MIT"
  requires-python = ">=3.11"
  authors = [
    { name = "Justin Ram", email = "<read from existing if available>" }
  ]
  classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Typing :: Typed",
  ]

  [project.urls]
  Homepage = "https://github.com/infoil/tidewatch"
  Documentation = "https://github.com/infoil/tidewatch#readme"
  Repository = "https://github.com/infoil/tidewatch"
  Issues = "https://github.com/infoil/tidewatch/issues"

Add [tool.ruff] and [tool.pytest.ini_options] if not present. Use ruff
defaults. Preserve any existing tool configs.

### 2b. LICENSE

If missing, create MIT license file with:
  Copyright (c) 2026 Justin Ram / Infoil LLC

### 2c. CITATION.cff

Create a CITATION.cff file (CFF version 1.2.0) with:
  - Paper title (read from .tex or abstract)
  - Authors: Justin Ram
  - DOI: placeholder "10.XXXX/tidewatch" (to be replaced with real DOI)
  - Repository URL
  - License: MIT
  - Type: software
  - Preferred-citation type: article (for the paper)

### 2d. .github/FUNDING.yml

Create:
  github: [infoil]
  custom: []

(User will update with actual GitHub Sponsors username once profile is live)

### 2e. .github/workflows/ci.yml

Create a GitHub Actions CI workflow:
  - Trigger on push to main and pull requests
  - Matrix: Python 3.11, 3.12, 3.13
  - Steps: checkout, setup-python, pip install .[dev] or pip install -e ".[test]",
    run pytest with coverage
  - Upload coverage results
  - Use ubuntu-latest

### 2f. CHANGELOG.md

Create with keep-a-changelog format:
  # Changelog
  All notable changes documented here. Format: [Keep a Changelog](https://keepachangelog.com/).

  ## [Unreleased]

  ## [0.1.0] - 2026-03-21
  ### Added
  - Initial public release
  - Six-factor Late Collapse scoring engine
  - Monte Carlo evaluation framework
  - Capacity-aware bandwidth modulation with 3-tier risk classification
  - Factor ablation analysis
  - <N> deterministic and property-based tests

### 2g. CONTRIBUTING.md

Create a brief contributing guide:
  - How to set up dev environment
  - How to run tests
  - Code style (ruff)
  - PR process
  - Link to issues

### 2h. .pre-commit-config.yaml

Create with:
  - ruff (lint + format)
  - ruff-format check
  - trailing-whitespace, end-of-file-fixer, check-yaml

### 2i. py.typed

Create an empty py.typed marker file in the tidewatch package directory.

### 2j. .gitignore

If missing or minimal, ensure Python template coverage:
  __pycache__/, *.pyc, .venv/, dist/, build/, *.egg-info/,
  .pytest_cache/, .coverage, htmlcov/, .ruff_cache/

========================================================================
PHASE 3 — README REWRITE
========================================================================

Rewrite README.md following this exact structure. The content must align
with the post-remediation codebase — do not claim features that don't exist.

### Structure:

1. BADGE ROW (single line, no descriptions):
   - CI status (GitHub Actions badge — use the workflow file from Phase 2)
   - Coverage % (shields.io badge with actual % from Phase 1 recon)
   - PyPI version (placeholder until published)
   - Python versions (3.11 | 3.12 | 3.13)
   - License (MIT)
   - Paper DOI (placeholder)

2. ONE-LINER (≤15 words):
   "Tidewatch scores your tasks by deadline pressure, capacity, and what
   actually matters."
   (Or similar — must be human-readable, not academic jargon)

3. WHY TIDEWATCH? (3-5 bullets, ✅ emoji + bold):
   - ✅ **Not just overdue/not-overdue** — continuous pressure scoring that
     sees urgency accumulating, not just binary deadlines
   - ✅ **Knows when you're running low** — capacity-aware reranking surfaces
     lighter tasks when bandwidth drops, without hiding critical deadlines
   - ✅ **Shows its work** — Late Collapse architecture preserves all six
     scoring factors for inspection, not a black-box scalar
   - ✅ **Tested to 10⁻¹⁰** — <N> tests including Hypothesis property checks,
     Monte Carlo evaluation against EDF/FIFO/Random baselines
   - ✅ **Zero dependencies** — pure Python 3.11+ stdlib only

4. QUICK START:
   ```python
   pip install tidewatch

   from tidewatch import <primary_import>
   # 3-5 lines showing: create an obligation, score it, get a ranked list
   ```
   (Read the actual API to determine the correct import and usage. If the
    public API isn't clean enough for a 5-line demo, flag this as a finding
    in STATE_REPORT.md but write the best possible version.)

5. HOW IT WORKS (brief):
   One paragraph explaining the 6-factor model. Then a factor table:

   | Factor | What It Captures | Key Parameter |
   |--------|-----------------|---------------|
   | Time decay | Urgency acceleration as deadline approaches | k (rate constant) |
   | Materiality | Relative importance weighting | weight ∈ [0,1] |
   | Dependency fanout | Downstream impact of delays | k_f (fanout rate) |
   | Completion dampening | Reduced pressure as work completes | logistic sigmoid |
   | Timing sensitivity | Escalation for stagnant tasks | logistic ramp |
   | Violation amplification | Penalty for missed deadlines (decaying) | 14-day half-life |

6. EVALUATION (from Monte Carlo results):
   Embed the key results table from the paper:

   | Baseline | N=50 Missed % | N=200 Missed % |
   |----------|--------------|----------------|
   | Tidewatch | 6.7% | 20.1% |
   | EDF | 6.7% | 18.5% |
   | FIFO | ~X% | ~X% |
   | Random | ~X% | ~X% |

   (Read actual values from the evaluation code/results. Use MEASURED values
    only. Add footnote: "200 trials, seed=42, LogNormal durations. Full
    methodology in the paper.")

7. ARCHITECTURE (optional diagram):
   If there's an existing diagram, reference it. If not, create a simple
   ASCII or mermaid diagram showing:
   Obligations → Scorer (6 factors) → ComponentSpace → Collapse/Pareto → Ranked Queue
                                                    ↑
                                        Bandwidth Modulator (3-tier risk)

8. PART OF THE SENTINEL CONSTELLATION:
   Brief paragraph: "Tidewatch is part of a family of tools for
   cognitive-load-aware personal infrastructure. Related projects:
   [Sentinel](link) (orchestrator), [Gravitas](link) (memory retrieval),
   [Cohesion](link) (system modeling)."

9. PAPER:
   "📄 Read the paper: [link or 'forthcoming']"
   "📚 Cite this work:" + brief BibTeX block (from CITATION.cff)

10. SPONSORS:
    "💛 Tidewatch is independently developed. If it helps your workflow,
    consider [sponsoring](link)."
    (Even if no sponsors yet — signals intent and professionalism.)

11. LICENSE:
    "MIT — see [LICENSE](LICENSE)"

========================================================================
PHASE 4 — PAPER-REPO ALIGNMENT VERIFICATION
========================================================================

After Phases 2 and 3 are complete:

1. Read the paper abstract (from .tex or doc file).
2. Read the new README.md.
3. Compare every factual claim in the README against:
   a. The paper abstract
   b. The actual codebase (run grep/search as needed)
4. Check specifically:
   - Test count in README matches actual test count from pytest
   - Factor count matches actual implemented factors
   - Baseline names match actual baseline implementations
   - Monte Carlo parameters (trial count, seed, distribution) match code
   - "Zero dependencies" claim — verify no non-stdlib imports
   - Python version claim — verify pyproject.toml requires-python
5. Produce ALIGNMENT_REPORT.md listing every claim and its verification
   status (PASS/FAIL + evidence).
6. If any FAIL: fix the README claim to match reality. Do NOT change code
   to match README.

========================================================================
CONSTRAINTS
========================================================================

- Do NOT modify any Python source code (.py files) in scoring, ranking,
  evaluation, or test modules. This prompt is about packaging and
  presentation, not functionality.
- Do NOT rename or restructure Python packages/modules.
- Do NOT add runtime dependencies. Dev dependencies (ruff, pytest, coverage,
  pre-commit) are fine in [project.optional-dependencies].
- GitHub org/username: use "infoil" as placeholder. User will confirm.
- All badge URLs should use shields.io with correct org/repo path.
- If the repo remote URL reveals the actual GitHub org/username, use that
  instead of "infoil".
- Commit after each phase with descriptive commit messages:
  "chore: Phase 1 — baseline state report"
  "chore: Phase 2 — repo infrastructure for public release"
  "docs: Phase 3 — README rewrite for visibility and monetization"
  "docs: Phase 4 — paper-repo alignment verification"
```

---

## POST-RELEASE PLAYBOOK (for Justin, not for Claude Code)

After the Claude Code prompt lands:

1. **Verify GitHub org/username** — confirm "infoil" or update to actual
2. **Create GitHub Sponsors profile** — set up tiers ($5/mo, $25/mo, $100/mo "agency")
3. **Publish to PyPI** — `python -m build && twine upload dist/*`
4. **Update badge URLs** — replace placeholders with real PyPI/coverage values
5. **Submit paper** — get DOI → update CITATION.cff and README
6. **Hacker News / Reddit launch post** — use the one-liner + benchmark table
7. **Create a 30-second terminal GIF** — `asciinema` or `terminalizer` showing scoring demo
8. **Set up GitHub Discussions** — for community engagement
9. **Consider sponsorware** — premium features (Sentinel integration, dashboard UI) behind sponsor tier
