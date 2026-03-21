# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Generate Synthetic Obligation Benchmark (SOB).

1,000 obligations across 5 domains with realistic deadline distributions,
dependency graphs, and completion trajectories. Uses seeded random.Random
for reproducibility — same seed produces identical output.

Usage:
    python -m benchmarks.datasets.generate_obligations --output sob.json
"""

import argparse
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from benchmarks.constants import DEFAULT_N, DEFAULT_OUTPUT, DEFAULT_SEED, JSON_INDENT

DOMAINS = ["legal", "financial", "client_work", "personal_admin", "health"]


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


def _build_obligation(
    idx: int, domain: str, materiality: str, due_date: str,
    dep_count: int, completion: float, days_out: int,
    optimal_attention_days: float,
) -> dict:
    """Build a single synthetic obligation dict."""
    return {
        "id": idx + 1,
        "title": f"{domain.replace('_', ' ').title()} Task {idx + 1}",
        "due_date": due_date,
        "materiality": materiality,
        "dependency_count": dep_count,
        "completion_pct": completion,
        "domain": domain,
        "days_out": days_out,
        "optimal_attention_days": round(optimal_attention_days, 1),
    }


def _sample_obligation_fields(
    rng: random.Random,
    config: SOBConfig,
    now: datetime,
) -> tuple[str, str, int, str, int, float, float]:
    """Sample random fields for a single synthetic obligation.

    Returns:
        (domain, materiality, days_out, due_date_iso, dep_count,
         completion, optimal_attention_days)
    """
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

    return domain, materiality, days_out, due_date, dep_count, completion, optimal_attention_days


def generate(
    n: int = 1000,
    seed: int = 42,
    config: SOBConfig | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Generate n synthetic obligations.

    Inputs:
      n: number of obligations
      seed: random seed for reproducibility
      config: generation parameters (defaults if None)
      now: reference time for due_date generation (default: UTC now)

    Outputs:
      list of obligation dicts with ground-truth optimal_attention_days
    """
    if config is None:
        config = SOBConfig()

    rng = random.Random(seed)
    obligations = []
    if now is None:
        now = datetime.now(UTC)

    for i in range(n):
        domain, materiality, days_out, due_date, dep_count, completion, optimal_attention_days = (
            _sample_obligation_fields(rng, config, now)
        )
        obligations.append(_build_obligation(
            i, domain, materiality, due_date,
            dep_count, completion, days_out, optimal_attention_days,
        ))

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
