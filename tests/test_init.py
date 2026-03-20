# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch/__init__.py — public API hub coverage."""

import inspect

import tidewatch


class TestPublicAPI:
    """Verify all __all__ exports are importable and correctly typed."""

    def test_version(self):
        assert isinstance(tidewatch.__version__, str)
        parts = tidewatch.__version__.split(".")
        assert len(parts) >= 2

    def test_all_exports_exist(self):
        for name in tidewatch.__all__:
            assert hasattr(tidewatch, name), f"missing export: {name}"

    def test_callable_exports(self):
        expected_callables = [
            "calculate_pressure",
            "pressure_zone",
            "recalculate_batch",
            "bandwidth_adjusted_sort",
            "export_pressure_summary",
            "estimate_task_demand",
        ]
        for name in expected_callables:
            obj = getattr(tidewatch, name)
            assert callable(obj), f"{name} should be callable"

    def test_class_exports(self):
        expected_classes = [
            "SpeculativePlanner",
            "TriageQueue",
            "CognitiveContext",
            "TaskDemand",
            "Obligation",
            "PressureResult",
            "PlanRequest",
            "PlanResult",
            "Zone",
            "TriageCandidate",
        ]
        for name in expected_classes:
            obj = getattr(tidewatch, name)
            assert inspect.isclass(obj), f"{name} should be a class"

    def test_zone_enum_values(self):
        assert tidewatch.Zone.GREEN < tidewatch.Zone.RED

    def test_calculate_pressure_returns_result(self):
        obl = tidewatch.Obligation(
            id="test-1",
            title="Test obligation",
            due_date=None,
            materiality="routine",
            dependency_count=0,
            completion_pct=0.0,
        )
        result = tidewatch.calculate_pressure(obl)
        assert isinstance(result, tidewatch.PressureResult)
        assert 0.0 <= result.pressure <= 1.0
