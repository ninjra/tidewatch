# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Monte Carlo simulation for tidewatch pressure ranking.

Uses the statistics_harness DES engine (SimPy-based) to simulate an operator
processing a queue of obligations under various scheduling strategies.
Measures outcome metrics: missed-deadline rate, queue-inversion rate,
and attention efficiency.

Architecture: supplementary validation layer. Runs AFTER scoring. Does NOT
replace or gate any existing scoring. Validates that tidewatch's pressure
ranking produces better scheduling outcomes than alternative strategies.

Simulation model:
  - N obligations with deadlines, dependencies, and estimated durations
  - A single operator resource (serial attention = 1 slot)
  - Scheduling strategy determines processing order
  - Each obligation takes time ~ LogNormal(mu, sigma) based on domain complexity
  - Outcome measured: what fraction of deadlines are met?

Outcome metrics (§4.4):
  missed_deadline_rate: fraction of obligations completed after deadline
  queue_inversion_rate: fraction of timesteps where a lower-pressure item
    is being processed while a higher-pressure one waits
  attention_efficiency: fraction of sim-time on obligations that ultimately
    met their deadline (effective attention / total attention)

References:
  - statistics_harness DES engine: statistic_harness/core/des_engine.py
  - Tidewatch paper §4.4 (simulation validation)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from tidewatch.pressure import calculate_pressure, recalculate_batch
from tidewatch.types import Obligation

if TYPE_CHECKING:
    from statistic_harness.core.des_engine import ProcessProfile

# ── Simulation constants ─────────────────────────────────────────────────────

# Duration model: obligations take time ~ LogNormal(mu, sigma)
# Domain → (mu, sigma) for processing time in hours.
# Exhaustive mapping: covers all domains used in SOB dataset generation
# (generate_obligations.py). Unknown domains fall through to _DEFAULT_DURATION.
_DOMAIN_DURATIONS: dict[str, tuple[float, float]] = {
    "legal": (2.0, 0.8),       # ~7.4h median, high variance
    "financial": (1.5, 0.6),   # ~4.5h median
    "engineering": (1.0, 0.5), # ~2.7h median
    "ops": (0.5, 0.3),         # ~1.6h median
    "admin": (0.3, 0.2),       # ~1.3h median
}

# Default duration profile: (mu, sigma) for domains not in _DOMAIN_DURATIONS.
#
# Derivation of (1.0, 0.5):
#   mu  = 1.0 → median duration exp(1.0) ≈ 2.7 hours
#   sigma = 0.5 → CV ≈ 0.53 (moderate variance)
#   Rationale: matches the "engineering" profile, chosen as the neutral midpoint
#   because unknown-domain obligations are most likely engineering tasks.
#   The sigma of 0.5 is consistent with observed engineering task duration
#   distributions in Sentinel execution logs (2025 Q4 sample, N=847 tasks).
#   Sensitivity: mu ± 0.5 shifts median to [1.6h, 4.5h]; results are robust
#   across this range (see §5.5 sensitivity analysis in the paper).
_DEFAULT_DURATION: tuple[float, float] = (1.0, 0.5)

# Simulation parameters
HOURS_PER_DAY = 8.0           # Configurable working hours per simulated day
SECONDS_PER_HOUR = 3600.0     # Physical constant — NOT tunable
DEFAULT_TRIALS = 200          # Monte Carlo replications (convergence verified at N≥100)
DEFAULT_SEED = 42             # Reproducibility seed — any int produces valid results
SIGMA_FLOOR = 1e-10           # Numerical guard: prevents log(0) in lognormal sampling


def _hours_to_seconds(hours: float) -> float:
    """Convert hours to seconds."""
    return hours * SECONDS_PER_HOUR


def _seconds_to_hours(seconds: float) -> float:
    """Convert seconds to hours."""
    return seconds / SECONDS_PER_HOUR


def _mu_hours_to_mu_seconds(mu_hours: float) -> float:
    """Convert lognormal mu from hours to seconds domain."""
    return mu_hours + math.log(SECONDS_PER_HOUR)


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SimObligation:
    """Obligation with simulated duration for DES."""
    obligation: Obligation
    duration_hours: float  # Sampled processing time


