# CLAUDE.md -- Tidewatch

## What This Repo Is

Tidewatch is a pure-math scoring engine for obligation pressure with cognitive
bandwidth adaptation and a benchmark analytics harness. Core capabilities:

- **Pressure scoring**: continuous scores (0.0-1.0) from deadline proximity,
  materiality, dependencies, and completion progress
- **Cognitive bandwidth modulation** (CognitiveContext): re-ranks the pressure-sorted
  queue based on operator physiological state (sleep, pain, HRV) — integral to the
  scoring engine, not an add-on
- **Speculative planning** (SpeculativePlanner): uses idle compute to pre-generate
  action plans for high-pressure obligations — extends the scoring engine's output
  into actionable plan requests
- **Triage** (TriageQueue): stages candidate obligations from external scanners
  for operator review with deduplication

An accompanying SSRN paper formalizes the exponential decay pressure model.

## Paper Quality Gate

Before any abstract or paper modification, run this checklist. These are
the problem classes encountered in the 2026-03-22 pipeline and must never
recur:

1. **Deployment framing**: Abstract and intro must lead with agent
   orchestration (the actual deployment model), not human task management.
   Tidewatch is a prioritization substrate for agent systems, not a
   scheduler competing with EDF.
2. **Contribution framing**: The EDF gap is the *cost* of multi-factor
   ranking, not a deficiency. Lead with what tidewatch can do that EDF
   cannot (materiality, dependencies, completion discrimination), not
   with the deadline comparison tidewatch loses.
3. **Count consistency**: Test count and line count in the paper must
   match reality. `pytest tests/ -q` gives the test count;
   `wc -l tidewatch/*.py` gives line count. Gate 22 in the golden
   pipeline enforces this automatically.
4. **Version/dep contract**: `pyproject.toml` version must match
   `__init__.__version__`. Dependencies list must be empty (zero-dep
   contract). Gate 01 enforces this automatically.
5. **Obligation verification**: Never report `pending_review` obligations
   as unresolved without checking the paper/code for the actual
   deliverable. pending_review means awaiting approval, not awaiting work.
6. **Large-N claims**: If the abstract or body mentions large-N scaling
   features (adaptive k, rank normalization, zone capacity, log-scaled
   dep cap), verify they are tested and the acceptance criteria pass.
7. **Bandwidth framing**: Bandwidth modulation applies to operator *or*
   system load. Do not frame exclusively as physiological/cognitive.
   The module is specified but empirically unvalidated — state this.

## Build Commands

```bash
pip install -e ".[dev]"
pytest tests/ -v
python -m benchmarks.run --suite all
```

## Code Standards

- Python 3.11+, type hints on all public functions
- Pure math in core -- no database, no LLM, no async in the pressure engine
- Speculative planner returns prompt templates -- caller provides the LLM
- Zero runtime dependencies. stdlib math only.

## Key Equations

P = min(1.0, P_time * M * A * D * T_amp * V_amp)

- P_time(t) = 1 - exp(-k / max(t, 0.01)) for t > 0; 1.0 for t <= 0 (k=3.0)
- M = 1.5 (material) or 1.0 (routine)
- A = 1.0 + (dep_count * 0.1 * temporal_gate(t))
- D = 1.0 - (0.6 * sigmoid(8 * (completion_pct - 0.5)))
- T_amp = 1.0 + 0.2 / (1 + exp(-0.5 * (days_in_status - 7)))
- V_amp = 1.0 + min(log(1 + violations * decay) * 0.05, 0.5)

Zones: green < 0.30, yellow < 0.60, orange < 0.80, red >= 0.80

## Testing

Run before every commit: `python -m pytest tests/ -v`

## Verification Block

Quick verification that tidewatch is healthy within the constellation:

```bash
python -m pytest tests/ -q                    # 651 tests, all must pass
python -m ruff check tidewatch/ tests/        # lint clean
python -c "import tidewatch; print(tidewatch.__version__)"  # 0.4.4
python -c "
from datetime import UTC, datetime, timedelta
from tidewatch import calculate_pressure, Obligation
now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
ob = Obligation(id=1, title='Smoke', due_date=now + timedelta(days=7))
r = calculate_pressure(ob, now=now)
assert 0.30 <= r.pressure <= 0.40, f'Expected yellow, got {r.pressure}'
assert r.zone == 'yellow'
print('PASS: pressure engine healthy')
"
```

## Interface Seams

Tidewatch connects to the constellation at these boundaries:

### Provides to constellation
| Consumer | Interface | Purpose |
|----------|-----------|---------|
| **forge** | `export_pressure_summary()` | System pressure signal; forge pauses evolution when `should_pause_evolution=True` |
| **Sentinel/autobot** | `calculate_pressure()`, `recalculate_batch()` | Scores obligations for queue ordering |
| **gravitas** | `PressureResult.pressure`, zone labels | `obligation_ranker.py` complements tidewatch urgency with domain relevance |

### Consumes from constellation
| Provider | Interface | Required? |
|----------|-----------|-----------|
| **gravitas** | `gravitas.types.ComponentSpace` | Optional — fallback `_FallbackComponentSpace` used when unavailable |
| **Sentinel** | `sentinel_sdk.metrics.get_buffer()` | Optional — telemetry degrades gracefully |
| **Sentinel** | `sentinel_query.py` | Workflow only — not a runtime dependency |

### Contract: zero runtime dependencies
Tidewatch's core library (`tidewatch/`) uses stdlib only. All constellation
integrations are optional extras that degrade gracefully via try/except import
guards. The package installs and runs with `dependencies = []`.

## Sentinel Integration

This repo is part of the Sentinel ecosystem. Use `sentinel_query.py` for all cross-repo
coordination. The tool lives at `~/projects/Sentinel/scripts/sentinel_query.py`.

**Note:** Sentinel integration is a development workflow dependency, NOT a runtime
dependency. The tidewatch library (`tidewatch/`) has zero external dependencies and
functions fully without Sentinel. The sentinel_sdk telemetry integration is an optional
extra (`pip install -e ".[telemetry]"`) that degrades gracefully if unavailable.

### Session Lifecycle

At the start of every Claude Code session in this repo:
```bash
python3 ~/projects/Sentinel/scripts/sentinel_query.py session-start tidewatch "<brief task description>"
```

At the end of every session:
```bash
python3 ~/projects/Sentinel/scripts/sentinel_query.py session-complete "<summary>"
```

### Check Obligations

Before starting work, check what's owed:
```bash
python3 ~/projects/Sentinel/scripts/sentinel_query.py obligations --repo tidewatch
```

### Cross-Repo Awareness

See what other Claude sessions are doing right now:
```bash
python3 ~/projects/Sentinel/scripts/sentinel_query.py sessions
```

### Memory

Read/write persistent memories that survive across sessions:
```bash
python3 ~/projects/Sentinel/scripts/sentinel_query.py memory-read "<name>"
python3 ~/projects/Sentinel/scripts/sentinel_query.py memory-save "<name>" "<type>" "<description>" "<content>"
python3 ~/projects/Sentinel/scripts/sentinel_query.py memory --search "<search term>"
```

### Important

- **Do NOT use session_log.py** — it is deprecated. sentinel_query.py is the replacement.
- **Do NOT write to flat .md/.json memory files** — all memory goes to MSSQL via sentinel_query.py.
- **Do NOT skip session-start/session-complete** — obligation tracking and cross-repo awareness depend on it.
