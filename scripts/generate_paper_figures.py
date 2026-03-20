#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Generate all figures for the Tidewatch paper.

Figures:
  1. Pressure curve: P_time(t) for t in [-5, 60] days
  2. Factor decomposition: stacked area showing P_time, M, A, D contributions
  3. Bandwidth modulation: sort order shift at varying bandwidth levels
  4. Sensitivity analysis: pressure curves for k in {2, 3, 4, 5}
  5. Baseline comparison: Tidewatch vs EDF, CPM-priority, linear decay

Output: paper/figures/*.pdf
"""
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tidewatch.constants import (
    COMPLETION_DAMPENING,
    MATERIALITY_WEIGHTS,
    RATE_CONSTANT,
    ZONE_ORANGE,
    ZONE_RED,
    ZONE_YELLOW,
)

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "paper", "figures")
os.makedirs(OUTDIR, exist_ok=True)

# Style
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "figure.figsize": (5.5, 3.5),
    "figure.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
})

COLORS = {
    "green": "#2ecc71",
    "yellow": "#f1c40f",
    "orange": "#e67e22",
    "red": "#e74c3c",
    "blue": "#3498db",
    "purple": "#9b59b6",
    "gray": "#95a5a6",
}


def p_time(t, k=RATE_CONSTANT):
    """Time pressure component."""
    if t <= 0:
        return 1.0
    return 1.0 - math.exp(-k / t)


def pressure(t, deps=0, material=False, completion=0.0, k=RATE_CONSTANT):
    """Full pressure equation."""
    pt = p_time(t, k)
    m = MATERIALITY_WEIGHTS["material"] if material else MATERIALITY_WEIGHTS["routine"]
    a = 1.0 + deps * 0.1
    d = 1.0 - completion * COMPLETION_DAMPENING
    return min(1.0, pt * m * a * d)


def zone_color(p):
    if p < ZONE_YELLOW:
        return COLORS["green"]
    elif p < ZONE_ORANGE:
        return COLORS["yellow"]
    elif p < ZONE_RED:
        return COLORS["orange"]
    return COLORS["red"]


# =========================================================================
# Figure 1: Pressure Curve P_time(t)
# =========================================================================
def fig_pressure_curve():
    t = np.linspace(0.1, 60, 500)
    p = [p_time(ti) for ti in t]

    fig, ax = plt.subplots()

    # Zone backgrounds
    ax.axhspan(0, ZONE_YELLOW, color=COLORS["green"], alpha=0.08)
    ax.axhspan(ZONE_YELLOW, ZONE_ORANGE, color=COLORS["yellow"], alpha=0.08)
    ax.axhspan(ZONE_ORANGE, ZONE_RED, color=COLORS["orange"], alpha=0.08)
    ax.axhspan(ZONE_RED, 1.0, color=COLORS["red"], alpha=0.08)

    ax.plot(t, p, color=COLORS["blue"], linewidth=2)
    ax.set_xlabel("Days until deadline ($t$)")
    ax.set_ylabel("Time pressure $P_{\\mathrm{time}}(t)$")
    ax.set_xlim(0, 60)
    ax.set_ylim(0, 1.05)
    ax.invert_xaxis()

    # Zone labels
    ax.text(55, 0.15, "Green", fontsize=8, color=COLORS["green"], fontweight="bold")
    ax.text(55, 0.45, "Yellow", fontsize=8, color="#b8860b", fontweight="bold")
    ax.text(55, 0.70, "Orange", fontsize=8, color=COLORS["orange"], fontweight="bold")
    ax.text(55, 0.90, "Red", fontsize=8, color=COLORS["red"], fontweight="bold")

    # Zone lines
    for threshold in [ZONE_YELLOW, ZONE_ORANGE, ZONE_RED]:
        ax.axhline(threshold, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)

    ax.set_title("Exponential Decay Pressure: $P_{\\mathrm{time}} = 1 - e^{-k/t}$, $k=3$")
    fig.savefig(os.path.join(OUTDIR, "pressure_curve.pdf"))
    plt.close(fig)
    print("  pressure_curve.pdf")


# =========================================================================
# Figure 2: Factor Decomposition
# =========================================================================
def fig_factor_decomposition():
    t = np.linspace(0.5, 30, 200)

    # Scenario: material obligation, 2 deps, 40% complete
    pt_vals = [p_time(ti) for ti in t]
    m_factor = MATERIALITY_WEIGHTS["material"]
    a_factor = 1.0 + 2 * 0.1  # 2 deps
    d_factor = 1.0 - 0.4 * COMPLETION_DAMPENING  # 40% complete

    p_base = np.array(pt_vals)
    p_mat = np.clip(p_base * m_factor, 0, 1)
    p_dep = np.clip(p_base * m_factor * a_factor, 0, 1)
    p_full = np.clip(p_base * m_factor * a_factor * d_factor, 0, 1)

    fig, ax = plt.subplots()
    ax.plot(t, p_base, label="$P_{\\mathrm{time}}$ only", color=COLORS["blue"], linewidth=1.5)
    ax.plot(t, p_mat, label="+ Materiality ($M=1.5$)", color=COLORS["orange"], linewidth=1.5)
    ax.plot(t, p_dep, label="+ Dependencies ($A=1.2$)", color=COLORS["red"], linewidth=1.5)
    ax.plot(t, p_full, label="+ Completion 40\\% ($D=0.76$)", color=COLORS["purple"],
            linewidth=1.5, linestyle="--")

    ax.set_xlabel("Days until deadline")
    ax.set_ylabel("Composite pressure $P$")
    ax.set_xlim(0.5, 30)
    ax.set_ylim(0, 1.05)
    ax.invert_xaxis()
    ax.legend(loc="lower left", framealpha=0.9)
    ax.set_title("Factor Decomposition: Material Obligation, 2 Deps, 40\\% Complete")
    fig.savefig(os.path.join(OUTDIR, "factor_decomposition.pdf"))
    plt.close(fig)
    print("  factor_decomposition.pdf")


# =========================================================================
# Figure 3: Sensitivity Analysis (k values)
# =========================================================================
def fig_sensitivity():
    t = np.linspace(0.5, 30, 300)
    k_values = [2, 3, 4, 5]
    colors = [COLORS["green"], COLORS["blue"], COLORS["orange"], COLORS["red"]]

    fig, ax = plt.subplots()

    for k, c in zip(k_values, colors, strict=True):
        p = [p_time(ti, k=k) for ti in t]
        ax.plot(t, p, label=f"$k = {k}$", color=c, linewidth=1.5)

    # Zone thresholds
    for threshold, _label in [(ZONE_YELLOW, "Yellow"), (ZONE_ORANGE, "Orange"), (ZONE_RED, "Red")]:
        ax.axhline(threshold, color="gray", linestyle=":", linewidth=0.5, alpha=0.6)

    ax.set_xlabel("Days until deadline ($t$)")
    ax.set_ylabel("Time pressure $P_{\\mathrm{time}}(t)$")
    ax.set_xlim(0.5, 30)
    ax.set_ylim(0, 1.05)
    ax.invert_xaxis()
    ax.legend(loc="lower left", framealpha=0.9)
    ax.set_title("Sensitivity: Rate Constant $k$")
    fig.savefig(os.path.join(OUTDIR, "sensitivity_k.pdf"))
    plt.close(fig)
    print("  sensitivity_k.pdf")


# =========================================================================
# Figure 4: Baseline Comparison
# =========================================================================
def fig_baselines():
    t = np.linspace(0.5, 30, 300)

    # Tidewatch
    tw = [p_time(ti) for ti in t]

    # EDF: binary step at deadline (1 if overdue, else 1/t normalized)
    # Actually: EDF priority = 1/t (closer deadline = higher priority)
    edf = [1.0 / ti for ti in t]
    edf_max = max(edf)
    edf = [e / edf_max for e in edf]  # normalize to [0, 1]

    # Linear decay: P = 1 - t/t_max
    t_max = 30
    linear = [max(0, 1.0 - ti / t_max) for ti in t]

    # Step function: binary at 7 days
    step = [1.0 if ti <= 7 else 0.0 for ti in t]

    fig, ax = plt.subplots()
    ax.plot(t, tw, label="Tidewatch ($1 - e^{-3/t}$)", color=COLORS["blue"], linewidth=2)
    ax.plot(t, edf, label="EDF ($1/t$, normalized)", color=COLORS["orange"],
            linewidth=1.5, linestyle="--")
    ax.plot(t, linear, label="Linear ($1 - t/30$)", color=COLORS["green"],
            linewidth=1.5, linestyle="-.")
    ax.plot(t, step, label="Binary (overdue at $t=7$)", color=COLORS["red"],
            linewidth=1.5, linestyle=":")

    ax.set_xlabel("Days until deadline ($t$)")
    ax.set_ylabel("Urgency / pressure signal")
    ax.set_xlim(0.5, 30)
    ax.set_ylim(-0.05, 1.1)
    ax.invert_xaxis()
    ax.legend(loc="center left", framealpha=0.9)
    ax.set_title("Baseline Comparison: Urgency Models")
    fig.savefig(os.path.join(OUTDIR, "baseline_comparison.pdf"))
    plt.close(fig)
    print("  baseline_comparison.pdf")


# =========================================================================
# Figure 5: Bandwidth Modulation
# =========================================================================
def fig_bandwidth():
    bandwidths = np.linspace(0.0, 1.0, 100)

    # Two tasks: legal (high demand=0.9) and ops (low demand=0.2)
    # Pressure: legal=1.0, ops=0.777
    p_legal = 1.0
    p_ops = 0.777
    demand_legal = 0.9
    demand_ops = 0.2

    def adjusted_score(p, demand, b):
        """Bandwidth-adjusted score: penalize high-demand at low bandwidth."""
        if b < 0.5:
            penalty = (1.0 - b) * demand
            return p * (1.0 - penalty * 0.8)
        return p

    legal_scores = [adjusted_score(p_legal, demand_legal, b) for b in bandwidths]
    ops_scores = [adjusted_score(p_ops, demand_ops, b) for b in bandwidths]

    fig, ax = plt.subplots()
    ax.plot(bandwidths, legal_scores, label="Legal brief ($P=1.0$, demand=0.9)",
            color=COLORS["red"], linewidth=2)
    ax.plot(bandwidths, ops_scores, label="Config update ($P=0.78$, demand=0.2)",
            color=COLORS["blue"], linewidth=2)

    # Mark crossover
    for i in range(len(bandwidths) - 1):
        if legal_scores[i] > ops_scores[i] and legal_scores[i + 1] <= ops_scores[i + 1]:
            cross_b = bandwidths[i]
            cross_v = legal_scores[i]
            ax.axvline(cross_b, color="gray", linestyle="--", linewidth=0.5)
            ax.annotate("Crossover", xy=(cross_b, cross_v), xytext=(cross_b + 0.12, cross_v - 0.08),
                        fontsize=8, arrowprops=dict(arrowstyle="->", color="gray"))
            break

    ax.set_xlabel("Cognitive bandwidth $b$")
    ax.set_ylabel("Adjusted priority score")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("Bandwidth Modulation: Task Priority vs. Operator Capacity")
    fig.savefig(os.path.join(OUTDIR, "bandwidth_modulation.pdf"))
    plt.close(fig)
    print("  bandwidth_modulation.pdf")


# =========================================================================
# Main
# =========================================================================
if __name__ == "__main__":
    print("Generating paper figures...")
    fig_pressure_curve()
    fig_factor_decomposition()
    fig_sensitivity()
    fig_baselines()
    fig_bandwidth()
    print(f"Done. {len(os.listdir(OUTDIR))} figures in {OUTDIR}")