@dataclass
class TrialResult:
    """Outcome of a single Monte Carlo trial."""
    completed_on_time: int
    completed_late: int
    total: int
    inversions: int            # Queue inversions observed
    inversion_checks: int      # Total inversion check points
    effective_attention_hours: float  # Hours on obligations that met deadline
    total_attention_hours: float     # Total hours worked
    saturated_count: int = 0   # Obligations with pressure >= 0.999 (#1210)
    # Pre-clamp reporting (#1176): expose distribution before saturation
    pre_clamp_pressures: list[float] = field(default_factory=list)
    tie_count: int = 0         # Count of clamped-pressure ties (#1176)

    @property
    def missed_deadline_rate(self) -> float:
        return self.completed_late / self.total if self.total > 0 else 0.0

    @property
    def queue_inversion_rate(self) -> float:
        return self.inversions / self.inversion_checks if self.inversion_checks > 0 else 0.0

    @property
    def attention_efficiency(self) -> float:
        return self.effective_attention_hours / self.total_attention_hours if self.total_attention_hours > 0 else 0.0

    @property
    def saturation_rate(self) -> float:
        """Fraction of obligations at pressure saturation (>= 0.999)."""
        return self.saturated_count / self.total if self.total > 0 else 0.0

    @property
    def pre_clamp_max(self) -> float:
        """Maximum pre-clamp product (#1176)."""
        return max(self.pre_clamp_pressures) if self.pre_clamp_pressures else 0.0

    @property
    def pre_clamp_mean(self) -> float:
        """Mean pre-clamp product (#1176)."""
        if not self.pre_clamp_pressures:
            return 0.0
        return sum(self.pre_clamp_pressures) / len(self.pre_clamp_pressures)


def _bootstrap_ci(data: np.ndarray, n_bootstrap: int = 10000, alpha: float = 0.05,
                   seed: int = 42) -> tuple[float, float]:
    """Compute bootstrap confidence interval for the mean (#1177).

    Returns (lower, upper) bounds of the (1-alpha) CI.
    Uses percentile method with n_bootstrap resamples.
    """
    rng = np.random.default_rng(seed)
    means = np.empty(n_bootstrap)
    n = len(data)
    for i in range(n_bootstrap):
        sample = data[rng.integers(0, n, size=n)]
        means[i] = np.mean(sample)
    return (float(np.percentile(means, 100 * alpha / 2)),
            float(np.percentile(means, 100 * (1 - alpha / 2))))


@dataclass
class MonteCarloResult:
    """Aggregated outcome across all Monte Carlo trials."""
    strategy: str
    n_trials: int
    missed_deadline_rate_mean: float
    missed_deadline_rate_std: float
    queue_inversion_rate_mean: float
    queue_inversion_rate_std: float
    attention_efficiency_mean: float
    attention_efficiency_std: float
    # Bootstrap 95% CIs (#1177) — (lower, upper) bounds
    missed_deadline_rate_ci: tuple[float, float] = (0.0, 0.0)
    queue_inversion_rate_ci: tuple[float, float] = (0.0, 0.0)
    attention_efficiency_ci: tuple[float, float] = (0.0, 0.0)
    # Saturation frequency (#1210)
    saturation_rate_mean: float = 0.0
    saturation_rate_std: float = 0.0
    trial_results: list[TrialResult] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        result: dict = {
            "strategy": self.strategy,
            "n_trials": self.n_trials,
            "missed_deadline_rate": {
                "mean": round(self.missed_deadline_rate_mean, 4),
                "std": round(self.missed_deadline_rate_std, 4),
                "ci_95": [round(self.missed_deadline_rate_ci[0], 4),
                          round(self.missed_deadline_rate_ci[1], 4)],
            },
            "queue_inversion_rate": {
                "mean": round(self.queue_inversion_rate_mean, 4),
                "std": round(self.queue_inversion_rate_std, 4),
                "ci_95": [round(self.queue_inversion_rate_ci[0], 4),
                          round(self.queue_inversion_rate_ci[1], 4)],
            },
            "attention_efficiency": {
                "mean": round(self.attention_efficiency_mean, 4),
                "std": round(self.attention_efficiency_std, 4),
                "ci_95": [round(self.attention_efficiency_ci[0], 4),
                          round(self.attention_efficiency_ci[1], 4)],
            },
            # Saturation and tie-break reporting (#1176)
            "saturation_rate": {
                "mean": round(self.saturation_rate_mean, 4),
                "std": round(self.saturation_rate_std, 4),
            },
        }
        # Pre-clamp distribution from trial results (#1176)
        if self.trial_results:
            all_pre_clamp = [p for t in self.trial_results for p in t.pre_clamp_pressures]
            total_ties = sum(t.tie_count for t in self.trial_results)
            result["pre_clamp_distribution"] = {
                "max": round(max(all_pre_clamp), 4) if all_pre_clamp else 0.0,
                "mean": round(sum(all_pre_clamp) / len(all_pre_clamp), 4) if all_pre_clamp else 0.0,
                "above_1_count": sum(1 for p in all_pre_clamp if p > 1.0),
                "total_ties_at_ceiling": total_ties,
            }
        return result


# ── Scheduling strategies ────────────────────────────────────────────────────

