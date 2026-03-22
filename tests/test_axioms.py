# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Layer 0 — Axiom verification for tidewatch.

These tests verify pure functions by mathematical properties, not behavior.
Every assertion traces to a provable property of the function's domain.
No mocks. No I/O. No randomness (seeded RNG where needed).

Axiom verification criteria:
  1. Identity: f(identity_input) == identity_output
  2. Bounds: output stays within provable bounds
  3. Monotonicity: if input increases, output moves in provable direction
  4. Symmetry: f(a,b) == f(b,a) where commutative
  5. Idempotence: f(f(x)) == f(x) where applicable
  6. Inverse: round-trip serialization preserves state
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from tidewatch.constants import (
    ADAPTIVE_K_MAX,
    ADAPTIVE_K_MIN,
    BANDWIDTH_MIN_FLOOR,
    BANDWIDTH_NO_DATA,
    COMPLETION_DAMPENING,
    COMPLETION_LOGISTIC_K,
    COMPLETION_LOGISTIC_MID,
    DEPENDENCY_AMPLIFICATION,
    DEPENDENCY_CAP_LOG_MIN,
    DEPENDENCY_COUNT_CAP,
    DIVISION_GUARD,
    EVOLUTION_PAUSE_THRESHOLD,
    FANOUT_TEMPORAL_K,
    HALFLIFE_BASE,
    MATERIALITY_WEIGHTS,
    OVERDUE_PRESSURE,
    RATE_CONSTANT,
    TIMING_MAX_MULTIPLIER,
    TIMING_MID_DAYS,
    VIOLATION_AMPLIFICATION,
    VIOLATION_MAX_AMPLIFICATION,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
    clamp_unit,
    normalize_hours,
    saturate,
)
from tidewatch.components import (
    PressureComponents,
    _FallbackComponentSpace,
    _clamp_normalize,
    build_pressure_space,
)
from tidewatch.pressure import (
    compute_adaptive_k,
    compute_dependency_cap,
    pressure_zone,
    export_pressure_summary,
    top_k_obligations,
    apply_zone_capacity,
    bandwidth_adjusted_sort,
    calculate_pressure,
)
from tidewatch.types import (
    CognitiveContext,
    DeadlineDistribution,
    Obligation,
    PressureResult,
    RiskTier,
    TaskDemand,
    Zone,
    estimate_task_demand,
)
from tidewatch.wearable_spec import (
    WearableReading,
    normalize_hrv,
    normalize_pain,
    normalize_sleep_hours,
    normalize_sleep_score,
    normalize_strain,
    reading_to_context,
)


# ── saturate axioms ──────────────────────────────────────────────────────────


class TestSaturate:
    """Verify saturate enforces the [0, 1] pressure domain."""

    def test_identity_interior(self):
        """Values in (0,1) pass through unchanged."""
        assert saturate(0.5) == 0.5

    def test_bounds_lower(self):
        """Negative values clamp to 0.0."""
        assert saturate(-1.0) == 0.0
        assert saturate(-100.0) == 0.0

    def test_bounds_upper(self):
        """Values above 1.0 clamp to 1.0."""
        assert saturate(1.5) == 1.0
        assert saturate(100.0) == 1.0

    def test_boundary_exact(self):
        """Boundary values: 0.0 and 1.0 are in domain."""
        assert saturate(0.0) == 0.0
        assert saturate(1.0) == 1.0

    def test_idempotence(self):
        """saturate(saturate(x)) == saturate(x) for all x."""
        for x in [-1.0, 0.0, 0.5, 1.0, 2.0]:
            assert saturate(saturate(x)) == saturate(x)

    def test_monotonicity(self):
        """If a < b then saturate(a) <= saturate(b)."""
        values = [-1.0, -0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
        for i in range(len(values) - 1):
            assert saturate(values[i]) <= saturate(values[i + 1])


# ── clamp_unit axioms ────────────────────────────────────────────────────────


class TestClampUnit:
    """Verify clamp_unit matches saturate behavior (same domain enforcement)."""

    def test_identity_interior(self):
        assert clamp_unit(0.3) == 0.3

    def test_bounds(self):
        assert clamp_unit(-0.5) == 0.0
        assert clamp_unit(1.5) == 1.0

    def test_idempotence(self):
        for x in [-1.0, 0.0, 0.5, 1.0, 2.0]:
            assert clamp_unit(clamp_unit(x)) == clamp_unit(x)

    def test_equivalence_with_saturate(self):
        """clamp_unit and saturate use the same bounds."""
        for x in [-2.0, -0.5, 0.0, 0.3, 0.7, 1.0, 1.5, 5.0]:
            assert clamp_unit(x) == saturate(x)


# ── normalize_hours axioms ───────────────────────────────────────────────────


class TestNormalizeHours:
    """Verify normalize_hours maps hours-since-sleep to [0, 1]."""

    def test_identity_at_good(self):
        """0 to good hours all return 1.0 (full bandwidth)."""
        assert normalize_hours(0.0, good=8.0, span=8.0) == 1.0
        assert normalize_hours(4.0, good=8.0, span=8.0) == 1.0
        assert normalize_hours(8.0, good=8.0, span=8.0) == 1.0

    def test_floor_at_limit(self):
        """At good + span hours, returns 0.0."""
        assert normalize_hours(16.0, good=8.0, span=8.0) == 0.0
        assert normalize_hours(20.0, good=8.0, span=8.0) == 0.0

    def test_midpoint(self):
        """Midpoint of the degradation ramp returns 0.5."""
        assert normalize_hours(12.0, good=8.0, span=8.0) == pytest.approx(0.5)

    def test_bounds(self):
        """Output always in [0, 1]."""
        for hours in [0, 4, 8, 12, 16, 24, 100]:
            result = normalize_hours(float(hours), good=8.0, span=8.0)
            assert 0.0 <= result <= 1.0

    def test_monotone_decreasing(self):
        """More hours since sleep -> lower score."""
        values = [normalize_hours(float(h), good=8.0, span=8.0) for h in range(0, 25)]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1]


