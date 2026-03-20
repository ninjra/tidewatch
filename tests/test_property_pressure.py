# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Property-based tests for tidewatch pressure engine.

Uses hypothesis to verify structural invariants that hold for ALL valid inputs,
not just hand-picked scenarios. These complement the golden pipeline tests
(which verify exact known values) with randomized boundary exploration.

Properties verified:
  - Bounds: pressure in [0, 1] for all valid inputs
  - Monotonicity: pressure increases as deadline approaches
  - Monotonicity: pressure increases with more dependencies
  - Monotonicity: pressure decreases with more completion
  - Anti-clamping: saturation does not flatten the signal in normal ranges
  - Zone partition: every pressure maps to exactly one zone
  - Temporal gate: dep_amp converges to static formula as deadline approaches
  - Pareto: dominance relationship is consistent with ranking
  - Ablation: disabling a factor produces <= full pressure
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tidewatch.components import (
    COMP_COMPLETION_DAMP,
    COMP_DEPENDENCY_AMP,
    COMP_MATERIALITY,
    COMP_TIME_PRESSURE,
    COMP_TIMING_AMP,
    COMP_VIOLATION_AMP,
)
from tidewatch.pressure import (
    _temporal_gate,
    calculate_pressure,
    pressure_zone,
    recalculate_batch,
)
from tidewatch.types import Obligation

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

# --- Strategies ---

days_out_strategy = st.floats(min_value=0.01, max_value=365.0)
completion_strategy = st.floats(min_value=0.0, max_value=1.0)
deps_strategy = st.integers(min_value=0, max_value=40)
materiality_strategy = st.sampled_from(["routine", "material"])


def _make_ob(
    days_out: float,
    materiality: str = "routine",
    deps: int = 0,
    completion: float = 0.0,
    **kwargs,
) -> Obligation:
    return Obligation(
        id=kwargs.get("id", 1),
        title="prop-test",
        due_date=NOW + timedelta(days=days_out),
        materiality=materiality,
        dependency_count=deps,
        completion_pct=completion,
        days_in_status=kwargs.get("days_in_status", 0),
        violation_count=kwargs.get("violation_count", 0),
    )


# ── Bounds ───────────────────────────────────────────────────────────────────


class TestBounds:
    """Pressure must stay in [0, 1] for all valid inputs."""

    @given(
        days=days_out_strategy,
        mat=materiality_strategy,
        deps=deps_strategy,
        comp=completion_strategy,
    )
    @settings(max_examples=500)
    def test_pressure_bounded(self, days, mat, deps, comp):
        ob = _make_ob(days, materiality=mat, deps=deps, completion=comp)
        r = calculate_pressure(ob, now=NOW)
        assert 0.0 <= r.pressure <= 1.0

    @given(
        days=days_out_strategy,
        deps=deps_strategy,
        comp=completion_strategy,
        days_stuck=st.integers(min_value=0, max_value=60),
        violations=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=300)
    def test_pressure_bounded_with_amplifiers(self, days, deps, comp, days_stuck, violations):
        """Even with timing + violation amplifiers, pressure stays in [0, 1]."""
        ob = _make_ob(
            days, deps=deps, completion=comp,
            days_in_status=days_stuck, violation_count=violations,
        )
        r = calculate_pressure(ob, now=NOW)
        assert 0.0 <= r.pressure <= 1.0


# ── Monotonicity ──────────────────────────────────────────────────────────────


class TestMonotonicity:
    """Pressure must respond in the correct direction to each factor."""

    @given(
        days_near=st.floats(min_value=0.01, max_value=30.0),
        delta=st.floats(min_value=0.1, max_value=30.0),
    )
    @settings(max_examples=300)
    def test_closer_deadline_higher_pressure(self, days_near, delta):
        """Monotonicity in time: shorter deadline -> higher pressure."""
        ob_near = _make_ob(days_near)
        ob_far = _make_ob(days_near + delta)
        r_near = calculate_pressure(ob_near, now=NOW)
        r_far = calculate_pressure(ob_far, now=NOW)
        assert r_near.pressure >= r_far.pressure

    @given(
        days=days_out_strategy,
        deps_low=st.integers(min_value=0, max_value=19),
    )
    @settings(max_examples=300)
    def test_more_deps_higher_pressure(self, days, deps_low):
        """Monotonicity in dependencies: more deps -> higher pressure."""
        ob_low = _make_ob(days, deps=deps_low)
        ob_high = _make_ob(days, deps=deps_low + 1)
        r_low = calculate_pressure(ob_low, now=NOW)
        r_high = calculate_pressure(ob_high, now=NOW)
        assert r_high.pressure >= r_low.pressure

    @given(
        days=days_out_strategy,
        comp_low=st.floats(min_value=0.0, max_value=0.99),
    )
    @settings(max_examples=300)
    def test_more_completion_lower_pressure(self, days, comp_low):
        """Monotonicity in completion: higher completion -> lower pressure."""
        comp_high = min(1.0, comp_low + 0.01)
        ob_low = _make_ob(days, completion=comp_low)
        ob_high = _make_ob(days, completion=comp_high)
        r_low = calculate_pressure(ob_low, now=NOW)
        r_high = calculate_pressure(ob_high, now=NOW)
        assert r_high.pressure <= r_low.pressure

    @given(days=days_out_strategy)
    @settings(max_examples=200)
    def test_material_higher_than_routine(self, days):
        """Material obligations always have >= pressure than routine."""
        ob_r = _make_ob(days, materiality="routine")
        ob_m = _make_ob(days, materiality="material")
        r_r = calculate_pressure(ob_r, now=NOW)
        r_m = calculate_pressure(ob_m, now=NOW)
        assert r_m.pressure >= r_r.pressure


