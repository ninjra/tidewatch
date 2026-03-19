# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Benchmark runner for Tidewatch.

Usage:
    python -m benchmarks.run --suite all
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tidewatch import Obligation, recalculate_batch

from benchmarks.baselines import binary_deadline, eisenhower, linear_urgency
from benchmarks.datasets.generate_obligations import generate
from benchmarks.metrics import (
    attention_allocation_efficiency,
    false_alarm_rate,
    missed_deadline_rate,
    zone_transition_timeliness,
)


def run_tidewatch(obligations_data: list[dict], now: datetime) -> list[float]:
    """Run Tidewatch on a list of obligation dicts, return pressure scores."""
    obs = []
    for d in obligations_data:
        due = datetime.fromisoformat(d["due_date"]) if d.get("due_date") else None
        obs.append(Obligation(
            id=d["id"],
            title=d["title"],
            due_date=due,
            materiality=d.get("materiality", "routine"),
            dependency_count=d.get("dependency_count", 0),
            completion_pct=d.get("completion_pct", 0.0),
            domain=d.get("domain"),
        ))
    results = recalculate_batch(obs, now=now)
    # Return in original order
    score_map = {r.obligation_id: r.pressure for r in results}
    return [score_map.get(d["id"], 0.0) for d in obligations_data]


def run_baseline(name: str, obligations_data: list[dict]) -> list[float]:
    """Run a baseline scorer on obligation dicts."""
    scorers = {
        "binary": binary_deadline.score,
        "linear": linear_urgency.score,
        "eisenhower": eisenhower.score,
    }
    scorer = scorers[name]
    return [
        scorer(
            days_remaining=d.get("days_out"),
            materiality=d.get("materiality", "routine"),
        )
        for d in obligations_data
    ]


def main():
    parser = argparse.ArgumentParser(description="Run Tidewatch benchmarks")
    parser.add_argument("--suite", choices=["all", "pressure", "baselines"], default="all")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Generating {args.n} obligations (seed={args.seed})...")
    data = generate(n=args.n, seed=args.seed)
    now = datetime.now(timezone.utc)

    print("\n--- Tidewatch ---")
    tw_scores = run_tidewatch(data, now)
    print(f"  Mean pressure: {sum(tw_scores) / len(tw_scores):.3f}")
    print(f"  Max pressure:  {max(tw_scores):.3f}")
    print(f"  Min pressure:  {min(tw_scores):.3f}")

    for baseline in ["binary", "linear", "eisenhower"]:
        print(f"\n--- {baseline.title()} ---")
        scores = run_baseline(baseline, data)
        print(f"  Mean score: {sum(scores) / len(scores):.3f}")
        print(f"  Max score:  {max(scores):.3f}")
        print(f"  Min score:  {min(scores):.3f}")

    print("\nBenchmark complete.")


if __name__ == "__main__":
    main()