# ── _clamp_normalize axioms ─────────────────────────────────────────────────


class TestClampNormalize:
    """Verify _clamp_normalize maps [lo, hi] to [0, 1]."""

    def test_identity_at_lo(self):
        assert _clamp_normalize(0.0, 0.0, 1.0) == 0.0

    def test_identity_at_hi(self):
        assert _clamp_normalize(1.0, 0.0, 1.0) == 1.0

    def test_midpoint(self):
        assert _clamp_normalize(0.5, 0.0, 1.0) == pytest.approx(0.5)

    def test_below_lo_clamps_to_zero(self):
        assert _clamp_normalize(-1.0, 0.0, 1.0) == 0.0

    def test_above_hi_clamps_to_one(self):
        assert _clamp_normalize(2.0, 0.0, 1.0) == 1.0

    def test_nonzero_range(self):
        """Verify with bounds [1.0, 5.0]."""
        assert _clamp_normalize(1.0, 1.0, 5.0) == 0.0
        assert _clamp_normalize(3.0, 1.0, 5.0) == pytest.approx(0.5)
        assert _clamp_normalize(5.0, 1.0, 5.0) == 1.0

    def test_degenerate_span_returns_zero(self):
        """When lo == hi, span is 0, returns 0.0."""
        assert _clamp_normalize(5.0, 5.0, 5.0) == 0.0

    def test_bounds_output(self):
        """Output always in [0, 1] for any inputs."""
        for v in [-10.0, 0.0, 0.5, 1.0, 3.0, 10.0]:
            result = _clamp_normalize(v, 1.0, 5.0)
            assert 0.0 <= result <= 1.0

    def test_monotonicity(self):
        """Within bounds, increasing value -> increasing normalized output."""
        values = [_clamp_normalize(float(v), 0.0, 10.0) for v in range(-5, 16)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1]


# ── FallbackComponentSpace axioms ────────────────────────────────────────────


class TestFallbackComponentSpace:
    """Verify the ComponentSpace collapse operations."""

    def test_collapsed_product_identity(self):
        """Product of all-ones components is 1.0."""
        space = _FallbackComponentSpace(
            _components={"a": 1.0, "b": 1.0, "c": 1.0},
        )
        assert space.collapsed == pytest.approx(1.0)

    def test_collapsed_product(self):
        """Product of components: 0.5 * 0.8 = 0.4."""
        space = _FallbackComponentSpace(
            _components={"a": 0.5, "b": 0.8},
        )
        assert space.collapsed == pytest.approx(0.4)

    def test_collapsed_zero_absorbs(self):
        """Zero in any component zeros the product."""
        space = _FallbackComponentSpace(
            _components={"a": 0.0, "b": 0.8, "c": 1.0},
        )
        assert space.collapsed == 0.0

    def test_weighted_collapse_uniform_weights(self):
        """Uniform weights = unweighted mean after normalization."""
        space = _FallbackComponentSpace(
            _components={"a": 0.5, "b": 0.5},
            _bounds={"a": (0.0, 1.0), "b": (0.0, 1.0)},
        )
        result = space.weighted_collapse({"a": 1.0, "b": 1.0})
        assert result == pytest.approx(0.5)

    def test_weighted_collapse_empty_weights_uses_defaults(self):
        """Missing weights default to 1.0."""
        space = _FallbackComponentSpace(
            _components={"a": 0.5, "b": 0.5},
            _bounds={"a": (0.0, 1.0), "b": (0.0, 1.0)},
        )
        result_explicit = space.weighted_collapse({"a": 1.0, "b": 1.0})
        result_default = space.weighted_collapse({})
        assert result_explicit == pytest.approx(result_default)

    def test_dominates_always_none_for_fallback(self):
        """Fallback implementation returns None (incomparable)."""
        s1 = _FallbackComponentSpace(_components={"a": 1.0})
        s2 = _FallbackComponentSpace(_components={"a": 0.5})
        assert s1.dominates(s2) is None

    def test_components_returns_copy(self):
        """components property returns a copy, not the original dict."""
        original = {"a": 0.5}
        space = _FallbackComponentSpace(_components=original)
        returned = space.components
        returned["a"] = 999.0
        assert space.components["a"] == 0.5  # Original unchanged


# ── PressureComponents axioms ────────────────────────────────────────────────


class TestPressureComponents:
    """Verify PressureComponents pressure collapse and zone classification."""

    def test_pressure_bounded_zero_one(self):
        """Pressure is always in [0, 1] (saturate applied)."""
        pc = build_pressure_space(
            time_pressure=0.95, materiality=1.5, dependency_amp=3.0,
            completion_damp=1.0, timing_amp=1.2, violation_amp=1.5,
            obligation_id=1,
        )
        assert 0.0 <= pc.pressure <= 1.0

    def test_pressure_identity_all_ones(self):
        """All factors at identity (1.0) yield pressure = 1.0 (time_pressure=1.0)."""
        pc = build_pressure_space(
            time_pressure=1.0, materiality=1.0, dependency_amp=1.0,
            completion_damp=1.0, timing_amp=1.0, violation_amp=1.0,
            obligation_id=1,
        )
        assert pc.pressure == pytest.approx(1.0)

    def test_pressure_zero_when_time_zero(self):
        """Zero time pressure -> zero overall pressure."""
        pc = build_pressure_space(
            time_pressure=0.0, materiality=1.5, dependency_amp=2.0,
            completion_damp=1.0, timing_amp=1.2, violation_amp=1.5,
            obligation_id=1,
        )
        assert pc.pressure == 0.0

    def test_collapse_default_equals_pressure(self):
        """collapse() without weights returns the saturated product."""
        pc = build_pressure_space(
            time_pressure=0.5, materiality=1.0, dependency_amp=1.0,
            completion_damp=0.8, timing_amp=1.0, violation_amp=1.0,
            obligation_id=1,
        )
        assert pc.collapse() == pytest.approx(pc.pressure)

    def test_zone_red(self):
        """High pressure -> red zone."""
        pc = build_pressure_space(
            time_pressure=0.9, materiality=1.5, dependency_amp=1.0,
            completion_damp=1.0, timing_amp=1.0, violation_amp=1.0,
            obligation_id=1,
        )
        assert pc.zone == "red"

    def test_zone_green(self):
        """Low pressure -> green zone."""
        pc = build_pressure_space(
            time_pressure=0.1, materiality=1.0, dependency_amp=1.0,
            completion_damp=1.0, timing_amp=1.0, violation_amp=1.0,
            obligation_id=1,
        )
        assert pc.zone == "green"

    def test_component_accessors(self):
        """Property accessors reflect constructed values."""
        pc = build_pressure_space(
            time_pressure=0.7, materiality=1.5, dependency_amp=1.2,
            completion_damp=0.9, timing_amp=1.1, violation_amp=1.05,
            obligation_id=99,
        )
        assert pc.time_pressure == 0.7
        assert pc.materiality_mult == 1.5
        assert pc.dependency_amp == 1.2
        assert pc.completion_damp == 0.9


