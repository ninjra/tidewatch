"""Eisenhower matrix baseline: 4-bucket static classification.

Urgent/Important matrix:
  Q1 (urgent + important) = 1.0
  Q2 (not urgent + important) = 0.5
  Q3 (urgent + not important) = 0.75
  Q4 (not urgent + not important) = 0.0
"""

URGENT_THRESHOLD_DAYS = 7


def score(
    days_remaining: float | None,
    materiality: str = "routine",
    **kwargs,
) -> float:
    """Eisenhower urgency score.

    Inputs:
      days_remaining: days until deadline
      materiality: "material" (important) or "routine" (not important)

    Outputs:
      float score based on quadrant
    """
    if days_remaining is None:
        return 0.0

    urgent = days_remaining <= URGENT_THRESHOLD_DAYS
    important = materiality == "material"

    if urgent and important:
        return 1.0  # Q1
    elif urgent and not important:
        return 0.75  # Q3
    elif not urgent and important:
        return 0.5  # Q2
    else:
        return 0.0  # Q4
