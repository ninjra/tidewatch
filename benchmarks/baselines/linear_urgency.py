# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Linear urgency baseline: urgency = clamp_unit(1 - days_remaining / horizon)."""

from tidewatch.constants import OVERDUE_PRESSURE, clamp_unit


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
      float 0.0-1.0. Returns OVERDUE_PRESSURE for overdue items.
    """
    if days_remaining is None:
        return 0.0
    if days_remaining <= 0:
        return OVERDUE_PRESSURE
    return clamp_unit(1.0 - days_remaining / horizon)