# ── pressure_zone axioms ────────────────────────────────────────────────────


class TestPressureZone:
    """Verify zone classification satisfies boundary invariants."""

    def test_zone_boundaries(self):
        """Exact boundary values land in correct zones."""
        assert pressure_zone(0.0) == "green"
        assert pressure_zone(0.29) == "green"
        assert pressure_zone(0.30) == "yellow"
        assert pressure_zone(0.59) == "yellow"
        assert pressure_zone(0.60) == "orange"
        assert pressure_zone(0.79) == "orange"
        assert pressure_zone(0.80) == "red"
        assert pressure_zone(1.0) == "red"

    def test_monotonicity(self):
        """Higher pressure never yields a lower zone.

        Zone ordering: green < yellow < orange < red.
        """
        zone_order = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
        pressures = [i / 100.0 for i in range(101)]
        zones = [pressure_zone(p) for p in pressures]
        for i in range(len(zones) - 1):
            assert zone_order[zones[i]] <= zone_order[zones[i + 1]]

    def test_exhaustive_coverage(self):
        """Every valid pressure maps to exactly one of the four zones."""
        valid_zones = {"green", "yellow", "orange", "red"}
        for p in [i / 100.0 for i in range(101)]:
            assert pressure_zone(p) in valid_zones

    def test_nan_raises(self):
        """NaN pressure raises ValueError."""
        with pytest.raises(ValueError):
            pressure_zone(float("nan"))

    def test_inf_raises(self):
        """Inf pressure raises ValueError."""
        with pytest.raises(ValueError):
            pressure_zone(float("inf"))


# ── compute_adaptive_k axioms ────────────────────────────────────────────────


class TestComputeAdaptiveK:
    """Verify adaptive rate constant selection properties."""

    def test_bounds(self):
        """Result always in [ADAPTIVE_K_MIN, ADAPTIVE_K_MAX]."""
        for median in [0.1, 1.0, 7.0, 45.0, 365.0]:
            dist = DeadlineDistribution(min_days=0, max_days=100, median_days=median, count=100)
            k = compute_adaptive_k(dist)
            assert ADAPTIVE_K_MIN <= k <= ADAPTIVE_K_MAX

    def test_monotonicity_with_median(self):
        """Larger median -> larger k (curve stretches for wider populations)."""
        k_values = []
        for median in [1.0, 7.0, 14.0, 30.0, 60.0]:
            dist = DeadlineDistribution(min_days=0, max_days=100, median_days=median, count=100)
            k_values.append(compute_adaptive_k(dist))
        for i in range(len(k_values) - 1):
            assert k_values[i] <= k_values[i + 1]

    def test_negative_median_returns_default(self):
        """Negative median (all overdue) returns default RATE_CONSTANT."""
        dist = DeadlineDistribution(min_days=-5, max_days=-1, median_days=-3, count=10)
        assert compute_adaptive_k(dist) == RATE_CONSTANT

    def test_zero_median_returns_default(self):
        """Zero median returns default RATE_CONSTANT."""
        dist = DeadlineDistribution(min_days=0, max_days=0, median_days=0, count=10)
        assert compute_adaptive_k(dist) == RATE_CONSTANT

    def test_formula_at_default_median(self):
        """At median=7d with ZONE_YELLOW=0.30: k = -7 * ln(0.70) ~ 2.497."""
        dist = DeadlineDistribution(min_days=0, max_days=14, median_days=7.0, count=10)
        k = compute_adaptive_k(dist)
        expected = -7.0 * math.log(1.0 - ZONE_YELLOW)
        assert k == pytest.approx(expected)


# ── compute_dependency_cap axioms ────────────────────────────────────────────


class TestComputeDependencyCap:
    """Verify dependency cap modes."""

    def test_fixed_mode_returns_constant(self):
        """Fixed mode returns DEPENDENCY_COUNT_CAP regardless of population."""
        for n in [1, 10, 100, 10000]:
            assert compute_dependency_cap(n, mode="fixed") == DEPENDENCY_COUNT_CAP

    def test_log_scaled_floor(self):
        """Log-scaled mode never goes below DEPENDENCY_CAP_LOG_MIN."""
        for n in [0, 1, 2, 5]:
            cap = compute_dependency_cap(n, mode="log_scaled")
            assert cap >= DEPENDENCY_CAP_LOG_MIN

    def test_log_scaled_monotonicity(self):
        """Larger populations -> equal or larger cap."""
        caps = [compute_dependency_cap(n, mode="log_scaled") for n in [1, 10, 100, 1000, 10000]]
        for i in range(len(caps) - 1):
            assert caps[i] <= caps[i + 1]

    def test_unknown_mode_raises(self):
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown"):
            compute_dependency_cap(100, mode="invalid")


# ── Zone enum axioms ─────────────────────────────────────────────────────────


