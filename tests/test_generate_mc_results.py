# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Smoke tests for scripts/generate_mc_results.py."""

import importlib


class TestGenerateMCResults:
    """Basic import and structure tests for the MC results generator."""

    def test_module_imports(self):
        """Module imports without error."""
        mod = importlib.import_module("scripts.generate_mc_results")
        assert hasattr(mod, "main")
        assert hasattr(mod, "PAPER_STRATEGIES")

    def test_paper_strategies_non_empty(self):
        """PAPER_STRATEGIES contains expected baseline strategies."""
        from scripts.generate_mc_results import PAPER_STRATEGIES
        assert len(PAPER_STRATEGIES) >= 5
        assert "tidewatch" in PAPER_STRATEGIES
        assert "edf" in PAPER_STRATEGIES

    def test_obligations_from_sob(self):
        """_obligations_from_sob produces Obligation objects."""
        from datetime import UTC, datetime

        from scripts.generate_mc_results import _obligations_from_sob
        from tidewatch.types import Obligation

        sim_start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        obs = _obligations_from_sob(5, seed=42, sim_start=sim_start)
        assert len(obs) == 5
        assert all(isinstance(o, Obligation) for o in obs)
