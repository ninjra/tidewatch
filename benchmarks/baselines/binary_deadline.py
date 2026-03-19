# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Binary deadline baseline: urgency = 1 if overdue, 0 otherwise."""


def score(days_remaining: float | None, **kwargs) -> float:
    """Binary urgency score.

    Inputs:
      days_remaining: days until deadline (negative = overdue, None = no deadline)

    Outputs:
      1.0 if overdue, 0.0 otherwise
    """
    if days_remaining is None:
        return 0.0
    return 1.0 if days_remaining <= 0 else 0.0
