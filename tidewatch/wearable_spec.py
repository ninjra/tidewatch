# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Wearable API integration specification for CognitiveContext.

Defines the data contract for mapping wearable sensor streams to
CognitiveContext fields. This is a SPECIFICATION — the actual adapter
implementation lives in a separate repo. Tidewatch consumes the
normalized output.

Supported signal sources:
  - Apple HealthKit (via Health app export or HealthConnect)
  - Whoop API (recovery, strain, sleep)
  - Oura Ring API (readiness, sleep stages, HRV)
  - Generic HRV monitor (Polar, Garmin via BLE)

Each source maps to CognitiveContext fields through normalization
functions defined here. The adapter repo calls these functions to
produce a CognitiveContext ready for bandwidth_adjusted_sort().
"""
from __future__ import annotations

from dataclasses import dataclass

from tidewatch.constants import (
    HRV_BASELINE_DEFAULT_MS,
    HRV_BASELINE_RATIO,
    HRV_SCALE_FACTOR,
    PAIN_NRS_SCALE_MAX,
    SLEEP_HOURS_DEPRIVED,
    SLEEP_HOURS_WELL_RESTED,
    SLEEP_SCORE_SCALE_MAX,
    WHOOP_STRAIN_MAX,
    clamp_unit,
    complement_hours,
)

# ── Signal normalization functions ───────────────────────────────────────────

# These are the data contracts. Adapter implementations call these
# to normalize raw sensor values into CognitiveContext [0, 1] fields.


def normalize_hrv(rmssd_ms: float, baseline_ms: float = HRV_BASELINE_DEFAULT_MS) -> float:
    """Normalize HRV (RMSSD in milliseconds) to hrv_trend [0, 1].

    Args:
        rmssd_ms: Root mean square of successive differences (ms).
            Typical range: 20-100ms for adults.
        baseline_ms: Individual's baseline RMSSD. Default 50ms (population median).

    Returns:
        0.0 = severely depressed HRV (high stress / poor recovery)
        0.5 = at personal baseline
        1.0 = elevated HRV (excellent recovery)

    Normalization: ratio to baseline, clamped to [0, 1].
    """
    if baseline_ms <= 0:
        return HRV_BASELINE_RATIO
    ratio = rmssd_ms / baseline_ms
    return clamp_unit(ratio / HRV_SCALE_FACTOR)  # baseline → 0.5, 2x baseline → 1.0


def normalize_sleep_score(score: float, scale_max: float = SLEEP_SCORE_SCALE_MAX) -> float:
    """Normalize sleep quality score to sleep_quality [0, 1].

    Args:
        score: Sleep quality score from wearable.
            Whoop: 0-100 (recovery score).
            Oura: 0-100 (sleep score).
            Apple: sleep duration hours (use normalize_sleep_hours instead).
        scale_max: Maximum value of the source scale.

    Returns:
        0.0 = very poor sleep
        1.0 = excellent sleep
    """
    return clamp_unit(score / scale_max)


def normalize_sleep_hours(hours: float) -> float:
    """Normalize sleep duration to sleep_quality [0, 1].

    Args:
        hours: Total sleep duration.

    Returns:
        0.0 = <4 hours (severely sleep deprived)
        0.5 = 6 hours (marginal)
        1.0 = >=8 hours (well rested)

    Linear interpolation between 4h (0.0) and 8h (1.0).
    """
    if hours >= SLEEP_HOURS_WELL_RESTED:
        return 1.0
    if hours <= SLEEP_HOURS_DEPRIVED:
        return 0.0
    span = SLEEP_HOURS_WELL_RESTED - SLEEP_HOURS_DEPRIVED
    return (hours - SLEEP_HOURS_DEPRIVED) / span


def normalize_pain(pain_scale: float, scale_max: float = PAIN_NRS_SCALE_MAX) -> float:
    """Normalize pain level to pain_level [0, 1].

    Args:
        pain_scale: Self-reported or derived pain score.
            Standard NRS: 0 (no pain) to 10 (worst imaginable).
        scale_max: Maximum value of the source scale.

    Returns:
        0.0 = severe pain (high pain_scale)
        1.0 = no pain (low pain_scale)

    INVERTED: CognitiveContext.pain_level uses 1.0 = optimal (no pain).
    """
    return clamp_unit(1.0 - (pain_scale / scale_max))


def normalize_strain(strain: float, max_strain: float = WHOOP_STRAIN_MAX) -> float:
    """Normalize activity strain to session_load [0, 1].

    Args:
        strain: Accumulated strain score.
            Whoop: 0-21 (daily strain).
            Generic: activity intensity metric.
        max_strain: Maximum value of the source scale.

    Returns:
        0.0 = idle (no strain)
        1.0 = saturated (maximum strain)
    """
    return clamp_unit(strain / max_strain)


# ── Adapter data contract ────────────────────────────────────────────────────


@dataclass
class WearableReading:
    """Raw reading from a wearable device.

    Adapter implementations produce these; the bridge function below
    converts them to CognitiveContext.
    """
    source: str  # "whoop" | "oura" | "apple_health" | "polar" | "manual"
    hrv_rmssd_ms: float | None = None
    hrv_baseline_ms: float | None = None
    sleep_score: float | None = None     # 0-100 composite
    sleep_hours: float | None = None     # total sleep duration
    pain_nrs: float | None = None        # 0-10 NRS
    strain: float | None = None          # activity strain
    timestamp_utc: str | None = None     # ISO 8601


def reading_to_context(reading: WearableReading) -> dict[str, float | None]:
    """Convert a WearableReading to CognitiveContext field values.

    Returns a dict of field_name → normalized value that can be unpacked
    into CognitiveContext(**result).

    Only fields with non-None source values are included.
    This is the formal data contract between the adapter repo and tidewatch.
    """
    fields: dict[str, float | None] = {}

    if reading.hrv_rmssd_ms is not None:
        baseline = reading.hrv_baseline_ms or HRV_BASELINE_DEFAULT_MS
        fields["hrv_trend"] = normalize_hrv(reading.hrv_rmssd_ms, baseline)

    if reading.sleep_score is not None:
        fields["sleep_quality"] = normalize_sleep_score(reading.sleep_score)
    elif reading.sleep_hours is not None:
        fields["sleep_quality"] = normalize_sleep_hours(reading.sleep_hours)

    if reading.pain_nrs is not None:
        fields["pain_level"] = normalize_pain(reading.pain_nrs)

    if reading.strain is not None:
        fields["session_load"] = normalize_strain(reading.strain)

    if reading.sleep_hours is not None:
        fields["hours_since_sleep"] = complement_hours(reading.sleep_hours)

    return fields


# ── Polling contract ─────────────────────────────────────────────────────────

# Recommended polling intervals by source:
#   Whoop API:       every 15 minutes (rate-limited)
#   Oura API:        every 30 minutes (daily summaries, intraday optional)
#   Apple HealthKit: on-change (HealthKit observer queries)
#   Manual entry:    on user prompt
#
# Failure modes:
#   - Source unavailable: CognitiveContext uses BANDWIDTH_NO_DATA (0.8)
#   - Stale data (>2h): Log warning, use last known value with decay
#   - Invalid reading: Skip field, let CognitiveContext average remaining signals
#   - All sources down: Full graceful degradation — pure pressure ordering
