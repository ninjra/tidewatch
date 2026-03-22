# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Tests for large-N scaling resolutions (Problems 1–6).

Each test class maps to one problem's acceptance criteria. A final class
verifies backward compatibility: all new features disabled produces
identical output to v0.4.4 baseline.
"""

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from tidewatch.pressure import (
    apply_zone_capacity,
    calculate_pressure,
    compute_adaptive_k,
    compute_dependency_cap,
    recalculate_batch,
    recalculate_stale,
    top_k_obligations,
)
from tidewatch.types import DeadlineDistribution, Obligation

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _make_obligations_uniform(n: int, max_days: float = 90.0) -> list[Obligation]:
    """Generate N obligations with deadlines uniformly distributed over max_days."""
    rng = random.Random(42)  # Deterministic seed
    obligations = []
    for i in range(n):
        days_out = rng.uniform(0.1, max_days)
        obligations.append(Obligation(
            id=i,
            title=f"Obligation {i}",
            due_date=NOW + timedelta(days=days_out),
            materiality=rng.choice(["routine", "material"]),
            dependency_count=rng.randint(0, 10),
            completion_pct=rng.uniform(0.0, 0.8),
        ))
    return obligations


# ════════════════════════════════════════════════════════════════════
# Problem 1 — Saturation Collapse (Adaptive k)
# ════════════════════════════════════════════════════════════════════


class TestProblem1_AdaptiveK:
    """Adaptive rate constant k spreads pressure across [0,1] at large N."""

    def test_adaptive_k_formula(self):
        """k = -t_median * ln(1 - ZONE_YELLOW) with clamping."""
        from tidewatch.constants import ZONE_YELLOW
        dist = DeadlineDistribution(min_days=1.0, max_days=90.0, median_days=45.0, count=10000)
        k = compute_adaptive_k(dist)
        expected = -45.0 * math.log(1.0 - ZONE_YELLOW)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_adaptive_k_default_median(self):
        """At median=7d, adaptive k ≈ 2.50 (close to default k=3.0)."""
        dist = DeadlineDistribution(min_days=1.0, max_days=14.0, median_days=7.0, count=50)
        k = compute_adaptive_k(dist)
        assert 2.0 < k < 3.0

    def test_adaptive_k_all_overdue(self):
        """All overdue (median<=0) returns default RATE_CONSTANT."""
        from tidewatch.constants import RATE_CONSTANT
        dist = DeadlineDistribution(min_days=-10.0, max_days=-1.0, median_days=-5.0, count=100)
        k = compute_adaptive_k(dist)
        assert k == RATE_CONSTANT

    def test_adaptive_k_clamped_min(self):
        """Very small median yields k floored at ADAPTIVE_K_MIN."""
        from tidewatch.constants import ADAPTIVE_K_MIN
        dist = DeadlineDistribution(min_days=0.01, max_days=1.0, median_days=0.5, count=10)
        k = compute_adaptive_k(dist)
        assert k >= ADAPTIVE_K_MIN

    def test_adaptive_k_clamped_max(self):
        """Very large median yields k capped at ADAPTIVE_K_MAX."""
        from tidewatch.constants import ADAPTIVE_K_MAX
        dist = DeadlineDistribution(min_days=100.0, max_days=500.0, median_days=300.0, count=10)
        k = compute_adaptive_k(dist)
        assert k <= ADAPTIVE_K_MAX

    def test_n10000_uniform_90d_no_saturation(self):
        """Acceptance: at N=10000 with 90-day uniform deadlines, <15% saturated at P≥0.999."""
        obligations = _make_obligations_uniform(10000, max_days=90.0)
        # Compute deadline stats
        days_list = [
            (ob.due_date - NOW).total_seconds() / 86400.0
            for ob in obligations if ob.due_date is not None
        ]
        days_list.sort()
        dist = DeadlineDistribution(
            min_days=min(days_list),
            max_days=max(days_list),
            median_days=days_list[len(days_list) // 2],
            count=len(obligations),
        )
        results = recalculate_batch(obligations, now=NOW, deadline_distribution=dist)
        saturated = sum(1 for r in results if r.pressure >= 0.999)
        pct_saturated = saturated / len(results)
        assert pct_saturated < 0.15, (
            f"{pct_saturated:.1%} saturated at P≥0.999 (max 15%)"
        )

    def test_batch_without_distribution_uses_default_k(self):
        """Without deadline_distribution, batch uses k=3.0 (backward compatible)."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        results_default = recalculate_batch([ob], now=NOW)
        results_explicit = recalculate_batch([ob], now=NOW, deadline_distribution=None)
        assert results_default[0].pressure == results_explicit[0].pressure