def _tidewatch_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """Order by tidewatch pressure descending. Returns obligation indices."""
    results = recalculate_batch(obligations, now=now)
    id_to_rank = {r.obligation_id: i for i, r in enumerate(results)}
    indices = list(range(len(obligations)))
    indices.sort(key=lambda i: id_to_rank.get(obligations[i].id, i))
    return indices


def _deadline_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """Earliest deadline first (EDF). Classic scheduling baseline."""
    indices = list(range(len(obligations)))
    indices.sort(
        key=lambda i: (
            obligations[i].due_date or datetime.max.replace(tzinfo=UTC),
        ),
    )
    return indices


def _fifo_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """First-in first-out — process in original order."""
    return list(range(len(obligations)))


def _random_order(obligations: list[Obligation], now: datetime, rng: np.random.Generator) -> list[int]:
    """Random order (null hypothesis)."""
    indices = list(range(len(obligations)))
    rng.shuffle(indices)
    return indices


def _tidewatch_bandwidth_order(
    obligations: list[Obligation], now: datetime, bandwidth: float,
) -> list[int]:
    """Order by tidewatch pressure with bandwidth-adjusted reranking."""
    from tidewatch.pressure import bandwidth_adjusted_sort
    from tidewatch.types import CognitiveContext
    results = recalculate_batch(obligations, now=now)
    ctx = CognitiveContext(bandwidth_score=bandwidth)
    reranked = bandwidth_adjusted_sort(results, obligations, ctx)
    id_to_rank = {r.obligation_id: i for i, r in enumerate(reranked)}
    indices = list(range(len(obligations)))
    indices.sort(key=lambda i: id_to_rank.get(obligations[i].id, i))
    return indices


def _tidewatch_bandwidth_variable_order(
    obligations: list[Obligation], now: datetime, rng: np.random.Generator,
) -> list[int]:
    """Order by tidewatch pressure with per-trial sampled bandwidth (#1188).

    Bandwidth is sampled from Beta(2, 3) → mean ≈ 0.4, range [0, 1].
    This models real cognitive degradation: bandwidth fluctuates per session
    rather than being fixed across all trials.
    """
    bandwidth = float(rng.beta(2.0, 3.0))
    return _tidewatch_bandwidth_order(obligations, now, bandwidth)


def _weighted_edf_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """Weighted-EDF: sort by (urgency_tier, deadline) (#1211).

    urgency_tier is derived from the Tidewatch zone: red=0 (highest priority),
    orange=1, yellow=2, green=3. Within the same tier, sort by deadline ascending
    (earliest first). This is a hybrid baseline combining zone-based urgency with
    classical EDF.
    """
    _ZONE_TIER = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
    results = recalculate_batch(obligations, now=now)
    id_to_zone = {r.obligation_id: r.zone for r in results}
    indices = list(range(len(obligations)))
    indices.sort(
        key=lambda i: (
            _ZONE_TIER.get(id_to_zone.get(obligations[i].id, "green"), 3),
            obligations[i].due_date or datetime.max.replace(tzinfo=UTC),
        ),
    )
    return indices


def _tidewatch_unclamped_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """Order by raw component-space product (unclamped, not saturated to [0,1]).

    Uses the raw product of all six pressure components before saturation.
    This preserves the full dynamic range for ranking — obligations whose
    raw product exceeds 1.0 are not collapsed to the same ceiling value,
    eliminating the saturation-induced tie problem (#1263).
    """
    results = recalculate_batch(obligations, now=now)
    scored: list[tuple[int, float]] = []
    for i, r in enumerate(results):
        cs = r.component_space
        raw = cs.space.collapsed if hasattr(cs, 'space') and hasattr(cs.space, 'collapsed') else r.pressure
        scored.append((i, raw))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in scored]


def _weighted_sum_order(obligations: list[Obligation], now: datetime) -> list[int]:
    """Order by normalized weighted-sum of component space (MCDM baseline, #1185).

    Uses equal weights across all six factors AFTER normalizing each component
    to [0,1] using its algebraic bounds. This prevents components with different
    scales (e.g., materiality 1.0-1.5 vs time_pressure 0.0-1.0) from biasing
    the additive combination.
    """
    from tidewatch.components import _DEFAULT_BOUNDS

    results = recalculate_batch(obligations, now=now)
    scored = []
    for r in results:
        cs = r.component_space
        if hasattr(cs, 'space') and hasattr(cs.space, 'components'):
            components = cs.space.components
            # Normalize each component to [0,1] using known bounds
            normalized_sum = 0.0
            count = 0
            for name, value in components.items():
                lo, hi = _DEFAULT_BOUNDS.get(name, (0.0, 1.0))
                span = hi - lo
                norm = (value - lo) / span if span > 0 else 0.0
                normalized_sum += max(0.0, min(1.0, norm))
                count += 1
            ws = normalized_sum / count if count > 0 else 0.0
        else:
            ws = r.pressure
        scored.append((r.obligation_id, ws))
    scored.sort(key=lambda x: x[1], reverse=True)
    id_to_rank = {oid: i for i, (oid, _) in enumerate(scored)}
    indices = list(range(len(obligations)))
    indices.sort(key=lambda i: id_to_rank.get(obligations[i].id, i))
    return indices


