# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for scripts/generate_paper_figures.py — domain functions and figure output."""

import os
import sys

import pytest

# Add scripts/ to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

pytest.importorskip("matplotlib")
pytest.importorskip("numpy")

import generate_paper_figures as gpf

# ── Domain function tests ────────────────────────────────────────────────────


class TestPTime:
    def test_overdue_returns_max(self):
        assert gpf.p_time(0) == gpf.OVERDUE_PRESSURE
        assert gpf.p_time(-5) == gpf.OVERDUE_PRESSURE

    def test_far_future_near_zero(self):
        assert gpf.p_time(60) < 0.1

    def test_one_day_high_pressure(self):
        assert gpf.p_time(1) > 0.9

    def test_monotonic_decrease(self):
        values = [gpf.p_time(t) for t in [1, 3, 7, 14, 30, 60]]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1]

    def test_custom_k(self):
        assert gpf.p_time(7, k=5) > gpf.p_time(7, k=3)


class TestPressureScore:
    def test_base_case(self):
        score = gpf.pressure_score(7)
        assert 0.0 <= score <= 1.0

    def test_materiality_amplifies(self):
        base = gpf.pressure_score(7, material=False)
        mat = gpf.pressure_score(7, material=True)
        assert mat > base

    def test_dependencies_amplify(self):
        base = gpf.pressure_score(7, deps=0)
        deps = gpf.pressure_score(7, deps=5)
        assert deps > base

    def test_completion_dampens(self):
        base = gpf.pressure_score(7, completion=0.0)
        done = gpf.pressure_score(7, completion=0.8)
        assert done < base

    def test_saturates_at_one(self):
        score = gpf.pressure_score(0.1, deps=10, material=True)
        assert score <= 1.0


# ── Dataclass defaults ───────────────────────────────────────────────────────


class TestDataclasses:
    def test_plot_style_defaults(self):
        style = gpf.PlotStyle()
        assert style.fig_width == 5.5
        assert style.dpi == 300
        assert style.sample_points_fine == 500

    def test_decomposition_scenario_defaults(self):
        s = gpf.DecompositionScenario()
        assert s.dependency_count == 2
        assert s.completion_pct == 0.4

    def test_bandwidth_scenario_defaults(self):
        s = gpf.BandwidthScenario()
        assert s.legal_pressure == 1.0
        assert s.ops_demand == 0.2

    def test_baseline_scenario_defaults(self):
        s = gpf.BaselineScenario()
        assert s.linear_horizon == 30.0
        assert s.step_threshold_days == 7.0


# ── Figure generation tests ──────────────────────────────────────────────────


class TestFigureGeneration:
    """Verify each figure function runs without error and produces a file."""

    @pytest.fixture(autouse=True)
    def _use_tmpdir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gpf, "OUTDIR", str(tmp_path))
        self.outdir = tmp_path

    def test_pressure_curve(self):
        gpf.fig_pressure_curve()
        assert (self.outdir / "pressure_curve.pdf").exists()

    def test_factor_decomposition(self):
        gpf.fig_factor_decomposition()
        assert (self.outdir / "factor_decomposition.pdf").exists()

    def test_sensitivity(self):
        gpf.fig_sensitivity()
        assert (self.outdir / "sensitivity_k.pdf").exists()

    def test_baselines(self):
        gpf.fig_baselines()
        assert (self.outdir / "baseline_comparison.pdf").exists()

    def test_bandwidth(self):
        gpf.fig_bandwidth()
        assert (self.outdir / "bandwidth_modulation.pdf").exists()

    def test_all_figures_produce_nonzero_files(self):
        gpf.fig_pressure_curve()
        gpf.fig_factor_decomposition()
        gpf.fig_sensitivity()
        gpf.fig_baselines()
        gpf.fig_bandwidth()
        for f in self.outdir.iterdir():
            assert f.stat().st_size > 0, f"{f.name} is empty"
