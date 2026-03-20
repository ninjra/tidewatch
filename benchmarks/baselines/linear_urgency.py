# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Linear urgency baseline: urgency = max(0, min(1, 1 - days_remaining / horizon)).

Independent implementation — no imports from tidewatch core to avoid
shared-infrastructure bias in benchmark comparisons.
"""


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
      float 0.0-1.0. Returns 1.0 for overdue items.
    """
    if days_remaining is None:
        return 0.0
    if days_remaining <= 0:
        return 1.0
    raw = 1.0 - days_remaining / horizon
    return max(0.0, min(1.0, raw))
