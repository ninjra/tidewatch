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
from datetime import UTC, datetime, timedelta

DOMAINS = ["legal", "financial", "client_work", "personal_admin", "health"]
MATERIALITY_DIST = {"material": 0.3, "routine": 0.7}

# --- SOB generation parameters ---
MATERIAL_PROBABILITY = 0.3       # Fraction of obligations that are "material"
OVERDUE_PROBABILITY = 0.1        # Fraction of obligations that are overdue
OVERDUE_MAX_DAYS = 14            # Max days overdue for generated obligations
DEADLINE_HORIZON_DAYS = 90       # Max days out for non-overdue obligations
MAX_DEPENDENCY_COUNT = 10        # Cap on power-law dependency generation
DEPENDENCY_PARETO_ALPHA = 1.5    # Shape parameter for dependency count distribution
OPTIMAL_ATTENTION_FRACTION = 0.3 # Start work at this fraction of remaining time
MIN_ATTENTION_DAYS = 2           # Minimum attention window (days)


def generate(n: int = 1000, seed: int = 42) -> list[dict]:
    """Generate n synthetic obligations.

    Inputs:
      n: number of obligations
      seed: random seed for reproducibility

    Outputs:
      list of obligation dicts with ground-truth optimal_attention_days
    """
    rng = random.Random(seed)
    obligations = []
    now = datetime.now(UTC)

    for i in range(n):
        domain = rng.choice(DOMAINS)
        materiality = "material" if rng.random() < MATERIAL_PROBABILITY else "routine"

        # Deadline: uniform 1-DEADLINE_HORIZON days, with OVERDUE_PROBABILITY overdue
        if rng.random() < OVERDUE_PROBABILITY:
            days_out = -rng.randint(1, OVERDUE_MAX_DAYS)
        else:
            days_out = rng.randint(1, DEADLINE_HORIZON_DAYS)

        due_date = (now + timedelta(days=days_out)).isoformat()

        # Dependencies: power-law, capped
        dep_count = min(int(rng.paretovariate(DEPENDENCY_PARETO_ALPHA)), MAX_DEPENDENCY_COUNT)

        # Completion: random progress
        completion = round(rng.random() * rng.random(), 2)  # skewed toward 0

        # Ground truth: optimal attention time
        optimal_attention_days = max(days_out * OPTIMAL_ATTENTION_FRACTION, MIN_ATTENTION_DAYS) if days_out > 0 else 0

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
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default="sob.json")
    args = parser.parse_args()

    data = generate(n=args.n, seed=args.seed)
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Generated {len(data)} obligations -> {args.output}")


if __name__ == "__main__":
    main()
