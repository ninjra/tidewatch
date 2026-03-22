# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests targeting specific coverage gaps in components.py and pressure.py.

Covers: fallback ComponentSpace, _clamp_normalize edge cases, zombie task guard,
linear dampening branch, empty/edge-case inputs, export_pressure_summary,
Pareto edge cases, and rank normalization edge cases.
"""

from datetime import UTC, datetime, timedelta

import pytest

from tidewatch.components import (
    _clamp_normalize,
    _FallbackComponentSpace,
    build_pressure_space,
)
from tidewatch.pressure import (
    _find_pareto_front,
    _obligation_input_hash,
    _rank_normalize_results,
    apply_zone_capacity,
    calculate_pressure,
    compute_dependency_cap,
    export_pressure_summary,
    pressure_zone,
    recalculate_batch,
    recalculate_stale,
    top_k_obligations,
)
from tidewatch.types import Obligation, PressureResult

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


# ── _clamp_normalize edge cases ──────────────────────────────────────────────


class TestClampNormalize:

    def test_value_below_lo(self):
        assert _clamp_normalize(-1.0, 0.0, 1.0) == 0.0

    def test_value_above_hi(self):
        assert _clamp_normalize(2.0, 0.0, 1.0) == 1.0

    def test_value_at_lo(self):
        assert _clamp_normalize(0.0, 0.0, 1.0) == 0.0

    def test_value_at_hi(self):
        assert _clamp_normalize(1.0, 0.0, 1.0) == 1.0

    def test_value_mid(self):
        assert _clamp_normalize(0.5, 0.0, 1.0) == 0.5

    def test_zero_span(self):
        """When lo == hi, return 0.0."""
        assert _clamp_normalize(5.0, 5.0, 5.0) == 0.0

    def test_custom_bounds(self):
        assert _clamp_normalize(3.0, 1.0, 5.0) == 0.5


# ── FallbackComponentSpace ───────────────────────────────────────────────────


class TestFallbackComponentSpace:

    def test_components_returns_copy(self):
        cs = _FallbackComponentSpace({"a": 1.0, "b": 2.0})
        comps = cs.components
        comps["c"] = 3.0  # Mutate the copy
        assert "c" not in cs.components  # Original unchanged

    def test_component_bounds_returns_copy(self):
        cs = _FallbackComponentSpace({"a": 1.0}, _bounds={"a": (0.0, 1.0)})
        bounds = cs.component_bounds
        bounds["b"] = (0.0, 2.0)
        assert "b" not in cs.component_bounds

    def test_collapsed_product(self):
        cs = _FallbackComponentSpace({"a": 2.0, "b": 3.0, "c": 0.5})
        assert cs.collapsed == 3.0

    def test_collapsed_empty(self):
        cs = _FallbackComponentSpace({})
        assert cs.collapsed == 1.0  # Identity

    def test_weighted_collapse(self):
        cs = _FallbackComponentSpace(
            {"a": 0.5, "b": 1.0},
            _bounds={"a": (0.0, 1.0), "b": (0.0, 1.0)},
        )
        result = cs.weighted_collapse({"a": 2.0, "b": 1.0})
        # a: norm=0.5, weight=2.0 → 1.0
        # b: norm=1.0, weight=1.0 → 1.0
        # total=2.0, weight_sum=3.0 → 2/3
        assert result == pytest.approx(2.0 / 3.0)

    def test_weighted_collapse_zero_weights(self):
        cs = _FallbackComponentSpace({"a": 0.5})
        result = cs.weighted_collapse({})
        # Default weight = 1.0, so it just returns normalized value
        assert result > 0

    def test_dominates_always_none(self):
        cs1 = _FallbackComponentSpace({"a": 1.0})
        cs2 = _FallbackComponentSpace({"a": 0.5})
        assert cs1.dominates(cs2) is None


# ── PressureComponents properties ────────────────────────────────────────────


class TestPressureComponentsProperties:

    def test_pressure_saturated(self):
        pc = build_pressure_space(
            time_pressure=1.0, materiality=1.5,
            dependency_amp=3.0, completion_damp=1.0,
            timing_amp=1.2, violation_amp=1.5,
            obligation_id="test",
        )
        assert pc.pressure <= 1.0

    def test_zone_property(self):
        pc = build_pressure_space(
            time_pressure=0.5, materiality=1.0,
            dependency_amp=1.0, completion_damp=1.0,
            timing_amp=1.0, violation_amp=1.0,
            obligation_id="test",
        )
        assert pc.zone in ("green", "yellow", "orange", "red")

    def test_component_accessors(self):
        pc = build_pressure_space(
            time_pressure=0.35, materiality=1.5,
            dependency_amp=1.2, completion_damp=0.8,
            timing_amp=1.1, violation_amp=1.05,
            obligation_id="test",
        )
        assert pc.time_pressure == pytest.approx(0.35)
        assert pc.materiality_mult == pytest.approx(1.5)
        assert pc.dependency_amp == pytest.approx(1.2)
        assert pc.completion_damp == pytest.approx(0.8)

    def test_collapse_with_weights(self):
        pc = build_pressure_space(
            time_pressure=0.5, materiality=1.0,
            dependency_amp=1.0, completion_damp=1.0,
            timing_amp=1.0, violation_amp=1.0,
            obligation_id="test",
        )
        result = pc.collapse(weights={"time_pressure": 2.0})
        assert result > 0

    def test_collapse_without_weights(self):
        pc = build_pressure_space(
            time_pressure=0.5, materiality=1.0,
            dependency_amp=1.0, completion_damp=1.0,
            timing_amp=1.0, violation_amp=1.0,
            obligation_id="test",
        )
        assert pc.collapse() == pc.pressure

    def test_dominates(self):
        pc1 = build_pressure_space(
            time_pressure=1.0, materiality=1.5,
            dependency_amp=2.0, completion_damp=1.0,
            timing_amp=1.2, violation_amp=1.5,
            obligation_id="a",
        )
        pc2 = build_pressure_space(
            time_pressure=0.5, materiality=1.0,
            dependency_amp=1.0, completion_damp=0.8,
            timing_amp=1.0, violation_amp=1.0,
            obligation_id="b",
        )
        # pc1 dominates pc2 on all dimensions
        result = pc1.dominates(pc2)
        assert result is True or result is None  # True with full Pareto backend, None with fallback


# ── Zombie task guard ────────────────────────────────────────────────────────


class TestZombieTaskGuard:

    def test_completed_done_returns_zero(self):
        """100% complete + status=done → pressure=0.0."""
        ob = Obligation(
            id=1, title="Done task",
            due_date=NOW + timedelta(days=1),
            completion_pct=1.0, status="done",
        )
        result = calculate_pressure(ob, now=NOW)
        assert result.pressure == 0.0
        assert result.zone == "green"

    def test_completed_status_returns_zero(self):
        """100% complete + status=completed → pressure=0.0."""
        ob = Obligation(
            id=1, title="Completed task",
            due_date=NOW + timedelta(days=1),
            completion_pct=1.0, status="completed",
        )
        result = calculate_pressure(ob, now=NOW)
        assert result.pressure == 0.0

    def test_completed_but_active_not_zero(self):
        """100% complete but status=active → still has pressure."""
        ob = Obligation(
            id=1, title="Mislabeled task",
            due_date=NOW + timedelta(days=1),
            completion_pct=1.0, status="active",
        )
        result = calculate_pressure(ob, now=NOW)
        assert result.pressure > 0


# ── Linear dampening branch ──────────────────────────────────────────────────


class TestLinearDampening:

    def test_linear_dampening_mode(self):
        """COMPLETION_DAMPENING_MODE=linear uses D = 1 - pct * 0.6."""
        import tidewatch.pressure as p
        original = p.COMPLETION_DAMPENING_MODE
        try:
            p.COMPLETION_DAMPENING_MODE = "linear"
            ob = Obligation(
                id=1, title="Test", due_date=NOW + timedelta(days=7),
                completion_pct=0.5,
            )
            result = calculate_pressure(ob, now=NOW)
            # D = 1 - 0.5 * 0.6 = 0.7
            assert result.completion_damp == pytest.approx(0.7)
        finally:
            p.COMPLETION_DAMPENING_MODE = original


# ── Pareto edge cases ────────────────────────────────────────────────────────


class TestParetoEdgeCases:

    def test_empty_results(self):
        assert _find_pareto_front([]) == []

    def test_single_result(self):
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        front = _find_pareto_front([result])
        assert len(front) == 1

    def test_result_without_component_space(self):
        """Results with component_space=None go directly to front."""
        r = PressureResult(
            obligation_id=1, pressure=0.5, zone="yellow",
            time_pressure=0.5, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
            component_space=None,
        )
        front = _find_pareto_front([r])
        assert len(front) == 1


# ── Export pressure summary ──────────────────────────────────────────────────


class TestExportPressureSummary:

    def test_empty_results(self):
        summary = export_pressure_summary([])
        assert summary["system_pressure"] == 0.0
        assert summary["red_count"] == 0
        assert summary["obligations_at_risk"] == []

    def test_with_red_items(self):
        obligations = [
            Obligation(id=1, title="Overdue", due_date=NOW - timedelta(days=1),
                       materiality="material"),
            Obligation(id=2, title="Far", due_date=NOW + timedelta(days=30)),
        ]
        results = recalculate_batch(obligations, now=NOW)
        summary = export_pressure_summary(results)
        assert summary["system_pressure"] == 1.0
        assert summary["red_count"] >= 1
        assert summary["should_pause_evolution"] is True

    def test_no_red_items(self):
        obligations = [
            Obligation(id=1, title="Far", due_date=NOW + timedelta(days=60)),
        ]
        results = recalculate_batch(obligations, now=NOW)
        summary = export_pressure_summary(results)
        assert summary["red_count"] == 0
        assert summary["should_pause_evolution"] is False


# ── Rank normalization edge cases ────────────────────────────────────────────


class TestRankNormalizeEdgeCases:

    def test_single_item(self):
        """Single item returns unchanged."""
        ob = Obligation(id=1, title="Solo", due_date=NOW + timedelta(days=7))
        results = recalculate_batch([ob], now=NOW, rank_normalize=True)
        assert len(results) == 1

    def test_no_component_space(self):
        """Results without component_space get empty component dict."""
        r = PressureResult(
            obligation_id=1, pressure=0.5, zone="yellow",
            time_pressure=0.5, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
            component_space=None,
        )
        normalized = _rank_normalize_results([r, r])
        assert len(normalized) == 2


# ── Recalculate stale edge cases ─────────────────────────────────────────────


class TestRecalculateStaleEdgeCases:

    def test_missing_obligation(self):
        """Results for obligations not in the list are kept as-is."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        # Pass empty obligations list
        updated = recalculate_stale([result], [], now=NOW, staleness_budget=1.0)
        assert len(updated) == 1

    def test_no_scored_at(self):
        """Results without scored_at are treated as stale."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        result.scored_at = None
        updated = recalculate_stale([result], [ob], now=NOW, staleness_budget=99999.0)
        assert updated[0].scored_at == NOW


# ── Top K edge cases ─────────────────────────────────────────────────────────


class TestTopKEdgeCases:

    def test_k_larger_than_results(self):
        obligations = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        results = recalculate_batch(obligations, now=NOW)
        top = top_k_obligations(results, k=100)
        assert len(top) == 5


# ── Zone capacity edge cases ────────────────────────────────────────────────


class TestZoneCapacityEdgeCases:

    def test_empty_results(self):
        assert apply_zone_capacity([], zone_capacity=10) == []

    def test_capacity_larger_than_zone(self):
        """No demotion when all zones are under capacity."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        results = recalculate_batch(obligations, now=NOW)
        zones_before = {r.obligation_id: r.zone for r in results}
        capped = apply_zone_capacity(results, zone_capacity=100)
        zones_after = {r.obligation_id: r.zone for r in capped}
        assert zones_before == zones_after


