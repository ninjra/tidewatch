"""Triage queue -- stage candidate obligations for user review.

In-memory queue. Caller handles persistence.
No database, no filesystem, no async.

Usage:
  queue = TriageQueue()
  cid = queue.stage(TriageCandidate(title="File Q1 taxes", source="email"))
  pending = queue.list_pending()
  obligation = queue.accept(cid)
"""

import uuid
from datetime import datetime

from tidewatch.types import Obligation, TriageCandidate


class TriageQueue:
    """In-memory triage queue for candidate obligations.

    Inputs (constructor): None

    Notes:
      Deduplicates by (title_lower, source, due_date) tuple.
      Caller handles persistence -- Tidewatch provides the logic.
    """

    def __init__(self) -> None:
        self._candidates: dict[str, TriageCandidate] = {}
        self._seen: set[tuple[str, str, datetime | None]] = set()
        self._id_counter = 0

    def _dedup_key(self, candidate: TriageCandidate) -> tuple[str, str, datetime | None]:
        """Generate deduplication key for a candidate."""
        return (
            candidate.title.lower().strip(),
            candidate.source,
            candidate.due_date,
        )

    def stage(self, candidate: TriageCandidate) -> str | None:
        """Stage a candidate for user review.

        Inputs:
          candidate: TriageCandidate to stage

        Logic:
          1. Check dedup key (title_lower, source, due_date)
          2. If duplicate, return None
          3. Otherwise, assign ID and store

        Outputs:
          str ID if staged, None if duplicate
        """
        key = self._dedup_key(candidate)
        if key in self._seen:
            return None

        self._seen.add(key)
        cid = str(uuid.uuid4())
        self._candidates[cid] = candidate
        return cid

    def list_pending(self) -> list[tuple[str, TriageCandidate]]:
        """List all pending triage candidates.

        Outputs:
          list of (id, TriageCandidate) tuples, ordered by staged_at
        """
        items = list(self._candidates.items())
        items.sort(key=lambda x: x[1].staged_at)
        return items

    def accept(self, candidate_id: str) -> Obligation | None:
        """Accept a staged candidate, creating an Obligation.

        Inputs:
          candidate_id: the ID returned by stage()

        Logic:
          1. Look up candidate by ID
          2. Remove from queue
          3. Create and return Obligation

        Outputs:
          Obligation if found, None if not found
        """
        candidate = self._candidates.pop(candidate_id, None)
        if candidate is None:
            return None

        return Obligation(
            id=candidate_id,
            title=candidate.title,
            due_date=candidate.due_date,
            domain=candidate.domain,
            description=candidate.context,
            status="active",
        )

    def reject(self, candidate_id: str) -> bool:
        """Reject a staged candidate, removing it from the queue.

        Inputs:
          candidate_id: the ID returned by stage()

        Outputs:
          True if found and removed, False if not found
        """
        candidate = self._candidates.pop(candidate_id, None)
        return candidate is not None
