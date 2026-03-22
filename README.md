# Tidewatch

**Multi-objective task prioritization with deferred scalarization.**

Tidewatch decomposes urgency into six multiplicative factors (all bounded
away from zero) and retains them in a six-dimensional component space with
deferred scalarization — preserving per-factor interpretability until
ranking time.

## Install

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from datetime import datetime, timezone, timedelta
from tidewatch import (
    Obligation, calculate_pressure, recalculate_batch,
    CognitiveContext, bandwidth_adjusted_sort,
)

# Create obligations
now = datetime.now(timezone.utc)
obligations = [
    Obligation(
        id=1, title="File Q1 taxes",
        due_date=now + timedelta(days=3),
        materiality="material", dependency_count=2,
        completion_pct=0.1,
    ),
    Obligation(
        id=2, title="Update project README",
        due_date=now + timedelta(days=14),
        materiality="routine", dependency_count=0,
        completion_pct=0.0,
    ),
]

# Calculate pressure (product of all six components)
results = recalculate_batch(obligations)
for r in results:
    print(f"{r.obligation_id}: P={r.pressure:.3f} [{r.zone}]")
    # Access individual factors via component space
    if r.component_space:
        cs = r.component_space.space.components
        print(f"  time={cs['time_pressure']:.3f} mat={cs['materiality']:.1f} "
              f"dep={cs['dependency_amp']:.3f} comp={cs['completion_damp']:.3f}")

# Bandwidth-aware reranking (specified, not empirically validated)
ctx = CognitiveContext(sleep_quality=0.4, pain_level=0.3)
reranked = bandwidth_adjusted_sort(results, obligations, ctx)
for r in reranked:
    print(f"{r.obligation_id}: P={r.pressure:.3f} (reranked)")
```

## Six Factors

| Category | Factor | Role |
|----------|--------|------|
| Temporal | Exponential time-decay | Base urgency signal |
| Temporal | Timing-sensitivity amplification | Escalation for stagnant tasks |
| Temporal | Deadline-violation amplification | Decaying penalty for past misses |
| State | Materiality weighting | Impact classification |
| State | Logistic completion dampening | Urgency reduces as completion → 100% |
| Structural | Temporally gated dependency fanout | Amplification from downstream blockers |

All factors are bounded away from zero. The product cannot collapse from
a single factor.

## Pressure Curve

The exponential time-decay with k=3.0 produces:
- 14 days out: P ≈ 0.19 (green)
- 7 days out: P ≈ 0.35 (yellow)
- 3 days out: P ≈ 0.63 (orange)
- 1 day out: P ≈ 0.95 (red)

## EDF Comparison

EDF is theoretically optimal for deadline minimization. Tidewatch does
not compete on that metric. At N=200, EDF achieves 18.5% missed deadlines
vs. Tidewatch's 20.1% — an 8.6% relative cost of encoding materiality,
dependency fanout, and completion state alongside deadline proximity.

The contribution is interpretable, auditable multi-factor ranking with
deferred scalarization, not deadline optimality.

## Tests

```bash
pytest tests/ -q            # 563 tests
ruff check .                # lint
```

Golden values verified to Δ < 10⁻¹⁰ against analytically computed
reference values under pinned Python 3.11+ with zero runtime dependencies.

## Paper

> **Tidewatch: Continuous Obligation Pressure with Cognitive Bandwidth Adaptation**
> S. N. Justin Ram, Infoil LLC (2026)
> [SSRN link pending]

## License

Apache-2.0 OR Commercial