class TestZoneEnum:
    """Verify Zone ordering is a total order."""

    def test_strict_ordering(self):
        """GREEN < YELLOW < ORANGE < RED."""
        assert Zone.GREEN < Zone.YELLOW
        assert Zone.YELLOW < Zone.ORANGE
        assert Zone.ORANGE < Zone.RED

    def test_reflexive_equality(self):
        """Each zone equals itself."""
        for z in Zone:
            assert z == z
            assert z <= z
            assert z >= z

    def test_antisymmetric(self):
        """If a < b then not b < a."""
        assert Zone.GREEN < Zone.RED
        assert not Zone.RED < Zone.GREEN

    def test_transitive(self):
        """If GREEN < YELLOW and YELLOW < RED then GREEN < RED."""
        assert Zone.GREEN < Zone.RED


# ── calculate_pressure axioms ────────────────────────────────────────────────


class TestCalculatePressure:
    """Verify calculate_pressure satisfies mathematical invariants."""

    _NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _make_ob(self, **kwargs) -> Obligation:
        defaults = dict(
            id=1, title="test",
            due_date=self._NOW + timedelta(days=7),
            materiality="routine",
            dependency_count=0,
            completion_pct=0.0,
        )
        defaults.update(kwargs)
        return Obligation(**defaults)

    def test_bounds(self):
        """Pressure always in [0, 1]."""
        for days in [0.1, 1, 3, 7, 14, 30, 90, 365]:
            ob = self._make_ob(due_date=self._NOW + timedelta(days=days))
            r = calculate_pressure(ob, now=self._NOW)
            assert 0.0 <= r.pressure <= 1.0

    def test_monotone_decreasing_with_time(self):
        """More days remaining -> lower pressure (monotone decreasing)."""
        pressures = []
        for days in [1, 3, 7, 14, 30, 60]:
            ob = self._make_ob(due_date=self._NOW + timedelta(days=days))
            pressures.append(calculate_pressure(ob, now=self._NOW).pressure)
        for i in range(len(pressures) - 1):
            assert pressures[i] >= pressures[i + 1]

    def test_overdue_maximum_pressure(self):
        """Overdue obligation has time_pressure = 1.0 (OVERDUE_PRESSURE)."""
        ob = self._make_ob(due_date=self._NOW - timedelta(days=1))
        r = calculate_pressure(ob, now=self._NOW)
        assert r.time_pressure == OVERDUE_PRESSURE

    def test_no_deadline_zero_pressure(self):
        """Obligation without deadline has zero pressure."""
        ob = self._make_ob(due_date=None)
        r = calculate_pressure(ob, now=self._NOW)
        assert r.pressure == 0.0
        assert r.zone == "green"

    def test_material_amplifies(self):
        """Material obligations have higher pressure than routine."""
        ob_routine = self._make_ob(materiality="routine")
        ob_material = self._make_ob(materiality="material")
        p_r = calculate_pressure(ob_routine, now=self._NOW).pressure
        p_m = calculate_pressure(ob_material, now=self._NOW).pressure
        assert p_m > p_r

    def test_materiality_multiplier_values(self):
        """Materiality multiplier matches constants."""
        ob = self._make_ob(materiality="material")
        r = calculate_pressure(ob, now=self._NOW)
        assert r.materiality_mult == MATERIALITY_WEIGHTS["material"]

    def test_dependencies_amplify(self):
        """More dependencies -> higher pressure (at same time to deadline)."""
        ob_none = self._make_ob(dependency_count=0)
        ob_deps = self._make_ob(dependency_count=5)
        p0 = calculate_pressure(ob_none, now=self._NOW).pressure
        p5 = calculate_pressure(ob_deps, now=self._NOW).pressure
        assert p5 >= p0

    def test_completion_dampens(self):
        """Higher completion -> lower pressure."""
        ob_fresh = self._make_ob(completion_pct=0.0)
        ob_half = self._make_ob(completion_pct=0.5)
        ob_done = self._make_ob(completion_pct=0.9)
        p0 = calculate_pressure(ob_fresh, now=self._NOW).pressure
        p50 = calculate_pressure(ob_half, now=self._NOW).pressure
        p90 = calculate_pressure(ob_done, now=self._NOW).pressure
        assert p0 >= p50 >= p90

    def test_determinism(self):
        """Same inputs -> same output (no randomness)."""
        ob = self._make_ob()
        r1 = calculate_pressure(ob, now=self._NOW)
        r2 = calculate_pressure(ob, now=self._NOW)
        assert r1.pressure == r2.pressure
        assert r1.zone == r2.zone

    def test_zombie_task_zeroed(self):
        """100% complete + done status -> zero pressure (#1212)."""
        ob = self._make_ob(completion_pct=1.0, status="done")
        r = calculate_pressure(ob, now=self._NOW)
        assert r.pressure == 0.0
        assert r.zone == "green"

    def test_invalid_completion_raises(self):
        """completion_pct outside [0, 1] raises ValueError."""
        ob = self._make_ob(completion_pct=1.5)
        with pytest.raises(ValueError, match="completion_pct"):
            calculate_pressure(ob, now=self._NOW)

    def test_negative_deps_raises(self):
        """Negative dependency_count raises ValueError."""
        ob = self._make_ob(dependency_count=-1)
        with pytest.raises(ValueError, match="dependency_count"):
            calculate_pressure(ob, now=self._NOW)

    def test_rate_constant_override(self):
        """Custom rate_constant changes pressure (higher k -> steeper curve)."""
        ob = self._make_ob(due_date=self._NOW + timedelta(days=7))
        r_default = calculate_pressure(ob, now=self._NOW)
        r_high_k = calculate_pressure(ob, now=self._NOW, rate_constant=10.0)
        # Higher k means more pressure at the same time distance
        assert r_high_k.pressure >= r_default.pressure


# ── Pressure equation factor axioms ──────────────────────────────────────────


