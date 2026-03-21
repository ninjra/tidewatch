# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch.pressure — the core pressure engine.

18 tests covering the pressure equation, zones, batch recalculation,
and result decomposition.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest

from tidewatch.pressure import calculate_pressure, pressure_zone, recalculate_batch
from tidewatch.types import Obligation, PressureResult


def _make_obligation(
    days_out: float | None = 7,
    materiality: str = "routine",
    dependency_count: int = 0,
    completion_pct: float = 0.0,
    **kwargs,
) -> tuple[Obligation, datetime]:
    """Helper: create an obligation N days from now."""
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    due = now + timedelta(days=days_out) if days_out is not None else None
    ob = Obligation(
        id=kwargs.get("id", 1),
        title=kwargs.get("title", "Test obligation"),
        due_date=due,
        materiality=materiality,
        dependency_count=dependency_count,
        completion_pct=completion_pct,
    )
    return ob, now


class TestTimePressure:
    """P_time(t) = 1 - exp(-3 / max(t, 0.01)) for t > 0; 1.0 for t <= 0."""

    def test_no_deadline_returns_zero(self):
        ob, now = _make_obligation(days_out=None)
        # Override due_date to None
        ob.due_date = None
        result = calculate_pressure(ob, now=now)
        assert result.pressure == 0.0
        assert result.zone == "green"

    def test_overdue_returns_one(self):
        ob, now = _make_obligation(days_out=-2)
        result = calculate_pressure(ob, now=now)
        assert result.time_pressure == 1.0

    def test_14_days_out(self):
        ob, now = _make_obligation(days_out=14)
        result = calculate_pressure(ob, now=now)
        expected = 1.0 - math.exp(-3.0 / 14.0)
        assert abs(result.time_pressure - expected) < 0.001
        assert abs(result.time_pressure - 0.19) < 0.02

    def test_7_days_out(self):
        ob, now = _make_obligation(days_out=7)
        result = calculate_pressure(ob, now=now)
        expected = 1.0 - math.exp(-3.0 / 7.0)
        assert abs(result.time_pressure - expected) < 0.001
        assert abs(result.time_pressure - 0.35) < 0.02

    def test_3_days_out(self):
        ob, now = _make_obligation(days_out=3)
        result = calculate_pressure(ob, now=now)
        expected = 1.0 - math.exp(-3.0 / 3.0)
        assert abs(result.time_pressure - expected) < 0.001
        assert abs(result.time_pressure - 0.63) < 0.02

    def test_1_day_out(self):
        ob, now = _make_obligation(days_out=1)
        result = calculate_pressure(ob, now=now)
        expected = 1.0 - math.exp(-3.0 / 1.0)
        assert abs(result.time_pressure - expected) < 0.001
        assert abs(result.time_pressure - 0.95) < 0.02


class TestMateriality:

    def test_materiality_multiplier(self):
        ob_routine, now = _make_obligation(days_out=7, materiality="routine")
        ob_material, _ = _make_obligation(days_out=7, materiality="material")
        r_routine = calculate_pressure(ob_routine, now=now)
        r_material = calculate_pressure(ob_material, now=now)
        assert r_material.materiality_mult == 1.5
        assert r_routine.materiality_mult == 1.0
        assert abs(r_material.pressure - r_routine.pressure * 1.5) < 0.001


