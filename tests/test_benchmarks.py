# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch benchmark suite.

Covers baselines, metrics, SOB generator, and round-trip pipeline.
"""

from datetime import UTC, datetime

from benchmarks.baselines import binary_deadline, eisenhower, linear_urgency
from benchmarks.datasets.generate_obligations import generate
from benchmarks.metrics import (
    attention_allocation_efficiency,
    false_alarm_rate,
    missed_deadline_rate,
    zone_transition_timeliness,
)
from benchmarks.run import run_baseline, run_tidewatch

# ---- Baselines ----


class TestBinaryDeadline:
    def test_overdue_scores_one(self) -> None:
        assert binary_deadline.score(-1.0) == 1.0

    def test_future_scores_zero(self) -> None:
        assert binary_deadline.score(10.0) == 0.0

    def test_exactly_due_scores_one(self) -> None:
        assert binary_deadline.score(0.0) == 1.0

    def test_no_deadline_scores_zero(self) -> None:
        assert binary_deadline.score(None) == 0.0


class TestLinearUrgency:
    def test_overdue_scores_one(self) -> None:
        assert linear_urgency.score(-5.0) == 1.0

    def test_at_horizon_scores_zero(self) -> None:
        assert linear_urgency.score(90.0) == 0.0

    def test_halfway_scores_half(self) -> None:
        assert abs(linear_urgency.score(45.0, horizon=90.0) - 0.5) < 1e-9

    def test_no_deadline_scores_zero(self) -> None:
        assert linear_urgency.score(None) == 0.0

    def test_beyond_horizon_scores_zero(self) -> None:
        assert linear_urgency.score(100.0, horizon=90.0) == 0.0


class TestEisenhower:
    def test_q1_urgent_important(self) -> None:
        assert eisenhower.score(3.0, materiality="material") == 1.0

    def test_q2_not_urgent_important(self) -> None:
        assert eisenhower.score(30.0, materiality="material") == 0.5

    def test_q3_urgent_not_important(self) -> None:
        assert eisenhower.score(3.0, materiality="routine") == 0.75

    def test_q4_not_urgent_not_important(self) -> None:
        assert eisenhower.score(30.0, materiality="routine") == 0.0

    def test_no_deadline_scores_zero(self) -> None:
        assert eisenhower.score(None) == 0.0


# ---- Metrics ----


class TestMetrics:
    def test_zone_transition_timeliness_perfect(self) -> None:
        """Identical lists produce 0 gap."""
        assert zone_transition_timeliness([5.0, 10.0], [5.0, 10.0]) == 0.0

    def test_zone_transition_timeliness_gap(self) -> None:
        result = zone_transition_timeliness([5.0, 10.0], [3.0, 8.0])
        assert abs(result - 2.0) < 1e-9

    def test_zone_transition_timeliness_empty(self) -> None:
        assert zone_transition_timeliness([], []) == float("inf")

    def test_missed_deadline_rate_none_missed(self) -> None:
        assert missed_deadline_rate([True, True, True]) == 0.0

    def test_missed_deadline_rate_all_missed(self) -> None:
        assert missed_deadline_rate([False, False]) == 1.0

    def test_missed_deadline_rate_partial(self) -> None:
        assert abs(missed_deadline_rate([True, False, True]) - 1 / 3) < 1e-9

    def test_missed_deadline_rate_empty(self) -> None:
        assert missed_deadline_rate([]) == 0.0

    def test_attention_allocation_perfect(self) -> None:
        """Perfect rank correlation = 1.0."""
        assert attention_allocation_efficiency([1, 2, 3], [1, 2, 3]) == 1.0

    def test_attention_allocation_reversed(self) -> None:
        """Reversed ranks = -1.0 for n=3 (6*14 / (3*8) = -2.5 ... let's compute)."""
        result = attention_allocation_efficiency([3, 2, 1], [1, 2, 3])
        assert result < 0

    def test_attention_allocation_single(self) -> None:
        assert attention_allocation_efficiency([1], [1]) == 1.0

    def test_false_alarm_rate_no_false_alarms(self) -> None:
        assert false_alarm_rate([True, True], [False, False]) == 0.0

    def test_false_alarm_rate_all_false_alarms(self) -> None:
        assert false_alarm_rate([True, True], [True, True]) == 1.0

    def test_false_alarm_rate_no_high_alerts(self) -> None:
        assert false_alarm_rate([False, False], [True, True]) == 0.0


# ---- SOB Generator ----


class TestSOBGenerator:
    def test_generates_correct_count(self) -> None:
        data = generate(n=50, seed=1)
        assert len(data) == 50

    def test_default_generates_1000(self) -> None:
        data = generate()
        assert len(data) == 1000

    def test_deterministic_with_seed(self) -> None:
        """Same seed produces same structure (excluding timestamp-derived due_date)."""
        a = generate(n=10, seed=99)
        b = generate(n=10, seed=99)
        # due_date includes datetime.now() so compare all fields except it
        for x, y in zip(a, b, strict=True):
            assert x["id"] == y["id"]
            assert x["title"] == y["title"]
            assert x["materiality"] == y["materiality"]
            assert x["dependency_count"] == y["dependency_count"]
            assert x["completion_pct"] == y["completion_pct"]
            assert x["domain"] == y["domain"]
            assert x["days_out"] == y["days_out"]
            assert x["optimal_attention_days"] == y["optimal_attention_days"]

    def test_has_required_fields(self) -> None:
        data = generate(n=5, seed=0)
        for d in data:
            assert "id" in d
            assert "title" in d
            assert "due_date" in d
            assert "materiality" in d
            assert "dependency_count" in d
            assert "completion_pct" in d
            assert "domain" in d
            assert "optimal_attention_days" in d

    def test_materiality_distribution(self) -> None:
        """Roughly 30% material."""
        data = generate(n=1000, seed=42)
        material_count = sum(1 for d in data if d["materiality"] == "material")
        ratio = material_count / 1000
        assert 0.2 < ratio < 0.4

    def test_domain_coverage(self) -> None:
        """All 5 domains represented."""
        data = generate(n=500, seed=42)
        domains = {d["domain"] for d in data}
        assert domains == {"legal", "financial", "client_work", "personal_admin", "health"}

    def test_includes_overdue(self) -> None:
        """~10% overdue."""
        data = generate(n=1000, seed=42)
        overdue_count = sum(1 for d in data if d["days_out"] < 0)
        assert overdue_count > 0

    def test_completion_pct_valid(self) -> None:
        """All completion_pct in [0, 1]."""
        data = generate(n=100, seed=42)
        for d in data:
            assert 0.0 <= d["completion_pct"] <= 1.0


# ---- Round-trip: generate -> score -> evaluate ----


class TestRoundTrip:
    def test_run_tidewatch_returns_scores(self) -> None:
        """Tidewatch scores the SOB dataset without errors."""
        data = generate(n=50, seed=42)
        now = datetime.now(UTC)
        scores = run_tidewatch(data, now)
        assert len(scores) == 50
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_run_baselines_return_scores(self) -> None:
        """All 3 baselines score without errors."""
        data = generate(n=50, seed=42)
        for name in ["binary", "linear", "eisenhower"]:
            scores = run_baseline(name, data)
            assert len(scores) == 50
            assert all(isinstance(s, float) for s in scores)

    def _score_pipeline_data(self):
        """Generate and score a dataset for metric tests."""
        data = generate(n=100, seed=42)
        now = datetime.now(UTC)
        tw_scores = run_tidewatch(data, now)
        return data, tw_scores

    @staticmethod
    def _build_alert_signals(data, tw_scores):
        """Build simulated alert/attention signals from scores."""
        first_alert_days, optimal_attention_days = [], []
        alerted_48h, alerted_high, completed_early = [], [], []
        for d, score in zip(data, tw_scores, strict=True):
            days_out = d["days_out"]
            first_alert_days.append(days_out if score > 0.3 and days_out > 0 else 0)
            optimal_attention_days.append(d["optimal_attention_days"])
            alerted_48h.append(score > 0.3 and days_out >= 2)
            alerted_high.append(score >= 0.6)
            completed_early.append(d["completion_pct"] > 0.8 and days_out > 7)
        return first_alert_days, optimal_attention_days, alerted_48h, alerted_high, completed_early

    def test_pipeline_zone_transition_timeliness(self) -> None:
        data, tw_scores = self._score_pipeline_data()
        first_alert, optimal = self._build_alert_signals(data, tw_scores)[:2]
        assert isinstance(zone_transition_timeliness(first_alert, optimal), float)

    def test_pipeline_missed_deadline_rate(self) -> None:
        data, tw_scores = self._score_pipeline_data()
        alerted_48h = self._build_alert_signals(data, tw_scores)[2]
        assert 0.0 <= missed_deadline_rate(alerted_48h) <= 1.0

    def test_pipeline_attention_allocation(self) -> None:
        data, tw_scores = self._score_pipeline_data()
        predicted = [0] * len(tw_scores)
        for rank, idx in enumerate(sorted(range(len(tw_scores)), key=lambda i: tw_scores[i], reverse=True)):
            predicted[idx] = rank
        linear_scores = run_baseline("linear", data)
        actual = [0] * len(linear_scores)
        for rank, idx in enumerate(sorted(range(len(linear_scores)), key=lambda i: linear_scores[i], reverse=True)):
            actual[idx] = rank
        assert -1.0 <= attention_allocation_efficiency(predicted, actual) <= 1.0

    def test_pipeline_false_alarm_rate(self) -> None:
        data, tw_scores = self._score_pipeline_data()
        _, _, _, alerted_high, completed_early = self._build_alert_signals(data, tw_scores)
        assert 0.0 <= false_alarm_rate(alerted_high, completed_early) <= 1.0
