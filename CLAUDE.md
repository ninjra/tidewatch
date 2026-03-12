# CLAUDE.md -- Tidewatch

## What This Repo Is

Tidewatch is a standalone Python library + SSRN paper that extracts and
formalizes the obligation pressure engine and speculative planning system
from Sentinel. It models deadline urgency as a continuous pressure field
rather than a binary overdue/not-overdue flag, and uses idle compute cycles
to proactively generate action plans for high-pressure obligations.

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

P = min(1.0, P_time * M * A * D)

- P_time(t) = 1 - exp(-3 / max(t, 0.01)) for t > 0; 1.0 for t <= 0
- M = 1.5 (material) or 1.0 (routine)
- A = 1.0 + (dependency_count * 0.1)
- D = 1.0 - (completion_pct * 0.6)

Zones: green < 0.30, yellow < 0.60, orange < 0.80, red >= 0.80

## Testing

Run before every commit: `python -m pytest tests/ -v`
