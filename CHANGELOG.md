# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.4.4] - 2026-03-22

### Added
- Large-N scaling: adaptive rate constant, rank normalization, incremental
  rescoring, Pareto budget, zone capacity limits, log-scaled dependency cap
- Self-evolving pipeline gate registry (`gates/registry.yaml`, `scripts/add_gate.py`)
- Verification block and interface seams in CLAUDE.md
- Paper quality gate checklist (7 structural checks)
- 659 deterministic and property-based tests (97% coverage)

### Changed
- Abstract and paper reframed for agent orchestration deployment model
- pyproject.toml: version synced to 0.4.4, gravitas moved to optional dep
- CLAUDE.md: updated equation to show all 6 factors

### Removed
- Vestigial constants: HARD_FLOOR_DOMAINS, BANDWIDTH_HOURS_BAD,
  PROVENANCE_COMPLETION_JUMP_THRESHOLD

## [0.4.3] - 2026-03-21

### Added
- Phase 5 audit fixes: terminology, repetition cleanup
- Minds-eye findings: format string extraction, constant naming

## [0.4.0] - 2026-03-20

### Added
- Six-factor pressure scoring engine with deferred scalarization
- Cognitive bandwidth modulation with 3-tier risk classification
- Speculative planner (prompt template generation)
- Triage queue with deduplication
- Monte Carlo evaluation framework (13 strategies, 200 trials)
- Factor ablation analysis
- Pareto-layered ranking
- Golden pipeline (21 deterministic gates)
- Zero runtime dependencies (stdlib only)
