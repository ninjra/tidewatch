# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Eisenhower matrix baseline: 4-bucket static classification.

Urgent/Important matrix:
  Q1 (urgent + important) = 1.0
  Q2 (not urgent + important) = 0.5
  Q3 (urgent + not important) = 0.75
  Q4 (not urgent + not important) = 0.0
"""

from benchmarks.constants import EISENHOWER_URGENT_THRESHOLD_DAYS


def _quadrant_scores() -> dict[tuple[bool, bool], float]:
    """Eisenhower quadrant scores — fixed by definition of the matrix."""
    return {
        (True, True): 1.0,    # Q1: urgent + important
        (True, False): 0.75,  # Q3: urgent + not important
        (False, True): 0.5,   # Q2: not urgent + important
        (False, False): 0.0,  # Q4: not urgent + not important
    }


QUADRANT_SCORES = _quadrant_scores()


def score(
    days_remaining: float | None,
    materiality: str = "routine",
    urgent_threshold_days: float = EISENHOWER_URGENT_THRESHOLD_DAYS,
    **kwargs,
) -> float:
    """Eisenhower urgency score.

    Inputs:
      days_remaining: days until deadline
      materiality: "material" (important) or "routine" (not important)
      urgent_threshold_days: days within which an obligation is "urgent"

    Outputs:
      float score based on quadrant
    """
    if days_remaining is None:
        return 0.0

    urgent = days_remaining <= urgent_threshold_days
    important = materiality == "material"
    return QUADRANT_SCORES[(urgent, important)]
