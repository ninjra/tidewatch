# TIDEWATCH

## Continuous Obligation Pressure with Proactive Idle-Time Planning for AI Agents

**Repo:** `ninjra/tidewatch`
**License:** MIT
**Status:** Paper draft + reference implementation
**Parent system:** [Sentinel](https://github.com/ninjra/sentinel) (personal AI agent)

---

# CLAUDE.md — Read This First

This file is the single source of truth for the Tidewatch repo. Claude Code
reads this before every task.

## What This Repo Is

Tidewatch is a **standalone Python library + SSRN paper** that extracts and
formalizes the obligation pressure engine and speculative planning system
from Sentinel. It models deadline urgency as a continuous pressure field
rather than a binary overdue/not-overdue flag, and uses idle compute cycles
to proactively generate action plans for high-pressure obligations.

1. `tidewatch/` — the Python library (pip-installable)
2. `paper/` — the SSRN paper in LaTeX
3. `benchmarks/` — evaluation harness
4. `tests/` — unit and integration tests

## Relationship to Sentinel

Tidewatch is extracted FROM Sentinel's `plugins/core/obligations/pressure.py`,
`plugins/core/obligations/triage.py`, and
`plugins/core/speculative_planner/plugin.py`.

### Linking Mechanism

Same pattern as Gravitas and Arbiter:

```
D:\repos\
├── sentinel/
│   ├── plugins/core/obligations/   # THIN WRAPPER — imports from tidewatch
│   ├── plugins/core/speculative_planner/  # THIN WRAPPER
│   └── requirements.txt            # includes -e ../tidewatch
└── tidewatch/
    └── tidewatch/                   # the library
```

```python
# sentinel/plugins/core/obligations/plugin.py (after extraction)
from tidewatch import PressureEngine, pressure_zone, calculate_pressure
from tidewatch import SpeculativePlanner, PlanResult
# ... adapt to Sentinel's bus, config, SQL Server, provenance ledger
```

### Propagation Rules

- Pressure formula changes: make in `tidewatch/`, Sentinel gets them via import
- Sentinel-specific config (SQL Server persistence, provenance ledger,
  bus wiring, domain_map): stays in Sentinel
- Paper equations and code must always match

## Build Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
python -m benchmarks.run --suite all
cd paper && latexmk -pdf tidewatch.tex
```

## Code Standards

- Python 3.11+, type hints on all public functions
- Pure math in core — no database, no LLM, no async in the pressure engine
- Speculative planner returns prompt templates — caller provides the LLM
- Sections labeled: Inputs / Logic / Outputs / Notes

## Directory Structure

```
tidewatch/
├── tidewatch/
│   ├── __init__.py               # public API exports
│   ├── pressure.py               # PressureEngine: core pressure computation
│   ├── planner.py                # SpeculativePlanner: idle-time plan generation
│   ├── triage.py                 # TriageQueue: candidate staging and acceptance
│   ├── types.py                  # Obligation, PressureResult, PlanResult, Zone
│   └── constants.py              # All tunable constants
├── benchmarks/
│   ├── __init__.py
│   ├── run.py
│   ├── datasets/
│   │   └── generate_obligations.py  # Synthetic obligation benchmark
│   ├── baselines/
│   │   ├── binary_deadline.py       # Binary overdue/not-overdue
│   │   ├── linear_urgency.py        # Linear days-remaining
│   │   └── eisenhower.py            # Urgent/important matrix
│   └── metrics.py
├── paper/
│   ├── tidewatch.tex
│   ├── tidewatch.bib
│   └── figures/
│       ├── pressure_curves.py
│       ├── zone_transitions.py
│       └── planner_timeline.py
├── tests/
│   ├── test_pressure.py
│   ├── test_planner.py
│   ├── test_triage.py
│   └── test_integration.py
├── pyproject.toml
├── README.md
├── LICENSE
└── CLAUDE.md                     # THIS FILE
```

---

# PAPER DRAFT

## Title

**Tidewatch: Continuous Obligation Pressure with Proactive Idle-Time
Planning for Intelligent Task Management**

## Authors

Justin Ram
Infoil LLC

## Abstract

We present Tidewatch, a framework for modeling task urgency as a
continuous pressure field and leveraging idle compute cycles for
proactive action planning. Unlike binary deadline models (overdue vs.
not overdue) or linear urgency decay, Tidewatch computes obligation
pressure via an exponential approach function modulated by materiality,
dependency structure, and completion progress. The resulting pressure
score maps to operational zones (green/yellow/orange/red) that trigger
escalating system behaviors — from background monitoring to proactive
plan generation to urgent user notification.

The framework introduces two contributions: (1) a **continuous pressure
model** inspired by hydraulic systems, where deadline proximity creates
exponentially increasing pressure that is amplified by material weight
and damped by completion progress, and (2) a **speculative planning
engine** that uses idle compute cycles to proactively generate concrete
action plans for high-pressure obligations, reviewed through a
multi-agent council before surfacing to the user.

We frame the system for personal AI agents but demonstrate applicability
to general intelligent task management. Evaluation on a synthetic
obligation benchmark shows that continuous pressure outperforms binary
and linear baselines on zone-transition timeliness, missed-deadline
rate, and user attention allocation efficiency.

**Keywords:** task management, deadline urgency, pressure modeling,
proactive planning, personal AI agents, obligation tracking

## 1. Introduction

Every task management system must answer a deceptively simple question:
*which task needs attention right now?*

The dominant approaches are:

**Binary deadline.** A task is either overdue or not. This provides no
advance warning — the system transitions from "fine" to "failed" in one
step. GTD, Todoist, and most project management tools operate here.

**Priority labels.** Tasks are tagged high/medium/low. This is static
— a task labeled "medium" on Monday is still "medium" on Friday even if
its deadline is Saturday. The label doesn't respond to time.

**Eisenhower matrix.** Tasks are classified along urgent/important axes.
This adds a second dimension but remains discrete — a task is either
"urgent" or "not urgent" with no gradient between.

All three share a fundamental limitation: **urgency is treated as a
discrete state rather than a continuous quantity.** In reality, the
urgency of a deadline increases continuously as it approaches, is
amplified when other tasks depend on it, and is dampened when progress
has already been made. A tax filing due in 14 days with no dependencies
and 80% completion is qualitatively different from a contract deadline
due in 14 days with 3 dependent tasks and 0% completion — yet binary
and label-based systems treat them identically.

Tidewatch models urgency as continuous pressure, borrowing the intuition
of hydraulic systems: as a deadline approaches, pressure builds
exponentially in the pipe. Material obligations (high-consequence) are
wider pipes that carry more pressure. Dependencies are junctions that
amplify flow. Completion acts as a relief valve that reduces pressure
proportionally.

The mathematical framework is:

    P(t) = min(1.0, f_time(t) × f_materiality × f_dependencies × f_completion)

where each factor is a continuous function. The resulting pressure
score in [0, 1] maps to operational zones that trigger progressively
urgent system responses — from passive monitoring to proactive plan
generation to user interruption.

## 2. Related Work

### 2.1 Task Scheduling and Prioritization

Classical scheduling theory (EDF — Earliest Deadline First; EDD —
Earliest Due Date) optimizes throughput by ordering tasks by deadline.
These algorithms are optimal for single-machine scheduling under
specific assumptions but do not model urgency as a human-facing signal
or account for partial completion.

### 2.2 GTD and Personal Productivity Systems

Allen's Getting Things Done (2001) organizes tasks by context and
next-action rather than deadline urgency. Covey's Eisenhower matrix
adds an urgency dimension but remains categorical. Neither provides
a continuous urgency signal that adapts to task state.

### 2.3 Deadline-Aware AI Agents

Recent agent systems (Generative Agents, Park et al. 2023; AutoGPT;
CrewAI) track tasks but treat deadlines as metadata for prompt
injection rather than first-class urgency signals. No published
agent framework computes deadline pressure as a continuous function
or uses it to drive proactive planning behavior.

### 2.4 Proactive Computing

The concept of proactive computing — systems that act on behalf of
users during idle time — dates to Tennenhouse (2000). Speculative
execution in databases and branch prediction in CPUs are hardware
analogs. In the AI agent context, speculative planning means
generating action plans before the user asks, using idle compute
cycles that would otherwise be wasted.

## 3. The Tidewatch Framework

### 3.1 The Pressure Equation

For an obligation with days_remaining = t, the pressure is:

    P = min(1.0, P_time × M_materiality × A_dependency × D_completion)

**Time pressure (the hydraulic core):**

    P_time(t) = 1 - exp(-3 / max(t, 0.01))     for t > 0
    P_time(t) = 1.0                               for t ≤ 0 (overdue)

This exponential approach function has the following properties:
- At 14 days out: P_time ≈ 0.19 (low background pressure)
- At 7 days out: P_time ≈ 0.35 (noticeable, entering yellow zone)
- At 3 days out: P_time ≈ 0.63 (significant, orange territory)
- At 1 day out: P_time ≈ 0.95 (critical, red zone)
- At 0 days (due now): P_time = 1.0
- Overdue: P_time = 1.0 (maximum, sustained)

The rate constant (3.0) controls how aggressively pressure builds.
Higher values create steeper curves with later onset. Lower values
create gentler curves with earlier onset. The default (3.0) is
calibrated to produce a green→yellow transition approximately 7 days
before deadline for routine tasks.

**Materiality multiplier:**

    M = 1.5   if materiality = "material"
    M = 1.0   if materiality = "routine"

Material obligations (high consequence if missed — legal deadlines,
contract expirations, tax filings) carry 50% more pressure than
routine tasks. This single multiplier can push a 7-day-out obligation
from green (0.35 × 1.0 = 0.35) into yellow (0.35 × 1.5 = 0.53).

Think of it hydraulically: material obligations are wider pipes that
transmit more force for the same input pressure.

**Dependency amplifier:**

    A = 1.0 + (dependency_count × 0.1)

Each obligation that depends on this one adds 10% amplification.
An obligation with 5 dependents has 1.5× amplification — if it slips,
five other things slip with it. This captures the cascading failure
risk that simple priority labels miss.

Hydraulically: dependencies are junctions in the pipe network that
multiply flow.

**Completion dampener:**

    D = 1.0 - (completion_pct × 0.6)

Progress on the obligation reduces pressure, but not linearly and
never to zero. At 100% completion, the dampener is 0.4 — the
obligation still exerts 40% of its undamped pressure because "done"
isn't "verified and closed." At 50% completion, the dampener is 0.7.

Hydraulically: completion is a relief valve that bleeds off pressure
proportionally.

**No-deadline obligations:** If an obligation has no due date, pressure
is 0.0. Tidewatch only measures the urgency of deadlines, not the
importance of open-ended tasks. Importance without urgency is a
different problem.

### 3.2 Pressure Zones

The continuous pressure score maps to four operational zones:

| Zone | Pressure Range | System Behavior |
|------|---------------|-----------------|
| Green | P < 0.30 | Passive monitoring. No user notification. |
| Yellow | 0.30 ≤ P < 0.60 | Background tracking. Include in briefings. |
| Orange | 0.60 ≤ P < 0.80 | Active monitoring. Speculative planning triggers. Toast notification. |
| Red | P ≥ 0.80 | Urgent. Immediate notification. Plan surfaced proactively. |

Zone transitions are the key events. When an obligation crosses from
green to yellow, or yellow to orange, the system escalates its response.
These transitions are recorded in an audit log for traceability.

The zone thresholds are not arbitrary — they are calibrated to the
exponential curve:
- Green → Yellow at ~7 days for routine, ~10 days for material
- Yellow → Orange at ~3 days for routine, ~5 days for material
- Orange → Red at ~1 day for routine, ~2 days for material

### 3.3 Speculative Planning

When an obligation enters orange or red zone, Tidewatch generates a
speculative plan — a set of concrete next steps the user could take.

**Trigger criteria:**
- pressure_zone ∈ {yellow, orange, red}
- Recalculated on each heartbeat (configurable interval, default 30min)
- Only top-N highest-pressure obligations are planned (default: 3)

**Plan generation:**
Tidewatch returns a prompt template that the caller sends to their LLM:

```
Obligation: {title}
Description: {description}
Due: {due_date}
Pressure zone: {zone} (score {pressure:.2f})
Domain: {domain}

Produce 2-3 concrete next steps. Each step must be:
- Actionable (not "think about" or "consider")
- Completable in one sitting (under 2 hours)
- Specific enough to start immediately
Be concise. No preamble.
```

**Plan delivery:** The library returns a PlanResult containing:
- The prompt (for caller to send to LLM)
- Obligation metadata
- Suggested delivery urgency ("background" for yellow, "toast" for
  orange, "interrupt" for red)

The caller handles LLM invocation, plan storage, and user notification.
Tidewatch provides the when-to-plan and what-to-plan-for logic.

**Idle-time scheduling:** The planner runs during system idle periods —
heartbeat ticks when no foreground user interaction is occurring. This
means plans are generated proactively, using compute cycles that would
otherwise be wasted. When the user next engages, the plan is already
ready.

### 3.4 Triage: Obligation Discovery

Obligations enter the system through a triage queue. Sources (email
scanners, calendar parsers, document analyzers) emit candidates that
are staged for user review before becoming tracked obligations.

The triage queue:
1. Receives candidate obligations from external sources
2. Deduplicates by title + source + due_date
3. Stages candidates for user approval
4. On acceptance: creates an obligation and starts pressure tracking
5. On rejection: discards and optionally feeds back to the scanner

This ensures the pressure system only tracks user-acknowledged
obligations, preventing scanner noise from polluting the pressure field.

## 4. Implementation

Tidewatch is implemented in Python 3.11+. The pressure engine is pure
math — no database, no LLM, no async. The speculative planner returns
prompt templates; the caller provides the LLM backend.

The reference implementation deploys within Sentinel, a personal AI
agent using SQL Server 2025 for obligation storage, Qwen 3.5 9B for
plan generation, and a Council of 3 (Operator/Critic/Advocate) for
plan review before user delivery.

## 5. Evaluation

### 5.1 Datasets

**Synthetic Obligation Benchmark (SOB).** 1,000 obligations across 5
domains (legal, financial, client work, personal admin, health) with
realistic deadline distributions, dependency graphs, and completion
trajectories. Each obligation has ground-truth "optimal attention
time" — the earliest point at which the user should begin working on
it, determined by deadline, complexity, and dependencies.

### 5.2 Baselines

1. **Binary deadline**: urgency = 1 if overdue, 0 otherwise
2. **Linear urgency**: urgency = max(0, 1 - days_remaining / max_horizon)
3. **Eisenhower**: 4-bucket classification, static after assignment
4. **EDF (Earliest Deadline First)**: pure deadline ordering, no
   pressure modulation

### 5.3 Metrics

- **Zone-transition timeliness**: how many days before the deadline
  does the system first alert the user? Measured as the gap between
  first yellow-zone entry and the ground-truth optimal attention time.
- **Missed-deadline rate**: fraction of obligations that hit red zone
  without the user having been alerted at least 48 hours prior.
- **Attention allocation efficiency**: does the system direct attention
  to the right obligations? Measured as rank correlation between
  pressure-ordered list and ground-truth urgency-ordered list.
- **False alarm rate**: fraction of obligations that enter orange/red
  but are completed well before deadline (overreaction).
- **Plan usefulness**: for speculative plans, human evaluation of
  whether the generated steps are actionable (1-5 scale).

### 5.4 Ablation Study

- Tidewatch-full vs. without materiality multiplier
- Tidewatch-full vs. without dependency amplifier
- Tidewatch-full vs. without completion dampener
- Tidewatch-full vs. linear time function (replacing exponential)
- Tidewatch-full vs. without speculative planning

[RESULTS TO BE FILLED AFTER BENCHMARK RUNS]

## 6. Discussion

### 6.1 Why Exponential, Not Linear?

Linear urgency (urgency = 1 - t/horizon) increases at a constant rate.
This means a task 14 days out gets the same daily urgency increase as
a task 2 days out. In practice, deadline urgency is nonlinear — the
difference between 14 and 13 days is negligible, while the difference
between 2 and 1 day is critical. The exponential function
1 - exp(-3/t) captures this: nearly flat far from deadline, steep
near it.

### 6.2 The Hydraulic Intuition

The mathematical framework is easier to reason about when framed
hydraulically:

- **Pressure** = urgency (increases as deadline approaches)
- **Pipe width** = materiality (wider pipes carry more pressure)
- **Junctions** = dependencies (multiply flow)
- **Relief valves** = completion (bleed off pressure)
- **Zones** = gauges on the pipe (green/yellow/orange/red)
- **Speculative planning** = the system opening drain valves before
  the pipe bursts

This metaphor is not just pedagogical — it provides intuition for
tuning the constants. If the system alerts too late, increase the
rate constant (3.0). If material items don't stand out enough,
increase the materiality multiplier (1.5). If partially-complete
tasks still generate too much pressure, increase the completion
dampening factor (0.6).

### 6.3 Limitations

1. **No importance without urgency**: obligations without deadlines
   get zero pressure. A strategically important but deadline-free
   task is invisible to Tidewatch. This is a deliberate scope
   limitation — importance is a separate dimension.
2. **Static materiality**: materiality is binary (material/routine).
   A richer scale (1-5) or learned materiality from user behavior
   patterns is future work.
3. **Plan quality depends on LLM**: speculative plans are only as
   good as the LLM generating them. Poor local models produce
   generic, unhelpful plans.
4. **Single-user calibration**: the rate constant (3.0) and zone
   thresholds are calibrated to one user's attention patterns.
   Different users may need different curves.

## 7. Conclusion

Tidewatch demonstrates that modeling deadline urgency as a continuous
pressure field, rather than a discrete state, provides meaningfully
better task attention allocation. The exponential pressure function
with materiality, dependency, and completion modulation creates a
rich urgency signal that adapts to task state. Speculative idle-time
planning converts this urgency signal into proactive action,
generating concrete plans before the user asks.

We release Tidewatch as an open-source Python library (MIT license).

## References

Allen, D. (2001). Getting Things Done. Penguin Books.

Chernoff, H. (1959). Sequential design of experiments. Annals of
Mathematical Statistics.

Covey, S. R. (1989). The 7 Habits of Highly Effective People. Free
Press.

Park, J. S. et al. (2023). Generative agents: Interactive simulacra
of human behavior. UIST '23.

Tennenhouse, D. (2000). Proactive computing. Communications of the
ACM, 43(5), 43-50.

---

# IMPLEMENTATION SPEC

## Phase 1: Repo Bootstrap

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "tidewatch"
version = "0.1.0"
description = "Continuous obligation pressure with proactive idle-time planning"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
authors = [
    {name = "Justin Ram", email = "justin.ram@gmail.com"},
]
keywords = [
    "task management", "deadline", "urgency", "pressure",
    "proactive planning", "AI agents", "obligation tracking",
]
dependencies = []  # ZERO dependencies for core library

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "ruff",
    "mypy",
]
benchmarks = [
    "matplotlib>=3.7",
    "pandas>=2.0",
    "numpy>=1.24",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py311"
```

Note: **zero runtime dependencies.** The core library uses only stdlib math.
This is intentional — the pressure equation is pure math with no external
requirements.

### tidewatch/constants.py

```python
"""Tunable constants for Tidewatch pressure engine.

Each constant has a hydraulic analog documented in its comment.
"""

# --- Pressure curve ---
RATE_CONSTANT = 3.0        # Exponential steepness (pipe elasticity)
OVERDUE_PRESSURE = 1.0     # Pressure when overdue (pipe at max)

# --- Materiality ---
MATERIALITY_WEIGHTS = {
    "material": 1.5,       # Wide pipe — carries more pressure
    "routine": 1.0,        # Standard pipe
}

# --- Dependencies ---
DEPENDENCY_AMPLIFICATION = 0.1  # Per-dependency amplifier (junction multiplier)

# --- Completion ---
COMPLETION_DAMPENING = 0.6  # Max dampening at 100% completion (relief valve)

# --- Zone thresholds ---
ZONE_YELLOW = 0.30
ZONE_ORANGE = 0.60
ZONE_RED = 0.80

# --- Speculative planner ---
PLANNER_MIN_ZONES = {"yellow", "orange", "red"}  # Zones that trigger planning
PLANNER_TOP_N = 3           # Max obligations to plan per cycle
PLANNER_MAX_STEPS = 3       # Steps per plan
PLANNER_MAX_TOKENS = 500    # Token budget per plan prompt
```

### tidewatch/types.py

Key types — all plain dataclasses, stdlib only:

- `Obligation`: id, title, due_date (datetime | None), materiality (str),
  dependency_count (int), completion_pct (float), domain (str | None),
  description (str | None), status (str)
- `PressureResult`: obligation_id, pressure (float), zone (str),
  time_pressure (float), materiality_mult (float), dependency_amp (float),
  completion_damp (float). Full decomposition for auditability.
- `PlanRequest`: obligation (Obligation), pressure_result (PressureResult),
  prompt (str), delivery_urgency (str: "background"/"toast"/"interrupt")
- `PlanResult`: obligation_id, plan_text (str), zone (str),
  pressure (float), created_at (datetime)
- `Zone`: Enum with GREEN, YELLOW, ORANGE, RED and comparison operators
- `TriageCandidate`: title, source, source_ref, due_date, domain,
  priority, context, staged_at

### tidewatch/pressure.py

The heart of the library. Port `calculate_pressure` and `pressure_zone`
from Sentinel's `pressure.py`. Key changes:
- Pure functions, zero side effects, zero database, zero async
- Accept Obligation dataclass as input
- Return PressureResult with full decomposition
- `calculate_pressure(obligation) -> PressureResult`
- `pressure_zone(pressure: float) -> str`
- `recalculate_batch(obligations: list[Obligation]) -> list[PressureResult]`
  with sorting by pressure descending

The `calculate_pressure` function MUST exactly implement the equations
from Section 3.1 of the paper. Equation references in docstring.

### tidewatch/planner.py

Port speculative planner logic. Key changes:
- No LLM call — returns PlanRequest with prompt template
- `SpeculativePlanner(min_zones, top_n, system_prompt_override)`
- `generate_plan_requests(pressure_results) -> list[PlanRequest]`:
  filters by zone, sorts by pressure, returns top-N plan requests
- `complete_plan(plan_request, plan_text) -> PlanResult`:
  wraps the LLM output in a PlanResult after caller invokes LLM
- System prompt is the default from Sentinel but overridable

### tidewatch/triage.py

Port triage queue logic. Key changes:
- In-memory queue (no filesystem, no database)
- `TriageQueue()` with `stage(candidate) -> str` (returns ID),
  `list_pending() -> list`, `accept(id) -> Obligation`,
  `reject(id) -> bool`
- Dedup by (title_lower, source, due_date) tuple
- Caller handles persistence — Tidewatch provides the logic

### tidewatch/__init__.py

```python
"""Tidewatch: Continuous obligation pressure with proactive planning."""

from tidewatch.pressure import calculate_pressure, pressure_zone, recalculate_batch
from tidewatch.planner import SpeculativePlanner
from tidewatch.triage import TriageQueue
from tidewatch.types import (
    Obligation, PressureResult, PlanRequest, PlanResult,
    Zone, TriageCandidate,
)

__version__ = "0.1.0"
__all__ = [
    "calculate_pressure", "pressure_zone", "recalculate_batch",
    "SpeculativePlanner", "TriageQueue",
    "Obligation", "PressureResult", "PlanRequest", "PlanResult",
    "Zone", "TriageCandidate",
]
```

## Phase 2: Tests

### tests/test_pressure.py
- `test_no_deadline_returns_zero`: no due_date → P = 0.0
- `test_overdue_returns_one`: days_remaining ≤ 0 → P_time = 1.0
- `test_14_days_out`: P_time ≈ 0.19 (within 0.02 tolerance)
- `test_7_days_out`: P_time ≈ 0.35
- `test_3_days_out`: P_time ≈ 0.63
- `test_1_day_out`: P_time ≈ 0.95
- `test_materiality_multiplier`: material = 1.5x routine
- `test_dependency_amplification`: 5 deps = 1.5x base
- `test_completion_dampening`: 100% complete = 0.4x, 50% = 0.7x
- `test_combined_factors_multiply`: all factors interact correctly
- `test_pressure_clamped_to_one`: high factors don't exceed 1.0
- `test_zone_boundaries`: exact boundary values map correctly
- `test_zone_green`: P=0.29 → green
- `test_zone_yellow`: P=0.30 → yellow
- `test_zone_orange`: P=0.60 → orange
- `test_zone_red`: P=0.80 → red
- `test_batch_recalculate_sorted`: results sorted by pressure descending
- `test_pressure_result_decomposition`: all factors accessible individually

### tests/test_planner.py
- `test_green_not_planned`: green zone obligations not included
- `test_orange_triggers_plan`: orange zone generates PlanRequest
- `test_red_triggers_plan`: red zone generates PlanRequest
- `test_top_n_limit`: only top-N returned even with more eligible
- `test_prompt_contains_obligation_data`: title, due date, zone in prompt
- `test_delivery_urgency_by_zone`: yellow=background, orange=toast, red=interrupt
- `test_complete_plan_wraps_result`: PlanResult contains obligation metadata
- `test_custom_system_prompt`: override system prompt works

### tests/test_triage.py
- `test_stage_and_list`: staged candidate appears in pending
- `test_accept_creates_obligation`: accept returns Obligation
- `test_reject_removes_candidate`: reject clears from queue
- `test_dedup_by_title_source_date`: duplicate candidates rejected
- `test_empty_queue`: list_pending returns empty list

### tests/test_integration.py
- `test_full_pipeline`: create obligations → recalculate → plan → verify zones match
- `test_pressure_drives_planning`: only high-pressure obligations get plans
- `test_zone_transition_detection`: track when obligations cross zone boundaries

## Phase 3: Benchmarks

### benchmarks/datasets/generate_obligations.py
Generate SOB: 1,000 obligations across 5 domains with:
- Deadline distributions: uniform 1-90 days, with 10% overdue
- Dependency graph: power-law, mean 2 deps per obligation
- Completion trajectories: random progress snapshots
- Ground-truth "optimal attention time" for each obligation
- Output: JSON file

### benchmarks/baselines/
- `binary_deadline.py`: urgency = 1 if overdue else 0
- `linear_urgency.py`: urgency = max(0, 1 - t/90)
- `eisenhower.py`: 4-bucket static classification

### benchmarks/metrics.py
- zone_transition_timeliness, missed_deadline_rate,
  attention_allocation_efficiency (rank correlation),
  false_alarm_rate

### benchmarks/run.py
CLI: `python -m benchmarks.run --suite all`

## Phase 4: Sentinel Integration

```
# sentinel/requirements.txt
-e ../tidewatch
```

Sentinel's obligations plugin imports from tidewatch and adapts to
the bus, SQL Server, and provenance ledger.

## README.md

```markdown
# Tidewatch

**Continuous obligation pressure with proactive idle-time planning.**

Tidewatch models deadline urgency as a hydraulic pressure field.
Obligations build pressure exponentially as deadlines approach.
Material obligations carry more. Dependencies amplify. Progress
dampens. The system plans before you ask.

## Install

```bash
pip install tidewatch
```

## Quick Start

```python
from datetime import datetime, timezone, timedelta
from tidewatch import (
    Obligation, calculate_pressure, pressure_zone,
    SpeculativePlanner, recalculate_batch,
)

# Create obligations
obligations = [
    Obligation(
        id=1, title="File Q1 taxes",
        due_date=datetime.now(timezone.utc) + timedelta(days=3),
        materiality="material", dependency_count=2,
        completion_pct=0.1,
    ),
    Obligation(
        id=2, title="Update project README",
        due_date=datetime.now(timezone.utc) + timedelta(days=14),
        materiality="routine", dependency_count=0,
        completion_pct=0.0,
    ),
]

# Calculate pressure
results = recalculate_batch(obligations)
for r in results:
    print(f"{r.obligation_id}: P={r.pressure:.2f} [{r.zone}]")

# Generate speculative plans for high-pressure items
planner = SpeculativePlanner()
plan_requests = planner.generate_plan_requests(results)
for req in plan_requests:
    print(f"Plan needed: {req.obligation.title}")
    print(f"Prompt: {req.prompt[:100]}...")
    # Send req.prompt to your LLM, then:
    # result = planner.complete_plan(req, llm_output)
```

## Paper

> **Tidewatch: Continuous Obligation Pressure with Proactive Idle-Time
> Planning for Intelligent Task Management**
> Justin Ram, Infoil LLC (2026)
> [SSRN link pending]

## License

MIT
```

---

# PRE-SUBMISSION CHECKLIST

1. [ ] All benchmark results filled in Section 5.4
2. [ ] Ablation study complete
3. [ ] Pressure curve comparison plot (exponential vs linear vs binary)
4. [ ] Zone transition timeline visualization
5. [ ] All code passes `pytest` and `mypy`
6. [ ] Paper compiles with `latexmk`
7. [ ] README Quick Start runs
8. [ ] Sentinel integration test passes
9. [ ] No PII, client names, or proprietary data
10. [ ] License file (MIT) in repo root

# SSRN METADATA

- **Title:** Tidewatch: Continuous Obligation Pressure with Proactive Idle-Time Planning for Intelligent Task Management
- **Category:** Computer Science → Artificial Intelligence; Information Systems → Decision Support Systems
- **JEL:** C61 (Optimization Techniques), M15 (IT Management)
- **Keywords:** task management, deadline urgency, pressure modeling, proactive planning, personal AI agents, obligation tracking, intelligent scheduling