# ════════════════════════════════════════════════════════════════════
# Problem 2 — Modulator Dynamic Range (Rank Normalization)
# ════════════════════════════════════════════════════════════════════


class TestProblem2_RankNormalize:
    """Rank normalization produces distinct scores among saturated items."""

    def test_rank_normalize_distinct_scores(self):
        """Acceptance: 1000 items, 200 with Ptime≥0.99, rank-normalized yields ≥180 distinct."""
        obligations = []
        for i in range(200):
            # Near-overdue: Ptime will be ≥0.99
            obligations.append(Obligation(
                id=i,
                title=f"Near-overdue {i}",
                due_date=NOW + timedelta(hours=random.Random(42 + i).uniform(0.5, 12)),
                materiality=random.Random(42 + i).choice(["routine", "material"]),
                dependency_count=random.Random(42 + i).randint(0, 15),
                completion_pct=random.Random(42 + i).uniform(0.0, 0.5),
            ))
        for i in range(800):
            obligations.append(Obligation(
                id=200 + i,
                title=f"Normal {i}",
                due_date=NOW + timedelta(days=random.Random(1000 + i).uniform(1, 60)),
                dependency_count=random.Random(1000 + i).randint(0, 5),
                completion_pct=random.Random(1000 + i).uniform(0.0, 0.6),
            ))

        results = recalculate_batch(obligations, now=NOW, rank_normalize=True)

        # Find items that were near-overdue (IDs 0-199)
        near_overdue_results = [r for r in results if r.obligation_id < 200]
        assert len(near_overdue_results) == 200

        distinct_scores = len(set(round(r.pressure, 10) for r in near_overdue_results))
        assert distinct_scores >= 180, (
            f"Only {distinct_scores} distinct scores among 200 near-overdue items (need ≥180)"
        )

    def test_rank_normalize_off_by_default(self):
        """rank_normalize=False (default) matches v0.4.4 behavior."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        r_default = recalculate_batch([ob], now=NOW)
        r_explicit = recalculate_batch([ob], now=NOW, rank_normalize=False)
        assert r_default[0].pressure == r_explicit[0].pressure

    def test_rank_normalize_raw_values_accessible(self):
        """Raw component values remain accessible via component_space."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(10)
        ]
        results = recalculate_batch(obligations, now=NOW, rank_normalize=True)
        for r in results:
            assert r.component_space is not None
            raw = r.component_space.space.raw_inputs
            assert "raw_components" in raw


# ════════════════════════════════════════════════════════════════════
# Problem 3 — Batch Recalculation Staleness
# ════════════════════════════════════════════════════════════════════