class TestPressureFactors:
    """Verify individual pressure equation factors via the internal API."""

    def test_time_pressure_formula(self):
        """P_time(7) = 1 - exp(-3/7) ~ 0.349 with default k=3."""
        expected = 1.0 - math.exp(-RATE_CONSTANT / 7.0)
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        ob = Obligation(id=1, title="t", due_date=now + timedelta(days=7))
        r = calculate_pressure(ob, now=now)
        assert r.time_pressure == pytest.approx(expected, rel=1e-6)

    def test_completion_dampening_at_zero(self):
        """D(0.0) = 1.0 - (0.6 * sigmoid(-4)) ~ 1.0 (minimal dampening)."""
        sigmoid_at_zero = 1.0 / (1.0 + math.exp(-COMPLETION_LOGISTIC_K * (0.0 - COMPLETION_LOGISTIC_MID)))
        expected = 1.0 - COMPLETION_DAMPENING * sigmoid_at_zero
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        ob = Obligation(id=1, title="t", due_date=now + timedelta(days=7), completion_pct=0.0)
        r = calculate_pressure(ob, now=now)
        assert r.completion_damp == pytest.approx(expected, rel=1e-6)

    def test_completion_dampening_at_full(self):
        """D(1.0) = 1.0 - (0.6 * sigmoid(4)) ~ 0.41."""
        sigmoid_at_one = 1.0 / (1.0 + math.exp(-COMPLETION_LOGISTIC_K * (1.0 - COMPLETION_LOGISTIC_MID)))
        expected = 1.0 - COMPLETION_DAMPENING * sigmoid_at_one
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        ob = Obligation(id=1, title="t", due_date=now + timedelta(days=7), completion_pct=1.0)
        r = calculate_pressure(ob, now=now)
        assert r.completion_damp == pytest.approx(expected, rel=1e-6)

    def test_completion_dampening_bounds(self):
        """D(pct) is always in (0, 1] for pct in [0, 1]."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        for pct in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            ob = Obligation(id=1, title="t", due_date=now + timedelta(days=7), completion_pct=pct)
            r = calculate_pressure(ob, now=now)
            assert 0.0 < r.completion_damp <= 1.0

    def test_dep_amp_identity_at_zero_deps(self):
        """A(0 deps) = 1.0 (multiplicative identity)."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        ob = Obligation(id=1, title="t", due_date=now + timedelta(days=7), dependency_count=0)
        r = calculate_pressure(ob, now=now)
        assert r.dependency_amp == 1.0

    def test_dep_amp_monotone_increasing(self):
        """More deps -> higher amplification."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        amps = []
        for deps in [0, 1, 5, 10, 20]:
            ob = Obligation(id=1, title="t", due_date=now + timedelta(days=3), dependency_count=deps)
            r = calculate_pressure(ob, now=now)
            amps.append(r.dependency_amp)
        for i in range(len(amps) - 1):
            assert amps[i] <= amps[i + 1]

    def test_dep_amp_capped(self):
        """Dependencies above cap don't further increase amplification."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        ob_at_cap = Obligation(id=1, title="t", due_date=now + timedelta(days=3), dependency_count=DEPENDENCY_COUNT_CAP)
        ob_over_cap = Obligation(id=2, title="t", due_date=now + timedelta(days=3), dependency_count=DEPENDENCY_COUNT_CAP + 50)
        r_cap = calculate_pressure(ob_at_cap, now=now)
        r_over = calculate_pressure(ob_over_cap, now=now)
        assert r_cap.dependency_amp == pytest.approx(r_over.dependency_amp)


# ── export_pressure_summary axioms ───────────────────────────────────────────


class TestExportPressureSummary:
    """Verify export_pressure_summary properties."""

    def test_empty_input(self):
        """No results -> zero pressure, no obligations at risk."""
        summary = export_pressure_summary([])
        assert summary["system_pressure"] == 0.0
        assert summary["red_count"] == 0
        assert summary["obligations_at_risk"] == []

    def test_system_pressure_is_max(self):
        """system_pressure equals the maximum pressure in the batch."""
        results = [
            PressureResult(obligation_id=1, pressure=0.3, zone="yellow",
                          time_pressure=0.3, materiality_mult=1.0,
                          dependency_amp=1.0, completion_damp=1.0),
            PressureResult(obligation_id=2, pressure=0.9, zone="red",
                          time_pressure=0.9, materiality_mult=1.0,
                          dependency_amp=1.0, completion_damp=1.0),
        ]
        summary = export_pressure_summary(results)
        assert summary["system_pressure"] == 0.9

    def test_pause_threshold(self):
        """should_pause_evolution true when system_pressure >= EVOLUTION_PAUSE_THRESHOLD."""
        result_high = PressureResult(
            obligation_id=1, pressure=EVOLUTION_PAUSE_THRESHOLD,
            zone="red", time_pressure=0.8, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
        )
        summary = export_pressure_summary([result_high])
        assert summary["should_pause_evolution"] is True

    def test_red_count_accurate(self):
        """red_count counts only items in the red zone."""
        results = [
            PressureResult(obligation_id=1, pressure=0.85, zone="red",
                          time_pressure=0.85, materiality_mult=1.0,
                          dependency_amp=1.0, completion_damp=1.0),
            PressureResult(obligation_id=2, pressure=0.5, zone="yellow",
                          time_pressure=0.5, materiality_mult=1.0,
                          dependency_amp=1.0, completion_damp=1.0),
            PressureResult(obligation_id=3, pressure=0.9, zone="red",
                          time_pressure=0.9, materiality_mult=1.0,
                          dependency_amp=1.0, completion_damp=1.0),
        ]
        summary = export_pressure_summary(results)
        assert summary["red_count"] == 2
        assert set(summary["obligations_at_risk"]) == {1, 3}


# ── top_k_obligations axioms ─────────────────────────────────────────────────


