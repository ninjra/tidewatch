# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.baselines.binary_deadline — binary urgency baseline."""

from benchmarks.baselines.binary_deadline import score


class TestBinaryDeadline:
    def test_overdue_returns_max(self):
        assert score(-1.0) == 1.0

    def test_at_deadline_returns_max(self):
        assert score(0.0) == 1.0

    def test_future_returns_zero(self):
        assert score(10.0) == 0.0

    def test_no_deadline_returns_zero(self):
        assert score(None) == 0.0

    def test_kwargs_ignored(self):
        assert score(5.0, extra="ignored") == 0.0
