# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Shared fixtures for Tidewatch tests."""

from datetime import datetime, timedelta, timezone

import pytest

from tidewatch.planner import SpeculativePlanner
from tidewatch.types import Obligation


@pytest.fixture
def standard_obligation() -> Obligation:
    """Standard obligation: id=1, due in 7 days, materiality=routine."""
    now = datetime.now(timezone.utc)
    return Obligation(
        id=1,
        title="Standard test obligation",
        due_date=now + timedelta(days=7),
        materiality="routine",
        dependency_count=0,
        completion_pct=0.0,
        domain="test",
        description="A standard test obligation for fixtures.",
        status="active",
    )


@pytest.fixture
def mixed_zone_obligations() -> list[Obligation]:
    """Batch of obligations spanning green, yellow, orange, and red zones.

    Produced by varying days_out and materiality to hit different zones:
    - Green: far deadline, routine
    - Yellow: moderate deadline, routine
    - Orange: close deadline, material
    - Red: overdue, material
    """
    now = datetime.now(timezone.utc)
    return [
        Obligation(
            id=1,
            title="Green zone — far out",
            due_date=now + timedelta(days=60),
            materiality="routine",
            dependency_count=0,
            completion_pct=0.0,
        ),
        Obligation(
            id=2,
            title="Yellow zone — moderate",
            due_date=now + timedelta(days=5),
            materiality="routine",
            dependency_count=1,
            completion_pct=0.0,
        ),
        Obligation(
            id=3,
            title="Orange zone — close + material",
            due_date=now + timedelta(days=3),
            materiality="material",
            dependency_count=2,
            completion_pct=0.0,
        ),
        Obligation(
            id=4,
            title="Red zone — overdue + material",
            due_date=now - timedelta(days=1),
            materiality="material",
            dependency_count=3,
            completion_pct=0.0,
        ),
    ]


@pytest.fixture
def default_planner() -> SpeculativePlanner:
    """SpeculativePlanner with default settings."""
    return SpeculativePlanner()
