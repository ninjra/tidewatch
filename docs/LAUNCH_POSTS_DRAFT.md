# Launch Post Drafts — For Review

> These are drafts. Nothing gets posted without your explicit approval.

---

## Hacker News — Show HN

**Title:** Show HN: Tidewatch – Continuous pressure scoring for obligation queues (zero deps, 659 tests)

**Body:**

I built a scoring engine that tells agents (or humans) what to work on next.

Most task systems use binary overdue/not-overdue or simple priority labels. Tidewatch computes a continuous pressure score (0.0–1.0) from six multiplicative factors: deadline proximity (exponential decay), materiality, dependency fanout, completion progress, stagnation, and violation history.

The key insight is deferred scalarization — the six factors stay decomposed until the final score, so you can inspect exactly why something ranked high. It's not a black box.

Why I built it: I needed an obligation queue for an agent orchestration system where the agents needed to autonomously decide what to work on. EDF (Earliest Deadline First) doesn't account for importance or dependencies. Priority labels don't capture urgency accumulating over time.

Stats:
- 659 tests, 97% coverage
- Zero runtime dependencies (stdlib math only)
- Verified to delta < 10^-10 against closed-form reference values
- Scales to 5M obligations in 74s single-core
- Python 3.11+

Paper: "Multi-Factor Obligation Pressure with Deferred Scalarization" (SSRN, in review)

pip install tidewatch

https://github.com/ninjra/tidewatch

---

## Reddit r/Python

**Title:** I built a zero-dependency pressure scoring engine for task/obligation queues — 659 tests, 97% coverage

**Body:**

**What My Project Does**

Tidewatch computes continuous pressure scores (0.0–1.0) for obligations/tasks based on six factors: deadline proximity, materiality, dependency count, completion progress, time-in-status, and violation history. It's designed for agent orchestration — giving autonomous agents a mathematically grounded way to decide what to work on next.

The core equation: `P = min(1.0, P_time × M × A × D × T_amp × V_amp)`

Each factor stays decomposed until the final score (deferred scalarization), so every ranking decision is auditable.

**Target Audience**

- People building agent orchestration systems who need queue ordering beyond simple priority labels
- Anyone working with deadline-driven work queues who wants continuous urgency signals instead of binary overdue/not-overdue
- Researchers interested in obligation scheduling theory

**Comparison**

- vs. EDF (Earliest Deadline First): Tidewatch considers materiality and dependencies, not just time
- vs. priority labels (P0/P1/P2): Tidewatch is continuous, so urgency accumulates gradually — you see a task heating up days before it's due
- vs. weighted scoring: Tidewatch uses deferred scalarization — factors stay independent for inspection rather than collapsing into an opaque weighted sum

**Stats:** 659 tests, 97% coverage, zero runtime dependencies, Python 3.11+ stdlib only, scales to 5M obligations in 74s.

```bash
pip install tidewatch
```

GitHub: https://github.com/ninjra/tidewatch

Paper (SSRN, in review): "Multi-Factor Obligation Pressure with Deferred Scalarization"
