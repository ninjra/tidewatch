# Tidewatch

**Continuous obligation pressure with proactive idle-time planning.**

Tidewatch models deadline urgency as a hydraulic pressure field.
Obligations build pressure exponentially as deadlines approach.
Material obligations carry more. Dependencies amplify. Progress
dampens. The system plans before you ask.

## Install

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from datetime import datetime, timezone, timedelta
from tidewatch import (
    Obligation, calculate_pressure, pressure_zone,
    SpeculativePlanner, recalculate_batch,
)

# Create obligations
obligations = [
    Obligation(
        id=1, title="File Q1 taxes",
        due_date=datetime.now(timezone.utc) + timedelta(days=3),
        materiality="material", dependency_count=2,
        completion_pct=0.1,
    ),
    Obligation(
        id=2, title="Update project README",
        due_date=datetime.now(timezone.utc) + timedelta(days=14),
        materiality="routine", dependency_count=0,
        completion_pct=0.0,
    ),
]

# Calculate pressure
results = recalculate_batch(obligations)
for r in results:
    print(f"{r.obligation_id}: P={r.pressure:.2f} [{r.zone}]")

# Generate speculative plans for high-pressure items
planner = SpeculativePlanner()
plan_requests = planner.generate_plan_requests(results, obligations=obligations)
for req in plan_requests:
    print(f"Plan needed: {req.obligation.title}")
    print(f"Prompt: {req.prompt[:100]}...")
    # Send req.prompt to your LLM, then:
    # result = planner.complete_plan(req, llm_output)
```

## Paper

> **Tidewatch: Continuous Obligation Pressure with Proactive Idle-Time
> Planning for Intelligent Task Management**
> Justin Ram, Infoil LLC (2026)
> [SSRN link pending]

## License

Apache-2.0 OR Commercial