class TestTopKObligations:
    """Verify top_k_obligations ranking properties."""

    def _make_result(self, ob_id: int, pressure: float) -> PressureResult:
        return PressureResult(
            obligation_id=ob_id, pressure=pressure,
            zone=pressure_zone(pressure),
            time_pressure=pressure, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
        )

    def test_returns_k_items(self):
        """Returns exactly k items when len(results) >= k."""
        results = [self._make_result(i, i * 0.1) for i in range(10)]
        top3 = top_k_obligations(results, k=3)
        assert len(top3) == 3

    def test_returns_all_when_k_exceeds_count(self):
        """Returns all items when k > len(results)."""
        results = [self._make_result(i, i * 0.1) for i in range(3)]
        top10 = top_k_obligations(results, k=10)
        assert len(top10) == 3

    def test_sorted_descending(self):
        """Results are sorted by pressure descending."""
        results = [self._make_result(i, i * 0.1) for i in range(10)]
        top5 = top_k_obligations(results, k=5)
        for i in range(len(top5) - 1):
            assert top5[i].pressure >= top5[i + 1].pressure

    def test_highest_pressure_first(self):
        """The first element is the highest-pressure item."""
        results = [self._make_result(i, i * 0.1) for i in range(10)]
        top1 = top_k_obligations(results, k=1)
        max_p = max(r.pressure for r in results)
        assert top1[0].pressure == max_p


# ── CognitiveContext.effective_bandwidth axioms ──────────────────────────────


class TestEffectiveBandwidth:
    """Verify effective_bandwidth satisfies bandwidth domain invariants."""

    def test_no_data_returns_default(self):
        """No signals -> BANDWIDTH_NO_DATA."""
        ctx = CognitiveContext()
        assert ctx.effective_bandwidth() == BANDWIDTH_NO_DATA

    def test_pre_computed_bandwidth_passthrough(self):
        """bandwidth_score is used directly when set."""
        ctx = CognitiveContext(bandwidth_score=0.6)
        assert ctx.effective_bandwidth() == 0.6

    def test_pre_computed_bandwidth_clamped(self):
        """bandwidth_score clamped to [0, 1]."""
        ctx = CognitiveContext(bandwidth_score=1.5)
        assert ctx.effective_bandwidth() == 1.0
        ctx2 = CognitiveContext(bandwidth_score=-0.5)
        assert ctx2.effective_bandwidth() == 0.0

    def test_floor_enforced(self):
        """Even all-zero signals can't go below BANDWIDTH_MIN_FLOOR."""
        ctx = CognitiveContext(
            sleep_quality=0.0, hrv_trend=0.0, pain_level=0.0,
        )
        assert ctx.effective_bandwidth() >= BANDWIDTH_MIN_FLOOR

    def test_all_optimal_returns_one(self):
        """All signals at 1.0 -> bandwidth = 1.0."""
        ctx = CognitiveContext(sleep_quality=1.0, hrv_trend=1.0, pain_level=1.0)
        assert ctx.effective_bandwidth() == pytest.approx(1.0)

    def test_bounds(self):
        """Output always in [BANDWIDTH_MIN_FLOOR, 1.0] when signals present."""
        for sq, hrv, pain in [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)]:
            ctx = CognitiveContext(sleep_quality=sq, hrv_trend=hrv, pain_level=pain)
            bw = ctx.effective_bandwidth()
            assert BANDWIDTH_MIN_FLOOR <= bw <= 1.0

    def test_partial_signals_averaged(self):
        """Partial signals: mean of available signals."""
        ctx = CognitiveContext(sleep_quality=0.6, pain_level=0.8)
        bw = ctx.effective_bandwidth()
        expected = (0.6 + 0.8) / 2.0
        assert bw == pytest.approx(max(expected, BANDWIDTH_MIN_FLOOR))


# ── estimate_task_demand axioms ──────────────────────────────────────────────


class TestEstimateTaskDemand:
    """Verify task demand estimation properties."""

    def test_known_domain(self):
        """Known domain maps to profile values."""
        ob = Obligation(id=1, title="t", domain="legal")
        d = estimate_task_demand(ob)
        assert d.complexity == pytest.approx(0.8)
        assert d.decision_weight == pytest.approx(0.9)

    def test_unknown_domain_uses_defaults(self):
        """Unknown domain uses default profile (0.5 each)."""
        ob = Obligation(id=1, title="t", domain="unknown_domain")
        d = estimate_task_demand(ob)
        assert d.complexity == pytest.approx(0.5)
        assert d.decision_weight == pytest.approx(0.5)
        assert d.novelty == pytest.approx(0.5)

    def test_material_boosts_complexity(self):
        """Material items get complexity and decision_weight boosts."""
        ob_r = Obligation(id=1, title="t", domain="engineering", materiality="routine")
        ob_m = Obligation(id=2, title="t", domain="engineering", materiality="material")
        d_r = estimate_task_demand(ob_r)
        d_m = estimate_task_demand(ob_m)
        assert d_m.complexity > d_r.complexity
        assert d_m.decision_weight > d_r.decision_weight

    def test_demand_values_bounded(self):
        """All demand values in [0, 1] (clamped)."""
        for domain in ["legal", "financial", "engineering", "ops", "admin", None]:
            for mat in ["routine", "material"]:
                ob = Obligation(id=1, title="t", domain=domain, materiality=mat)
                d = estimate_task_demand(ob)
                assert 0.0 <= d.complexity <= 1.0
                assert 0.0 <= d.novelty <= 1.0
                assert 0.0 <= d.decision_weight <= 1.0

    def test_no_domain_uses_default(self):
        """None domain uses default profile."""
        ob = Obligation(id=1, title="t", domain=None)
        d = estimate_task_demand(ob)
        assert d.complexity == pytest.approx(0.5)


# ── Wearable normalization axioms ────────────────────────────────────────────


