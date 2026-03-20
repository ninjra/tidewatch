# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch.constants — domain functions and tunable values."""


from tidewatch.constants import (
    BANDWIDTH_NO_DATA,
    COMPLETION_DAMPENING,
    DEPENDENCY_AMPLIFICATION,
    MATERIALITY_WEIGHTS,
    OVERDUE_PRESSURE,
    RATE_CONSTANT,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
    clamp_unit,
    normalize_hours,
    saturate,
)


class TestSaturate:
    def test_within_range(self):
        assert saturate(0.5) == 0.5

    def test_at_zero(self):
        assert saturate(0.0) == 0.0

    def test_at_one(self):
        assert saturate(1.0) == 1.0

    def test_above_one(self):
        assert saturate(1.5) == 1.0

    def test_below_zero(self):
        assert saturate(-0.1) == 0.0

    def test_large_value(self):
        assert saturate(100.0) == 1.0


class TestClampUnit:
    def test_within_range(self):
        assert clamp_unit(0.7) == 0.7

    def test_above_one(self):
        assert clamp_unit(2.0) == 1.0

    def test_below_zero(self):
        assert clamp_unit(-1.0) == 0.0

    def test_boundary_zero(self):
        assert clamp_unit(0.0) == 0.0

    def test_boundary_one(self):
        assert clamp_unit(1.0) == 1.0


class TestNormalizeHours:
    def test_within_good(self):
        assert normalize_hours(4.0, good=8.0, span=8.0) == 1.0

    def test_at_good_boundary(self):
        assert normalize_hours(8.0, good=8.0, span=8.0) == 1.0

    def test_at_bad_boundary(self):
        assert normalize_hours(16.0, good=8.0, span=8.0) == 0.0

    def test_midpoint(self):
        assert abs(normalize_hours(12.0, good=8.0, span=8.0) - 0.5) < 1e-9

    def test_beyond_bad(self):
        assert normalize_hours(24.0, good=8.0, span=8.0) == 0.0


class TestConstantValues:
    def test_rate_constant_is_3(self):
        assert RATE_CONSTANT == 3.0

    def test_overdue_pressure_is_1(self):
        assert OVERDUE_PRESSURE == 1.0

    def test_materiality_weights(self):
        assert MATERIALITY_WEIGHTS["material"] == 1.5
        assert MATERIALITY_WEIGHTS["routine"] == 1.0

    def test_completion_dampening_bounded(self):
        assert 0.0 < COMPLETION_DAMPENING < 1.0

    def test_dependency_amplification_positive(self):
        assert DEPENDENCY_AMPLIFICATION > 0.0

    def test_zone_ordering(self):
        assert ZONE_YELLOW < ZONE_ORANGE < ZONE_RED

    def test_bandwidth_no_data_is_conservative(self):
        assert BANDWIDTH_NO_DATA == 0.8


class TestZoneEnvOverride:
    def test_default_zone_values(self):
        assert ZONE_YELLOW == 0.30
        assert ZONE_ORANGE == 0.60
        assert ZONE_RED == 0.80
