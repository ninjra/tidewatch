# tidewatch — Implementation Matrix

**Generated:** 2026-03-12  
**Test functions:** 34  
**Test files:** 4  
**Conftest:** NO  
**Packages:** 5

## Module Status

| Package | Modules | Test Files | Status |
|---------|---------|------------|--------|
| `benchmarks` | 2 | 0 | UNTESTED |
| `benchmarks/baselines` | 3 | 0 | UNTESTED |
| `benchmarks/datasets` | 1 | 0 | UNTESTED |
| `tests` | 4 | 0 | UNTESTED |
| `tidewatch` | 5 | 3 | TESTED |

### Untested Modules

- `benchmarks/metrics.py`
- `benchmarks/run.py`
- `benchmarks/baselines/binary_deadline.py`
- `benchmarks/baselines/eisenhower.py`
- `benchmarks/baselines/linear_urgency.py`
- `benchmarks/datasets/generate_obligations.py`
- `tests/test_integration.py`
- `tests/test_planner.py`
- `tests/test_pressure.py`
- `tests/test_triage.py`
- `tidewatch/constants.py`
- `tidewatch/types.py`

## Frozen Surfaces

Public API signatures and data contracts that MUST NOT change without 
version bump + migration path. Breaking changes require explicit approval.

### `benchmarks`

**Public Functions:**
- `metrics.zone_transition_timeliness(first_alert_days, optimal_attention_days)`
- `metrics.missed_deadline_rate(alerted_48h_prior)`
- `metrics.attention_allocation_efficiency(predicted_ranks, actual_ranks)`
- `metrics.false_alarm_rate(alerted_high, completed_early)`
- `run.run_tidewatch(obligations_data, now)`
- `run.run_baseline(name, obligations_data)`
- `run.main()`

### `benchmarks/baselines`

**Public Functions:**
- `binary_deadline.score(days_remaining)`
- `eisenhower.score(days_remaining, materiality)`
- `linear_urgency.score(days_remaining, horizon)`

### `benchmarks/datasets`

**Public Functions:**
- `generate_obligations.generate(n, seed)`
- `generate_obligations.main()`

### `tests`

**Public Classes:**
- `test_integration.TestFullPipeline`
  - `test_full_pipeline()`
  - `test_pressure_drives_planning()`
  - `test_zone_transition_detection()`
- `test_planner.TestPlannerFiltering`
  - `test_green_not_planned()`
  - `test_orange_triggers_plan()`
  - `test_red_triggers_plan()`
- `test_planner.TestPlannerLimits`
  - `test_top_n_limit()`
- `test_planner.TestPromptContent`
  - `test_prompt_contains_obligation_data()`
- `test_planner.TestDeliveryUrgency`
  - `test_delivery_urgency_by_zone()`
- `test_planner.TestPlanCompletion`
  - `test_complete_plan_wraps_result()`
  - `test_custom_system_prompt()`
- `test_pressure.TestTimePressure`
  - `test_no_deadline_returns_zero()`
  - `test_overdue_returns_one()`
  - `test_14_days_out()`
  - `test_7_days_out()`
  - `test_3_days_out()`
  - `test_1_day_out()`
- `test_pressure.TestMateriality`
  - `test_materiality_multiplier()`
- `test_pressure.TestDependencies`
  - `test_dependency_amplification()`
- `test_pressure.TestCompletion`
  - `test_completion_dampening()`
- `test_pressure.TestCombined`
  - `test_combined_factors_multiply()`
  - `test_pressure_clamped_to_one()`
- `test_pressure.TestZones`
  - `test_zone_boundaries()`
  - `test_zone_green()`
  - `test_zone_yellow()`
  - `test_zone_orange()`
  - `test_zone_red()`
- `test_pressure.TestBatch`
  - `test_batch_recalculate_sorted()`
  - `test_pressure_result_decomposition()`
- `test_triage.TestTriageQueue`
  - `test_stage_and_list()`
  - `test_accept_creates_obligation()`
  - `test_reject_removes_candidate()`
  - `test_dedup_by_title_source_date()`
  - `test_empty_queue()`

### `tidewatch`

**Exported API (`__init__.py`):**
- `calculate_pressure` (__all__)
- `pressure_zone` (__all__)
- `recalculate_batch` (__all__)
- `SpeculativePlanner` (__all__)
- `TriageQueue` (__all__)
- `Obligation` (__all__)
- `PressureResult` (__all__)
- `PlanRequest` (__all__)
- `PlanResult` (__all__)
- `Zone` (__all__)
- `TriageCandidate` (__all__)

**Public Classes:**
- `planner.SpeculativePlanner`
  - `generate_plan_requests(pressure_results, obligations, obligation_map)`
  - `complete_plan(plan_request, plan_text)`
- `triage.TriageQueue`
  - `stage(candidate)`
  - `list_pending()`
  - `accept(candidate_id)`
  - `reject(candidate_id)`
- `types.Zone`
- `types.Obligation`
- `types.PressureResult`
- `types.PlanRequest`
- `types.PlanResult`
- `types.TriageCandidate`

**Public Functions:**
- `pressure.calculate_pressure(obligation, now)`
- `pressure.pressure_zone(pressure)`
- `pressure.recalculate_batch(obligations, now)`

## Changelog (recent)

- dfd3f5d feat: initial tidewatch library — pressure engine, planner, triage

## Phase Tracking

| Phase | Status | Notes |
|-------|--------|-------|
| Core implementation | ACTIVE | — |
| Test coverage | TODO | — |
| Frozen surface audit | TODO | Review auto-detected surfaces above |
