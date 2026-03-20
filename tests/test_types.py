# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch.types — core dataclasses, bandwidth, task demand."""

from datetime import UTC, datetime

from tidewatch.types import (
    CognitiveContext,
    Obligation,
    TaskDemand,
    TriageCandidate,
    Zone,
    estimate_task_demand,
)


class TestObligation:
    def test_minimal_construction(self):
        ob = Obligation(id=1, title="test", due_date=datetime.now(UTC))
        assert ob.id == 1
        assert ob.materiality == "routine"
        assert ob.completion_pct == 0.0
        assert ob.dependency_count == 0

    def test_defaults(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC))
        assert ob.domain is None
        assert ob.hard_floor is False
        assert ob.days_in_status == 0
        assert ob.violation_count == 0

    def test_material_obligation(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC), materiality="material")
        assert ob.materiality == "material"


class TestCognitiveContext:
    def test_no_signals_returns_full_bandwidth(self):
        ctx = CognitiveContext()
        assert ctx.effective_bandwidth() == 1.0

    def test_explicit_bandwidth_score(self):
        ctx = CognitiveContext(bandwidth_score=0.5)
        assert ctx.effective_bandwidth() == 0.5

    def test_bandwidth_score_clamped_above(self):
        ctx = CognitiveContext(bandwidth_score=1.5)
        assert ctx.effective_bandwidth() == 1.0

    def test_bandwidth_score_clamped_below(self):
        ctx = CognitiveContext(bandwidth_score=-0.5)
        assert ctx.effective_bandwidth() == 0.0

    def test_sleep_quality_only(self):
        ctx = CognitiveContext(sleep_quality=0.8)
        assert ctx.effective_bandwidth() == 0.8

    def test_pain_level_only(self):
        ctx = CognitiveContext(pain_level=0.3)
        assert ctx.effective_bandwidth() == 0.3

    def test_multi_signal_average(self):
        ctx = CognitiveContext(sleep_quality=0.8, pain_level=0.4)
        assert abs(ctx.effective_bandwidth() - 0.6) < 1e-9

    def test_hours_since_sleep_good(self):
        ctx = CognitiveContext(hours_since_sleep=4.0)
        assert ctx.effective_bandwidth() == 1.0

    def test_hours_since_sleep_bad(self):
        ctx = CognitiveContext(hours_since_sleep=16.0)
        assert ctx.effective_bandwidth() == 0.0

    def test_hours_since_sleep_midpoint(self):
        ctx = CognitiveContext(hours_since_sleep=12.0)
        assert abs(ctx.effective_bandwidth() - 0.5) < 1e-9

    def test_violation_rate_reduces_bandwidth(self):
        ctx = CognitiveContext(violation_rate=0.3)
        assert abs(ctx.effective_bandwidth() - 0.7) < 1e-9


class TestTaskDemand:
    def test_default_values(self):
        td = TaskDemand()
        assert td.complexity == 0.5
        assert td.novelty == 0.5
        assert td.decision_weight == 0.5


class TestEstimateTaskDemand:
    def test_legal_domain_high_demand(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC), domain="legal")
        demand = estimate_task_demand(ob)
        assert demand.complexity >= 0.8
        assert demand.decision_weight >= 0.9

    def test_ops_domain_low_demand(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC), domain="ops")
        demand = estimate_task_demand(ob)
        assert demand.complexity <= 0.3
        assert demand.decision_weight <= 0.2

    def test_material_boosts_complexity(self):
        ob_routine = Obligation(id=1, title="t", due_date=datetime.now(UTC),
                                domain="ops", materiality="routine")
        ob_material = Obligation(id=2, title="t", due_date=datetime.now(UTC),
                                 domain="ops", materiality="material")
        d_routine = estimate_task_demand(ob_routine)
        d_material = estimate_task_demand(ob_material)
        assert d_material.complexity > d_routine.complexity
        assert d_material.decision_weight > d_routine.decision_weight

    def test_demand_dimensions_bounded(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC),
                        domain="legal", materiality="material")
        demand = estimate_task_demand(ob)
        assert 0.0 <= demand.complexity <= 1.0
        assert 0.0 <= demand.novelty <= 1.0
        assert 0.0 <= demand.decision_weight <= 1.0

    def test_unknown_domain_uses_default(self):
        ob = Obligation(id=1, title="t", due_date=datetime.now(UTC), domain="alien")
        demand = estimate_task_demand(ob)
        assert demand.complexity == 0.5


class TestZone:
    def test_zone_values(self):
        assert Zone.GREEN.value == "green"
        assert Zone.YELLOW.value == "yellow"
        assert Zone.ORANGE.value == "orange"
        assert Zone.RED.value == "red"


class TestTriageCandidate:
    def test_construction(self):
        tc = TriageCandidate(title="Review PR", source="github")
        assert tc.title == "Review PR"
        assert tc.source == "github"