class TestNormalizeHRV:
    """Verify HRV normalization satisfies the data contract."""

    def test_at_baseline(self):
        """At personal baseline -> 0.5."""
        assert normalize_hrv(50.0, baseline_ms=50.0) == pytest.approx(0.5)

    def test_at_double_baseline(self):
        """At 2x baseline -> 1.0 (excellent recovery)."""
        assert normalize_hrv(100.0, baseline_ms=50.0) == pytest.approx(1.0)

    def test_at_zero(self):
        """HRV = 0 -> 0.0 (severe stress)."""
        assert normalize_hrv(0.0, baseline_ms=50.0) == 0.0

    def test_bounds(self):
        """Output always in [0, 1]."""
        for rmssd in [0, 10, 25, 50, 75, 100, 200]:
            assert 0.0 <= normalize_hrv(float(rmssd)) <= 1.0

    def test_zero_baseline_fallback(self):
        """Zero baseline -> 0.5 (safe default)."""
        assert normalize_hrv(50.0, baseline_ms=0.0) == 0.5

    def test_monotonicity(self):
        """Higher HRV -> higher score."""
        values = [normalize_hrv(float(r), baseline_ms=50.0) for r in range(0, 150, 10)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1]


class TestNormalizeSleepScore:
    """Verify sleep score normalization."""

    def test_at_zero(self):
        assert normalize_sleep_score(0.0) == 0.0

    def test_at_max(self):
        assert normalize_sleep_score(100.0) == 1.0

    def test_midpoint(self):
        assert normalize_sleep_score(50.0) == pytest.approx(0.5)

    def test_bounds(self):
        for score in [0, 25, 50, 75, 100, 150]:
            assert 0.0 <= normalize_sleep_score(float(score)) <= 1.0

    def test_custom_scale(self):
        """Custom scale_max works correctly."""
        assert normalize_sleep_score(5.0, scale_max=10.0) == pytest.approx(0.5)


class TestNormalizeSleepHours:
    """Verify sleep hours normalization."""

    def test_well_rested(self):
        """8+ hours -> 1.0."""
        assert normalize_sleep_hours(8.0) == 1.0
        assert normalize_sleep_hours(10.0) == 1.0

    def test_severely_deprived(self):
        """4 or fewer hours -> 0.0."""
        assert normalize_sleep_hours(4.0) == 0.0
        assert normalize_sleep_hours(2.0) == 0.0

    def test_midpoint(self):
        """6 hours -> 0.5."""
        assert normalize_sleep_hours(6.0) == pytest.approx(0.5)

    def test_bounds(self):
        for hours in [0, 2, 4, 6, 8, 10, 12]:
            assert 0.0 <= normalize_sleep_hours(float(hours)) <= 1.0

    def test_monotonicity(self):
        values = [normalize_sleep_hours(float(h)) for h in range(0, 13)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1]


class TestNormalizePain:
    """Verify pain normalization (inverted scale)."""

    def test_no_pain(self):
        """NRS 0 (no pain) -> 1.0 (optimal)."""
        assert normalize_pain(0.0) == 1.0

    def test_max_pain(self):
        """NRS 10 (worst) -> 0.0."""
        assert normalize_pain(10.0) == 0.0

    def test_inversion(self):
        """Higher pain -> lower output (inverted)."""
        assert normalize_pain(2.0) > normalize_pain(8.0)

    def test_bounds(self):
        for p in range(0, 15):
            assert 0.0 <= normalize_pain(float(p)) <= 1.0


class TestNormalizeStrain:
    """Verify strain normalization."""

    def test_idle(self):
        """Zero strain -> 0.0."""
        assert normalize_strain(0.0) == 0.0

    def test_max_strain(self):
        """Max strain -> 1.0."""
        assert normalize_strain(21.0) == 1.0

    def test_bounds(self):
        for s in range(0, 30):
            assert 0.0 <= normalize_strain(float(s)) <= 1.0

    def test_monotonicity(self):
        values = [normalize_strain(float(s)) for s in range(0, 25)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1]


# ── reading_to_context round-trip axioms ────────────────────────────────────


class TestReadingToContext:
    """Verify WearableReading -> CognitiveContext conversion."""

    def test_empty_reading(self):
        """Reading with no data -> empty context dict."""
        reading = WearableReading(source="test")
        ctx = reading_to_context(reading)
        assert ctx == {}

    def test_all_fields_populated(self):
        """All fields produce all expected context keys."""
        reading = WearableReading(
            source="test",
            hrv_rmssd_ms=50.0,
            sleep_score=80.0,
            pain_nrs=3.0,
            strain=10.0,
            sleep_hours=7.0,
        )
        ctx = reading_to_context(reading)
        assert "hrv_trend" in ctx
        assert "sleep_quality" in ctx
        assert "pain_level" in ctx
        assert "session_load" in ctx
        assert "hours_since_sleep" in ctx

    def test_sleep_score_priority_over_hours(self):
        """When both sleep_score and sleep_hours present, sleep_score is used for sleep_quality."""
        reading = WearableReading(
            source="test", sleep_score=80.0, sleep_hours=6.0,
        )
        ctx = reading_to_context(reading)
        # sleep_quality comes from sleep_score (80/100 = 0.8), not sleep_hours
        assert ctx["sleep_quality"] == pytest.approx(0.8)

    def test_hours_since_sleep_derived(self):
        """hours_since_sleep = max(0, 24 - sleep_hours)."""
        reading = WearableReading(source="test", sleep_hours=7.0)
        ctx = reading_to_context(reading)
        assert ctx["hours_since_sleep"] == pytest.approx(17.0)

    def test_all_values_bounded(self):
        """All normalized values in [0, 1] for reasonable inputs."""
        reading = WearableReading(
            source="test", hrv_rmssd_ms=60.0, sleep_score=75.0,
            pain_nrs=5.0, strain=12.0,
        )
        ctx = reading_to_context(reading)
        for key, val in ctx.items():
            if key == "hours_since_sleep":
                continue  # This is raw hours, not normalized
            assert 0.0 <= val <= 1.0, f"{key}={val} out of bounds"


# ── Benchmark metrics axioms ─────────────────────────────────────────────────


