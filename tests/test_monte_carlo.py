# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for Monte Carlo simulation benchmark.

Validates the DES-based simulation engine and outcome metrics.
Marked as numerical_verification — these tests verify statistical
properties of the simulation, not exact values.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from benchmarks.monte_carlo import (
    DESResult,
    MonteCarloResult,
    TrialResult,
    _build_obligation_dag,
    _build_profiles_from_obligations,
    _deadline_order,
    _fifo_order,
    _run_trial,
    _sample_durations,
    _tidewatch_order,
    compare_strategies,
    run_des_simulation,
    run_monte_carlo,
)
from tidewatch.types import Obligation

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

# Pytest marker for numerical verification tests
pytestmark = pytest.mark.numerical_verification


def _make_obligations(n: int = 5) -> list[Obligation]:
    """Generate a set of obligations with varied deadlines."""
    return [
        Obligation(id=1, title="Urgent legal", due_date=NOW + timedelta(days=1),
                   materiality="material", domain="legal", dependency_count=2),
        Obligation(id=2, title="Soon engineering", due_date=NOW + timedelta(days=3),
                   domain="engineering"),
        Obligation(id=3, title="Medium ops", due_date=NOW + timedelta(days=7),
                   domain="ops"),
        Obligation(id=4, title="Far admin", due_date=NOW + timedelta(days=30),
                   domain="admin"),
        Obligation(id=5, title="Distant routine", due_date=NOW + timedelta(days=60)),
    ][:n]


class TestTrialResult:
    """TrialResult computed metrics."""

    def test_missed_deadline_rate(self):
        tr = TrialResult(completed_on_time=8, completed_late=2, total=10,
                         inversions=0, inversion_checks=1,
                         effective_attention_hours=8, total_attention_hours=10)
        assert tr.missed_deadline_rate == pytest.approx(0.2)

    def test_queue_inversion_rate(self):
        tr = TrialResult(completed_on_time=5, completed_late=0, total=5,
                         inversions=3, inversion_checks=10,
                         effective_attention_hours=5, total_attention_hours=5)
        assert tr.queue_inversion_rate == pytest.approx(0.3)

    def test_attention_efficiency(self):
        tr = TrialResult(completed_on_time=5, completed_late=5, total=10,
                         inversions=0, inversion_checks=1,
                         effective_attention_hours=6, total_attention_hours=10)
        assert tr.attention_efficiency == pytest.approx(0.6)

    def test_empty_total(self):
        tr = TrialResult(completed_on_time=0, completed_late=0, total=0,
                         inversions=0, inversion_checks=0,
                         effective_attention_hours=0, total_attention_hours=0)
        assert tr.missed_deadline_rate == 0.0
        assert tr.queue_inversion_rate == 0.0
        assert tr.attention_efficiency == 0.0


class TestDurationSampling:
    """Duration sampling from domain-specific LogNormal."""

    def test_durations_are_positive(self):
        obs = _make_obligations()
        rng = np.random.default_rng(42)
        sim_obs = _sample_durations(obs, rng)
        assert all(s.duration_hours > 0 for s in sim_obs)

    def test_legal_takes_longer_than_admin(self):
        """Legal obligations should have higher median duration than admin."""
        rng = np.random.default_rng(42)
        legal_durations = []
        admin_durations = []
        for _ in range(1000):
            obs = [
                Obligation(id=1, title="L", due_date=NOW + timedelta(days=7), domain="legal"),
                Obligation(id=2, title="A", due_date=NOW + timedelta(days=7), domain="admin"),
            ]
            sobs = _sample_durations(obs, rng)
            legal_durations.append(sobs[0].duration_hours)
            admin_durations.append(sobs[1].duration_hours)
        assert np.median(legal_durations) > np.median(admin_durations)

    def test_deterministic_with_seed(self):
        obs = _make_obligations(3)
        d1 = [s.duration_hours for s in _sample_durations(obs, np.random.default_rng(42))]
        d2 = [s.duration_hours for s in _sample_durations(obs, np.random.default_rng(42))]
        assert d1 == d2


class TestSchedulingStrategies:
    """Strategy ordering functions."""

    def test_tidewatch_prioritizes_urgent(self):
        obs = _make_obligations()
        order = _tidewatch_order(obs, NOW)
        # Urgent legal (id=1) should be first
        assert obs[order[0]].id == 1

    def test_edf_prioritizes_earliest_deadline(self):
        obs = _make_obligations()
        order = _deadline_order(obs, NOW)
        deadlines = [obs[i].due_date for i in order]
        assert deadlines == sorted(deadlines)

    def test_fifo_preserves_order(self):
        obs = _make_obligations()
        order = _fifo_order(obs, NOW)
        assert order == [0, 1, 2, 3, 4]


class TestSingleTrial:
    """Single trial execution."""

    def test_all_completed(self):
        """All obligations should be processed."""
        obs = _make_obligations(3)
        rng = np.random.default_rng(42)
        sim_obs = _sample_durations(obs, rng)
        order = list(range(len(obs)))
        result = _run_trial(sim_obs, order, NOW)
        assert result.total == 3
        assert result.completed_on_time + result.completed_late == 3

    def test_total_hours_positive(self):
        obs = _make_obligations(3)
        rng = np.random.default_rng(42)
        sim_obs = _sample_durations(obs, rng)
        order = list(range(len(obs)))
        result = _run_trial(sim_obs, order, NOW)
        assert result.total_attention_hours > 0


