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

## Sentinel Integration

This repo is part of the Sentinel ecosystem. Use `sentinel_query.py` for all cross-repo
coordination. The tool lives at `~/projects/Sentinel/scripts/sentinel_query.py`.

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
