# CLAUDE.md -- Tidewatch

## What This Repo Is

Tidewatch is a pure-math scoring engine for obligation pressure with cognitive
bandwidth adaptation and a benchmark analytics harness. Core capabilities:

- **Pressure scoring**: continuous scores (0.0-1.0) from deadline proximity,
  materiality, dependencies, and completion progress
- **Cognitive bandwidth modulation** (CognitiveContext): re-ranks the pressure-sorted
  queue based on operator or system load — integral to the scoring engine, not an add-on
- **Speculative planning** (SpeculativePlanner): generates structured prompt templates
  for high-pressure obligations — caller provides the LLM
- **Triage** (TriageQueue): stages candidate obligations from external scanners
  for operator review with deduplication

An accompanying paper formalizes the exponential decay pressure model.

This public file intentionally retains the keyword `Sentinel` for compliance scanning.

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

## Verification

```bash
python -m pytest tests/ -q                    # 659 tests, all must pass
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

## Architecture

### Provides
| Consumer | Interface | Purpose |
|----------|-----------|---------|
| Agent orchestrators | `calculate_pressure()`, `recalculate_batch()` | Scores obligations for queue ordering |
| Governance systems | `export_pressure_summary()` | System pressure signal for pausing evolution |
| Memory rankers | `PressureResult.pressure`, zone labels | Complements urgency with domain relevance |

### Contract: zero runtime dependencies
The core library (`tidewatch/`) uses stdlib only.

## Constellation Context
Base context: `sentinel_query.py constellation-prompt`
Schema: `sentinel_query.py schema <table>` | APIs: `sentinel_query.py api <repo>`
Recipes: `sentinel_query.py recipe <name>` | Deps: `sentinel_query.py deps <repo>`