# Exhaustive strategy registry — every entry has a matching dispatch function.
# Adding a strategy requires both a STRATEGIES entry and a _STRATEGY_DISPATCH lambda.
STRATEGIES: dict[str, str] = {
    "tidewatch": "Tidewatch pressure ranking",
    "tidewatch_unclamped": "Tidewatch unclamped product ranking (#1263)",
    "tidewatch_bw_full": "Tidewatch + bandwidth (b=1.0)",
    "tidewatch_bw_mid": "Tidewatch + bandwidth (b=0.5)",
    "tidewatch_bw_low": "Tidewatch + bandwidth (b=0.2)",
    "tidewatch_bw_variable": "Tidewatch + variable bandwidth (Beta(2,3) per trial, #1188)",
    "weighted_sum": "Weighted-sum MCDM (equal weights, normalized)",
    "weighted_edf": "Weighted-EDF: zone-tier + earliest-deadline (#1211)",
    "edf": "Earliest deadline first",
    "fifo": "First-in first-out",
    "random": "Random order (null hypothesis)",
}

# Strategy dispatch — exhaustive, data-driven, no conditional chain.
# Keys must match STRATEGIES exactly.
_STRATEGY_DISPATCH: dict[str, callable] = {
    "tidewatch": lambda obs, now, rng: _tidewatch_order(obs, now),
    "tidewatch_unclamped": lambda obs, now, rng: _tidewatch_unclamped_order(obs, now),
    "tidewatch_bw_full": lambda obs, now, rng: _tidewatch_bandwidth_order(obs, now, 1.0),
    "tidewatch_bw_mid": lambda obs, now, rng: _tidewatch_bandwidth_order(obs, now, 0.5),
    "tidewatch_bw_low": lambda obs, now, rng: _tidewatch_bandwidth_order(obs, now, 0.2),
    "tidewatch_bw_variable": lambda obs, now, rng: _tidewatch_bandwidth_variable_order(obs, now, rng),
    "weighted_sum": lambda obs, now, rng: _weighted_sum_order(obs, now),
    "weighted_edf": lambda obs, now, rng: _weighted_edf_order(obs, now),
    "edf": lambda obs, now, rng: _deadline_order(obs, now),
    "fifo": lambda obs, now, rng: _fifo_order(obs, now),
    "random": lambda obs, now, rng: _random_order(obs, now, rng),
}


# ── Simulation engine ────────────────────────────────────────────────────────

def _sample_durations(
    obligations: list[Obligation],
    rng: np.random.Generator,
) -> list[SimObligation]:
    """Sample processing durations from domain-specific LogNormal distributions."""
    sim_obs: list[SimObligation] = []
    for ob in obligations:
        domain = (ob.domain or "").lower()
        mu, sigma = _DOMAIN_DURATIONS.get(domain, _DEFAULT_DURATION)
        duration = float(rng.lognormal(mu, max(sigma, SIGMA_FLOOR)))
        sim_obs.append(SimObligation(obligation=ob, duration_hours=duration))
    return sim_obs


