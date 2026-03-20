# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for benchmarks.datasets.generate_obligations — SOB generator."""

from benchmarks.datasets.generate_obligations import SOBConfig, generate


class TestSOBGeneration:
    def test_default_config(self):
        data = generate(n=50, seed=42)
        assert len(data) == 50

    def test_custom_config(self):
        cfg = SOBConfig(material_probability=0.5, overdue_probability=0.2)
        data = generate(n=100, seed=42, config=cfg)
        assert len(data) == 100
        material_ratio = sum(1 for d in data if d["materiality"] == "material") / 100
        assert material_ratio > 0.35

    def test_deterministic(self):
        a = generate(n=10, seed=99)
        b = generate(n=10, seed=99)
        for x, y in zip(a, b, strict=True):
            assert x["id"] == y["id"]
            assert x["materiality"] == y["materiality"]
            assert x["dependency_count"] == y["dependency_count"]

    def test_all_domains_present(self):
        data = generate(n=500, seed=42)
        domains = {d["domain"] for d in data}
        assert len(domains) == 5

    def test_completion_bounded(self):
        data = generate(n=100, seed=42)
        for d in data:
            assert 0.0 <= d["completion_pct"] <= 1.0

    def test_dependency_count_bounded(self):
        cfg = SOBConfig(max_dependency_count=5)
        data = generate(n=200, seed=42, config=cfg)
        for d in data:
            assert d["dependency_count"] <= 5


class TestSOBConfig:
    def test_defaults(self):
        cfg = SOBConfig()
        assert cfg.material_probability == 0.3
        assert cfg.overdue_probability == 0.1
        assert cfg.deadline_horizon_days == 90

    def test_custom(self):
        cfg = SOBConfig(deadline_horizon_days=30)
        assert cfg.deadline_horizon_days == 30
