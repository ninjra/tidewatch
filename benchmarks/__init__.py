# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tidewatch benchmarks — Monte Carlo and DES simulation harness.

Public API:
  compare_strategies — run MC comparison across all scheduling strategies
  compare_strategies_multi_seed — inter-seed sensitivity analysis
  run_ablation_study — 6-factor ablation study (§4.3)
  run_kf_sensitivity — FANOUT_TEMPORAL_K sensitivity sweep
  run_des_simulation — DES simulation via statistics_harness
  run_monte_carlo — single-strategy MC simulation
"""

from benchmarks.monte_carlo import (
    compare_strategies,
    compare_strategies_multi_seed,
    run_ablation_study,
    run_des_simulation,
    run_kf_sensitivity,
    run_monte_carlo,
)

__all__ = [
    "compare_strategies",
    "compare_strategies_multi_seed",
    "run_ablation_study",
    "run_des_simulation",
    "run_kf_sensitivity",
    "run_monte_carlo",
]
