#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Terminal demo for README GIF recording.

Usage:
    asciinema rec demo.cast --command "python3 scripts/demo.py"
    agg demo.cast demo.gif

Or with terminalizer:
    terminalizer record demo --command "python3 scripts/demo.py"
    terminalizer render demo
"""
import time
from datetime import UTC, datetime, timedelta

from tidewatch import Obligation, recalculate_batch


# Simulate typing delay for demo
def show(text, delay=0.03):
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()

def pause(seconds=0.5):
    time.sleep(seconds)

# Header
show(">>> from tidewatch import Obligation, recalculate_batch")
pause()


show(">>> now = datetime.now(UTC)")
pause(0.3)

now = datetime(2026, 6, 15, 9, 0, 0, tzinfo=UTC)

show(">>> obligations = [")
show('...     Obligation(id=1, title="File Q1 taxes",')
show('...                due_date=now + timedelta(days=2),')
show('...                materiality="material", dependency_count=3),')
show('...     Obligation(id=2, title="Review PR #847",')
show('...                due_date=now + timedelta(days=7)),')
show('...     Obligation(id=3, title="Update monitoring dashboards",')
show('...                due_date=now + timedelta(days=21)),')
show('...     Obligation(id=4, title="Renew SSL certificates",')
show('...                due_date=now + timedelta(hours=18),')
show('...                materiality="material", dependency_count=8),')
show("... ]")
pause()

obligations = [
    Obligation(id=1, title="File Q1 taxes",
               due_date=now + timedelta(days=2),
               materiality="material", dependency_count=3),
    Obligation(id=2, title="Review PR #847",
               due_date=now + timedelta(days=7)),
    Obligation(id=3, title="Update monitoring dashboards",
               due_date=now + timedelta(days=21)),
    Obligation(id=4, title="Renew SSL certificates",
               due_date=now + timedelta(hours=18),
               materiality="material", dependency_count=8),
]

show(">>> results = recalculate_batch(obligations, now=now)")
pause()

results = recalculate_batch(obligations, now=now)

show(">>> for r in results:")
show('...     print(f"  {r.zone:6s} P={r.pressure:.3f}  {obligations_map[r.obligation_id]}")')
pause(0.3)

obligations_map = {ob.id: ob.title for ob in obligations}

print()
for r in results:
    zone_colors = {"red": "\033[91m", "orange": "\033[93m", "yellow": "\033[33m", "green": "\033[92m"}
    reset = "\033[0m"
    color = zone_colors.get(r.zone, "")
    bar = "█" * int(r.pressure * 30)
    print(f"  {color}{r.zone:6s}{reset} P={r.pressure:.3f}  {bar}  {obligations_map[r.obligation_id]}")
    time.sleep(0.4)

print()
pause(0.5)

show(">>> # Factor decomposition for top item:")
top = results[0]
if top.component_space:
    cs = top.component_space.space.components
    show(f">>> r = results[0]  # {obligations_map[top.obligation_id]}")
    pause(0.3)
    print(f"  time_pressure:  {cs.get('time_pressure', 0):.3f}")
    time.sleep(0.2)
    print(f"  materiality:    {cs.get('materiality', 1):.1f}")
    time.sleep(0.2)
    print(f"  dependency_amp: {cs.get('dependency_amp', 1):.3f}")
    time.sleep(0.2)
    print(f"  completion:     {cs.get('completion_damp', 1):.3f}")
    time.sleep(0.2)

print()
show("# Zero dependencies. Pure Python 3.11+. 688 tests.")
pause(1)
