# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.baselines.eisenhower — Eisenhower matrix baseline."""

from benchmarks.baselines.eisenhower import QUADRANT_SCORES, score
from benchmarks.constants import EISENHOWER_Q2_SCORE, EISENHOWER_Q3_SCORE


class TestEisenhower:
    def test_q1_urgent_important(self):
        assert score(1.0, materiality="material") == 1.0

    def test_q2_not_urgent_important(self):
        assert score(30.0, materiality="material") == EISENHOWER_Q2_SCORE

    def test_q3_urgent_not_important(self):
        assert score(1.0, materiality="routine") == EISENHOWER_Q3_SCORE

    def test_q4_not_urgent_not_important(self):
        assert score(30.0, materiality="routine") == 0.0

    def test_no_deadline_returns_zero(self):
        assert score(None) == 0.0

    def test_quadrant_scores_complete(self):
        assert len(QUADRANT_SCORES) == 4
