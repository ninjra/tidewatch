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
        ob_zero, now = _make_obligation(days_out=7, dependency_count=0)
        ob_five, _ = _make_obligation(days_out=7, dependency_count=5)
        r_zero = calculate_pressure(ob_zero, now=now)
        r_five = calculate_pressure(ob_five, now=now)
        assert r_five.dependency_amp == 1.5
        assert r_zero.dependency_amp == 1.0
        assert abs(r_five.pressure - r_zero.pressure * 1.5) < 0.001


class TestCompletion:

    def test_completion_dampening(self):
        ob_zero, now = _make_obligation(days_out=7, completion_pct=0.0)
        ob_half, _ = _make_obligation(days_out=7, completion_pct=0.5)
        ob_full, _ = _make_obligation(days_out=7, completion_pct=1.0)

        r_zero = calculate_pressure(ob_zero, now=now)
        r_half = calculate_pressure(ob_half, now=now)
        r_full = calculate_pressure(ob_full, now=now)

        assert r_zero.completion_damp == 1.0
        assert abs(r_half.completion_damp - 0.7) < 0.001
        assert abs(r_full.completion_damp - 0.4) < 0.001


class TestCombined:

    def test_combined_factors_multiply(self):
        """All factors interact multiplicatively."""
        ob, now = _make_obligation(
            days_out=3,
            materiality="material",
            dependency_count=2,
            completion_pct=0.25,
        )
        result = calculate_pressure(ob, now=now)

        # Manual computation
        time_p = 1.0 - math.exp(-3.0 / 3.0)
        mat = 1.5
        dep = 1.0 + (2 * 0.1)
        comp = 1.0 - (0.25 * 0.6)
        expected = min(1.0, time_p * mat * dep * comp)
        assert abs(result.pressure - expected) < 0.001

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
        assert result.pressure == 1.0  # Should be clamped


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
        assert result.dependency_amp == 1.3
        assert abs(result.completion_damp - 0.76) < 0.001
        assert result.zone in ("green", "yellow", "orange", "red")


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