# ── Anti-clamping ─────────────────────────────────────────────────────────────


class TestAntiClamping:
    """Saturation (min(1.0, ...)) should not flatten the signal in normal ranges.

    For obligations with reasonable parameters (7+ days out, few deps, routine),
    the unsaturated product should be < 1.0, meaning the saturation bound does
    not destroy information.
    """

    @given(
        days=st.floats(min_value=7.0, max_value=365.0),
        deps=st.integers(min_value=0, max_value=3),
        comp=st.floats(min_value=0.0, max_value=0.5),
    )
    @settings(max_examples=300)
    def test_normal_range_not_clamped(self, days, deps, comp):
        """In normal operating range, pressure < 1.0 (not clamped)."""
        ob = _make_ob(days, materiality="routine", deps=deps, completion=comp)
        r = calculate_pressure(ob, now=NOW)
        assert r.pressure < 1.0, (
            f"Unexpected clamping at {days:.1f}d, {deps} deps, {comp:.2f} comp: P={r.pressure}"
        )

    @given(
        days=st.floats(min_value=0.01, max_value=0.5),
        deps=st.integers(min_value=5, max_value=40),
    )
    @settings(max_examples=200)
    def test_extreme_range_clamped(self, days, deps):
        """In extreme range (near deadline + many deps), saturation should engage."""
        ob = _make_ob(days, materiality="material", deps=deps, completion=0.0)
        r = calculate_pressure(ob, now=NOW)
        assert r.pressure == 1.0


# ── Zone partition ────────────────────────────────────────────────────────────


class TestZonePartition:
    """Every pressure value maps to exactly one valid zone."""

    @given(p=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=500)
    def test_all_pressures_have_zone(self, p):
        zone = pressure_zone(p)
        assert zone in {"green", "yellow", "orange", "red"}

    @given(p=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=500)
    def test_zone_boundary_consistency(self, p):
        """Zone must be consistent with boundary thresholds."""
        zone = pressure_zone(p)
        if p < 0.30:
            assert zone == "green"
        elif p < 0.60:
            assert zone == "yellow"
        elif p < 0.80:
            assert zone == "orange"
        else:
            assert zone == "red"


# ── Temporal gate properties ─────────────────────────────────────────────────


class TestTemporalGate:
    """Properties of the dependency temporal gate (§3.2)."""

    @given(t=st.floats(min_value=0.01, max_value=365.0))
    @settings(max_examples=300)
    def test_temporal_gate_bounded(self, t):
        """Temporal gate is in (0, 1] for positive t."""
        gate = _temporal_gate(t)
        assert 0.0 < gate <= 1.0

    def test_temporal_gate_overdue(self):
        """Overdue obligations get full dependency amplification."""
        assert _temporal_gate(0.0) == 1.0
        assert _temporal_gate(-5.0) == 1.0

    @given(
        t_near=st.floats(min_value=0.01, max_value=100.0),
        delta=st.floats(min_value=0.01, max_value=100.0),
    )
    @settings(max_examples=300)
    def test_temporal_gate_monotonic(self, t_near, delta):
        """Closer deadline -> higher temporal gate (more dep amplification)."""
        gate_near = _temporal_gate(t_near)
        gate_far = _temporal_gate(t_near + delta)
        assert gate_near >= gate_far

    @given(days=st.floats(min_value=0.01, max_value=1.0))
    @settings(max_examples=100)
    def test_temporal_gate_near_one_at_short_deadline(self, days):
        """At very short deadlines, temporal gate approaches 1.0."""
        gate = _temporal_gate(days)
        assert gate > 0.9


# ── Pareto ranking ────────────────────────────────────────────────────────────