class TestDependencies:

    def test_dependency_amplification(self):
        """dep_amp = 1.0 + deps × AMPLIFICATION × temporal_gate(t) (§3.2)."""
        import math

        from tidewatch.constants import FANOUT_TEMPORAL_K
        ob_zero, now = _make_obligation(days_out=7, dependency_count=0)
        ob_five, _ = _make_obligation(days_out=7, dependency_count=5)
        r_zero = calculate_pressure(ob_zero, now=now)
        r_five = calculate_pressure(ob_five, now=now)
        # temporal_gate at 7d = 1 - exp(-FANOUT_TEMPORAL_K/7) ≈ 0.249
        t_gate = 1.0 - math.exp(-FANOUT_TEMPORAL_K / 7.0)
        expected_dep_amp = 1.0 + 5 * 0.1 * t_gate
        assert r_five.dependency_amp == pytest.approx(expected_dep_amp, abs=1e-10)
        assert r_zero.dependency_amp == 1.0
        assert r_five.pressure == pytest.approx(r_zero.pressure * expected_dep_amp, abs=1e-10)

    def test_dependency_urgency_propagation(self):
        """Blocker with far deadline but near dependent gets amplified (#1180)."""
        import math

        from tidewatch.constants import FANOUT_TEMPORAL_K
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        # Blocker: due in 30 days, 3 deps, no dependent info
        ob_no_prop = Obligation(
            id=1, title="Blocker no prop", dependency_count=3,
            due_date=now + timedelta(days=30),
        )
        # Same blocker but with earliest_dependent_deadline = 2 days out
        ob_with_prop = Obligation(
            id=2, title="Blocker with prop", dependency_count=3,
            due_date=now + timedelta(days=30),
            earliest_dependent_deadline=now + timedelta(days=2),
        )
        r_no = calculate_pressure(ob_no_prop, now=now)
        r_yes = calculate_pressure(ob_with_prop, now=now)
        # With propagation, temporal gate uses min(30, 2) = 2 days
        t_gate_30 = 1.0 - math.exp(-FANOUT_TEMPORAL_K / 30.0)
        t_gate_2 = 1.0 - math.exp(-FANOUT_TEMPORAL_K / 2.0)
        assert t_gate_2 > t_gate_30  # 2-day gate much higher than 30-day
        # Propagated version should have higher dep_amp
        assert r_yes.dependency_amp > r_no.dependency_amp
        # Verify exact values
        expected_no = 1.0 + 3 * 0.1 * t_gate_30
        expected_yes = 1.0 + 3 * 0.1 * t_gate_2
        assert r_no.dependency_amp == pytest.approx(expected_no, abs=1e-10)
        assert r_yes.dependency_amp == pytest.approx(expected_yes, abs=1e-10)


class TestCompletion:

    def test_completion_dampening(self):
        ob_zero, now = _make_obligation(days_out=7, completion_pct=0.0)
        ob_half, _ = _make_obligation(days_out=7, completion_pct=0.5)
        ob_full, _ = _make_obligation(days_out=7, completion_pct=1.0)

        r_zero = calculate_pressure(ob_zero, now=now)
        r_half = calculate_pressure(ob_half, now=now)
        r_full = calculate_pressure(ob_full, now=now)

        # Logistic: at 0% damp ≈ 0.989, at 50% damp = 0.7, at 100% damp ≈ 0.411
        assert abs(r_zero.completion_damp - 0.989) < 0.01
        assert abs(r_half.completion_damp - 0.7) < 0.001
        assert abs(r_full.completion_damp - 0.411) < 0.01


class TestCombined:

    def test_combined_factors_multiply(self):
        """All factors interact multiplicatively including temporal gate."""
        from tidewatch.constants import FANOUT_TEMPORAL_K
        from tidewatch.pressure import _timing_amplifier, _violation_amplifier
        ob, now = _make_obligation(
            days_out=3,
            materiality="material",
            dependency_count=2,
            completion_pct=0.25,
        )
        result = calculate_pressure(ob, now=now)

        # Manual computation with logistic dampening and temporal gating (§3.2)
        time_p = 1.0 - math.exp(-3.0 / 3.0)
        mat = 1.5
        t_gate = 1.0 - math.exp(-FANOUT_TEMPORAL_K / 3.0)  # temporal_gate at 3 days
        dep = 1.0 + (2 * 0.1 * t_gate)
        sigmoid = 1.0 / (1.0 + math.exp(-8.0 * (0.25 - 0.5)))
        comp = 1.0 - (0.6 * sigmoid)
        timing = _timing_amplifier(ob.days_in_status)
        violation = _violation_amplifier(ob.violation_count, ob.days_in_status)
        expected = min(1.0, time_p * mat * dep * comp * timing * violation)
        assert result.pressure == pytest.approx(expected, abs=1e-10)

    def test_pressure_clamped_to_one(self):
        """High factors should not exceed 1.0."""
        ob, now = _make_obligation(
            days_out=0.5,
            materiality="material",
            dependency_count=10,
            completion_pct=0.0,
        )
        result = calculate_pressure(ob, now=now)
        assert result.pressure <= 1.0
        # With logistic dampening at 0%, pressure is clamped to 1.0 (product exceeds 1.0)
        assert result.pressure == 1.0


