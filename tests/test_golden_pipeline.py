# SPDX-License-Identifier: Apache-2.0 OR Commercial
# Copyright (c) 2026 Infoil LLC

"""Golden pipeline test — deterministic end-to-end validation of all Tidewatch subsystems.

21 gates, each testing a real function with real data and hard-coded expected outputs.
Expected pressure values are pre-computed from the documented equation (§3.1):

    P = min(1.0, P_time × M × A × D)  # MATH_GUARD: equation reference
    P_time(t) = 1 - exp(-3 / max(t, 0.01))   for t > 0  # MATH_GUARD
    P_time(t) = 1.0                            for t ≤ 0 (overdue)
    M = 1.5 if material, 1.0 if routine
    A = 1.0 + (dependency_count × 0.1)
    D = 1.0 - (completion_pct × 0.6)

Gates:
  01. Package API Surface — all __all__ exports importable
  02. Type Construction — all 6 types instantiate with valid data
  03. Zone Enum Ordering — all comparison operators correct
  04. Constants Integrity — every constant present and matches expected value
  05. Pressure Known Values — deterministic outputs for 11 pre-computed scenarios
  06. Pressure Edge Cases — no deadline, overdue, timezone handling
  07. Input Validation — ValueError raised on invalid inputs
  08. Zone Classification — pressure_zone boundary correctness
  09. Batch Recalculation — sorting, count, shared-now consistency
  10. Planner Initialization — defaults match constants
  11. Plan Request Generation — zone filtering, top-N, urgency mapping
  12. Plan Completion — complete_plan wrapping with metadata
  13. Triage Stage and List — staging, deduplication, ordering
  14. Triage Accept and Reject — conversion to Obligation, removal
  15. Full Pipeline — triage → pressure → plan → result end-to-end
  16. Sentinel SDK Graceful Degradation — telemetry path without sentinel_sdk
  17. SOB Dataset Generator — deterministic output, valid fields, distributions
  18. Benchmark Baselines — binary, linear, eisenhower known-value scoring
  19. Benchmark Metrics — all four evaluation metrics with hard-coded outputs
  20. Benchmark Runner — run_tidewatch and run_baseline integration
  21. Pressure Invariants — ceiling bound, monotonicity, all-zone coverage
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

# Golden pipeline tests verify exact numerical outputs — reclassified as
# numerical_verification per §4.4.
pytestmark = pytest.mark.numerical_verification

# ── Fixed reference time for deterministic tests ──
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


# ════════════════════════════════════════════════════════════════════
# Gate 01 — Package API Surface
# ════════════════════════════════════════════════════════════════════

_EXPECTED_EXPORTS = [
    "calculate_pressure",
    "pressure_zone",
    "recalculate_batch",
    "bandwidth_adjusted_sort",
    "export_pressure_summary",
    "ComponentSpaceProtocol",
    "PressureComponents",
    "build_pressure_space",
    "PlanStubGenerator",
    "RiskTier",
    "SpeculativePlanner",
    "TriageQueue",
    "CognitiveContext",
    "TaskDemand",
    "estimate_task_demand",
    "Obligation",
    "PressureResult",
    "PlanRequest",
    "PlanResult",
    "Zone",
    "TriageCandidate",
]


class TestGate01_PackageAPISurface:
    """Every __all__ export must be importable from the top-level package."""

    @pytest.mark.parametrize("name", _EXPECTED_EXPORTS)
    def test_export_accessible(self, name: str) -> None:
        import tidewatch
        assert hasattr(tidewatch, name), f"tidewatch.{name} not found"

    def test_all_matches_expected(self) -> None:
        import tidewatch
        assert set(tidewatch.__all__) == set(_EXPECTED_EXPORTS)

    def test_version_present(self) -> None:
        import tidewatch
        assert isinstance(tidewatch.__version__, str)
        assert len(tidewatch.__version__) > 0


# ════════════════════════════════════════════════════════════════════
# Gate 02 — Type Construction
# ════════════════════════════════════════════════════════════════════

class TestGate02_TypeConstruction:
    """All 6 types must instantiate with valid data and expose correct fields."""

    def test_obligation(self) -> None:
        from tidewatch import Obligation
        ob = Obligation(id=1, title="Test", due_date=NOW, materiality="routine")
        assert ob.id == 1
        assert ob.title == "Test"
        assert ob.due_date == NOW
        assert ob.completion_pct == 0.0
        assert ob.dependency_count == 0
        assert ob.status == "active"

    def test_obligation_defaults(self) -> None:
        from tidewatch import Obligation
        ob = Obligation(id="x", title="Minimal")
        assert ob.due_date is None
        assert ob.materiality == "routine"
        assert ob.domain is None
        assert ob.description is None

    def test_pressure_result(self) -> None:
        from tidewatch import PressureResult
        pr = PressureResult(
            obligation_id=1, pressure=0.5, zone="yellow",
            time_pressure=0.5, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
        )
        assert pr.pressure == 0.5
        assert pr.zone == "yellow"

    def test_plan_request(self) -> None:
        from tidewatch import Obligation, PlanRequest, PressureResult
        ob = Obligation(id=1, title="T")
        pr = PressureResult(1, 0.8, "red", 0.8, 1.0, 1.0, 1.0)
        req = PlanRequest(obligation=ob, pressure_result=pr, prompt="p", delivery_urgency="interrupt")
        assert req.delivery_urgency == "interrupt"

    def test_plan_result(self) -> None:
        from tidewatch import PlanResult
        pr = PlanResult(obligation_id=1, plan_text="Do X", zone="red", pressure=0.9)
        assert pr.plan_text == "Do X"
        assert isinstance(pr.created_at, datetime)

    def test_triage_candidate(self) -> None:
        from tidewatch import TriageCandidate
        tc = TriageCandidate(title="File taxes", source="email")
        assert tc.title == "File taxes"
        assert tc.source == "email"
        assert tc.priority == 3
        assert isinstance(tc.staged_at, datetime)

    def test_zone_enum_values(self) -> None:
        from tidewatch import Zone
        assert Zone.GREEN.value == "green"
        assert Zone.YELLOW.value == "yellow"
        assert Zone.ORANGE.value == "orange"
        assert Zone.RED.value == "red"


# ════════════════════════════════════════════════════════════════════
# Gate 03 — Zone Enum Ordering
# ════════════════════════════════════════════════════════════════════

_ZONE_ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]
_LT_PAIRS = [
    (a, b) for i, a in enumerate(_ZONE_ORDER) for b in _ZONE_ORDER[i + 1:]
]
_GT_PAIRS = [(b, a) for a, b in _LT_PAIRS]


class TestGate03_ZoneOrdering:
    """Zone comparison operators must produce correct total ordering."""

    @pytest.mark.parametrize("lesser,greater", _LT_PAIRS,
                             ids=[f"{a}<{b}" for a, b in _LT_PAIRS])
    def test_less_than(self, lesser: str, greater: str) -> None:
        from tidewatch import Zone
        assert getattr(Zone, lesser) < getattr(Zone, greater)

    @pytest.mark.parametrize("greater,lesser", _GT_PAIRS,
                             ids=[f"{a}>{b}" for a, b in _GT_PAIRS])
    def test_greater_than(self, greater: str, lesser: str) -> None:
        from tidewatch import Zone
        assert getattr(Zone, greater) > getattr(Zone, lesser)

    @pytest.mark.parametrize("zone", _ZONE_ORDER)
    def test_le_self(self, zone: str) -> None:
        from tidewatch import Zone
        z = getattr(Zone, zone)
        assert z <= z

    @pytest.mark.parametrize("zone", _ZONE_ORDER)
    def test_ge_self(self, zone: str) -> None:
        from tidewatch import Zone
        z = getattr(Zone, zone)
        assert z >= z

    @pytest.mark.parametrize("zone", _ZONE_ORDER)
    def test_not_lt_self(self, zone: str) -> None:
        from tidewatch import Zone
        z = getattr(Zone, zone)
        assert not (z < z)

    @pytest.mark.parametrize("zone", _ZONE_ORDER)
    def test_not_gt_self(self, zone: str) -> None:
        from tidewatch import Zone
        z = getattr(Zone, zone)
        assert not (z > z)

    def test_not_implemented_for_non_zone(self) -> None:
        from tidewatch import Zone
        assert Zone.GREEN.__lt__(42) is NotImplemented
        assert Zone.GREEN.__gt__(42) is NotImplemented
        assert Zone.GREEN.__le__(42) is NotImplemented
        assert Zone.GREEN.__ge__(42) is NotImplemented


# ════════════════════════════════════════════════════════════════════
# Gate 04 — Constants Integrity
# ════════════════════════════════════════════════════════════════════

_EXPECTED_CONSTANTS = [
    ("RATE_CONSTANT", 3.0),
    ("OVERDUE_PRESSURE", 1.0),
    ("DEPENDENCY_AMPLIFICATION", 0.1),
    ("COMPLETION_DAMPENING", 0.6),
    ("ZONE_YELLOW", 0.30),
    ("ZONE_ORANGE", 0.60),
    ("ZONE_RED", 0.80),
    ("PLANNER_TOP_N", 3),
    ("PLANNER_MAX_STEPS", 3),
    ("PLANNER_MAX_TOKENS", 500),
    ("DEFAULT_DELIVERY_URGENCY", "background"),
    ("BANDWIDTH_FULL_THRESHOLD", 0.99),
    ("BANDWIDTH_HOURS_GOOD", 8.0),
    ("BANDWIDTH_NORMALIZATION_RANGE", 8.0),
    ("MATERIAL_COMPLEXITY_BOOST", 0.2),
    ("MATERIAL_DECISION_BOOST", 0.1),
    ("HARD_FLOOR_DAYS_THRESHOLD", 1.0),
    ("FIT_SCORE_MISMATCH_COMPONENTS", 3),
    ("TIMING_STALE_DAYS", 7),
    ("TIMING_CRITICAL_DAYS", 14),
    ("TIMING_STALE_MULTIPLIER", 1.1),
    ("TIMING_CRITICAL_MULTIPLIER", 1.2),
    ("VIOLATION_AMPLIFICATION", 0.05),
    ("VIOLATION_MAX_AMPLIFICATION", 0.5),
    ("GRAVITY_TIEBREAK_WEIGHT", 0.1),
    ("FORGE_PRESSURE_PAUSE_THRESHOLD", 0.80),
]


class TestGate04_Constants:
    """All tunable constants must be present with documented values."""

    @pytest.mark.parametrize("name,expected", _EXPECTED_CONSTANTS,
                             ids=[c[0] for c in _EXPECTED_CONSTANTS])
    def test_constant_value(self, name: str, expected: object) -> None:
        from tidewatch import constants
        assert getattr(constants, name) == expected

    def test_materiality_weights(self) -> None:
        from tidewatch.constants import MATERIALITY_WEIGHTS
        assert MATERIALITY_WEIGHTS == {"material": 1.5, "routine": 1.0}

    def test_delivery_urgency_map(self) -> None:
        from tidewatch.constants import DELIVERY_URGENCY_MAP
        assert DELIVERY_URGENCY_MAP == {
            "green": "background",
            "yellow": "background",
            "orange": "toast",
            "red": "interrupt",
        }

    def test_planner_min_zones(self) -> None:
        from tidewatch.constants import PLANNER_MIN_ZONES
        assert frozenset({"yellow", "orange", "red"}) == PLANNER_MIN_ZONES


# ════════════════════════════════════════════════════════════════════
# Gate 05 — Pressure Known Values
# ════════════════════════════════════════════════════════════════════

# Pre-computed from equation §3.1 using Python 3.12 math.exp
# Logistic dampening: D = 1 - 0.6 * sigmoid(8 * (pct - 0.5))
_PRESSURE_CASES = [
    # (days_out, materiality, deps, completion, expected_P, expected_zone, label)
    (60, "routine", 0, 0.0, 0.048244256812745, "green", "far_routine"),
    (30, "routine", 0, 0.5, 0.066613807374828, "green", "medium_half_done"),
    (14, "routine", 0, 0.0, 0.190800720574417, "green", "two_weeks"),
    (7,  "routine", 0, 0.0, 0.344799368291446, "yellow", "one_week"),
    (5,  "routine", 2, 0.3, 0.442324200840819, "yellow", "five_days_deps_partial"),
    (3,  "routine", 0, 0.0, 0.625298886973091, "orange", "three_days"),
    (2,  "routine", 0, 0.0, 0.768486073419898, "orange", "two_days"),
    (1,  "routine", 0, 0.0, 0.939958494053918, "red", "one_day"),
    (1,  "material", 3, 0.0, 1.0, "red", "one_day_material_deps"),
    (0,  "routine", 0, 0.0, 0.989208274022745, "red", "due_now"),
    (-5, "material", 0, 0.0, 1.0, "red", "overdue_material"),
]


class TestGate05_PressureKnownValues:
    """Pressure calculation must produce exact hard-coded results."""

    @pytest.mark.parametrize(
        "days_out,materiality,deps,completion,expected_p,expected_zone,label",
        _PRESSURE_CASES,
        ids=[c[6] for c in _PRESSURE_CASES],
    )
    def test_pressure_value(
        self, days_out: int, materiality: str, deps: int, completion: float,
        expected_p: float, expected_zone: str, label: str,
    ) -> None:
        from tidewatch import Obligation, calculate_pressure
        due = NOW + timedelta(days=days_out) if days_out != 0 else NOW
        if days_out < 0:
            due = NOW + timedelta(days=days_out)
        ob = Obligation(
            id=label, title=f"Test {label}",
            due_date=due, materiality=materiality,
            dependency_count=deps, completion_pct=completion,
        )
        result = calculate_pressure(ob, now=NOW)
        assert result.pressure == pytest.approx(expected_p, abs=1e-10), (
            f"{label}: expected P={expected_p}, got P={result.pressure}"
        )
        assert result.zone == expected_zone

    @pytest.mark.parametrize(
        "days_out,materiality,deps,completion,expected_p,expected_zone,label",
        _PRESSURE_CASES,
        ids=[f"{c[6]}_decomposition" for c in _PRESSURE_CASES],
    )
    def test_factor_decomposition(
        self, days_out: int, materiality: str, deps: int, completion: float,
        expected_p: float, expected_zone: str, label: str,
    ) -> None:
        """Verify that pressure = min(1.0, time_p * mat * dep * comp)."""
        from tidewatch import Obligation, calculate_pressure
        due = NOW + timedelta(days=days_out) if days_out != 0 else NOW
        if days_out < 0:
            due = NOW + timedelta(days=days_out)
        ob = Obligation(
            id=label, title=f"Test {label}",
            due_date=due, materiality=materiality,
            dependency_count=deps, completion_pct=completion,
        )
        r = calculate_pressure(ob, now=NOW)
        recomputed = min(
            1.0,
            r.time_pressure * r.materiality_mult * r.dependency_amp * r.completion_damp,
        )
        assert r.pressure == pytest.approx(recomputed, abs=1e-15)
        assert r.obligation_id == label


# ════════════════════════════════════════════════════════════════════
# Gate 06 — Pressure Edge Cases
# ════════════════════════════════════════════════════════════════════

class TestGate06_PressureEdgeCases:
    """Edge conditions: no deadline, overdue, timezone handling."""

    def test_no_deadline_zero_pressure(self) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(id=1, title="No deadline")
        r = calculate_pressure(ob, now=NOW)
        assert r.pressure == 0.0
        assert r.zone == "green"
        assert r.time_pressure == 0.0
        assert r.materiality_mult == 1.0
        assert r.dependency_amp == 1.0
        assert r.completion_damp == 1.0

    def test_overdue_maxes_time_pressure(self) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(id=1, title="Overdue", due_date=NOW - timedelta(days=30))
        r = calculate_pressure(ob, now=NOW)
        assert r.time_pressure == 1.0
        # Logistic dampening at 0% completion: D ≈ 0.989, so P < 1.0 for routine
        assert r.pressure == pytest.approx(0.989208274022745, abs=1e-10)

    def test_naive_datetime_treated_as_utc(self) -> None:
        """Naive datetimes should be treated as UTC (no crash)."""
        from tidewatch import Obligation, calculate_pressure
        naive_due = datetime(2026, 6, 8, 12, 0, 0)  # No tzinfo
        naive_now = datetime(2026, 6, 1, 12, 0, 0)
        ob = Obligation(id=1, title="Naive TZ", due_date=naive_due)
        r = calculate_pressure(ob, now=naive_now)
        # 7 days out — logistic dampening at 0% ≈ 0.989
        assert r.pressure == pytest.approx(0.344799368291446, abs=1e-10)

    def test_full_completion_dampens_pressure(self) -> None:
        import math

        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Done", due_date=NOW + timedelta(days=1),
            completion_pct=1.0,
        )
        r = calculate_pressure(ob, now=NOW)
        # Logistic: D = 1 - 0.6 * sigmoid(8 * (1.0 - 0.5)) = 1 - 0.6 * sigmoid(4)
        sigmoid_4 = 1.0 / (1.0 + math.exp(-4.0))
        expected_damp = 1.0 - 0.6 * sigmoid_4
        assert r.completion_damp == pytest.approx(expected_damp, abs=1e-10)
        assert r.pressure == pytest.approx(0.950212931632136 * expected_damp, abs=1e-10)

    def test_many_dependencies_amplify(self) -> None:
        import math

        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Many deps", due_date=NOW + timedelta(days=7),
            dependency_count=10,
        )
        r = calculate_pressure(ob, now=NOW)
        # dep_amp = 1.0 + 10 × 0.1 × temporal_gate(7d) (§3.2)
        t_gate = 1.0 - math.exp(-3.0 / 7.0)
        expected_dep_amp = 1.0 + 10 * 0.1 * t_gate
        assert r.dependency_amp == pytest.approx(expected_dep_amp, abs=1e-10)
        # Logistic damp at 0%: D ≈ 0.989
        sigmoid_neg4 = 1.0 / (1.0 + math.exp(4.0))
        damp_0 = 1.0 - 0.6 * sigmoid_neg4
        assert r.pressure == pytest.approx(0.348560942468944 * expected_dep_amp * damp_0, abs=1e-10)

    def test_unknown_materiality_defaults_to_one(self) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Unknown mat", due_date=NOW + timedelta(days=7),
            materiality="exotic",
        )
        r = calculate_pressure(ob, now=NOW)
        assert r.materiality_mult == 1.0


# ════════════════════════════════════════════════════════════════════
# Gate 07 — Input Validation
# ════════════════════════════════════════════════════════════════════

_INVALID_COMPLETION = [-0.1, 1.1, 2.0, -1.0]
_INVALID_DEPS = [-1, -5, -100]


class TestGate07_InputValidation:
    """Invalid inputs must raise ValueError, not silently clamp."""

    @pytest.mark.parametrize("bad_pct", _INVALID_COMPLETION)
    def test_invalid_completion_pct(self, bad_pct: float) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Bad pct", due_date=NOW + timedelta(days=7),
            completion_pct=bad_pct,
        )
        with pytest.raises(ValueError, match="completion_pct"):
            calculate_pressure(ob, now=NOW)

    @pytest.mark.parametrize("bad_deps", _INVALID_DEPS)
    def test_invalid_dependency_count(self, bad_deps: int) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Bad deps", due_date=NOW + timedelta(days=7),
            dependency_count=bad_deps,
        )
        with pytest.raises(ValueError, match="dependency_count"):
            calculate_pressure(ob, now=NOW)


# ════════════════════════════════════════════════════════════════════
# Gate 08 — Zone Classification
# ════════════════════════════════════════════════════════════════════

_ZONE_BOUNDARY_CASES = [
    (0.0, "green"),
    (0.001, "green"),
    (0.15, "green"),
    (0.29, "green"),
    (0.299, "green"),
    (0.2999999, "green"),
    (0.30, "yellow"),
    (0.301, "yellow"),
    (0.45, "yellow"),
    (0.59, "yellow"),
    (0.599, "yellow"),
    (0.5999999, "yellow"),
    (0.60, "orange"),
    (0.601, "orange"),
    (0.70, "orange"),
    (0.79, "orange"),
    (0.799, "orange"),
    (0.7999999, "orange"),
    (0.80, "red"),
    (0.801, "red"),
    (0.90, "red"),
    (0.999, "red"),
    (1.0, "red"),
]


class TestGate08_ZoneClassification:
    """pressure_zone() must respect documented boundaries exactly."""

    @pytest.mark.parametrize("pressure,expected_zone", _ZONE_BOUNDARY_CASES,
                             ids=[f"p={c[0]}" for c in _ZONE_BOUNDARY_CASES])
    def test_zone_boundary(self, pressure: float, expected_zone: str) -> None:
        from tidewatch import pressure_zone
        assert pressure_zone(pressure) == expected_zone


# ════════════════════════════════════════════════════════════════════
# Gate 09 — Batch Recalculation
# ════════════════════════════════════════════════════════════════════

class TestGate09_BatchRecalculation:
    """recalculate_batch() must sort descending and share now across batch."""

    def test_batch_sorted_descending(self) -> None:
        from tidewatch import Obligation, recalculate_batch
        obs = [
            Obligation(id=1, title="Far", due_date=NOW + timedelta(days=60)),
            Obligation(id=2, title="Near", due_date=NOW + timedelta(days=1)),
            Obligation(id=3, title="Mid", due_date=NOW + timedelta(days=7)),
        ]
        results = recalculate_batch(obs, now=NOW)
        assert len(results) == 3
        pressures = [r.pressure for r in results]
        assert pressures == sorted(pressures, reverse=True)

    def test_batch_highest_is_nearest_deadline(self) -> None:
        from tidewatch import Obligation, recalculate_batch
        obs = [
            Obligation(id="far", title="Far", due_date=NOW + timedelta(days=60)),
            Obligation(id="near", title="Near", due_date=NOW + timedelta(days=1)),
        ]
        results = recalculate_batch(obs, now=NOW)
        assert results[0].obligation_id == "near"
        assert results[1].obligation_id == "far"

    def test_batch_consistent_with_single(self) -> None:
        """Batch results must match individual calculate_pressure calls."""
        from tidewatch import Obligation, calculate_pressure, recalculate_batch
        obs = [
            Obligation(id=1, title="A", due_date=NOW + timedelta(days=3)),
            Obligation(id=2, title="B", due_date=NOW + timedelta(days=14)),
            Obligation(id=3, title="C", due_date=NOW + timedelta(days=1), materiality="material"),
        ]
        batch = recalculate_batch(obs, now=NOW)
        batch_map = {r.obligation_id: r.pressure for r in batch}
        for ob in obs:
            single = calculate_pressure(ob, now=NOW)
            assert batch_map[ob.id] == pytest.approx(single.pressure, abs=1e-15)

    def test_empty_batch(self) -> None:
        from tidewatch import recalculate_batch
        assert recalculate_batch([], now=NOW) == []

    def test_batch_with_no_deadlines(self) -> None:
        from tidewatch import Obligation, recalculate_batch
        obs = [
            Obligation(id=1, title="A"),
            Obligation(id=2, title="B"),
        ]
        results = recalculate_batch(obs, now=NOW)
        assert all(r.pressure == 0.0 for r in results)


# ════════════════════════════════════════════════════════════════════
# Gate 10 — Planner Initialization
# ════════════════════════════════════════════════════════════════════

class TestGate10_PlannerInit:
    """SpeculativePlanner defaults must match constants."""

    def test_defaults(self) -> None:
        from tidewatch import SpeculativePlanner
        from tidewatch.constants import (
            DEFAULT_DELIVERY_URGENCY,
            DELIVERY_URGENCY_MAP,
            PLANNER_MIN_ZONES,
            PLANNER_TOP_N,
        )
        p = SpeculativePlanner()
        assert p.min_zones == PLANNER_MIN_ZONES
        assert p.top_n == PLANNER_TOP_N
        assert p.delivery_urgency_map == DELIVERY_URGENCY_MAP
        assert p.default_delivery_urgency == DEFAULT_DELIVERY_URGENCY

    def test_custom_min_zones(self) -> None:
        from tidewatch import SpeculativePlanner
        p = SpeculativePlanner(min_zones={"red"})
        assert p.min_zones == frozenset({"red"})

    def test_custom_top_n(self) -> None:
        from tidewatch import SpeculativePlanner
        p = SpeculativePlanner(top_n=10)
        assert p.top_n == 10

    def test_custom_system_prompt(self) -> None:
        from tidewatch import SpeculativePlanner
        p = SpeculativePlanner(system_prompt="Custom")
        assert p.system_prompt == "Custom"

    def test_custom_urgency_map(self) -> None:
        from tidewatch import SpeculativePlanner
        custom = {"red": "page", "orange": "email"}
        p = SpeculativePlanner(delivery_urgency_map=custom)
        assert p.delivery_urgency_map == custom

    def test_custom_default_urgency(self) -> None:
        from tidewatch import SpeculativePlanner
        p = SpeculativePlanner(default_delivery_urgency="ignore")
        assert p.default_delivery_urgency == "ignore"


# ════════════════════════════════════════════════════════════════════
# Gate 11 — Plan Request Generation
# ════════════════════════════════════════════════════════════════════

class TestGate11_PlanRequestGeneration:
    """Plan generation must filter by zone, respect top_n, and map urgency."""

    def _make_obligations(self) -> list:
        from tidewatch import Obligation
        return [
            Obligation(id=1, title="Green item", due_date=NOW + timedelta(days=60)),
            Obligation(id=2, title="Yellow item", due_date=NOW + timedelta(days=7)),
            Obligation(id=3, title="Orange item", due_date=NOW + timedelta(days=3)),
            Obligation(id=4, title="Red item", due_date=NOW + timedelta(days=1), materiality="material"),
        ]

    def test_filters_green_zone(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obs)
        planned_ids = {r.obligation.id for r in requests}
        assert 1 not in planned_ids, "Green zone item should not get a plan"

    def test_includes_yellow_orange_red(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obs)
        planned_ids = {r.obligation.id for r in requests}
        # Items 2 (yellow), 3 (orange), 4 (red) should be planned
        assert {2, 3, 4}.issubset(planned_ids)

    def test_respects_top_n(self) -> None:
        from tidewatch import Obligation, SpeculativePlanner, recalculate_batch
        obs = [
            Obligation(id=i, title=f"Task {i}", due_date=NOW + timedelta(days=i))
            for i in range(1, 8)  # 7 obligations, all close enough to be non-green
        ]
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner(top_n=2)
        requests = planner.generate_plan_requests(results, obligations=obs)
        assert len(requests) <= 2

    def test_urgency_mapping(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obs)
        urgency_by_zone = {r.pressure_result.zone: r.delivery_urgency for r in requests}
        if "yellow" in urgency_by_zone:
            assert urgency_by_zone["yellow"] == "background"
        if "orange" in urgency_by_zone:
            assert urgency_by_zone["orange"] == "toast"
        if "red" in urgency_by_zone:
            assert urgency_by_zone["red"] == "interrupt"

    def test_prompt_contains_obligation_title(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obs)
        for req in requests:
            assert req.obligation.title in req.prompt

    def test_obligation_map_parameter(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        ob_map = {ob.id: ob for ob in obs}
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligation_map=ob_map)
        assert len(requests) > 0

    def test_sorted_by_pressure_descending(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner(top_n=10)
        requests = planner.generate_plan_requests(results, obligations=obs)
        pressures = [r.pressure_result.pressure for r in requests]
        assert pressures == sorted(pressures, reverse=True)

    def test_custom_min_zones_red_only(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obs = self._make_obligations()
        results = recalculate_batch(obs, now=NOW)
        planner = SpeculativePlanner(min_zones={"red"})
        requests = planner.generate_plan_requests(results, obligations=obs)
        for r in requests:
            assert r.pressure_result.zone == "red"


# ════════════════════════════════════════════════════════════════════
# Gate 12 — Plan Completion
# ════════════════════════════════════════════════════════════════════

class TestGate12_PlanCompletion:
    """complete_plan() must wrap LLM output correctly."""

    def test_complete_plan_fields(self) -> None:
        from tidewatch import Obligation, PlanRequest, PressureResult, SpeculativePlanner
        ob = Obligation(id=42, title="Test ob")
        pr = PressureResult(42, 0.85, "red", 0.85, 1.0, 1.0, 1.0)
        req = PlanRequest(obligation=ob, pressure_result=pr, prompt="p", delivery_urgency="interrupt")
        planner = SpeculativePlanner()
        result = planner.complete_plan(req, "Step 1: Do X\nStep 2: Do Y")
        assert result.obligation_id == 42
        assert result.plan_text == "Step 1: Do X\nStep 2: Do Y"
        assert result.zone == "red"
        assert result.pressure == 0.85
        assert isinstance(result.created_at, datetime)
        assert result.created_at.tzinfo is not None

    def test_empty_plan_text(self) -> None:
        from tidewatch import Obligation, PlanRequest, PressureResult, SpeculativePlanner
        ob = Obligation(id=1, title="T")
        pr = PressureResult(1, 0.5, "yellow", 0.5, 1.0, 1.0, 1.0)
        req = PlanRequest(obligation=ob, pressure_result=pr, prompt="p", delivery_urgency="background")
        planner = SpeculativePlanner()
        result = planner.complete_plan(req, "")
        assert result.plan_text == ""
        assert result.obligation_id == 1


# ════════════════════════════════════════════════════════════════════
# Gate 13 — Triage Stage and List
# ════════════════════════════════════════════════════════════════════

class TestGate13_TriageStageList:
    """Triage queue staging, deduplication, and listing."""

    def test_stage_returns_uuid(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(title="File taxes", source="email"))
        assert isinstance(cid, str)
        assert len(cid) > 0

    def test_duplicate_returns_none(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        c = TriageCandidate(title="File taxes", source="email", due_date=NOW)
        cid1 = q.stage(c)
        cid2 = q.stage(TriageCandidate(title="File taxes", source="email", due_date=NOW))
        assert cid1 is not None
        assert cid2 is None

    def test_case_insensitive_dedup(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        q.stage(TriageCandidate(title="File Taxes", source="email"))
        dup = q.stage(TriageCandidate(title="file taxes", source="email"))
        assert dup is None

    def test_different_source_not_duplicate(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid1 = q.stage(TriageCandidate(title="File taxes", source="email"))
        cid2 = q.stage(TriageCandidate(title="File taxes", source="calendar"))
        assert cid1 is not None
        assert cid2 is not None

    def test_list_pending_returns_all(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        q.stage(TriageCandidate(title="A", source="s1"))
        q.stage(TriageCandidate(title="B", source="s1"))
        q.stage(TriageCandidate(title="C", source="s1"))
        pending = q.list_pending()
        assert len(pending) == 3
        titles = [c.title for _, c in pending]
        assert titles == ["A", "B", "C"]

    def test_list_pending_empty_queue(self) -> None:
        from tidewatch import TriageQueue
        q = TriageQueue()
        assert q.list_pending() == []

    def test_list_pending_tuple_structure(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        q.stage(TriageCandidate(title="X", source="test"))
        pending = q.list_pending()
        assert len(pending) == 1
        cid, candidate = pending[0]
        assert isinstance(cid, str)
        assert candidate.title == "X"


# ════════════════════════════════════════════════════════════════════
# Gate 14 — Triage Accept and Reject
# ════════════════════════════════════════════════════════════════════

class TestGate14_TriageAcceptReject:
    """Accept converts to Obligation, reject removes from queue."""

    def test_accept_returns_obligation(self) -> None:
        from tidewatch import Obligation, TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(
            title="Pay invoice", source="email", due_date=NOW,
            domain="financial", context="Invoice #123",
        ))
        ob = q.accept(cid)
        assert isinstance(ob, Obligation)
        assert ob.title == "Pay invoice"
        assert ob.due_date == NOW
        assert ob.domain == "financial"
        assert ob.description == "Invoice #123"
        assert ob.status == "active"

    def test_accept_removes_from_pending(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(title="T", source="s"))
        q.accept(cid)
        assert q.list_pending() == []

    def test_accept_nonexistent_returns_none(self) -> None:
        from tidewatch import TriageQueue
        q = TriageQueue()
        assert q.accept("nonexistent-id") is None

    def test_reject_returns_true(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(title="T", source="s"))
        assert q.reject(cid) is True

    def test_reject_removes_from_pending(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(title="T", source="s"))
        q.reject(cid)
        assert q.list_pending() == []

    def test_reject_nonexistent_returns_false(self) -> None:
        from tidewatch import TriageQueue
        q = TriageQueue()
        assert q.reject("nonexistent-id") is False

    def test_double_accept_returns_none(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        cid = q.stage(TriageCandidate(title="T", source="s"))
        q.accept(cid)
        assert q.accept(cid) is None


# ════════════════════════════════════════════════════════════════════
# Gate 15 — Full Pipeline (triage → pressure → plan → result)
# ════════════════════════════════════════════════════════════════════

class TestGate15_FullPipeline:
    """End-to-end: stage candidates → accept → calculate pressure → plan."""

    @staticmethod
    def _stage_and_accept():
        """Stage candidates, accept all, return obligations."""
        from tidewatch import TriageCandidate, TriageQueue
        q = TriageQueue()
        candidates = [
            TriageCandidate(title="Q1 taxes", source="email", due_date=NOW + timedelta(days=2), domain="financial"),
            TriageCandidate(title="Update docs", source="slack", due_date=NOW + timedelta(days=30), domain="personal_admin"),
            TriageCandidate(title="Contract review", source="email", due_date=NOW + timedelta(days=1), domain="legal"),
        ]
        cids = [q.stage(c) for c in candidates]
        return [q.accept(cid) for cid in cids], q

    def test_triage_stages_and_accepts(self) -> None:
        obligations, q = self._stage_and_accept()
        assert all(ob is not None for ob in obligations)
        assert q.list_pending() == []

    def test_triage_to_pressure(self) -> None:
        from tidewatch import recalculate_batch
        obligations, _ = self._stage_and_accept()
        results = recalculate_batch(obligations, now=NOW)
        assert len(results) == 3
        assert results[0].pressure >= results[1].pressure >= results[2].pressure

    def test_triage_to_plan(self) -> None:
        from tidewatch import SpeculativePlanner, recalculate_batch
        obligations, _ = self._stage_and_accept()
        results = recalculate_batch(obligations, now=NOW)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obligations)
        assert len(requests) > 0
        for req in requests:
            plan = planner.complete_plan(req, f"Plan for {req.obligation.title}")
            assert plan.obligation_id == req.obligation.id

    def test_mixed_accept_reject(self) -> None:
        from tidewatch import TriageCandidate, TriageQueue, recalculate_batch

        q = TriageQueue()
        cid1 = q.stage(TriageCandidate(title="Keep", source="s", due_date=NOW + timedelta(days=3)))
        cid2 = q.stage(TriageCandidate(title="Discard", source="s", due_date=NOW + timedelta(days=5)))
        q.reject(cid2)
        ob = q.accept(cid1)
        assert ob is not None
        results = recalculate_batch([ob], now=NOW)
        assert len(results) == 1
        assert results[0].pressure > 0

    def test_single_obligation_pipeline(self) -> None:
        from tidewatch import Obligation, SpeculativePlanner, calculate_pressure
        ob = Obligation(
            id=99, title="Urgent legal", due_date=NOW + timedelta(days=1),
            materiality="material", dependency_count=2,
        )
        r = calculate_pressure(ob, now=NOW)
        assert r.zone == "red"
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests([r], obligations=[ob])
        assert len(requests) == 1
        plan = planner.complete_plan(requests[0], "Handle immediately")
        assert plan.zone == "red"


# ════════════════════════════════════════════════════════════════════
# Gate 16 — Sentinel SDK Graceful Degradation
# ════════════════════════════════════════════════════════════════════

class TestGate16_SentinelGraceful:
    """recalculate_batch must work without sentinel_sdk installed."""

    def test_batch_without_sentinel_sdk(self) -> None:
        """sentinel_sdk is optional — batch must not raise ImportError."""
        from tidewatch import Obligation, recalculate_batch
        obs = [
            Obligation(id=1, title="Test", due_date=NOW + timedelta(days=3)),
            Obligation(id=2, title="Test2", due_date=NOW + timedelta(days=1)),
        ]
        # This should not raise even if sentinel_sdk is not installed
        results = recalculate_batch(obs, now=NOW)
        assert len(results) == 2

    def test_telemetry_code_path_exists(self) -> None:
        """The try/except ImportError block must exist in pressure.py."""
        import inspect  # noqa: I001

        from tidewatch import pressure
        source = inspect.getsource(pressure.recalculate_batch)
        assert "sentinel_sdk" in source
        assert "ImportError" in source


# ════════════════════════════════════════════════════════════════════
# Gate 17 — SOB Dataset Generator
# ════════════════════════════════════════════════════════════════════

class TestGate17_SOBGenerator:
    """Synthetic Obligation Benchmark must be deterministic and valid."""

    def test_deterministic_output(self) -> None:
        """Same seed → same structure (days_out, domain, etc.) for all fields
        except due_date which depends on wall-clock now."""
        from benchmarks.datasets.generate_obligations import generate
        a = generate(n=50, seed=42)
        b = generate(n=50, seed=42)
        # due_date uses datetime.now() so compare all other fields
        stable_fields = ("id", "title", "materiality", "dependency_count",
                         "completion_pct", "domain", "days_out", "optimal_attention_days")
        for x, y in zip(a, b, strict=True):
            for f in stable_fields:
                assert x[f] == y[f], f"Field {f} differs: {x[f]} != {y[f]}"

    def test_different_seeds_differ(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        a = generate(n=50, seed=42)
        b = generate(n=50, seed=99)
        # At least some non-date fields must differ
        diffs = sum(1 for x, y in zip(a, b, strict=True) if x["materiality"] != y["materiality"])
        assert diffs > 0

    def test_correct_count(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=100, seed=42)
        assert len(data) == 100

    def test_required_fields(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=10, seed=42)
        required = {"id", "title", "due_date", "materiality", "dependency_count",
                     "completion_pct", "domain", "days_out", "optimal_attention_days"}
        for d in data:
            assert required.issubset(d.keys()), f"Missing fields in {d.keys()}"

    def test_valid_domains(self) -> None:
        from benchmarks.datasets.generate_obligations import DOMAINS, generate
        data = generate(n=200, seed=42)
        for d in data:
            assert d["domain"] in DOMAINS

    def test_valid_materiality(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=200, seed=42)
        for d in data:
            assert d["materiality"] in ("material", "routine")

    def test_completion_bounds(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=200, seed=42)
        for d in data:
            assert 0.0 <= d["completion_pct"] <= 1.0

    def test_dependency_bounds(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=200, seed=42)
        for d in data:
            assert 0 <= d["dependency_count"] <= 10

    def test_ids_sequential(self) -> None:
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=50, seed=42)
        assert [d["id"] for d in data] == list(range(1, 51))

    def test_some_overdue(self) -> None:
        """~10% should be overdue (days_out < 0)."""
        from benchmarks.datasets.generate_obligations import generate
        data = generate(n=1000, seed=42)
        overdue = sum(1 for d in data if d["days_out"] < 0)
        # Expect ~100 overdue (10%), allow 50-150 range
        assert 50 <= overdue <= 150


# ════════════════════════════════════════════════════════════════════
# Gate 18 — Benchmark Baselines
# ════════════════════════════════════════════════════════════════════

_BINARY_CASES = [
    (None, 0.0, "no_deadline"),
    (-5.0, 1.0, "overdue_5"),
    (-1.0, 1.0, "overdue_1"),
    (0.0, 1.0, "due_now"),
    (0.001, 0.0, "barely_future"),
    (5.0, 0.0, "five_days"),
    (30.0, 0.0, "thirty_days"),
]

_LINEAR_CASES = [
    (None, 90, 0.0, "no_deadline"),
    (-5.0, 90, 1.0, "overdue"),
    (0.0, 90, 1.0, "due_now"),
    (45.0, 90, 0.5, "half_horizon"),
    (90.0, 90, 0.0, "at_horizon"),
    (180.0, 90, 0.0, "beyond_horizon"),  # MATH_GUARD: max(0, 1 - 2) = 0
    (30.0, 90, 2 / 3, "one_third_horizon"),
]

_EISENHOWER_CASES = [
    # (days_rem, materiality, expected, label)
    (3.0, "material", 1.0, "q1_urgent_important"),
    (3.0, "routine", 0.75, "q3_urgent_unimportant"),
    (30.0, "material", 0.5, "q2_not_urgent_important"),
    (30.0, "routine", 0.0, "q4_not_urgent_unimportant"),
    (7.0, "material", 1.0, "boundary_urgent_important"),
    (7.0, "routine", 0.75, "boundary_urgent_unimportant"),
    (8.0, "material", 0.5, "just_past_threshold_important"),
    (8.0, "routine", 0.0, "just_past_threshold_unimportant"),
    (None, "material", 0.0, "no_deadline"),
]


class TestGate18_Baselines:
    """All three baselines must produce known scores."""

    @pytest.mark.parametrize("days_rem,expected,label", _BINARY_CASES,
                             ids=[c[2] for c in _BINARY_CASES])
    def test_binary(self, days_rem: float | None, expected: float, label: str) -> None:
        from benchmarks.baselines.binary_deadline import score
        assert score(days_remaining=days_rem) == expected

    @pytest.mark.parametrize("days_rem,horizon,expected,label", _LINEAR_CASES,
                             ids=[c[3] for c in _LINEAR_CASES])
    def test_linear(self, days_rem: float | None, horizon: float,
                    expected: float, label: str) -> None:
        from benchmarks.baselines.linear_urgency import score
        assert score(days_remaining=days_rem, horizon=horizon) == pytest.approx(expected, abs=1e-10)

    @pytest.mark.parametrize("days_rem,materiality,expected,label", _EISENHOWER_CASES,
                             ids=[c[3] for c in _EISENHOWER_CASES])
    def test_eisenhower(self, days_rem: float | None, materiality: str,
                        expected: float, label: str) -> None:
        from benchmarks.baselines.eisenhower import score
        assert score(days_remaining=days_rem, materiality=materiality) == expected


# ════════════════════════════════════════════════════════════════════
# Gate 19 — Benchmark Metrics
# ════════════════════════════════════════════════════════════════════

class TestGate19_Metrics:
    """All four evaluation metrics with pre-computed outputs."""

    def test_zone_transition_timeliness_known(self) -> None:
        from benchmarks.metrics import zone_transition_timeliness
        result = zone_transition_timeliness([5.0, 10.0, 3.0], [3.0, 8.0, 5.0])
        assert result == pytest.approx(2.0, abs=1e-10)

    def test_zone_transition_timeliness_perfect(self) -> None:
        from benchmarks.metrics import zone_transition_timeliness
        assert zone_transition_timeliness([5.0], [5.0]) == 0.0

    def test_zone_transition_timeliness_empty(self) -> None:
        from benchmarks.metrics import zone_transition_timeliness
        assert zone_transition_timeliness([], []) == float("inf")

    def test_missed_deadline_rate_known(self) -> None:
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([True, True, False]) == pytest.approx(1 / 3, abs=1e-10)

    def test_missed_deadline_rate_none_missed(self) -> None:
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([True, True, True]) == 0.0

    def test_missed_deadline_rate_all_missed(self) -> None:
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([False, False]) == 1.0

    def test_missed_deadline_rate_empty(self) -> None:
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([]) == 0.0

    def test_attention_efficiency_perfect(self) -> None:
        from benchmarks.metrics import attention_allocation_efficiency
        assert attention_allocation_efficiency([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

    def test_attention_efficiency_worst(self) -> None:
        from benchmarks.metrics import attention_allocation_efficiency
        # d² = (3-1)² + (2-2)² + (1-3)² = 8; 1 - 6*8/(3*8) = -1.0
        assert attention_allocation_efficiency([3, 2, 1], [1, 2, 3]) == pytest.approx(-1.0)

    def test_attention_efficiency_partial(self) -> None:
        from benchmarks.metrics import attention_allocation_efficiency
        # [1,3,2] vs [1,2,3]: d²=0+1+1=2; 1 - 6*2/24 = 0.5
        assert attention_allocation_efficiency([1, 3, 2], [1, 2, 3]) == pytest.approx(0.5)

    def test_attention_efficiency_single(self) -> None:
        from benchmarks.metrics import attention_allocation_efficiency
        assert attention_allocation_efficiency([1], [1]) == 1.0

    def test_false_alarm_rate_known(self) -> None:
        from benchmarks.metrics import false_alarm_rate
        # 2 high alerts, 1 of which completed early → 0.5
        assert false_alarm_rate([True, True, False], [True, False, True]) == pytest.approx(0.5)

    def test_false_alarm_rate_no_alerts(self) -> None:
        from benchmarks.metrics import false_alarm_rate
        assert false_alarm_rate([False, False], [True, True]) == 0.0

    def test_false_alarm_rate_no_false_alarms(self) -> None:
        from benchmarks.metrics import false_alarm_rate
        assert false_alarm_rate([True, True], [False, False]) == 0.0

    def test_false_alarm_rate_all_false_alarms(self) -> None:
        from benchmarks.metrics import false_alarm_rate
        assert false_alarm_rate([True, True], [True, True]) == 1.0


# ════════════════════════════════════════════════════════════════════
# Gate 20 — Benchmark Runner
# ════════════════════════════════════════════════════════════════════

class TestGate20_BenchmarkRunner:
    """run_tidewatch and run_baseline must integrate correctly."""

    def _make_data(self) -> list[dict]:
        return [
            {"id": 1, "title": "T1", "due_date": (NOW + timedelta(days=3)).isoformat(),
             "materiality": "material", "dependency_count": 2, "completion_pct": 0.1,
             "domain": "legal", "days_out": 3},
            {"id": 2, "title": "T2", "due_date": (NOW + timedelta(days=30)).isoformat(),
             "materiality": "routine", "dependency_count": 0, "completion_pct": 0.0,
             "domain": "personal_admin", "days_out": 30},
            {"id": 3, "title": "T3", "due_date": (NOW - timedelta(days=5)).isoformat(),
             "materiality": "routine", "dependency_count": 0, "completion_pct": 0.0,
             "domain": "financial", "days_out": -5},
        ]

    def test_run_tidewatch_returns_scores(self) -> None:
        from benchmarks.run import run_tidewatch
        scores = run_tidewatch(self._make_data(), NOW)
        assert len(scores) == 3
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_run_tidewatch_overdue_is_max(self) -> None:
        from benchmarks.run import run_tidewatch
        scores = run_tidewatch(self._make_data(), NOW)
        # Item 3 is overdue → should have highest pressure (logistic damp at 0% ≈ 0.989)
        assert scores[2] == pytest.approx(0.989208274022745, abs=1e-10)

    def test_run_tidewatch_order_matches_input(self) -> None:
        """Scores must be returned in input order, not pressure order."""
        from benchmarks.run import run_tidewatch
        data = self._make_data()
        scores = run_tidewatch(data, NOW)
        assert len(scores) == len(data)
        # Overdue item (id=3) is at index 2 in input
        assert scores[2] >= scores[1]

    @pytest.mark.parametrize("baseline", ["binary", "linear", "eisenhower"])
    def test_run_baseline(self, baseline: str) -> None:
        from benchmarks.run import run_baseline
        scores = run_baseline(baseline, self._make_data())
        assert len(scores) == 3
        assert all(isinstance(s, float) for s in scores)

    def test_run_baseline_binary_overdue(self) -> None:
        from benchmarks.run import run_baseline
        scores = run_baseline("binary", self._make_data())
        # Item 3 has days_out=-5 → score=1.0; Items 1,2 have days_out>0 → score=0.0
        assert scores[0] == 0.0
        assert scores[1] == 0.0
        assert scores[2] == 1.0


# ════════════════════════════════════════════════════════════════════
# Gate 21 — Pressure Invariants
# ════════════════════════════════════════════════════════════════════

class TestGate21_PressureInvariants:
    """Mathematical invariants that must hold for all inputs."""

    def test_pressure_never_exceeds_one(self) -> None:
        """Saturation bound: P ≤ 1.0 for any valid input."""
        from tidewatch import Obligation, calculate_pressure
        extreme = Obligation(
            id=1, title="Extreme", due_date=NOW - timedelta(days=100),
            materiality="material", dependency_count=10, completion_pct=0.0,
        )
        r = calculate_pressure(extreme, now=NOW)
        assert r.pressure <= 1.0

    def test_pressure_never_negative(self) -> None:
        from tidewatch import Obligation, calculate_pressure
        ob = Obligation(
            id=1, title="Far out", due_date=NOW + timedelta(days=365),
            completion_pct=1.0,
        )
        r = calculate_pressure(ob, now=NOW)
        assert r.pressure >= 0.0

    def test_monotonic_time_pressure(self) -> None:
        """Pressure must increase monotonically as deadline approaches."""
        from tidewatch import Obligation, calculate_pressure
        pressures = []
        for days in [60, 30, 14, 7, 5, 3, 2, 1]:
            ob = Obligation(id=days, title=f"D{days}", due_date=NOW + timedelta(days=days))
            r = calculate_pressure(ob, now=NOW)
            pressures.append(r.pressure)
        for i in range(1, len(pressures)):
            assert pressures[i] > pressures[i - 1], (
                f"Pressure must increase: P({60 - i}) > P({60 - i + 1})"
            )

    def test_materiality_amplifies(self) -> None:
        """Material obligations must have higher pressure than routine."""
        from tidewatch import Obligation, calculate_pressure
        routine = Obligation(id=1, title="R", due_date=NOW + timedelta(days=14))
        material = Obligation(id=2, title="M", due_date=NOW + timedelta(days=14), materiality="material")
        r_r = calculate_pressure(routine, now=NOW)
        r_m = calculate_pressure(material, now=NOW)
        assert r_m.pressure > r_r.pressure

    def test_dependencies_amplify(self) -> None:
        """More dependencies must produce higher pressure."""
        from tidewatch import Obligation, calculate_pressure
        ob0 = Obligation(id=1, title="D0", due_date=NOW + timedelta(days=14), dependency_count=0)
        ob5 = Obligation(id=2, title="D5", due_date=NOW + timedelta(days=14), dependency_count=5)
        r0 = calculate_pressure(ob0, now=NOW)
        r5 = calculate_pressure(ob5, now=NOW)
        assert r5.pressure > r0.pressure

    def test_completion_dampens(self) -> None:
        """Higher completion must produce lower pressure."""
        from tidewatch import Obligation, calculate_pressure
        ob0 = Obligation(id=1, title="C0", due_date=NOW + timedelta(days=7), completion_pct=0.0)
        ob9 = Obligation(id=2, title="C9", due_date=NOW + timedelta(days=7), completion_pct=0.9)
        r0 = calculate_pressure(ob0, now=NOW)
        r9 = calculate_pressure(ob9, now=NOW)
        assert r9.pressure < r0.pressure

    def test_all_zones_reachable(self) -> None:
        """All four zones must be reachable with valid inputs."""
        from tidewatch import Obligation, calculate_pressure
        scenarios = [
            (60, "routine", 0, 0.0, "green"),
            (7, "routine", 0, 0.0, "yellow"),
            (3, "routine", 0, 0.0, "orange"),
            (1, "routine", 0, 0.0, "red"),
        ]
        for days, mat, deps, comp, expected_zone in scenarios:
            ob = Obligation(
                id=days, title=f"Zone-{expected_zone}",
                due_date=NOW + timedelta(days=days),
                materiality=mat, dependency_count=deps, completion_pct=comp,
            )
            r = calculate_pressure(ob, now=NOW)
            assert r.zone == expected_zone, f"Expected {expected_zone}, got {r.zone}"

    def test_batch_large_scale(self) -> None:
        """Batch of 1000 obligations must all satisfy invariants."""
        from benchmarks.datasets.generate_obligations import generate
        from benchmarks.run import run_tidewatch
        data = generate(n=1000, seed=42)
        scores = run_tidewatch(data, NOW)
        assert len(scores) == 1000
        assert all(0.0 <= s <= 1.0 for s in scores), "All pressures must be in [0, 1]"
        # At least some should be high (overdue items with deps/material hit saturation)
        assert max(scores) >= 0.98
        # At least some should be low (far-out items exist)
        assert min(scores) < 0.2
