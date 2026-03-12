"""Benchmark metrics for comparing urgency models.

Metrics:
  - zone_transition_timeliness
  - missed_deadline_rate
  - attention_allocation_efficiency (rank correlation)
  - false_alarm_rate
"""

from __future__ import annotations


def zone_transition_timeliness(
    first_alert_days: list[float],
    optimal_attention_days: list[float],
) -> float:
    """Mean gap between first alert and optimal attention time.

    Inputs:
      first_alert_days: days before deadline when system first alerted
      optimal_attention_days: ground-truth optimal attention time

    Outputs:
      mean absolute gap (lower is better)
    """
    if not first_alert_days:
        return float("inf")
    gaps = [abs(a - o) for a, o in zip(first_alert_days, optimal_attention_days)]
    return sum(gaps) / len(gaps)


def missed_deadline_rate(
    alerted_48h_prior: list[bool],
) -> float:
    """Fraction of obligations not alerted at least 48h before deadline.

    Inputs:
      alerted_48h_prior: bool per obligation, True if alerted >= 48h before deadline

    Outputs:
      float 0.0-1.0 (lower is better)
    """
    if not alerted_48h_prior:
        return 0.0
    missed = sum(1 for a in alerted_48h_prior if not a)
    return missed / len(alerted_48h_prior)


def attention_allocation_efficiency(
    predicted_ranks: list[int],
    actual_ranks: list[int],
) -> float:
    """Spearman rank correlation between predicted and actual urgency ordering.

    Inputs:
      predicted_ranks: urgency ranking from the model
      actual_ranks: ground-truth urgency ranking

    Outputs:
      float -1.0 to 1.0 (higher is better)
    """
    n = len(predicted_ranks)
    if n < 2:
        return 1.0
    d_squared = sum((p - a) ** 2 for p, a in zip(predicted_ranks, actual_ranks))
    return 1.0 - (6.0 * d_squared) / (n * (n ** 2 - 1))


def false_alarm_rate(
    alerted_high: list[bool],
    completed_early: list[bool],
) -> float:
    """Fraction of high-alert obligations that were completed well before deadline.

    Inputs:
      alerted_high: True if obligation entered orange/red zone
      completed_early: True if completed > 7 days before deadline

    Outputs:
      float 0.0-1.0 (lower is better)
    """
    high_alerts = sum(1 for a in alerted_high if a)
    if high_alerts == 0:
        return 0.0
    false_alarms = sum(
        1 for a, c in zip(alerted_high, completed_early) if a and c
    )
    return false_alarms / high_alerts
