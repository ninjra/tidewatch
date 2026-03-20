# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.run — benchmark runner."""

from datetime import UTC, datetime

from benchmarks.datasets.generate_obligations import generate
from benchmarks.run import run_baseline, run_tidewatch


class TestRunTidewatch:
    def test_returns_correct_count(self):
        data = generate(n=20, seed=42)
        scores = run_tidewatch(data, datetime.now(UTC))
        assert len(scores) == 20

    def test_scores_bounded(self):
        data = generate(n=50, seed=42)
        scores = run_tidewatch(data, datetime.now(UTC))
        assert all(0.0 <= s <= 1.0 for s in scores)


class TestRunBaseline:
    def test_binary_baseline(self):
        data = generate(n=20, seed=42)
        scores = run_baseline("binary", data)
        assert len(scores) == 20

    def test_linear_baseline(self):
        data = generate(n=20, seed=42)
        scores = run_baseline("linear", data)
        assert len(scores) == 20

    def test_eisenhower_baseline(self):
        data = generate(n=20, seed=42)
        scores = run_baseline("eisenhower", data)
        assert len(scores) == 20

    def test_unknown_baseline_raises(self):
        import pytest
        data = generate(n=5, seed=42)
        with pytest.raises((KeyError, ValueError)):
            run_baseline("nonexistent", data)
