# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Linear urgency baseline: urgency = max(0, 1 - days_remaining / horizon)."""

DEFAULT_HORIZON = 90  # ASSUMPTION_OK: baseline parameter, not tunable in production


def score(
    days_remaining: float | None,
    horizon: float = DEFAULT_HORIZON,
    **kwargs,
) -> float:
    """Linear urgency score.

    Inputs:
      days_remaining: days until deadline (negative = overdue, None = no deadline)
      horizon: max planning horizon in days

    Outputs:
      float 0.0-1.0

    Notes:
      Returns 1.0 for overdue — this is max urgency by definition,
      not a missing measurement.  # ASSUMPTION_OK: overdue = max urgency
    """
    if days_remaining is None:
        return 0.0
    if days_remaining <= 0:
        return 1.0  # ASSUMPTION_OK: overdue = max urgency by definition
    return max(0.0, 1.0 - days_remaining / horizon)  # MATH_GUARD: linear interpolation floor