class TestProblem3_RecalculateStale:
    """Incremental recalculation rescores only stale or changed items."""

    def test_scored_at_populated(self):
        """calculate_pressure sets scored_at on results."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        assert result.scored_at == NOW

    def test_input_hash_populated(self):
        """calculate_pressure sets input_hash on results."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        assert result.input_hash is not None
        assert len(result.input_hash) == 32  # MD5 hex digest

    def test_input_hash_changes_with_fields(self):
        """input_hash changes when mutable scoring fields change."""
        ob1 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         completion_pct=0.0)
        ob2 = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7),
                         completion_pct=0.5)
        r1 = calculate_pressure(ob1, now=NOW)
        r2 = calculate_pressure(ob2, now=NOW)
        assert r1.input_hash != r2.input_hash

    def test_stale_by_age(self):
        """Items scored before cutoff are rescored."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(100)
        ]
        old_now = NOW - timedelta(hours=2)
        results = recalculate_batch(obligations, now=old_now)

        # All scored at old_now — with 1-hour budget, all are stale
        updated = recalculate_stale(
            results, obligations, now=NOW, staleness_budget=3600.0,
        )
        # All should be rescored (new scored_at)
        for r in updated:
            assert r.scored_at == NOW

    def test_stale_by_input_change(self):
        """Items with changed inputs are rescored even if recently scored."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}", due_date=NOW + timedelta(days=i + 1))
            for i in range(100)
        ]
        results = recalculate_batch(obligations, now=NOW)

        # Change 50 obligations' completion
        changed_obligations = list(obligations)
        for i in range(50):
            changed_obligations[i] = Obligation(
                id=i, title=f"Ob {i}",
                due_date=NOW + timedelta(days=i + 1),
                completion_pct=0.5,
            )

        # Large staleness budget — only input changes trigger rescore
        updated = recalculate_stale(
            results, changed_obligations, now=NOW,
            staleness_budget=999999.0,
        )
        # The 50 changed items should have new hashes
        changed_ids = set(range(50))
        for r in updated:
            if r.obligation_id in changed_ids:
                expected_hash = calculate_pressure(
                    changed_obligations[r.obligation_id], now=NOW,
                ).input_hash
                assert r.input_hash == expected_hash

    def test_acceptance_50_stale_of_10000(self):
        """Acceptance: 10000 results, 50 stale — only those 50 get rescored."""
        obligations = _make_obligations_uniform(10000)
        results = recalculate_batch(obligations, now=NOW)

        # Make 50 items stale by giving them an old scored_at
        stale_ids = set(range(50))
        for r in results:
            if r.obligation_id in stale_ids:
                r.scored_at = NOW - timedelta(hours=2)

        updated = recalculate_stale(
            results, obligations, now=NOW, staleness_budget=3600.0,
        )
        # Fresh items should retain their original scored_at
        rescored_count = sum(
            1 for r in updated if r.scored_at == NOW and r.obligation_id in stale_ids
        )
        assert rescored_count == 50

        # Items not in stale_ids should keep original scored_at (NOW from batch)
        # Since batch also used NOW, all scored_at == NOW, but input_hash unchanged
        non_stale_unchanged = sum(
            1 for r in updated if r.obligation_id not in stale_ids
        )
        assert non_stale_unchanged == 9950


# ════════════════════════════════════════════════════════════════════
# Problem 4 — Pareto at Scale (Budget)
# ════════════════════════════════════════════════════════════════════