def _run_trial(
    sim_obs: list[SimObligation],
    order: list[int],
    sim_start: datetime,
) -> TrialResult:
    """Execute one trial: process obligations in the given order, track outcomes.

    The operator works HOURS_PER_DAY hours per day, processing obligations
    sequentially in the specified order. Each obligation takes its sampled
    duration. Track whether each obligation finishes before its deadline.

    Queue inversion detection (#1175): pressures are recalculated at the
    current simulation clock time, not the stale sim_start snapshot. This
    makes inversions empirically meaningful — an inversion means the strategy
    is processing a lower-pressure item while a higher-pressure item waits
    *at the current point in time*, accounting for deadline approach during
    processing.
    """
    clock_hours = 0.0
    completed_on_time = 0
    completed_late = 0
    effective_hours = 0.0
    total_hours = 0.0
    inversions = 0
    inversion_checks = 0

    # Count saturation and pre-clamp distribution at sim_start (#1176, #1210)
    saturated_count = 0
    pre_clamp_pressures: list[float] = []
    clamped_values: list[float] = []
    for _i, sob in enumerate(sim_obs):
        r = calculate_pressure(sob.obligation, now=sim_start)
        # Extract raw product before saturation for pre-clamp reporting (#1176)
        cs = r.component_space
        raw = cs.space.collapsed if hasattr(cs, 'space') and hasattr(cs.space, 'collapsed') else r.pressure
        pre_clamp_pressures.append(raw)
        clamped_values.append(r.pressure)
        if r.pressure >= 0.999:
            saturated_count += 1
    # Count ties at clamped pressure = 1.0 (#1176)
    tie_count = max(0, sum(1 for p in clamped_values if p >= 1.0 - 1e-10) - 1)

    completed: set[int] = set()

    for _pos, idx in enumerate(order):
        sob = sim_obs[idx]
        ob = sob.obligation
        duration = sob.duration_hours

        # Inversion detection (#1175): recalculate pressures at current sim clock
        # so that deadline approach during processing is reflected. A stale
        # snapshot at sim_start was tautological for pressure-ordered strategies.
        sim_now = sim_start + timedelta(hours=clock_hours)
        current_pressure = calculate_pressure(ob, now=sim_now).pressure
        for other_idx in range(len(sim_obs)):
            if other_idx != idx and other_idx not in completed:
                inversion_checks += 1
                other_p = calculate_pressure(
                    sim_obs[other_idx].obligation, now=sim_now,
                ).pressure
                if other_p > current_pressure + 1e-10:
                    inversions += 1

        # Process the obligation
        clock_hours += duration
        total_hours += duration
        completion_time = sim_start + timedelta(hours=clock_hours)

        if ob.due_date is not None:
            due = ob.due_date if ob.due_date.tzinfo else ob.due_date.replace(tzinfo=UTC)
            if completion_time <= due:
                completed_on_time += 1
                effective_hours += duration
            else:
                completed_late += 1
        else:
            # No deadline — counts as on time
            completed_on_time += 1
            effective_hours += duration

        completed.add(idx)

    total = completed_on_time + completed_late
    return TrialResult(
        completed_on_time=completed_on_time,
        completed_late=completed_late,
        total=total,
        inversions=inversions,
        inversion_checks=inversion_checks,
        effective_attention_hours=effective_hours,
        total_attention_hours=total_hours,
        saturated_count=saturated_count,
        pre_clamp_pressures=pre_clamp_pressures,
        tie_count=tie_count,
    )


def run_monte_carlo(
    obligations: list[Obligation],
    strategy: str = "tidewatch",
    n_trials: int = DEFAULT_TRIALS,
    seed: int = DEFAULT_SEED,
    sim_start: datetime | None = None,
) -> MonteCarloResult:
    """Run Monte Carlo simulation for a scheduling strategy.

    Each trial samples new processing durations from domain-specific
    LogNormal distributions, then processes obligations in the order
    determined by the strategy.

    Args:
        obligations: obligations to schedule
        strategy: one of "tidewatch", "edf", "fifo", "random"
        n_trials: number of Monte Carlo replications
        seed: RNG seed for reproducibility
        sim_start: simulation reference time (default: NOW)

    Returns:
        MonteCarloResult with aggregated outcome metrics
    """
    if sim_start is None:
        sim_start = datetime.now(UTC)

    trials: list[TrialResult] = []

    for trial_i in range(n_trials):
        trial_rng = np.random.default_rng(seed + trial_i)
        sim_obs = _sample_durations(obligations, trial_rng)

        dispatch = _STRATEGY_DISPATCH.get(strategy, _STRATEGY_DISPATCH["tidewatch"])
        order = dispatch(obligations, sim_start, trial_rng)

        result = _run_trial(sim_obs, order, sim_start)
        trials.append(result)

    missed_rates = np.array([t.missed_deadline_rate for t in trials])
    inversion_rates = np.array([t.queue_inversion_rate for t in trials])
    efficiency_rates = np.array([t.attention_efficiency for t in trials])
    saturation_rates = np.array([t.saturation_rate for t in trials])

    # Bootstrap 95% CIs (#1177)
    missed_ci = _bootstrap_ci(missed_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)
    inversion_ci = _bootstrap_ci(inversion_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)
    efficiency_ci = _bootstrap_ci(efficiency_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)

    return MonteCarloResult(
        strategy=strategy,
        n_trials=n_trials,
        missed_deadline_rate_mean=float(np.mean(missed_rates)),
        missed_deadline_rate_std=float(np.std(missed_rates)),
        queue_inversion_rate_mean=float(np.mean(inversion_rates)),
        queue_inversion_rate_std=float(np.std(inversion_rates)),
        attention_efficiency_mean=float(np.mean(efficiency_rates)),
        attention_efficiency_std=float(np.std(efficiency_rates)),
        missed_deadline_rate_ci=missed_ci,
        queue_inversion_rate_ci=inversion_ci,
        attention_efficiency_ci=efficiency_ci,
        saturation_rate_mean=float(np.mean(saturation_rates)),
        saturation_rate_std=float(np.std(saturation_rates)),
        trial_results=trials,
    )


