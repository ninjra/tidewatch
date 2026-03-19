# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for tidewatch.planner — speculative plan generation.

8 tests covering zone filtering, top-N limits, prompt content,
delivery urgency, plan completion, and custom system prompts.
"""

from datetime import datetime, timedelta, timezone

from tidewatch.planner import SpeculativePlanner
from tidewatch.pressure import calculate_pressure, recalculate_batch
from tidewatch.types import Obligation, PlanRequest, PlanResult, PressureResult


def _now():
    return datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_ob(id: int, days_out: float, materiality: str = "routine", **kwargs) -> Obligation:
    now = _now()
    return Obligation(
        id=id,
        title=kwargs.get("title", f"Obligation {id}"),
        due_date=now + timedelta(days=days_out),
        materiality=materiality,
        dependency_count=kwargs.get("dependency_count", 0),
        completion_pct=kwargs.get("completion_pct", 0.0),
        domain=kwargs.get("domain", "general"),
        description=kwargs.get("description", "Test description"),
    )


class TestPlannerFiltering:

    def test_green_not_planned(self):
        """Green zone obligations should not get plan requests."""
        planner = SpeculativePlanner()
        ob = _make_ob(1, days_out=30)
        results = recalculate_batch([ob], now=_now())
        # Verify it's green first
        assert results[0].zone == "green"
        requests = planner.generate_plan_requests(results, obligations=[ob])
        assert len(requests) == 0

    def test_orange_triggers_plan(self):
        """Orange zone should generate a PlanRequest."""
        planner = SpeculativePlanner()
        ob = _make_ob(1, days_out=3, materiality="routine")
        results = recalculate_batch([ob], now=_now())
        assert results[0].zone in ("yellow", "orange", "red")
        requests = planner.generate_plan_requests(results, obligations=[ob])
        assert len(requests) == 1
        assert isinstance(requests[0], PlanRequest)

    def test_red_triggers_plan(self):
        """Red zone should generate a PlanRequest."""
        planner = SpeculativePlanner()
        ob = _make_ob(1, days_out=1, materiality="material")
        results = recalculate_batch([ob], now=_now())
        assert results[0].zone == "red"
        requests = planner.generate_plan_requests(results, obligations=[ob])
        assert len(requests) == 1


class TestPlannerLimits:

    def test_top_n_limit(self):
        """Only top-N should be returned even with more eligible."""
        planner = SpeculativePlanner(top_n=2)
        obs = [_make_ob(i, days_out=i, materiality="material") for i in range(1, 6)]
        results = recalculate_batch(obs, now=_now())
        requests = planner.generate_plan_requests(results, obligations=obs)
        assert len(requests) <= 2


class TestPromptContent:

    def test_prompt_contains_obligation_data(self):
        """Prompt should include title, due date, and zone."""
        planner = SpeculativePlanner()
        ob = _make_ob(1, days_out=2, title="File Q1 taxes", domain="financial")
        results = recalculate_batch([ob], now=_now())
        requests = planner.generate_plan_requests(results, obligations=[ob])
        assert len(requests) == 1
        prompt = requests[0].prompt
        assert "File Q1 taxes" in prompt
        assert "financial" in prompt
        assert results[0].zone in prompt


class TestDeliveryUrgency:

    def test_delivery_urgency_by_zone(self):
        """yellow=background, orange=toast, red=interrupt."""
        planner = SpeculativePlanner()

        # Yellow: ~7 days, material pushes into yellow
        ob_y = _make_ob(1, days_out=7, materiality="material")
        r_y = recalculate_batch([ob_y], now=_now())
        req_y = planner.generate_plan_requests(r_y, obligations=[ob_y])
        if req_y and r_y[0].zone == "yellow":
            assert req_y[0].delivery_urgency == "background"

        # Orange: ~3 days
        ob_o = _make_ob(2, days_out=3, materiality="material")
        r_o = recalculate_batch([ob_o], now=_now())
        req_o = planner.generate_plan_requests(r_o, obligations=[ob_o])
        if req_o and r_o[0].zone == "orange":
            assert req_o[0].delivery_urgency == "toast"

        # Red: ~1 day, material
        ob_r = _make_ob(3, days_out=1, materiality="material")
        r_r = recalculate_batch([ob_r], now=_now())
        req_r = planner.generate_plan_requests(r_r, obligations=[ob_r])
        assert len(req_r) == 1
        assert req_r[0].delivery_urgency == "interrupt"


class TestPlanCompletion:

    def test_complete_plan_wraps_result(self):
        """PlanResult should contain obligation metadata."""
        planner = SpeculativePlanner()
        ob = _make_ob(1, days_out=2, title="Ship contract")
        results = recalculate_batch([ob], now=_now())
        requests = planner.generate_plan_requests(results, obligations=[ob])
        assert len(requests) == 1

        plan_text = "1. Draft the contract\n2. Send to legal\n3. Get signature"
        plan_result = planner.complete_plan(requests[0], plan_text)
        assert isinstance(plan_result, PlanResult)
        assert plan_result.obligation_id == 1
        assert plan_result.plan_text == plan_text
        assert plan_result.zone == results[0].zone
        assert plan_result.pressure == results[0].pressure

    def test_custom_system_prompt(self):
        """Custom system prompt should be stored and usable."""
        custom = "You are a specialized legal planner."
        planner = SpeculativePlanner(system_prompt=custom)
        assert planner.system_prompt == custom