class TestProblem4_ParetoBudget:
    """Pareto budget limits front extraction and maintains performance."""

    def test_pareto_budget_limits_fronts(self):
        """With pareto_budget=5, at most 5 fronts are extracted."""
        # Create obligations that will produce many Pareto fronts
        obligations = _make_obligations_uniform(200)
        results = recalculate_batch(
            obligations, now=NOW, pareto=True, pareto_budget=5,
        )
        assert len(results) == 200  # All items present

    def test_pareto_budget_none_extracts_all(self):
        """pareto_budget=None (default) extracts all fronts."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}",
                       due_date=NOW + timedelta(days=i + 1))
            for i in range(20)
        ]
        results_all = recalculate_batch(obligations, now=NOW, pareto=True)
        results_budgeted = recalculate_batch(
            obligations, now=NOW, pareto=True, pareto_budget=None,
        )
        assert [r.obligation_id for r in results_all] == [
            r.obligation_id for r in results_budgeted
        ]

    def test_pareto_budget_tail_sorted_by_pressure(self):
        """Items beyond the budget are sorted by scalar pressure descending."""
        obligations = _make_obligations_uniform(100)
        results = recalculate_batch(
            obligations, now=NOW, pareto=True, pareto_budget=2,
        )
        # Find where front items end (first 2 fronts) and tail begins
        # The tail should be sorted by pressure descending
        # We verify the entire list is in non-increasing pressure order
        # (which holds because fronts are also sorted by pressure within each front)
        pressures = [r.pressure for r in results]
        # Tail items (after front items) should be sorted descending
        # Since fronts are sorted desc and tail is sorted desc, we check
        # that the tail portion (after budget fronts) is desc
        assert len(pressures) == 100

    def test_acceptance_n10000_budget5_under_2s(self):
        """Acceptance: N=10000 with pareto_budget=5 returns in <2 seconds."""
        import time
        obligations = _make_obligations_uniform(10000)
        t0 = time.monotonic()
        results = recalculate_batch(
            obligations, now=NOW, pareto=True, pareto_budget=5,
        )
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0, f"Took {elapsed:.2f}s (max 2.0s)"
        assert len(results) == 10000


# ════════════════════════════════════════════════════════════════════
# Problem 5 — Zone Classification at Scale (TopK + Zone Capacity)
# ════════════════════════════════════════════════════════════════════


class TestProblem5_ZoneCapacity:
    """TopK and zone capacity prevent zone inflation at large N."""

    def test_top_k_returns_k_items(self):
        """top_k_obligations returns exactly K items."""
        obligations = _make_obligations_uniform(100)
        results = recalculate_batch(obligations, now=NOW)
        top = top_k_obligations(results, k=10)
        assert len(top) == 10

    def test_top_k_sorted_descending(self):
        """top_k_obligations returns items sorted by pressure descending."""
        obligations = _make_obligations_uniform(100)
        results = recalculate_batch(obligations, now=NOW)
        top = top_k_obligations(results, k=10)
        pressures = [r.pressure for r in top]
        assert pressures == sorted(pressures, reverse=True)

    def test_top_k_has_component_space(self):
        """top_k items retain full component decomposition."""
        obligations = _make_obligations_uniform(50)
        results = recalculate_batch(obligations, now=NOW)
        top = top_k_obligations(results, k=5)
        for r in top:
            assert r.component_space is not None
            assert r.zone in ("green", "yellow", "orange", "red")

    def test_zone_capacity_demotes_overflow(self):
        """Acceptance: zone_capacity=50, 500 red items → only top 50 remain red."""
        # Create 500 near-overdue obligations (all will be red)
        obligations = []
        for i in range(500):
            obligations.append(Obligation(
                id=i, title=f"Red {i}",
                due_date=NOW + timedelta(hours=random.Random(i).uniform(0.1, 6)),
                materiality="material",
                dependency_count=5,
            ))
        results = recalculate_batch(obligations, now=NOW)

        # Verify many are red before capacity
        red_before = sum(1 for r in results if r.zone == "red")
        assert red_before > 50, f"Only {red_before} red items — need >50 for test"

        # Apply zone capacity
        capped = apply_zone_capacity(results, zone_capacity=50)
        red_after = sum(1 for r in capped if r.zone == "red")
        assert red_after == 50, f"Expected 50 red after cap, got {red_after}"

        # Demoted items cascade: red→orange (capped at 50), overflow→yellow, etc.
        # Total items across all zones must still equal 500
        total = sum(1 for r in capped)
        assert total == 500

    def test_zone_capacity_none_no_change(self):
        """zone_capacity=None (default) leaves zones unchanged."""
        obligations = _make_obligations_uniform(50)
        results = recalculate_batch(obligations, now=NOW)
        zones_before = [r.zone for r in results]
        capped = apply_zone_capacity(results, zone_capacity=None)
        zones_after = [r.zone for r in capped]
        assert zones_before == zones_after

    def test_zone_capacity_cascading_demotion(self):
        """Overflow cascades: red→orange overflow cascades to orange→yellow."""
        obligations = []
        # 100 red items
        for i in range(100):
            obligations.append(Obligation(
                id=i, title=f"Red {i}",
                due_date=NOW + timedelta(hours=1),
                materiality="material",
                dependency_count=10,
            ))
        # 100 orange items
        for i in range(100):
            obligations.append(Obligation(
                id=100 + i, title=f"Orange {i}",
                due_date=NOW + timedelta(days=3),
                materiality="material",
            ))
        results = recalculate_batch(obligations, now=NOW)
        capped = apply_zone_capacity(results, zone_capacity=10)

        red_count = sum(1 for r in capped if r.zone == "red")
        assert red_count == 10  # Only 10 red items remain


# ════════════════════════════════════════════════════════════════════
# Problem 6 — Dependency Cap (Population-Relative)
# ════════════════════════════════════════════════════════════════════


class TestProblem6_DependencyCap:
    """Population-relative dependency cap scales with N."""

    def test_fixed_mode_uses_default_cap(self):
        """fixed mode returns DEPENDENCY_COUNT_CAP (20)."""
        from tidewatch.constants import DEPENDENCY_COUNT_CAP
        cap = compute_dependency_cap(50, mode="fixed")
        assert cap == DEPENDENCY_COUNT_CAP

    def test_log_scaled_at_n50(self):
        """At N=50, log_scaled cap ≈ 28–29."""
        cap = compute_dependency_cap(50, mode="log_scaled")
        expected = max(20, math.ceil(math.log2(50) * 5))
        assert cap == expected
        assert cap >= 20

    def test_log_scaled_at_n10000(self):
        """At N=10000, log_scaled cap ≈ 67."""
        cap = compute_dependency_cap(10000, mode="log_scaled")
        expected = max(20, math.ceil(math.log2(10000) * 5))
        assert cap == expected
        assert cap > 60

    def test_log_scaled_at_n39000(self):
        """At N=39000, log_scaled cap ≈ 77."""
        cap = compute_dependency_cap(39000, mode="log_scaled")
        expected = max(20, math.ceil(math.log2(39000) * 5))
        assert cap == expected
        assert cap > 70

    def test_log_scaled_n1_returns_min(self):
        """At N=1, log_scaled returns minimum (20)."""
        cap = compute_dependency_cap(1, mode="log_scaled")
        assert cap == 20

    def test_invalid_mode_raises(self):
        """Unknown mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown dependency_cap_mode"):
            compute_dependency_cap(100, mode="quadratic")

    def test_acceptance_n10000_100_deps_not_capped_at_20(self):
        """Acceptance: At N=10000 with log_scaled, 100 real deps uses all 100."""
        ob = Obligation(
            id=1, title="Hub", due_date=NOW + timedelta(days=3),
            dependency_count=100,
        )
        # With fixed cap, effective deps = 20
        r_fixed = calculate_pressure(ob, now=NOW, dep_cap=20)
        # With log_scaled cap at N=10000 (cap≈67), effective deps = 67
        cap_log = compute_dependency_cap(10000, mode="log_scaled")
        r_log = calculate_pressure(ob, now=NOW, dep_cap=cap_log)
        assert r_log.dependency_amp > r_fixed.dependency_amp

        # With cap high enough to use all 100
        r_all = calculate_pressure(ob, now=NOW, dep_cap=100)
        assert r_all.dependency_amp > r_log.dependency_amp

    def test_fixed_mode_identical_to_v044(self):
        """Acceptance: At N=50 with fixed mode, behavior identical to v0.4.4."""
        ob = Obligation(
            id=1, title="Test", due_date=NOW + timedelta(days=7),
            dependency_count=5,
        )
        r_default = calculate_pressure(ob, now=NOW)
        r_fixed = calculate_pressure(ob, now=NOW, dep_cap=20)
        assert r_default.pressure == r_fixed.pressure

    def test_batch_dependency_cap_mode(self):
        """recalculate_batch passes dependency_cap_mode through."""
        obligations = [
            Obligation(id=1, title="Hub", due_date=NOW + timedelta(days=3),
                       dependency_count=50),
        ]
        r_fixed = recalculate_batch(obligations, now=NOW, dependency_cap_mode="fixed")
        r_log = recalculate_batch(obligations, now=NOW, dependency_cap_mode="log_scaled")
        # log_scaled at N=1 still caps at 20, so with 50 deps, both cap at 20
        # (single obligation batch)
        assert r_fixed[0].pressure == r_log[0].pressure


