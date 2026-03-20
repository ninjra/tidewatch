# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Generate Synthetic Obligation Benchmark (SOB).

1,000 obligations across 5 domains with realistic deadline distributions,
dependency graphs, and completion trajectories.

Usage:
    python -m benchmarks.datasets.generate_obligations --output sob.json
"""

import argparse
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DOMAINS = ["legal", "financial", "client_work", "personal_admin", "health"]

# CLI defaults
DEFAULT_N = 1000
DEFAULT_SEED = 42
DEFAULT_OUTPUT = "sob.json"
JSON_INDENT = 2


@dataclass
class SOBConfig:
    """Tunable parameters for SOB generation."""

    material_probability: float = 0.3
    overdue_probability: float = 0.1
    overdue_max_days: int = 14
    deadline_horizon_days: int = 90
    max_dependency_count: int = 10
    dependency_pareto_alpha: float = 1.5
    optimal_attention_fraction: float = 0.3
    min_attention_days: float = 2.0


def generate(
    n: int = 1000,
    seed: int = 42,
    config: SOBConfig | None = None,
) -> list[dict]:
    """Generate n synthetic obligations.

    Inputs:
      n: number of obligations
      seed: random seed for reproducibility
      config: generation parameters (defaults if None)

    Outputs:
      list of obligation dicts with ground-truth optimal_attention_days
    """
    if config is None:
        config = SOBConfig()

    rng = random.Random(seed)
    obligations = []
    now = datetime.now(UTC)

    for i in range(n):
        domain = rng.choice(DOMAINS)
        materiality = "material" if rng.random() < config.material_probability else "routine"

        if rng.random() < config.overdue_probability:
            days_out = -rng.randint(1, config.overdue_max_days)
        else:
            days_out = rng.randint(1, config.deadline_horizon_days)

        due_date = (now + timedelta(days=days_out)).isoformat()

        raw_dep = int(rng.paretovariate(config.dependency_pareto_alpha))
        dep_count = raw_dep if raw_dep <= config.max_dependency_count else config.max_dependency_count

        completion = round(rng.random() * rng.random(), 2)

        if days_out > 0:
            raw_attention = days_out * config.optimal_attention_fraction
            optimal_attention_days = raw_attention if raw_attention >= config.min_attention_days else config.min_attention_days
        else:
            optimal_attention_days = 0.0

        obligations.append({
            "id": i + 1,
            "title": f"{domain.replace('_', ' ').title()} Task {i + 1}",
            "due_date": due_date,
            "materiality": materiality,
            "dependency_count": dep_count,
            "completion_pct": completion,
            "domain": domain,
            "days_out": days_out,
            "optimal_attention_days": round(optimal_attention_days, 1),
        })

    return obligations


def main():
    parser = argparse.ArgumentParser(description="Generate SOB dataset")
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = generate(n=args.n, seed=args.seed)
    with open(args.output, "w") as f:
        json.dump(data, f, indent=JSON_INDENT)
    print(f"Generated {len(data)} obligations -> {args.output}")


if __name__ == "__main__":
    main()
