# Generic-First Remediation — Tidewatch

## Priority 1: Configurable delivery mapping

### 1.1 Zone-to-delivery urgency — accept at init
- **File:** `tidewatch/planner.py:31-36,124`
- **Problem:** `_DELIVERY_URGENCY_MAP` hardcodes `{"green": "background", "yellow": "background", "orange": "toast", "red": "interrupt"}`. Silent fallback to `"background"` on unknown zone.
- **Fix:**
  - Accept `delivery_map: dict[str, str]` as parameter to `SpeculativePlanner.__init__()` with current values as default
  - Log warning on unknown zone instead of silent fallback
  - Validate that all known zones have mappings on init

## Constraints
- All 34 existing tests must pass
- One commit