class TestBenchmarkMetrics:
    """Verify benchmark metric functions satisfy mathematical properties."""

    def test_zone_transition_empty(self):
        """Empty input -> inf (worst possible)."""
        from benchmarks.metrics import zone_transition_timeliness
        assert zone_transition_timeliness([], []) == float("inf")

    def test_zone_transition_perfect(self):
        """Perfect alignment -> 0.0."""
        from benchmarks.metrics import zone_transition_timeliness
        assert zone_transition_timeliness([5.0, 3.0], [5.0, 3.0]) == 0.0

    def test_zone_transition_nonnegative(self):
        """Gap is always non-negative (absolute values)."""
        from benchmarks.metrics import zone_transition_timeliness
        result = zone_transition_timeliness([1.0, 2.0], [5.0, 3.0])
        assert result >= 0.0

    def test_missed_deadline_empty(self):
        """Empty input -> 0.0."""
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([]) == 0.0

    def test_missed_deadline_bounds(self):
        """Output always in [0, 1]."""
        from benchmarks.metrics import missed_deadline_rate
        assert missed_deadline_rate([True, True, True]) == 0.0
        assert missed_deadline_rate([False, False, False]) == 1.0
        assert 0.0 <= missed_deadline_rate([True, False, True]) <= 1.0

    def test_false_alarm_no_alerts(self):
        """No high alerts -> 0.0."""
        from benchmarks.metrics import false_alarm_rate
        assert false_alarm_rate([False, False], [True, True]) == 0.0

    def test_false_alarm_bounds(self):
        """Output always in [0, 1]."""
        from benchmarks.metrics import false_alarm_rate
        assert 0.0 <= false_alarm_rate([True, True], [True, False]) <= 1.0

    def test_spearman_perfect_correlation(self):
        """Perfect rank agreement -> 1.0."""
        from benchmarks.metrics import attention_allocation_efficiency
        assert attention_allocation_efficiency([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)

    def test_spearman_bounds(self):
        """Spearman rho in [-1, 1]."""
        from benchmarks.metrics import attention_allocation_efficiency
        rho = attention_allocation_efficiency([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
        assert -1.0 <= rho <= 1.0


# ── apply_zone_capacity axioms ───────────────────────────────────────────────


class TestApplyZoneCapacity:
    """Verify zone capacity demotion logic."""

    def _make_result(self, ob_id: int, pressure: float) -> PressureResult:
        return PressureResult(
            obligation_id=ob_id, pressure=pressure,
            zone=pressure_zone(pressure),
            time_pressure=pressure, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
        )

    def test_no_capacity_no_change(self):
        """None capacity -> no demotion."""
        results = [self._make_result(1, 0.9), self._make_result(2, 0.85)]
        output = apply_zone_capacity(results, zone_capacity=None)
        assert all(r.zone == "red" for r in output)

    def test_capacity_demotes_overflow(self):
        """Excess red items get demoted to orange."""
        results = [
            self._make_result(1, 0.95),
            self._make_result(2, 0.90),
            self._make_result(3, 0.85),
        ]
        output = apply_zone_capacity(results, zone_capacity=1)
        red_count = sum(1 for r in output if r.zone == "red")
        assert red_count <= 1

    def test_pressure_unchanged(self):
        """Demotion changes zone labels but not pressure values."""
        results = [self._make_result(1, 0.95), self._make_result(2, 0.85)]
        output = apply_zone_capacity(results, zone_capacity=1)
        pressures = {r.obligation_id: r.pressure for r in output}
        assert pressures[1] == 0.95
        assert pressures[2] == 0.85


# ── bandwidth_adjusted_sort axioms ───────────────────────────────────────────


class TestBandwidthAdjustedSort:
    """Verify bandwidth-adjusted sort preserves invariants."""

    _NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _make_ob(self, ob_id: int, domain: str = "engineering", **kwargs) -> Obligation:
        return Obligation(
            id=ob_id, title=f"task_{ob_id}",
            due_date=self._NOW + timedelta(days=7),
            domain=domain, **kwargs,
        )

    def _make_result(self, ob_id: int, pressure: float) -> PressureResult:
        return PressureResult(
            obligation_id=ob_id, pressure=pressure,
            zone=pressure_zone(pressure),
            time_pressure=pressure, materiality_mult=1.0,
            dependency_amp=1.0, completion_damp=1.0,
        )

    def test_full_bandwidth_preserves_order(self):
        """At full bandwidth, sort order matches pure pressure."""
        obs = [self._make_ob(i) for i in range(3)]
        results = [self._make_result(i, (3 - i) * 0.25) for i in range(3)]
        ctx = CognitiveContext(bandwidth_score=1.0)
        sorted_r = bandwidth_adjusted_sort(results, obs, ctx)
        ids = [r.obligation_id for r in sorted_r]
        assert ids == [r.obligation_id for r in results]

    def test_low_bandwidth_favors_simple_tasks(self):
        """At low bandwidth, low-demand tasks rise relative to high-demand tasks."""
        ob_legal = self._make_ob(1, domain="legal")  # high demand
        ob_admin = self._make_ob(2, domain="admin")  # low demand
        obs = [ob_legal, ob_admin]
        # Give legal slightly higher pressure
        results = [
            self._make_result(1, 0.75),  # legal
            self._make_result(2, 0.70),  # admin
        ]
        ctx = CognitiveContext(bandwidth_score=0.3)
        sorted_r = bandwidth_adjusted_sort(results, obs, ctx)
        # Admin should rank higher due to lower cognitive demand
        assert sorted_r[0].obligation_id == 2

    def test_never_demotable_stays_on_top(self):
        """NEVER_DEMOTABLE obligations are not affected by bandwidth."""
        ob_binding = self._make_ob(1, risk_tier=RiskTier.NEVER_DEMOTABLE)
        ob_normal = self._make_ob(2)
        obs = [ob_binding, ob_normal]
        results = [
            self._make_result(1, 0.5),
            self._make_result(2, 0.9),
        ]
        ctx = CognitiveContext(bandwidth_score=0.1)
        sorted_r = bandwidth_adjusted_sort(results, obs, ctx)
        # Binding obligation sorts above all adjusted items regardless of pressure
        assert sorted_r[0].obligation_id == 1
