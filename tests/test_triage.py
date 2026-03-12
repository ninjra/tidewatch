"""Tests for tidewatch.triage — candidate staging and acceptance.

5 tests covering stage/list, accept, reject, dedup, and empty queue.
"""

from datetime import datetime, timezone

from tidewatch.triage import TriageQueue
from tidewatch.types import Obligation, TriageCandidate


class TestTriageQueue:

    def test_stage_and_list(self):
        """Staged candidate should appear in pending list."""
        queue = TriageQueue()
        candidate = TriageCandidate(
            title="File Q1 taxes",
            source="email",
            due_date=datetime(2026, 4, 15, tzinfo=timezone.utc),
        )
        cid = queue.stage(candidate)
        assert cid is not None

        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0][0] == cid
        assert pending[0][1].title == "File Q1 taxes"

    def test_accept_creates_obligation(self):
        """Accepting a candidate should return an Obligation."""
        queue = TriageQueue()
        candidate = TriageCandidate(
            title="Renew LLC",
            source="calendar",
            due_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
            domain="legal",
            context="Annual LLC renewal with state",
        )
        cid = queue.stage(candidate)
        obligation = queue.accept(cid)

        assert isinstance(obligation, Obligation)
        assert obligation.title == "Renew LLC"
        assert obligation.due_date == datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert obligation.domain == "legal"
        assert obligation.description == "Annual LLC renewal with state"
        assert obligation.status == "active"

        # Should be removed from pending
        assert len(queue.list_pending()) == 0

    def test_reject_removes_candidate(self):
        """Rejecting a candidate should remove it from the queue."""
        queue = TriageQueue()
        candidate = TriageCandidate(title="Spam task", source="email")
        cid = queue.stage(candidate)
        assert queue.reject(cid) is True
        assert len(queue.list_pending()) == 0
        # Reject non-existent
        assert queue.reject("nonexistent") is False

    def test_dedup_by_title_source_date(self):
        """Duplicate candidates (same title, source, due_date) should be rejected."""
        queue = TriageQueue()
        due = datetime(2026, 5, 1, tzinfo=timezone.utc)
        c1 = TriageCandidate(title="File taxes", source="email", due_date=due)
        c2 = TriageCandidate(title="File taxes", source="email", due_date=due)
        c3 = TriageCandidate(title="File taxes", source="calendar", due_date=due)

        cid1 = queue.stage(c1)
        cid2 = queue.stage(c2)  # duplicate
        cid3 = queue.stage(c3)  # different source

        assert cid1 is not None
        assert cid2 is None  # rejected as duplicate
        assert cid3 is not None  # different source = not duplicate
        assert len(queue.list_pending()) == 2

    def test_empty_queue(self):
        """Empty queue should return empty list."""
        queue = TriageQueue()
        assert queue.list_pending() == []
        assert queue.accept("nonexistent") is None
        assert queue.reject("nonexistent") is False
