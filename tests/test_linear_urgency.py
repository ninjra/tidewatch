# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.baselines.linear_urgency — linear urgency baseline."""

from benchmarks.baselines.linear_urgency import score


class TestLinearUrgency:
    def test_overdue_returns_max(self):
        assert score(-5.0) == 1.0

    def test_at_horizon_returns_zero(self):
        assert score(90.0) == 0.0

    def test_midpoint(self):
        assert abs(score(45.0, horizon=90.0) - 0.5) < 1e-9

    def test_no_deadline_returns_zero(self):
        assert score(None) == 0.0

    def test_beyond_horizon_returns_zero(self):
        assert score(100.0, horizon=90.0) == 0.0
