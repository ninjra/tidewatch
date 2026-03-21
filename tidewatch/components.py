# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Pressure component space — Late Collapse architecture for obligation scoring.

Individual scoring factors are preserved as named dimensions through the entire
pipeline. Collapse to a scalar [0,1] pressure score happens only when a consumer
requires it, via an explicit collapse method.

This module defines the interface (Protocol) and provides a default implementation
backed by gravitas.types.ComponentSpace. The gravitas dependency is optional —
any implementation satisfying ComponentSpaceProtocol can be substituted.

Architecture decision: exponential time-decay is the BASE SIGNAL. All other
factors (materiality, dependency, completion, timing, violation) are MODULATING
COMPONENTS that adjust the base signal's urgency weighting.

References:
  - Gravitas Late Collapse Principle (gravitas/types.py:ComponentSpace)
  - Tidewatch paper §3.1 (pressure equation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Protocol — any backend can implement this ─────────────────────────────────


@runtime_checkable
class ComponentSpaceProtocol(Protocol):
    """Interface for a multi-dimensional scoring space with late collapse.

    Implementations must support:
    - Named components with float values
    - Per-component bounds for normalization
    - Default collapse (product of all components)
    - Weighted collapse for query-adaptive ranking
    - Pareto dominance comparison
    """

    @property
    def components(self) -> dict[str, float]: ...

    @property
    def component_bounds(self) -> dict[str, tuple[float, float]]: ...

    @property
    def collapsed(self) -> float:
        """Default collapse: product of all components."""
        ...

    def weighted_collapse(self, weights: dict[str, float]) -> float:
        """Weighted sum collapse for query-adaptive ranking."""
        ...

    def dominates(self, other: ComponentSpaceProtocol) -> bool | None:
        """Pareto dominance: True if self >= other on all dimensions and > on at least one.
        None if incomparable."""
        ...


# ── Default implementation via Gravitas ───────────────────────────────────────


def _make_component_space(
    components: dict[str, float],
    component_bounds: dict[str, tuple[float, float]] | None = None,
    source_equation: str = "",
    raw_inputs: dict[str, Any] | None = None,
) -> ComponentSpaceProtocol:
    """Create a ComponentSpace using the best available backend.

    Tries gravitas.types.ComponentSpace first (full Pareto support).
    Falls back to a lightweight stdlib implementation if gravitas is unavailable.
    """
    try:
        from gravitas.types import ComponentSpace
        return ComponentSpace(
            components=components,
            component_bounds=component_bounds or {},
            source_equation=source_equation,
            raw_inputs=raw_inputs or {},
        )
    except ImportError:
        logger.debug("gravitas not available — using lightweight ComponentSpace fallback")
        return _FallbackComponentSpace(
            _components=components,
            _bounds=component_bounds or {},
            _source_equation=source_equation,
        )


@dataclass(frozen=True)
class _FallbackComponentSpace:
    """Lightweight ComponentSpace for environments without gravitas.

    Provides the same interface but without Pareto ranking support
    (dominates() always returns None).
    """

    _components: dict[str, float]
    _bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    _source_equation: str = ""

    @property
    def components(self) -> dict[str, float]:
        return dict(self._components)

    @property
    def component_bounds(self) -> dict[str, tuple[float, float]]:
        return dict(self._bounds)

    @property
    def collapsed(self) -> float:
        """Product of all components."""
        result = 1.0
        for v in self._components.values():
            result *= v
        return result

    def weighted_collapse(self, weights: dict[str, float]) -> float:
        """Weighted sum collapse with bound normalization (#1185).

        Each component is normalized to [0, 1] using its algebraic bounds
        before the weighted sum. This ensures components with different
        scales (e.g., time_pressure [0,1] vs dependency_amp [1,5])
        contribute proportionally rather than being dominated by
        higher-magnitude components.
        """
        total = 0.0
        weight_sum = 0.0
        for name, value in self._components.items():
            w = weights.get(name, 1.0)
            lo, hi = self._bounds.get(name, (0.0, 1.0))
            span = hi - lo
            norm = (value - lo) / span if span > 0 else 0.0
            norm = max(0.0, min(1.0, norm))
            total += w * norm
            weight_sum += w
        return total / weight_sum if weight_sum > 0 else 0.0

    def dominates(self, other: ComponentSpaceProtocol) -> bool | None:
        """Fallback: no Pareto support — always incomparable."""
        return None


# ── Pressure-specific component space ─────────────────────────────────────────


# Component names — canonical keys used throughout the pipeline
COMP_TIME_PRESSURE = "time_pressure"
COMP_MATERIALITY = "materiality"
COMP_DEPENDENCY_AMP = "dependency_amp"
COMP_COMPLETION_DAMP = "completion_damp"
COMP_TIMING_AMP = "timing_amp"
COMP_VIOLATION_AMP = "violation_amp"

# Default bounds per component (for normalization and Pareto).
# Exhaustive: one entry per COMP_* factor. Bounds derived from the pressure
# equation's algebraic range — see constants.py for the source values.
_DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    COMP_TIME_PRESSURE: (0.0, 1.0),
    COMP_MATERIALITY: (1.0, 1.5),
    COMP_DEPENDENCY_AMP: (1.0, 5.0),  # practical upper bound for 40 deps
    COMP_COMPLETION_DAMP: (0.4, 1.0),
    COMP_TIMING_AMP: (1.0, 1.2),
    COMP_VIOLATION_AMP: (1.0, 1.5),
}