class TestZones:

    def test_zone_boundaries(self):
        assert pressure_zone(0.0) == "green"
        assert pressure_zone(0.29) == "green"
        assert pressure_zone(0.30) == "yellow"
        assert pressure_zone(0.59) == "yellow"
        assert pressure_zone(0.60) == "orange"
        assert pressure_zone(0.79) == "orange"
        assert pressure_zone(0.80) == "red"
        assert pressure_zone(1.0) == "red"

    def test_zone_green(self):
        assert pressure_zone(0.29) == "green"

    def test_zone_yellow(self):
        assert pressure_zone(0.30) == "yellow"

    def test_zone_orange(self):
        assert pressure_zone(0.60) == "orange"

    def test_zone_red(self):
        assert pressure_zone(0.80) == "red"


class TestBatch:

    def test_batch_recalculate_sorted(self):
        """Results should be sorted by pressure descending."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        obligations = [
            Obligation(id=1, title="Far out", due_date=now + timedelta(days=30)),
            Obligation(id=2, title="Close", due_date=now + timedelta(days=1)),
            Obligation(id=3, title="Medium", due_date=now + timedelta(days=7)),
        ]
        results = recalculate_batch(obligations, now=now)
        pressures = [r.pressure for r in results]
        assert pressures == sorted(pressures, reverse=True)
        # Closest deadline should have highest pressure
        assert results[0].obligation_id == 2

    def test_pressure_result_decomposition(self):
        """All factors should be accessible individually."""
        import math as _m

        from tidewatch.constants import FANOUT_TEMPORAL_K
        ob, now = _make_obligation(
            days_out=5,
            materiality="material",
            dependency_count=3,
            completion_pct=0.4,
        )
        result = calculate_pressure(ob, now=now)
        assert isinstance(result, PressureResult)
        assert result.time_pressure > 0
        assert result.materiality_mult == 1.5
        # dep_amp = 1 + 3 × 0.1 × temporal_gate(5d) with FANOUT_TEMPORAL_K=2.0
        t_gate_5d = 1.0 - _m.exp(-FANOUT_TEMPORAL_K / 5.0)
        assert result.dependency_amp == pytest.approx(1.0 + 3 * 0.1 * t_gate_5d, abs=1e-10)
        # Logistic damp at 40%: sigmoid(8*(0.4-0.5)) = sigmoid(-0.8) ≈ 0.3100
        # D = 1 - 0.6 * 0.3100 ≈ 0.814
        assert abs(result.completion_damp - 0.814) < 0.01
        assert result.zone in ("green", "yellow", "orange", "red")


class TestWeightedCollapseNormalization:
    """Weighted sum collapse normalizes by component bounds (#1185)."""

    def test_equal_weights_proportional(self):
        """With equal weights, components with different scales contribute equally.

        Without normalization, dependency_amp [1,5] would dominate time_pressure [0,1].
        With normalization, both contribute proportionally to the weighted sum.
        """
        from tidewatch.components import build_pressure_space
        # Create space where dependency_amp is at its max bound (5.0)
        # and time_pressure is at its max bound (1.0)
        space_a = build_pressure_space(
            time_pressure=1.0, materiality=1.0, dependency_amp=5.0,
            completion_damp=1.0, timing_amp=1.0, violation_amp=1.0,
            obligation_id="test_a",
        )
        # Create space where only time_pressure varies
        space_b = build_pressure_space(
            time_pressure=0.5, materiality=1.0, dependency_amp=5.0,
            completion_damp=1.0, timing_amp=1.0, violation_amp=1.0,
            obligation_id="test_b",
        )
        ws_a = space_a.collapse(weights={"time_pressure": 1.0, "dependency_amp": 1.0})
        ws_b = space_b.collapse(weights={"time_pressure": 1.0, "dependency_amp": 1.0})
        # The difference should come from time_pressure changing from 1.0 to 0.5
        # which is a 50% reduction in that normalized dimension
        assert ws_a > ws_b
        # Normalized output should be in [0, 1]
        assert 0.0 <= ws_a <= 1.0
        assert 0.0 <= ws_b <= 1.0


class TestRateConstantSensitivity:
    """Sensitivity analysis for RATE_CONSTANT (§4.2).

    Verifies that the chosen k=3 produces the intended zone behavior
    and documents the impact of ±1 perturbation.
    """

    def test_k3_7day_enters_yellow(self):
        """k=3: 7-day deadline with no modifiers should be in yellow zone."""
        ob, now = _make_obligation(days_out=7)
        result = calculate_pressure(ob, now=now)
        assert result.zone == "yellow", f"Expected yellow at 7d, got {result.zone} (P={result.pressure:.3f})"

    def test_k3_14day_stays_green(self):
        """k=3: 14-day deadline should stay green."""
        ob, now = _make_obligation(days_out=14)
        result = calculate_pressure(ob, now=now)
        assert result.zone == "green", f"Expected green at 14d, got {result.zone} (P={result.pressure:.3f})"

    def test_k3_3day_enters_orange(self):
        """k=3: 3-day deadline should be in orange (with logistic dampening)."""
        ob, now = _make_obligation(days_out=3)
        result = calculate_pressure(ob, now=now)
        assert result.zone == "orange", f"Expected orange at 3d, got {result.zone} (P={result.pressure:.3f})"

    def test_sensitivity_k2_shifts_yellow_entry(self):
        """k=2: yellow zone entry shifts to ~5 days (less aggressive)."""
        import tidewatch.pressure as p
        original = p.RATE_CONSTANT
        try:
            p.RATE_CONSTANT = 2.0
            # At 7 days with k=2: P_time = 1-exp(-2/7) ≈ 0.248 → green
            ob, now = _make_obligation(days_out=7)
            result = calculate_pressure(ob, now=now)
            assert result.zone == "green", f"k=2, 7d should be green, got {result.zone} (P={result.pressure:.3f})"
            # At 5 days with k=2: P_time = 1-exp(-2/5) ≈ 0.330 → yellow
            ob5, _ = _make_obligation(days_out=5)
            r5 = calculate_pressure(ob5, now=now)
            assert r5.zone == "yellow", f"k=2, 5d should be yellow, got {r5.zone} (P={r5.pressure:.3f})"
        finally:
            p.RATE_CONSTANT = original

    def test_sensitivity_k4_shifts_yellow_entry(self):
        """k=4: yellow zone entry shifts to ~10 days (more aggressive)."""
        import tidewatch.pressure as p
        original = p.RATE_CONSTANT
        try:
            p.RATE_CONSTANT = 4.0
            # At 10 days with k=4: P_time = 1-exp(-4/10) ≈ 0.330 → yellow
            ob, now = _make_obligation(days_out=10)
            result = calculate_pressure(ob, now=now)
            assert result.zone == "yellow", f"k=4, 10d should be yellow, got {result.zone} (P={result.pressure:.3f})"
            # At 14 days with k=4: P_time = 1-exp(-4/14) ≈ 0.249 → green
            ob14, _ = _make_obligation(days_out=14)
            r14 = calculate_pressure(ob14, now=now)
            assert r14.zone == "green", f"k=4, 14d should be green, got {r14.zone} (P={r14.pressure:.3f})"
        finally:
            p.RATE_CONSTANT = original


class TestNanInfGuards:
    """NaN/Inf validation on float inputs."""

    def test_nan_completion_pct_raises(self):
        """NaN completion_pct raises ValueError."""
        ob, now = _make_obligation(days_out=7, completion_pct=float("nan"))
        with pytest.raises(ValueError, match="finite"):
            calculate_pressure(ob, now=now)

    def test_inf_completion_pct_raises(self):
        """Inf completion_pct raises ValueError."""
        ob, now = _make_obligation(days_out=7, completion_pct=float("inf"))
        with pytest.raises(ValueError, match="finite"):
            calculate_pressure(ob, now=now)

    def test_nan_pressure_zone_raises(self):
        """NaN pressure raises ValueError in pressure_zone."""
        with pytest.raises(ValueError, match="finite"):
            pressure_zone(float("nan"))


class TestViolationSublinear:
    """Violation amplifier uses sublinear (logarithmic) scaling (#1184)."""

    def test_diminishing_returns_per_violation(self):
        """Each additional violation adds less amplification than the previous.

        Logarithmic scaling: amp = 1 + min(log(1 + effective) * k, cap).
        The marginal contribution of violation N+1 is always less than N.
        """
        from tidewatch.pressure import _violation_amplifier

        amp_1 = _violation_amplifier(violation_count=1, days_in_status=0)
        amp_2 = _violation_amplifier(violation_count=2, days_in_status=0)
        amp_5 = _violation_amplifier(violation_count=5, days_in_status=0)
        amp_10 = _violation_amplifier(violation_count=10, days_in_status=0)

        # All should amplify
        assert amp_1 > 1.0
        assert amp_2 > amp_1
        assert amp_5 > amp_2
        assert amp_10 > amp_5

        # Marginal contribution must decrease (sublinear)
        marginal_1_2 = amp_2 - amp_1
        marginal_2_5 = (amp_5 - amp_2) / 3.0  # per-violation average
        marginal_5_10 = (amp_10 - amp_5) / 5.0
        assert marginal_2_5 < marginal_1_2
        assert marginal_5_10 < marginal_2_5

    def test_cap_still_enforced(self):
        """Even with many violations, amplification stays within cap."""
        from tidewatch.constants import VIOLATION_MAX_AMPLIFICATION
        from tidewatch.pressure import _violation_amplifier

        amp_100 = _violation_amplifier(violation_count=100, days_in_status=0)
        assert amp_100 <= 1.0 + VIOLATION_MAX_AMPLIFICATION + 1e-10


class TestStatusToggleExploit:
    """Anti-exploit: status-toggle cannot reset violation/timing decay (#1261)."""

    def test_status_toggle_cannot_reset_violation_decay(self):
        """Violation decay anchored to violation_first_at, not days_in_status.

        Creates two obligations with violation_count=3:
        - ob_reset: days_in_status=0 (simulating a status toggle), no violation_first_at
        - ob_anchored: days_in_status=0, but violation_first_at=14 days ago

        The anchored obligation should have LOWER violation amplification because
        its decay is computed from the actual violation event (14 days ago), not
        from the reset status age (0 days).
        """
        from tidewatch.pressure import _violation_amplifier

        # Simulated status reset: days_in_status=0, no event anchor
        # Decay = 2^(-0/14) = 1.0 → full violation amplification
        amp_reset = _violation_amplifier(violation_count=3, days_in_status=0)

        # With violation_first_at anchored to 14 days ago:
        # Decay = 2^(-14/14) = 0.5 → half the violation amplification
        amp_anchored = _violation_amplifier(
            violation_count=3, days_in_status=0, days_since_violation=14.0,
        )

        # The anchored version must have lower amplification — proving that
        # the decay is event-based (not status-based) when the field is populated
        assert amp_anchored < amp_reset
        # Both should be > 1.0 (violations still have some effect)
        assert amp_anchored > 1.0
        assert amp_reset > 1.0

    def test_status_toggle_cannot_reset_timing_amplifier(self):
        """Timing amplifier uses max(days_in_status, days_since_status_change) (#1261).

        Toggling status resets days_in_status to 0, but the timing amplifier
        falls back to days_since_status_change (computed from status_changed_at)
        which cannot be gamed by status toggling.
        """
        from tidewatch.pressure import _timing_amplifier

        # No status_changed_at: uses days_in_status directly
        amp_stuck_14d = _timing_amplifier(days_in_status=14.0)

        # Status toggled: days_in_status=0, but status_changed_at says 14 days
        amp_toggled = _timing_amplifier(
            days_in_status=0.0, days_since_status_change=14.0,
        )

        # Without exploit protection: days_in_status=0 → near-minimum amplification
        amp_exploited = _timing_amplifier(days_in_status=0.0)

        # The toggled version should match the stuck version (max(0, 14) = 14)
        assert amp_toggled == amp_stuck_14d
        # The exploited version (no anchor) should be lower
        assert amp_exploited < amp_toggled

    def test_full_pipeline_status_toggle_exploit(self):
        """End-to-end: obligation with status_changed_at resists reset exploit (#1261)."""
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Obligation stuck for 14 days, then status toggled (days_in_status reset to 0)
        # but status_changed_at preserves the original timing
        ob_anchored = Obligation(
            id=1, title="Anchored", due_date=now + timedelta(days=5),
            days_in_status=0.0,
            status_changed_at=now - timedelta(days=14),
            violation_count=3,
            violation_first_at=now - timedelta(days=14),
        )
        # Same obligation without event anchors — exploitable
        ob_exploitable = Obligation(
            id=2, title="Exploitable", due_date=now + timedelta(days=5),
            days_in_status=0.0,
            violation_count=3,
        )

        r_anchored = calculate_pressure(ob_anchored, now=now)
        r_exploitable = calculate_pressure(ob_exploitable, now=now)

        # Anchored version should have higher pressure (timing amp + violation
        # amp both use the event-anchored values instead of the reset ones)
        assert r_anchored.pressure > r_exploitable.pressure
