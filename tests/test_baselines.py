# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.baselines — baseline urgency models.

Convention-matched test file for the baselines package hub.
"""

from benchmarks.baselines import BASELINES, binary_deadline, eisenhower, linear_urgency


class TestBinaryDeadline:
    def test_overdue(self):
        assert binary_deadline.score(-1.0) == 1.0

    def test_future(self):
        assert binary_deadline.score(10.0) == 0.0

    def test_at_deadline(self):
        assert binary_deadline.score(0.0) == 1.0

    def test_no_deadline(self):
        assert binary_deadline.score(None) == 0.0


class TestLinearUrgency:
    def test_overdue(self):
        assert linear_urgency.score(-5.0) == 1.0

    def test_at_horizon(self):
        assert linear_urgency.score(90.0) == 0.0

    def test_midpoint(self):
        assert abs(linear_urgency.score(45.0, horizon=90.0) - 0.5) < 1e-9

    def test_no_deadline(self):
        assert linear_urgency.score(None) == 0.0

    def test_beyond_horizon(self):
        assert linear_urgency.score(100.0, horizon=90.0) == 0.0

    def test_custom_horizon(self):
        assert abs(linear_urgency.score(15.0, horizon=30.0) - 0.5) < 1e-9


class TestEisenhower:
    def test_q1_urgent_important(self):
        assert eisenhower.score(3.0, materiality="material") == 1.0

    def test_q2_not_urgent_important(self):
        assert eisenhower.score(30.0, materiality="material") == 0.5

    def test_q3_urgent_not_important(self):
        assert eisenhower.score(3.0, materiality="routine") == 0.75

    def test_q4_not_urgent_not_important(self):
        assert eisenhower.score(30.0, materiality="routine") == 0.0

    def test_no_deadline(self):
        assert eisenhower.score(None) == 0.0

    def test_custom_threshold(self):
        assert eisenhower.score(10.0, urgent_threshold_days=14.0, materiality="routine") == 0.75
        assert eisenhower.score(10.0, urgent_threshold_days=7.0, materiality="routine") == 0.0


class TestBaselineRegistry:
    def test_all_baselines_registered(self):
        assert set(BASELINES.keys()) == {"binary", "linear", "eisenhower"}

    def test_all_baselines_callable(self):
        for name, scorer in BASELINES.items():
            result = scorer(7.0)
            assert isinstance(result, float), f"{name} returned {type(result)}"
            assert 0.0 <= result <= 1.0

    def test_all_baselines_handle_none(self):
        for name, scorer in BASELINES.items():
            assert scorer(None) == 0.0, f"{name} should return 0.0 for None"
