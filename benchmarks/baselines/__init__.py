# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Baseline urgency models for benchmark comparison.

All baselines implement the BaselineScorer protocol: a `score()` function
accepting `days_remaining` as the first argument and returning a float in [0, 1].
Keyword arguments vary by model (e.g. materiality, horizon).
"""

from __future__ import annotations

from typing import Protocol

from benchmarks.baselines.binary_deadline import score as binary_score
from benchmarks.baselines.eisenhower import QUADRANT_SCORES, score as eisenhower_score
from benchmarks.baselines.linear_urgency import score as linear_score


class BaselineScorer(Protocol):
    """Protocol for baseline urgency scoring functions."""

    def __call__(self, days_remaining: float | None, **kwargs) -> float: ...


# Registry of all baseline scorers
BASELINES: dict[str, BaselineScorer] = {
    "binary": binary_score,
    "linear": linear_score,
    "eisenhower": eisenhower_score,
}

__all__ = [
    "BaselineScorer",
    "BASELINES",
    "binary_score",
    "eisenhower_score",
    "linear_score",
    "QUADRANT_SCORES",
]