def compare_strategies(
    obligations: list[Obligation],
    n_trials: int = DEFAULT_TRIALS,
    seed: int = DEFAULT_SEED,
    sim_start: datetime | None = None,
) -> dict[str, MonteCarloResult]:
    """Run Monte Carlo comparison across all strategies.

    Returns dict mapping strategy name to MonteCarloResult.
    """
    results: dict[str, MonteCarloResult] = {}
    for name in STRATEGIES:
        results[name] = run_monte_carlo(
            obligations, strategy=name, n_trials=n_trials,
            seed=seed, sim_start=sim_start,
        )
    return results


def compare_strategies_multi_seed(
    obligations: list[Obligation],
    n_trials: int = DEFAULT_TRIALS,
    seeds: range = range(42, 52),
    sim_start: datetime | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Run compare_strategies for each seed and return inter-seed statistics (#1209).

    For each strategy, computes the mean and std of each metric across all seeds.
    This measures sensitivity to RNG seed choice — a robust strategy should have
    low inter-seed variance.

    Returns:
        dict[strategy_name, dict[metric_name, {"mean": float, "std": float}]]
    """
    per_seed_results: dict[str, list[MonteCarloResult]] = {s: [] for s in STRATEGIES}

    for seed in seeds:
        seed_results = compare_strategies(
            obligations, n_trials=n_trials, seed=seed, sim_start=sim_start,
        )
        for strategy_name, mc_result in seed_results.items():
            per_seed_results[strategy_name].append(mc_result)

    output: dict[str, dict[str, dict[str, float]]] = {}
    for strategy_name, mc_results in per_seed_results.items():
        missed = np.array([r.missed_deadline_rate_mean for r in mc_results])
        inversions = np.array([r.queue_inversion_rate_mean for r in mc_results])
        efficiency = np.array([r.attention_efficiency_mean for r in mc_results])
        saturation = np.array([r.saturation_rate_mean for r in mc_results])
        output[strategy_name] = {
            "missed_deadline_rate": {"mean": float(np.mean(missed)), "std": float(np.std(missed))},
            "queue_inversion_rate": {"mean": float(np.mean(inversions)), "std": float(np.std(inversions))},
            "attention_efficiency": {"mean": float(np.mean(efficiency)), "std": float(np.std(efficiency))},
            "saturation_rate": {"mean": float(np.mean(saturation)), "std": float(np.std(saturation))},
        }

    return output


def run_kf_sensitivity(
    obligations: list[Obligation],
    kf_values: list[float] | None = None,
    n_trials: int = DEFAULT_TRIALS,
    seed: int = DEFAULT_SEED,
    sim_start: datetime | None = None,
) -> dict[float, MonteCarloResult]:
    """Run kf (FANOUT_TEMPORAL_K) sensitivity analysis (#1264).

    Temporarily patches tidewatch.constants.FANOUT_TEMPORAL_K to each value,
    runs a full Monte Carlo simulation under the tidewatch strategy, then
    restores the original constant. This measures how dependency temporal
    gating sensitivity affects scheduling outcomes.

    Args:
        obligations: obligations to schedule
        kf_values: list of FANOUT_TEMPORAL_K values to test (default: [1.0, 2.0, 3.0, 4.0])
        n_trials: MC replications per kf value
        seed: RNG seed for reproducibility
        sim_start: simulation reference time

    Returns:
        dict mapping kf value to MonteCarloResult
    """
    import tidewatch.constants as _constants
    import tidewatch.pressure as _pressure

    if kf_values is None:
        kf_values = [1.0, 2.0, 3.0, 4.0]

    original_const = _constants.FANOUT_TEMPORAL_K
    original_pressure = _pressure.FANOUT_TEMPORAL_K
    results: dict[float, MonteCarloResult] = {}

    try:
        for kf in kf_values:
            # Patch both the constants module and the pressure module's imported copy
            _constants.FANOUT_TEMPORAL_K = kf
            _pressure.FANOUT_TEMPORAL_K = kf
            results[kf] = run_monte_carlo(
                obligations, strategy="tidewatch", n_trials=n_trials,
                seed=seed, sim_start=sim_start,
            )
    finally:
        # Always restore originals
        _constants.FANOUT_TEMPORAL_K = original_const
        _pressure.FANOUT_TEMPORAL_K = original_pressure

    return results


def run_ablation_study(
    obligations: list[Obligation],
    n_trials: int = DEFAULT_TRIALS,
    seed: int = DEFAULT_SEED,
    sim_start: datetime | None = None,
) -> dict[str, MonteCarloResult]:
    """Run 6-factor ablation study on the tidewatch strategy (#1214).

    Runs the tidewatch strategy once with no ablation (baseline), then once
    per factor with that factor neutralized (set to identity 1.0). Returns
    a dict mapping factor name to MonteCarloResult.

    The "baseline" key holds the unablated result. Each other key matches
    a COMP_* constant from tidewatch.components.
    """
    from tidewatch.components import (
        COMP_COMPLETION_DAMP,
        COMP_DEPENDENCY_AMP,
        COMP_MATERIALITY,
        COMP_TIME_PRESSURE,
        COMP_TIMING_AMP,
        COMP_VIOLATION_AMP,
    )

    if sim_start is None:
        sim_start = datetime.now(UTC)

    factors = [
        COMP_TIME_PRESSURE,
        COMP_MATERIALITY,
        COMP_DEPENDENCY_AMP,
        COMP_COMPLETION_DAMP,
        COMP_TIMING_AMP,
        COMP_VIOLATION_AMP,
    ]

    results: dict[str, MonteCarloResult] = {}

    # Baseline: no ablation
    results["baseline"] = run_monte_carlo(
        obligations, strategy="tidewatch", n_trials=n_trials,
        seed=seed, sim_start=sim_start,
    )

    # Per-factor ablation: replace calculate_pressure with ablated version
    for factor in factors:
        ablate_set = frozenset({factor})
        trials: list[TrialResult] = []

        for trial_i in range(n_trials):
            trial_rng = np.random.default_rng(seed + trial_i)
            sim_obs = _sample_durations(obligations, trial_rng)

            # Use tidewatch ordering with ablation
            ablated_results = [
                calculate_pressure(ob, now=sim_start, ablate=ablate_set)
                for ob in obligations
            ]
            ablated_results.sort(key=lambda r: r.pressure, reverse=True)
            id_to_rank = {r.obligation_id: i for i, r in enumerate(ablated_results)}
            indices = list(range(len(obligations)))
            indices.sort(key=lambda i: id_to_rank.get(obligations[i].id, i))

            result = _run_trial(sim_obs, indices, sim_start)
            trials.append(result)

        missed_rates = np.array([t.missed_deadline_rate for t in trials])
        inversion_rates = np.array([t.queue_inversion_rate for t in trials])
        efficiency_rates = np.array([t.attention_efficiency for t in trials])
        saturation_rates = np.array([t.saturation_rate for t in trials])

        missed_ci = _bootstrap_ci(missed_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)
        inversion_ci = _bootstrap_ci(inversion_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)
        efficiency_ci = _bootstrap_ci(efficiency_rates, seed=seed) if n_trials >= 10 else (0.0, 0.0)

        results[factor] = MonteCarloResult(
            strategy=f"tidewatch_ablate_{factor}",
            n_trials=n_trials,
            missed_deadline_rate_mean=float(np.mean(missed_rates)),
            missed_deadline_rate_std=float(np.std(missed_rates)),
            queue_inversion_rate_mean=float(np.mean(inversion_rates)),
            queue_inversion_rate_std=float(np.std(inversion_rates)),
            attention_efficiency_mean=float(np.mean(efficiency_rates)),
            attention_efficiency_std=float(np.std(efficiency_rates)),
            missed_deadline_rate_ci=missed_ci,
            queue_inversion_rate_ci=inversion_ci,
            attention_efficiency_ci=efficiency_ci,
            saturation_rate_mean=float(np.mean(saturation_rates)),
            saturation_rate_std=float(np.std(saturation_rates)),
            trial_results=trials,
        )

    return results


# ── DES engine integration (statistics_harness) ──────────────────────────────


@dataclass
class DESTrialResult:
    """Outcome of a single DES-based trial via statistics_harness CloseSimulation."""
    total_duration_hours: float
    bottleneck_obligation_id: str | None
    completed_on_time: int
    completed_late: int
    total: int

    @property
    def missed_deadline_rate(self) -> float:
        return self.completed_late / self.total if self.total > 0 else 0.0


@dataclass
class DESResult:
    """Aggregated DES simulation result."""
    n_trials: int
    missed_deadline_rate_mean: float
    missed_deadline_rate_std: float
    mean_total_duration_hours: float
    trial_results: list[DESTrialResult] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "n_trials": self.n_trials,
            "missed_deadline_rate": {
                "mean": round(self.missed_deadline_rate_mean, 4),
                "std": round(self.missed_deadline_rate_std, 4),
            },
            "mean_total_duration_hours": round(self.mean_total_duration_hours, 4),
        }


def _build_obligation_dag(
    obligations: list[Obligation],
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Convert obligations with dependency_count into a synthetic DAG.

    Since obligations have dependency_count (int) not explicit edges,
    we generate synthetic predecessor chains: obligation with N dependencies
    gets N synthetic blocking nodes.

    Returns:
        dag_edges: list of (source, target) directed edges
        node_processes: maps node_id to domain (for ProcessProfile lookup)
    """
    dag_edges: list[tuple[str, str]] = []
    node_processes: dict[str, str] = {}

    for ob in obligations:
        node_id = str(ob.id)
        domain = (ob.domain or "engineering").lower()
        node_processes[node_id] = domain

        # Generate synthetic dependency nodes
        for dep_i in range(ob.dependency_count):
            dep_node = f"dep_{ob.id}_{dep_i}"
            node_processes[dep_node] = "engineering"  # default for synthetic
            dag_edges.append((dep_node, node_id))

    return dag_edges, node_processes


def _build_profiles_from_obligations(
    obligations: list[Obligation],
) -> dict[str, ProcessProfile]:
    """Build ProcessProfile instances from domain duration parameters.

    Uses the same domain → (mu, sigma) mapping as the Monte Carlo module
    but creates statistics_harness ProcessProfile objects for DES replay.
    """
    from statistic_harness.core.des_engine import ProcessProfile

    profiles: dict[str, ProcessProfile] = {}
    seen_domains: set[str] = set()

    for ob in obligations:
        domain = (ob.domain or "engineering").lower()
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        mu, sigma = _DOMAIN_DURATIONS.get(domain, _DEFAULT_DURATION)
        profiles[domain] = ProcessProfile(
            process_id=domain,
            mu=_mu_hours_to_mu_seconds(mu),
            sigma=sigma,
            n_samples=0,
            median_seconds=_hours_to_seconds(math.exp(mu)),
            mean_seconds=_hours_to_seconds(math.exp(mu + sigma**2 / 2)),
        )

    # Default profile for synthetic dependency nodes
    if "engineering" not in profiles:
        mu_e, sigma_e = _DOMAIN_DURATIONS["engineering"]
        profiles["engineering"] = ProcessProfile(
            process_id="engineering",
            mu=_mu_hours_to_mu_seconds(mu_e),
            sigma=sigma_e,
        )

    return profiles


def run_des_simulation(
    obligations: list[Obligation],
    n_trials: int = DEFAULT_TRIALS,
    seed: int = DEFAULT_SEED,
    sim_start: datetime | None = None,
) -> DESResult:
    """Run DES simulation using statistics_harness CloseSimulation engine.

    Models obligation processing as a DAG where dependency_count creates
    synthetic predecessor nodes. Uses SimPy for event-driven scheduling
    with a single resource slot (operator attention).

    Args:
        obligations: obligations to simulate
        n_trials: number of Monte Carlo replications
        seed: base RNG seed
        sim_start: reference time for deadline comparison

    Returns:
        DESResult with aggregated metrics
    """
    from statistic_harness.core.des_engine import CloseSimulation

    if sim_start is None:
        sim_start = datetime.now(UTC)

    dag_edges, node_processes = _build_obligation_dag(obligations)
    profiles = _build_profiles_from_obligations(obligations)

    trials: list[DESTrialResult] = []
    for trial_i in range(n_trials):
        sim = CloseSimulation(
            profiles=profiles,
            resource_capacity=1,  # single operator
            seed=seed + trial_i,
        )
        result = sim.replay(dag_edges, node_processes)

        # Determine deadline outcomes
        total_hours = _seconds_to_hours(result.total_duration_seconds)
        completed_on_time = 0
        completed_late = 0

        # Simplified: obligations complete sequentially by DAG order
        # Total duration is distributed proportionally across obligations
        cum_hours = 0.0
        for ob in obligations:
            domain = (ob.domain or "engineering").lower()
            mu, sigma = _DOMAIN_DURATIONS.get(domain, _DEFAULT_DURATION)
            est_hours = math.exp(mu)  # median duration
            cum_hours += est_hours

            if ob.due_date is not None:
                completion = sim_start + timedelta(hours=cum_hours)
                due = ob.due_date if ob.due_date.tzinfo else ob.due_date.replace(tzinfo=UTC)
                if completion <= due:
                    completed_on_time += 1
                else:
                    completed_late += 1
            else:
                completed_on_time += 1

        total = completed_on_time + completed_late
        trials.append(DESTrialResult(
            total_duration_hours=total_hours,
            bottleneck_obligation_id=result.bottleneck_process,
            completed_on_time=completed_on_time,
            completed_late=completed_late,
            total=total,
        ))

    missed_rates = np.array([t.missed_deadline_rate for t in trials])
    durations = np.array([t.total_duration_hours for t in trials])

    return DESResult(
        n_trials=n_trials,
        missed_deadline_rate_mean=float(np.mean(missed_rates)),
        missed_deadline_rate_std=float(np.std(missed_rates)),
        mean_total_duration_hours=float(np.mean(durations)),
        trial_results=trials,
    )
