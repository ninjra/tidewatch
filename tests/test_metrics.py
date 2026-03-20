# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.metrics — benchmark evaluation metrics."""

from benchmarks.metrics import (
    attention_allocation_efficiency,
    false_alarm_rate,
    missed_deadline_rate,
    zone_transition_timeliness,
)


class TestZoneTransitionTimeliness:
    def test_perfect_alignment(self):
        assert zone_transition_timeliness([5.0, 10.0], [5.0, 10.0]) == 0.0

    def test_uniform_gap(self):
        result = zone_transition_timeliness([7.0, 12.0], [5.0, 10.0])
        assert abs(result - 2.0) < 1e-9

    def test_empty_returns_inf(self):
        assert zone_transition_timeliness([], []) == float("inf")


class TestMissedDeadlineRate:
    def test_none_missed(self):
        assert missed_deadline_rate([True, True, True]) == 0.0

    def test_all_missed(self):
        assert missed_deadline_rate([False, False]) == 1.0

    def test_empty(self):
        assert missed_deadline_rate([]) == 0.0


class TestAttentionAllocationEfficiency:
    def test_perfect_correlation(self):
        assert attention_allocation_efficiency([1, 2, 3], [1, 2, 3]) == 1.0

    def test_reversed_negative(self):
        result = attention_allocation_efficiency([3, 2, 1], [1, 2, 3])
        assert result < 0

    def test_single_element(self):
        assert attention_allocation_efficiency([1], [1]) == 1.0


class TestFalseAlarmRate:
    def test_no_false_alarms(self):
        assert false_alarm_rate([True, True], [False, False]) == 0.0

    def test_all_false_alarms(self):
        assert false_alarm_rate([True, True], [True, True]) == 1.0

    def test_no_high_alerts(self):
        assert false_alarm_rate([False, False], [True, True]) == 0.0
