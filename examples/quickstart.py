#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Quickstart: Score obligations and get a ranked queue in 10 lines.

Usage:
    pip install tidewatch
    python examples/quickstart.py
"""
from datetime import UTC, datetime, timedelta

from tidewatch import Obligation, recalculate_batch

now = datetime.now(UTC)

obligations = [
    Obligation(id=1, title="Compliance audit",
               due_date=now + timedelta(days=3),
               materiality="material", dependency_count=12),
    Obligation(id=2, title="Update staging config",
               due_date=now + timedelta(days=2)),
    Obligation(id=3, title="Renew SSL certificates",
               due_date=now + timedelta(hours=8),
               materiality="material", dependency_count=30),
    Obligation(id=4, title="Write quarterly report",
               due_date=now + timedelta(days=14),
               completion_pct=0.6),
]

results = recalculate_batch(obligations)

print("Ranked obligations:")
print(f"{'#':>2}  {'Zone':6}  {'Pressure':>8}  Title")
print("-" * 50)
for i, r in enumerate(results, 1):
    ob = next(o for o in obligations if o.id == r.obligation_id)
    print(f"{i:>2}  {r.zone:6}  {r.pressure:>8.3f}  {ob.title}")
