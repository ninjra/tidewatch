"""Integration tests — full pipeline from obligations through planning.

3 tests covering the end-to-end flow.
"""

from datetime import datetime, timedelta, timezone

from tidewatch import (
    Obligation,
    SpeculativePlanner,
    TriageCandidate,
    TriageQueue,
    calculate_pressure,
    pressure_zone,
    recalculate_batch,
)


def _now():
    return datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestFullPipeline:

    def test_full_pipeline(self):
        """Create obligations -> recalculate -> plan -> verify zones match."""
        now = _now()
        obligations = [
            Obligation(
                id=1, title="File Q1 taxes",
                due_date=now + timedelta(days=3),
                materiality="material",
                dependency_count=2,
                completion_pct=0.1,
            ),
            Obligation(
                id=2, title="Update README",
                due_date=now + timedelta(days=14),
                materiality="routine",
                dependency_count=0,
                completion_pct=0.0,
            ),
            Obligation(
                id=3, title="Contract renewal",
                due_date=now + timedelta(days=1),
                materiality="material",
                dependency_count=3,
                completion_pct=0.0,
            ),
        ]

        # Recalculate batch
        results = recalculate_batch(obligations, now=now)
        assert len(results) == 3
        # Should be sorted by pressure descending
        assert results[0].pressure >= results[1].pressure >= results[2].pressure

        # Verify zones match pressure values
        for r in results:
            assert r.zone == pressure_zone(r.pressure)

        # Generate plans
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obligations)

        # Should have plans for non-green obligations
        for req in requests:
            assert req.pressure_result.zone in ("yellow", "orange", "red")
            assert req.obligation.title in [o.title for o in obligations]

    def test_pressure_drives_planning(self):
        """Only high-pressure obligations should get plans."""
        now = _now()
        obligations = [
            Obligation(id=1, title="Urgent", due_date=now + timedelta(days=1), materiality="material"),
            Obligation(id=2, title="Low priority", due_date=now + timedelta(days=60)),
            Obligation(id=3, title="Medium", due_date=now + timedelta(days=5), materiality="material"),
        ]

        results = recalculate_batch(obligations, now=now)
        planner = SpeculativePlanner()
        requests = planner.generate_plan_requests(results, obligations=obligations)

        # Low priority (60 days out, routine) should be green -> no plan
        planned_ids = {req.obligation.id for req in requests}
        assert 2 not in planned_ids
        # Urgent should always be planned
        assert 1 in planned_ids

    def test_zone_transition_detection(self):
        """Track when obligations cross zone boundaries over time."""
        base = _now()

        ob = Obligation(
            id=1, title="Approaching deadline",
            due_date=base + timedelta(days=10),
            materiality="routine",
        )

        zones_over_time = []
        for days_elapsed in range(0, 11):
            current = base + timedelta(days=days_elapsed)
            result = calculate_pressure(ob, now=current)
            zones_over_time.append(result.zone)

        # Should start green and end red
        assert zones_over_time[0] == "green"
        assert zones_over_time[-1] == "red"

        # Should transition through zones in order
        seen_zones = []
        for z in zones_over_time:
            if not seen_zones or seen_zones[-1] != z:
                seen_zones.append(z)

        # Transitions should be monotonically escalating
        zone_order = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
        for i in range(1, len(seen_zones)):
            assert zone_order[seen_zones[i]] > zone_order[seen_zones[i - 1]]
