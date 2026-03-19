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
from datetime import datetime, timedelta, timezone

DOMAINS = ["legal", "financial", "client_work", "personal_admin", "health"]
MATERIALITY_DIST = {"material": 0.3, "routine": 0.7}


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
    now = datetime.now(timezone.utc)

    for i in range(n):
        domain = rng.choice(DOMAINS)
        materiality = "material" if rng.random() < 0.3 else "routine"

        # Deadline: uniform 1-90 days, with 10% overdue
        if rng.random() < 0.1:
            days_out = -rng.randint(1, 14)  # overdue
        else:
            days_out = rng.randint(1, 90)

        due_date = (now + timedelta(days=days_out)).isoformat()

        # Dependencies: power-law, mean ~2
        dep_count = min(int(rng.paretovariate(1.5)), 10)

        # Completion: random progress
        completion = round(rng.random() * rng.random(), 2)  # skewed toward 0

        # Ground truth: optimal attention time
        # Heuristic: start working at max(days_out * 0.3, 2) days before deadline
        optimal_attention_days = max(days_out * 0.3, 2) if days_out > 0 else 0

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
