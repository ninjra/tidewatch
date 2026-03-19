# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for cognitive bandwidth dimension (obligation #254)."""
from datetime import UTC, datetime, timedelta

import pytest

from tidewatch import (
    CognitiveContext,
    Obligation,
    bandwidth_adjusted_sort,
    estimate_task_demand,
    recalculate_batch,
)


def _make_obligation(id, title, days_until_due=5, domain="engineering",
                     materiality="routine", **kw):
    now = datetime.now(UTC)
    return Obligation(
        id=id, title=title,
        due_date=now + timedelta(days=days_until_due),
        domain=domain, materiality=materiality, **kw,
    )


class TestCognitiveContext:
    def test_full_bandwidth_no_signals(self):
        ctx = CognitiveContext()
        assert ctx.effective_bandwidth() == 1.0

    def test_explicit_bandwidth_score(self):
        ctx = CognitiveContext(bandwidth_score=0.3)
        assert ctx.effective_bandwidth() == 0.3

    def test_explicit_overrides_signals(self):
        ctx = CognitiveContext(sleep_quality=1.0, bandwidth_score=0.2)
        assert ctx.effective_bandwidth() == 0.2

    def test_single_signal(self):
        ctx = CognitiveContext(sleep_quality=0.4)
        assert ctx.effective_bandwidth() == 0.4

    def test_multiple_signals_averaged(self):
        ctx = CognitiveContext(sleep_quality=0.8, pain_level=0.4)
        assert ctx.effective_bandwidth() == pytest.approx(0.6)

    def test_hours_since_sleep_normalization(self):
        ctx = CognitiveContext(hours_since_sleep=8.0)
        assert ctx.effective_bandwidth() == 1.0  # 8h = fully rested

        ctx = CognitiveContext(hours_since_sleep=16.0)
        assert ctx.effective_bandwidth() == 0.0  # 16h = depleted

        ctx = CognitiveContext(hours_since_sleep=12.0)
        assert ctx.effective_bandwidth() == 0.5  # 12h = half

    def test_bandwidth_clamped(self):
        ctx = CognitiveContext(bandwidth_score=1.5)
        assert ctx.effective_bandwidth() == 1.0
        ctx = CognitiveContext(bandwidth_score=-0.3)
        assert ctx.effective_bandwidth() == 0.0


class TestTaskDemand:
    def test_legal_high_demand(self):
        ob = _make_obligation(1, "Court filing", domain="legal")
        d = estimate_task_demand(ob)
        assert d.complexity >= 0.8
        assert d.decision_weight >= 0.8

    def test_ops_low_demand(self):
        ob = _make_obligation(2, "Update DNS", domain="ops")
        d = estimate_task_demand(ob)
        assert d.complexity <= 0.4
        assert d.decision_weight <= 0.3

    def test_material_higher_complexity(self):
        routine = _make_obligation(3, "Task", materiality="routine")
        material = _make_obligation(4, "Task", materiality="material")
        assert estimate_task_demand(material).complexity > estimate_task_demand(routine).complexity


class TestHardFloor:
    def test_explicit_hard_floor_sorts_first(self):
        obs = [
            _make_obligation(1, "Legal filing", days_until_due=0.5, domain="legal",
                             materiality="material", hard_floor=True),
            _make_obligation(2, "Update config", days_until_due=0.5, domain="ops"),
        ]
        results = recalculate_batch(obs)
        ctx = CognitiveContext(bandwidth_score=0.0)  # Zero bandwidth
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        # Hard floor must sort first even at zero bandwidth
        assert adjusted[0].obligation_id == 1

    def test_auto_hard_floor_legal_within_24h(self):
        obs = [
            _make_obligation(1, "Court deadline", days_until_due=0.5, domain="legal"),
            _make_obligation(2, "Send email", days_until_due=0.5, domain="ops"),
        ]
        results = recalculate_batch(obs)
        ctx = CognitiveContext(bandwidth_score=0.0)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        # Legal + within 24h = auto hard floor
        assert adjusted[0].obligation_id == 1

    def test_no_auto_hard_floor_legal_far_deadline(self):
        obs = [
            _make_obligation(1, "Legal research", days_until_due=10, domain="legal",
                             materiality="material"),
            _make_obligation(2, "Update config", days_until_due=10, domain="ops"),
        ]
        results = recalculate_batch(obs)
        ctx = CognitiveContext(bandwidth_score=0.1)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        # Legal but far deadline — no hard floor, ops sorts higher at low bandwidth
        assert adjusted[0].obligation_id == 2

    def test_hard_floor_financial(self):
        obs = [
            _make_obligation(1, "Tax payment", days_until_due=0.3, domain="financial"),
            _make_obligation(2, "Clean desk", days_until_due=0.3, domain="ops"),
        ]
        results = recalculate_batch(obs)
        ctx = CognitiveContext(bandwidth_score=0.0)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        assert adjusted[0].obligation_id == 1


class TestBandwidthAdjustedSort:
    def test_full_bandwidth_preserves_order(self):
        obs = [
            _make_obligation(1, "Urgent", days_until_due=1, domain="legal"),
            _make_obligation(2, "Easy", days_until_due=1, domain="ops"),
        ]
        results = recalculate_batch(obs)
        ctx = CognitiveContext(bandwidth_score=1.0)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        # At full bandwidth, order = pure pressure
        assert [r.obligation_id for r in adjusted] == [r.obligation_id for r in results]

    def test_low_bandwidth_promotes_easy_tasks(self):
        obs = [
            _make_obligation(1, "Legal brief", days_until_due=2, domain="legal", materiality="material"),
            _make_obligation(2, "Update config", days_until_due=2, domain="ops"),
        ]
        results = recalculate_batch(obs)
        # At full bandwidth, legal brief should be first (higher pressure from materiality)
        assert results[0].obligation_id == 1

        # At low bandwidth, ops task should sort higher
        ctx = CognitiveContext(bandwidth_score=0.1)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        assert adjusted[0].obligation_id == 2

    def test_no_context_defaults_to_full(self):
        obs = [_make_obligation(1, "Task", days_until_due=3)]
        results = recalculate_batch(obs)
        ctx = CognitiveContext()  # No signals = bandwidth 1.0
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        assert len(adjusted) == 1

    def test_medium_bandwidth_partial_reorder(self):
        obs = [
            _make_obligation(1, "Complex analysis", days_until_due=2, domain="financial", materiality="material"),
            _make_obligation(2, "Send email", days_until_due=2, domain="ops"),
            _make_obligation(3, "Code review", days_until_due=2, domain="engineering"),
        ]
        results = recalculate_batch(obs)

        # At 0.5 bandwidth, complex tasks penalized but not fully
        ctx = CognitiveContext(bandwidth_score=0.5)
        adjusted = bandwidth_adjusted_sort(results, obs, ctx)
        # Ops task should move up relative to financial
        ids = [r.obligation_id for r in adjusted]
        assert ids.index(2) < ids.index(1)  # Ops before financial
