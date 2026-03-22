# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for wearable API integration specification."""

import pytest

from tidewatch.wearable_spec import (
    WearableReading,
    normalize_hrv,
    normalize_pain,
    normalize_sleep_hours,
    normalize_sleep_score,
    normalize_strain,
    reading_to_context,
)


class TestNormalizeHRV:

    def test_at_baseline(self):
        assert normalize_hrv(50.0, baseline_ms=50.0) == pytest.approx(0.5)

    def test_double_baseline(self):
        assert normalize_hrv(100.0, baseline_ms=50.0) == pytest.approx(1.0)

    def test_zero_hrv(self):
        assert normalize_hrv(0.0, baseline_ms=50.0) == 0.0

    def test_zero_baseline(self):
        assert normalize_hrv(50.0, baseline_ms=0.0) == 0.5


class TestNormalizeSleepScore:

    def test_perfect(self):
        assert normalize_sleep_score(100.0) == 1.0

    def test_zero(self):
        assert normalize_sleep_score(0.0) == 0.0

    def test_midpoint(self):
        assert normalize_sleep_score(50.0) == pytest.approx(0.5)


class TestNormalizeSleepHours:

    def test_8_hours(self):
        assert normalize_sleep_hours(8.0) == 1.0

    def test_4_hours(self):
        assert normalize_sleep_hours(4.0) == 0.0

    def test_6_hours(self):
        assert normalize_sleep_hours(6.0) == pytest.approx(0.5)

    def test_10_hours(self):
        assert normalize_sleep_hours(10.0) == 1.0

    def test_2_hours(self):
        assert normalize_sleep_hours(2.0) == 0.0


class TestNormalizePain:

    def test_no_pain(self):
        assert normalize_pain(0.0) == 1.0

    def test_max_pain(self):
        assert normalize_pain(10.0) == 0.0

    def test_moderate(self):
        assert normalize_pain(5.0) == pytest.approx(0.5)


class TestNormalizeStrain:

    def test_zero(self):
        assert normalize_strain(0.0) == 0.0

    def test_max(self):
        assert normalize_strain(21.0) == 1.0

    def test_moderate(self):
        assert normalize_strain(10.5) == pytest.approx(0.5)


class TestReadingToContext:

    def test_full_whoop_reading(self):
        reading = WearableReading(
            source="whoop",
            hrv_rmssd_ms=60.0,
            hrv_baseline_ms=50.0,
            sleep_score=85.0,
            strain=12.0,
        )
        ctx = reading_to_context(reading)
        assert "hrv_trend" in ctx
        assert "sleep_quality" in ctx
        assert "session_load" in ctx
        assert all(0.0 <= v <= 1.0 for v in ctx.values() if v is not None)

    def test_minimal_reading(self):
        reading = WearableReading(source="manual", pain_nrs=3.0)
        ctx = reading_to_context(reading)
        assert "pain_level" in ctx
        assert len(ctx) == 1

    def test_empty_reading(self):
        reading = WearableReading(source="manual")
        ctx = reading_to_context(reading)
        assert ctx == {}

    def test_sleep_hours_fallback(self):
        """When sleep_score is None but sleep_hours provided, use hours."""
        reading = WearableReading(source="apple_health", sleep_hours=7.0)
        ctx = reading_to_context(reading)
        assert "sleep_quality" in ctx
        assert "hours_since_sleep" in ctx
