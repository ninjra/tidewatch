# Tidewatch — Next Session Tasks

**Repo:** Obligation pressure modeling library — continuous urgency scoring, speculative planning, triage queue.
**Consumer:** Sentinel imports `calculate_pressure`, `pressure_zone`, `recalculate_batch`, `SpeculativePlanner`, `Obligation`, `PressureResult`.
**Current:** v0.1.0, 34 tests, 5 core modules, zero runtime dependencies, MIT license.

---

## Priority 1 — Must Do

### 1. Fix hardcoded delivery urgency mapping
**Documented in:** `GENERIC_FIRST_REMEDIATION.md`
**Location:** `tidewatch/planner.py:31-36,124`

**Problem:** `_DELIVERY_URGENCY_MAP` is hardcoded and falls back silently to "background" on unknown zones.

**Fix:**
- Add `delivery_map: dict[str, str] | None = None` parameter to `SpeculativePlanner.__init__()`
- Default to current hardcoded values if None
- Store as `self._delivery_map`
- Use `self._delivery_map` in `generate_plan_requests()` instead of module-level constant
- On unknown zone: log a warning (`logging.getLogger(__name__).warning(...)`) instead of silent fallback
- Validate on init: all known zones (`Zone.GREEN`, `YELLOW`, `ORANGE`, `RED`) have mappings

**Constraint:** All 34 existing tests must pass. Add 3 new tests:
- Custom delivery map works
- Unknown zone logs warning
- Validation catches missing zone mapping

### 2. Add conftest.py
No shared fixtures exist. Create `tests/conftest.py` with:
- `@pytest.fixture` for a standard `Obligation` (id=1, due in 7 days, materiality=False)
- `@pytest.fixture` for a batch of obligations (mix of zones)
- `@pytest.fixture` for `SpeculativePlanner` with default settings

---

## Priority 2 — Should Do

### 3. Test the benchmark suite
`benchmarks/` has implementation code with no test coverage:
- `baselines/binary_deadline.py` — overdue/not-overdue baseline
- `baselines/linear_urgency.py` — linear decay baseline
- `baselines/eisenhower.py` — 4-quadrant matrix baseline
- `metrics.py` — 4 evaluation metrics
- `datasets/generate_obligations.py` — SOB generator (1000 obligations)

Create `tests/test_benchmarks.py` with:
- Each baseline produces valid PressureResult-like output
- Metrics compute without errors on synthetic data
- SOB generator creates expected number/distribution of obligations
- Round-trip: generate → score → evaluate pipeline

### 4. Update README with SSRN link
`README.md` has "[SSRN link pending]". If paper is published, update. If not, leave as-is but note status.

---

## Priority 3 — Backlog

### 5. Zone transition detection
The integration test `test_zone_transitions` exists but the library doesn't expose a first-class zone transition API. Consider adding:
- `detect_transitions(before: list[PressureResult], after: list[PressureResult]) -> list[Transition]`
- Where `Transition` has `obligation_id`, `from_zone`, `to_zone`, `pressure_delta`
- Use case: Sentinel's observer plugin could fire alerts on zone escalations

### 6. Async batch processing
`recalculate_batch()` is synchronous. For Sentinel's heartbeat (recalculating 100+ obligations), an async variant could yield between obligations to avoid blocking the event loop. Low priority — current batch is pure math and fast.

---

## Constraints

- All 34 existing tests must pass after changes
- Zero runtime dependencies — do not add numpy, pandas, or anything else to core
- Benchmarks can use optional deps (matplotlib, pandas, numpy) — that's fine
- Public API in `__init__.py` is frozen — don't change existing function signatures, only add new ones
- Sentinel imports are: `from tidewatch import calculate_pressure, pressure_zone, recalculate_batch`, `from tidewatch import SpeculativePlanner`, `from tidewatch.types import Obligation, PressureResult`
- Run `python3 -m pytest tests/ -q` before committing
- Run `ruff check tidewatch/ tests/` before committing