class TestParetoRanking:
    """Pareto-layered ranking preserves dominance relationships."""

    def test_dominated_result_ranks_lower(self):
        """An obligation dominated on all factors must rank below its dominator."""
        ob_dom = Obligation(
            id=1, title="Dominator",
            due_date=NOW + timedelta(days=1),
            materiality="material", dependency_count=5, completion_pct=0.0,
        )
        ob_sub = Obligation(
            id=2, title="Subordinate",
            due_date=NOW + timedelta(days=7),
            materiality="routine", dependency_count=0, completion_pct=0.5,
        )
        results = recalculate_batch([ob_sub, ob_dom], now=NOW, pareto=True)
        assert results[0].obligation_id == 1

    def test_pareto_agrees_with_scalar_on_dominated_pairs(self):
        """When one obligation dominates another, Pareto and scalar agree on order."""
        obs = [
            Obligation(id=1, title="A", due_date=NOW + timedelta(days=2),
                       materiality="material", dependency_count=3, completion_pct=0.0),
            Obligation(id=2, title="B", due_date=NOW + timedelta(days=10),
                       materiality="routine", dependency_count=0, completion_pct=0.3),
            Obligation(id=3, title="C", due_date=NOW + timedelta(days=30),
                       materiality="routine", dependency_count=0, completion_pct=0.8),
        ]
        scalar = recalculate_batch(obs, now=NOW, pareto=False)
        pareto = recalculate_batch(obs, now=NOW, pareto=True)
        # For fully dominated chains, order should match
        assert [r.obligation_id for r in scalar] == [r.obligation_id for r in pareto]

    def test_pareto_handles_incomparable(self):
        """Incomparable obligations (neither dominates) both appear in same front."""
        # High time pressure, low deps vs low time pressure, high deps
        ob_a = Obligation(
            id=1, title="Urgent-simple",
            due_date=NOW + timedelta(days=1),
            materiality="routine", dependency_count=0, completion_pct=0.0,
        )
        ob_b = Obligation(
            id=2, title="Relaxed-complex",
            due_date=NOW + timedelta(days=30),
            materiality="material", dependency_count=10, completion_pct=0.0,
        )
        results = recalculate_batch([ob_a, ob_b], now=NOW, pareto=True)
        assert len(results) == 2

    @given(
        n=st.integers(min_value=2, max_value=15),
    )
    @settings(max_examples=50)
    def test_pareto_preserves_all_results(self, n):
        """Pareto ranking returns all results (no losses)."""
        obs = [
            Obligation(
                id=i, title=f"Ob-{i}",
                due_date=NOW + timedelta(days=i * 3 + 1),
            )
            for i in range(n)
        ]
        results = recalculate_batch(obs, now=NOW, pareto=True)
        assert len(results) == n


# ── Ablation ──────────────────────────────────────────────────────────────────


class TestAblation:
    """Factor ablation: disabling a factor produces deterministic effects."""

    ALL_COMPONENTS = frozenset({
        COMP_TIME_PRESSURE, COMP_MATERIALITY, COMP_DEPENDENCY_AMP,
        COMP_COMPLETION_DAMP, COMP_TIMING_AMP, COMP_VIOLATION_AMP,
    })

    def test_ablate_single_factor_reduces_or_equals(self):
        """Ablating any amplifying factor should not increase pressure."""
        ob = _make_ob(3, materiality="material", deps=5, completion=0.2)
        full = calculate_pressure(ob, now=NOW)
        for comp in [COMP_MATERIALITY, COMP_DEPENDENCY_AMP, COMP_TIMING_AMP, COMP_VIOLATION_AMP]:
            ablated = calculate_pressure(ob, now=NOW, ablate=frozenset({comp}))
            assert ablated.pressure <= full.pressure + 1e-10, (
                f"Ablating {comp} increased pressure: {ablated.pressure} > {full.pressure}"
            )

    def test_ablate_completion_increases_pressure(self):
        """Ablating completion dampening should increase pressure (removes relief)."""
        ob = _make_ob(3, completion=0.8)
        full = calculate_pressure(ob, now=NOW)
        ablated = calculate_pressure(ob, now=NOW, ablate=frozenset({COMP_COMPLETION_DAMP}))
        assert ablated.pressure >= full.pressure

    def test_ablate_all_gives_one(self):
        """Ablating all factors gives pressure = 1.0 (all components = 1.0)."""
        ob = _make_ob(7)
        result = calculate_pressure(ob, now=NOW, ablate=self.ALL_COMPONENTS)
        assert result.pressure == 1.0

    def test_ablate_none_matches_full(self):
        """Empty ablation set matches full calculation."""
        ob = _make_ob(5, materiality="material", deps=3, completion=0.4)
        full = calculate_pressure(ob, now=NOW)
        no_ablate = calculate_pressure(ob, now=NOW, ablate=frozenset())
        assert full.pressure == no_ablate.pressure

    @given(
        days=days_out_strategy,
        deps=deps_strategy,
        comp=completion_strategy,
    )
    @settings(max_examples=200)
    def test_ablated_pressure_still_bounded(self, days, deps, comp):
        """Ablated results must still be in [0, 1]."""
        ob = _make_ob(days, deps=deps, completion=comp)
        for comp_name in self.ALL_COMPONENTS:
            result = calculate_pressure(ob, now=NOW, ablate=frozenset({comp_name}))
            assert 0.0 <= result.pressure <= 1.0
