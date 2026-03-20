# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Linear urgency baseline: urgency = max(0, min(1, 1 - days_remaining / horizon)).

Independent implementation — no imports from tidewatch core to avoid
shared-infrastructure bias in benchmark comparisons.
"""

# Score domain bounds — urgency is a [0,1] quantity by definition
_SCORE_FLOOR = 0.0
_SCORE_CEIL = 1.0
_NO_DEADLINE_SCORE = 0.0
# Overdue ceiling: days_remaining <= 0 means deadline passed, maximum urgency.
# This is a domain ceiling, not an approximation — urgency cannot exceed 1.0.
_OVERDUE_SCORE = 1.0


def score(
    days_remaining: float | None,
    horizon: float = 90.0,
    **kwargs,
) -> float:
    """Linear urgency score.

    Inputs:
      days_remaining: days until deadline (negative = overdue, None = no deadline)
      horizon: max planning horizon in days

    Outputs:
      float 0.0-1.0. Returns _OVERDUE_SCORE for overdue items.
    """
    if days_remaining is None:
        return _NO_DEADLINE_SCORE
    if days_remaining <= 0:
        return _OVERDUE_SCORE
    raw = 1.0 - days_remaining / horizon
    return max(_SCORE_FLOOR, min(_SCORE_CEIL, raw))
