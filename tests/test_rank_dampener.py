# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for rank stability dampener (PID-inspired anti-thrashing)."""

from datetime import UTC, datetime, timedelta

from tidewatch.pressure import dampen_rank_changes, recalculate_batch
from tidewatch.types import Obligation

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


class TestDampenRankChanges:

    def test_no_previous_returns_current(self):
        """Without previous results, no dampening applied."""
        obs = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        results = recalculate_batch(obs, now=NOW)
        dampened = dampen_rank_changes(results, previous=None, max_displacement=2)
        assert [r.obligation_id for r in dampened] == [r.obligation_id for r in results]

    def test_no_max_displacement_returns_current(self):
        """Without max_displacement, no dampening applied."""
        obs = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        results = recalculate_batch(obs, now=NOW)
        dampened = dampen_rank_changes(results, previous=results, max_displacement=None)
        assert [r.obligation_id for r in dampened] == [r.obligation_id for r in results]

    def test_displacement_is_reduced(self):
        """Dampener reduces displacement compared to undampened."""
        obs = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(10)
        ]
        prev = recalculate_batch(obs, now=NOW)

        # Reverse the deadlines to cause maximum displacement
        obs_reversed = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=10 - i))
            for i in range(10)
        ]
        curr = recalculate_batch(obs_reversed, now=NOW)

        dampened = dampen_rank_changes(curr, previous=prev, max_displacement=2)

        # Measure total displacement with and without dampening
        prev_positions = {r.obligation_id: i for i, r in enumerate(prev)}

        undampened_displacement = sum(
            abs(i - prev_positions.get(r.obligation_id, i))
            for i, r in enumerate(curr)
        )
        dampened_displacement = sum(
            abs(i - prev_positions.get(r.obligation_id, i))
            for i, r in enumerate(dampened)
        )

        # Dampened total displacement must be strictly less
        assert dampened_displacement < undampened_displacement, (
            f"Dampened ({dampened_displacement}) should be less than "
            f"undampened ({undampened_displacement})"
        )

    def test_new_items_not_dampened(self):
        """Items not in previous results are not dampened."""
        obs1 = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        prev = recalculate_batch(obs1, now=NOW)

        # Add a new high-priority item
        obs2 = obs1 + [
            Obligation(id=99, title="New urgent", due_date=NOW + timedelta(hours=1))
        ]
        curr = recalculate_batch(obs2, now=NOW)

        dampened = dampen_rank_changes(curr, previous=prev, max_displacement=1)
        # New item should still be near the top
        dampened_ids = [r.obligation_id for r in dampened]
        assert 99 in dampened_ids

    def test_backward_compatible_defaults(self):
        """Default parameters (None) reproduce undampened behavior."""
        obs = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(5)
        ]
        results = recalculate_batch(obs, now=NOW)
        dampened = dampen_rank_changes(results)
        assert [r.obligation_id for r in dampened] == [r.obligation_id for r in results]

    def test_empty_inputs(self):
        assert dampen_rank_changes([], previous=[]) == []
        assert dampen_rank_changes([], previous=None) == []
