#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Generate Monte Carlo benchmark results for the Tidewatch paper.

Produces JSON files for N=50 and N=200 simulations across all strategies.
Results are written to benchmarks/monte_carlo_results*.json.

Usage:
    python3 scripts/generate_mc_results.py
    python3 scripts/generate_mc_results.py --n 200 --output benchmarks/monte_carlo_results_n200.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC, datetime

from benchmarks.datasets.generate_obligations import generate
from benchmarks.monte_carlo import compare_strategies
from tidewatch.types import Obligation

# Paper strategies — subset that appears in manuscript tables
PAPER_STRATEGIES = [
    "tidewatch",
    "tidewatch_bw_mid",
    "tidewatch_bw_low",
    "tidewatch_bw_variable",
    "weighted_edf",
    "weighted_sum",
    "edf",
    "fifo",
    "random",
]

N_TRIALS = 200
SEED = 42
JSON_INDENT = 2


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


def main():
    parser = argparse.ArgumentParser(description="Generate MC benchmark results")
    parser.add_argument("--n", type=int, default=50, help="Number of obligations")
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.output is None:
        if args.n == 50:
            args.output = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "monte_carlo_results_full.json")
        else:
            args.output = os.path.join(os.path.dirname(__file__), "..", "benchmarks", f"monte_carlo_results_n{args.n}.json")

    sim_start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    obs = _obligations_from_sob(args.n, args.seed, sim_start)

    print(f"Running MC simulation: N={args.n}, trials={args.trials}, seed={args.seed}")
    all_results = compare_strategies(obs, n_trials=args.trials, seed=args.seed, sim_start=sim_start)

    # Filter to paper strategies
    output = {}
    for name in PAPER_STRATEGIES:
        if name in all_results:
            r = all_results[name]
            output[name] = {
                "strategy": name,
                "n_trials": r.n_trials,
                "missed_deadline_rate": {
                    "mean": round(r.missed_deadline_rate_mean, 4),
                    "std": round(r.missed_deadline_rate_std, 3),
                },
                "queue_inversion_rate": {
                    "mean": round(r.queue_inversion_rate_mean, 4),
                    "std": round(r.queue_inversion_rate_std, 4),
                },
                "attention_efficiency": {
                    "mean": round(r.attention_efficiency_mean, 4),
                    "std": round(r.attention_efficiency_std, 4),
                },
                "saturation_rate": {
                    "mean": round(r.saturation_rate_mean, 3),
                    "std": round(r.saturation_rate_std, 4),
                },
            }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=JSON_INDENT)

    print(f"Results written to {args.output}")
    for name, data in output.items():
        m = data["missed_deadline_rate"]["mean"]
        print(f"  {name:30s}  missed={m:.4f}")


if __name__ == "__main__":
    main()