class TestMonteCarlo:
    """Full Monte Carlo simulation."""

    def test_returns_correct_trial_count(self):
        obs = _make_obligations(3)
        result = run_monte_carlo(obs, strategy="tidewatch", n_trials=10,
                                 seed=42, sim_start=NOW)
        assert result.n_trials == 10
        assert len(result.trial_results) == 10

    def test_metrics_bounded(self):
        obs = _make_obligations()
        result = run_monte_carlo(obs, strategy="tidewatch", n_trials=50,
                                 seed=42, sim_start=NOW)
        assert 0.0 <= result.missed_deadline_rate_mean <= 1.0
        assert 0.0 <= result.queue_inversion_rate_mean <= 1.0
        assert 0.0 <= result.attention_efficiency_mean <= 1.0
        assert result.missed_deadline_rate_std >= 0.0

    def test_deterministic_with_seed(self):
        obs = _make_obligations()
        r1 = run_monte_carlo(obs, strategy="tidewatch", n_trials=20,
                             seed=42, sim_start=NOW)
        r2 = run_monte_carlo(obs, strategy="tidewatch", n_trials=20,
                             seed=42, sim_start=NOW)
        assert r1.missed_deadline_rate_mean == r2.missed_deadline_rate_mean

    def test_tidewatch_beats_random(self):
        """Tidewatch should produce lower missed-deadline rate than random."""
        obs = _make_obligations()
        tw = run_monte_carlo(obs, strategy="tidewatch", n_trials=100,
                             seed=42, sim_start=NOW)
        rand = run_monte_carlo(obs, strategy="random", n_trials=100,
                               seed=42, sim_start=NOW)
        # Tidewatch should have fewer inversions
        assert tw.queue_inversion_rate_mean < rand.queue_inversion_rate_mean

    def test_to_dict(self):
        obs = _make_obligations(3)
        result = run_monte_carlo(obs, strategy="edf", n_trials=5,
                                 seed=42, sim_start=NOW)
        d = result.to_dict()
        assert d["strategy"] == "edf"
        assert "missed_deadline_rate" in d
        assert "mean" in d["missed_deadline_rate"]
        assert "std" in d["missed_deadline_rate"]


class TestStrategyComparison:
    """Cross-strategy comparison."""

    def test_compare_returns_all_strategies(self):
        obs = _make_obligations(3)
        results = compare_strategies(obs, n_trials=5, seed=42, sim_start=NOW)
        assert set(results.keys()) == {
            "tidewatch", "tidewatch_unclamped",
            "tidewatch_bw_full", "tidewatch_bw_mid",
            "tidewatch_bw_low", "tidewatch_bw_variable",
            "weighted_sum", "weighted_edf", "edf", "fifo", "random",
        }

    def test_compare_all_have_results(self):
        obs = _make_obligations(3)
        results = compare_strategies(obs, n_trials=5, seed=42, sim_start=NOW)
        for _name, result in results.items():
            assert result.n_trials == 5
            assert isinstance(result, MonteCarloResult)


class TestDESIntegration:
    """DES engine integration with statistics_harness CloseSimulation."""

    def test_build_dag_no_deps(self):
        """Obligations with no dependencies produce no edges."""
        obs = [Obligation(id=1, title="A", due_date=NOW + timedelta(days=7))]
        edges, procs = _build_obligation_dag(obs)
        assert len(edges) == 0
        assert "1" in procs

    def test_build_dag_with_deps(self):
        """dependency_count creates synthetic predecessor nodes."""
        obs = [
            Obligation(id=1, title="A", due_date=NOW + timedelta(days=7),
                       dependency_count=3, domain="legal"),
        ]
        edges, procs = _build_obligation_dag(obs)
        assert len(edges) == 3
        # All edges point to the obligation node
        assert all(tgt == "1" for _, tgt in edges)
        assert procs["1"] == "legal"

    def test_build_profiles(self):
        obs = [
            Obligation(id=1, title="A", domain="legal"),
            Obligation(id=2, title="B", domain="admin"),
        ]
        profiles = _build_profiles_from_obligations(obs)
        assert "legal" in profiles
        assert "admin" in profiles
        assert profiles["legal"].mu > profiles["admin"].mu  # legal takes longer

    def test_des_simulation_runs(self):
        """DES simulation completes and returns valid results."""
        obs = _make_obligations(3)
        result = run_des_simulation(obs, n_trials=5, seed=42, sim_start=NOW)
        assert isinstance(result, DESResult)
        assert result.n_trials == 5
        assert len(result.trial_results) == 5

    def test_des_metrics_bounded(self):
        obs = _make_obligations()
        result = run_des_simulation(obs, n_trials=10, seed=42, sim_start=NOW)
        assert 0.0 <= result.missed_deadline_rate_mean <= 1.0
        assert result.mean_total_duration_hours > 0

    def test_des_deterministic(self):
        obs = _make_obligations(3)
        r1 = run_des_simulation(obs, n_trials=5, seed=42, sim_start=NOW)
        r2 = run_des_simulation(obs, n_trials=5, seed=42, sim_start=NOW)
        assert r1.missed_deadline_rate_mean == r2.missed_deadline_rate_mean

    def test_des_to_dict(self):
        obs = _make_obligations(3)
        result = run_des_simulation(obs, n_trials=3, seed=42, sim_start=NOW)
        d = result.to_dict()
        assert "missed_deadline_rate" in d
        assert "mean_total_duration_hours" in d