# ── Dependency cap edge cases ────────────────────────────────────────────────


class TestDependencyCapEdgeCases:

    def test_log_scaled_n0(self):
        """N=0 returns min cap."""
        cap = compute_dependency_cap(0, mode="log_scaled")
        assert cap == 20


# ── Input hash ───────────────────────────────────────────────────────────────


class TestInputHash:

    def test_same_obligation_same_hash(self):
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        h1 = _obligation_input_hash(ob)
        h2 = _obligation_input_hash(ob)
        assert h1 == h2

    def test_different_violation_count_different_hash(self):
        ob1 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         violation_count=0)
        ob2 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         violation_count=3)
        assert _obligation_input_hash(ob1) != _obligation_input_hash(ob2)

    def test_different_status_different_hash(self):
        ob1 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         status="active")
        ob2 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         status="done")
        assert _obligation_input_hash(ob1) != _obligation_input_hash(ob2)


# ── Negative dependency count validation ─────────────────────────────────────


class TestValidation:

    def test_negative_dependency_count_raises(self):
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                        dependency_count=-1)
        with pytest.raises(ValueError, match="dependency_count"):
            calculate_pressure(ob, now=NOW)

    def test_completion_pct_above_one_raises(self):
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                        completion_pct=1.5)
        with pytest.raises(ValueError, match="completion_pct"):
            calculate_pressure(ob, now=NOW)

    def test_inf_pressure_zone_raises(self):
        with pytest.raises(ValueError, match="finite"):
            pressure_zone(float("inf"))