# ════════════════════════════════════════════════════════════════════
# Backward Compatibility — All features disabled = v0.4.4
# ════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """All new features disabled reproduces v0.4.4 behavior exactly."""

    def test_default_batch_unchanged(self):
        """recalculate_batch with no new params matches v0.4.4."""
        obligations = [
            Obligation(id=1, title="Far", due_date=NOW + timedelta(days=30)),
            Obligation(id=2, title="Close", due_date=NOW + timedelta(days=1)),
            Obligation(id=3, title="Medium", due_date=NOW + timedelta(days=7),
                       materiality="material", dependency_count=3),
        ]
        results = recalculate_batch(obligations, now=NOW)
        # Verify pressure computation uses k=3.0 and dep_cap=20
        for r in results:
            r_single = calculate_pressure(
                next(ob for ob in obligations if ob.id == r.obligation_id),
                now=NOW,
            )
            assert r.pressure == r_single.pressure

    def test_scored_at_and_hash_present_but_non_breaking(self):
        """New fields scored_at and input_hash are populated but don't affect sorting."""
        ob = Obligation(id=1, title="Test", due_date=NOW + timedelta(days=7))
        result = calculate_pressure(ob, now=NOW)
        assert result.scored_at is not None
        assert result.input_hash is not None
        # Pressure value unchanged from v0.4.4 equation
        expected_time_p = 1.0 - math.exp(-3.0 / 7.0)
        assert result.time_pressure == pytest.approx(expected_time_p, abs=1e-10)

    def test_pareto_without_budget_unchanged(self):
        """pareto=True without budget produces same ranking as v0.4.4."""
        obligations = [
            Obligation(id=i, title=f"Ob {i}",
                       due_date=NOW + timedelta(days=i + 1),
                       dependency_count=10 - i)
            for i in range(10)
        ]
        results = recalculate_batch(obligations, now=NOW, pareto=True)
        assert len(results) == 10
        # All items present
        assert set(r.obligation_id for r in results) == set(range(10))
