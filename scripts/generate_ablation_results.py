#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Generate ablation study results for the Tidewatch paper (#1318).

Runs the 6-factor ablation study via run_ablation_study() and outputs:
  - Formatted table: baseline vs each ablated factor's missed_deadline_rate
  - JSON results: benchmarks/ablation_results.json

Usage:
    python3 scripts/generate_ablation_results.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC, datetime

from benchmarks.constants import (
    DEFAULT_SEED,
    DEFAULT_TRIALS,
    JSON_INDENT,
    PAPER_DEFAULT_N,
    PAPER_SIM_START_DAY,
    PAPER_SIM_START_HOUR,
    PAPER_SIM_START_MONTH,
    PAPER_SIM_START_YEAR,
)
from benchmarks.datasets.generate_obligations import generate
from benchmarks.monte_carlo import run_ablation_study
from tidewatch.types import Obligation


def _obligations_from_sob(n: int, seed: int, sim_start: datetime) -> list[Obligation]:
    """Generate Obligation objects from SOB dataset."""
    data = generate(n=n, seed=seed, now=sim_start)
    obs = []
    for d in data:
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
    return obs


def main() -> None:
    sim_start = datetime(
        PAPER_SIM_START_YEAR, PAPER_SIM_START_MONTH, PAPER_SIM_START_DAY,
        PAPER_SIM_START_HOUR, 0, 0, tzinfo=UTC,
    )
    obs = _obligations_from_sob(PAPER_DEFAULT_N, DEFAULT_SEED, sim_start)

    print(f"Running ablation study: N={PAPER_DEFAULT_N}, trials={DEFAULT_TRIALS}, seed={DEFAULT_SEED}")
    results = run_ablation_study(obs, n_trials=DEFAULT_TRIALS, seed=DEFAULT_SEED, sim_start=sim_start)

    # Formatted table
    print(f"\n{'Factor':<25s} {'Missed Rate':>12s} {'CI 95%':>20s} {'Delta':>8s}")
    _TABLE_WIDTH = 67  # Matches column header width above
    print("-" * _TABLE_WIDTH)
    baseline = results["baseline"]
    baseline_rate = baseline.missed_deadline_rate_mean
    baseline_ci = baseline.missed_deadline_rate_ci
    print(f"{'baseline':<25s} {baseline_rate:>12.4f} [{baseline_ci[0]:.4f}, {baseline_ci[1]:.4f}] {'---':>8s}")

    for factor, mc in results.items():
        if factor == "baseline":
            continue
        rate = mc.missed_deadline_rate_mean
        ci = mc.missed_deadline_rate_ci
        delta = rate - baseline_rate
        sign = "+" if delta >= 0 else ""
        print(f"{factor:<25s} {rate:>12.4f} [{ci[0]:.4f}, {ci[1]:.4f}] {sign}{delta:>.4f}")

    # Save JSON
    output_path = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "ablation_results.json")
    output = {name: mc.to_dict() for name, mc in results.items()}
    with open(output_path, "w") as f:
        json.dump(output, f, indent=JSON_INDENT)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