# Source equation for auditability
_SOURCE_EQUATION = "P = P_time × M × A × D × timing_amp × violation_amp (§3.1)"


@dataclass(frozen=True)
class PressureComponents:
    """Pressure decomposition preserving all factors as named components.

    This is the primary output of calculate_pressure(). The scalar .pressure
    property is a convenience that collapses all components via product.
    For Pareto-aware ranking, use .space directly.
    """

    space: ComponentSpaceProtocol
    obligation_id: int | str

    @property
    def pressure(self) -> float:
        """Default collapse: product of all components, saturated to [0,1]."""
        from tidewatch.constants import saturate
        return saturate(self.space.collapsed)

    @property
    def zone(self) -> str:
        """Zone classification from collapsed pressure."""
        from tidewatch.pressure import pressure_zone
        return pressure_zone(self.pressure)

    @property
    def time_pressure(self) -> float:
        return self.space.components.get(COMP_TIME_PRESSURE, 0.0)

    @property
    def materiality_mult(self) -> float:
        return self.space.components.get(COMP_MATERIALITY, 1.0)

    @property
    def dependency_amp(self) -> float:
        return self.space.components.get(COMP_DEPENDENCY_AMP, 1.0)

    @property
    def completion_damp(self) -> float:
        return self.space.components.get(COMP_COMPLETION_DAMP, 1.0)

    def collapse(self, weights: dict[str, float] | None = None) -> float:
        """Custom-weighted collapse for query-adaptive ranking (#1185).

        When weights are provided, each component is normalized to [0,1]
        using its algebraic bounds before the weighted sum. This ensures
        components with different scales contribute proportionally.
        """
        if weights:
            components = self.space.components
            bounds = self.space.component_bounds
            total = 0.0
            weight_sum = 0.0
            for name, value in components.items():
                w = weights.get(name, 1.0)
                lo, hi = bounds.get(name, (0.0, 1.0))
                span = hi - lo
                norm = (value - lo) / span if span > 0 else 0.0
                norm = max(0.0, min(1.0, norm))
                total += w * norm
                weight_sum += w
            return total / weight_sum if weight_sum > 0 else 0.0
        return self.pressure

    def dominates(self, other: PressureComponents) -> bool | None:
        """Pareto dominance: does this obligation dominate the other on all factors?"""
        return self.space.dominates(other.space)


def build_pressure_space(
    time_pressure: float,
    materiality: float,
    dependency_amp: float,
    completion_damp: float,
    timing_amp: float,
    violation_amp: float,
    obligation_id: int | str,
    raw_inputs: dict[str, Any] | None = None,
) -> PressureComponents:
    """Construct a PressureComponents from individual factor values."""
    space = _make_component_space(
        components={
            COMP_TIME_PRESSURE: time_pressure,
            COMP_MATERIALITY: materiality,
            COMP_DEPENDENCY_AMP: dependency_amp,
            COMP_COMPLETION_DAMP: completion_damp,
            COMP_TIMING_AMP: timing_amp,
            COMP_VIOLATION_AMP: violation_amp,
        },
        component_bounds=_DEFAULT_BOUNDS,
        source_equation=_SOURCE_EQUATION,
        raw_inputs=raw_inputs,
    )
    return PressureComponents(space=space, obligation_id=obligation_id)
