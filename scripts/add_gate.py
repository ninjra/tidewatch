#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Add a gate to the pipeline registry.

Usage:
    python3 scripts/add_gate.py \\
        --id "new_check_name" \\
        --type regex_present \\
        --file paper/tidewatch.tex \\
        --pattern "some pattern" \\
        --description "What this checks" \\
        --origin "2026-03-22: why this gate was added"

    python3 scripts/add_gate.py \\
        --id "dep_check" \\
        --type toml_empty \\
        --file pyproject.toml \\
        --toml-path project.dependencies \\
        --description "No runtime deps"

Gate types: regex_present, regex_absent, regex_consistent,
            count_drift, toml_equals, toml_empty, command_passes

Any constellation tool can call this script to evolve the pipeline.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a gate to the pipeline registry")
    parser.add_argument("--id", required=True, help="Unique gate identifier")
    parser.add_argument("--type", required=True, dest="gate_type",
                        choices=["regex_present", "regex_absent", "regex_consistent",
                                 "count_drift", "toml_equals", "toml_empty", "command_passes"],
                        help="Gate assertion type")
    parser.add_argument("--file", required=True, help="File to check (relative to repo root)")
    parser.add_argument("--pattern", help="Regex pattern (for regex_* and count_drift types)")
    parser.add_argument("--scope", default="full",
                        choices=["full", "abstract", "intro", "discussion", "conclusion"],
                        help="Scope within file (default: full)")
    parser.add_argument("--description", required=True, help="What this gate checks")
    parser.add_argument("--origin", help="Why this gate was added (incident reference)")
    parser.add_argument("--toml-path", help="TOML dotted path (for toml_* types)")
    parser.add_argument("--command", help="Shell command (for count_drift, command_passes)")
    parser.add_argument("--tolerance", type=float, help="Drift tolerance (for count_drift)")
    parser.add_argument("--expected", help="Expected value (for toml_equals)")
    parser.add_argument("--expected-from", help="Python attr path for expected value (for toml_equals)")

    args = parser.parse_args()

    registry = Path(__file__).parent.parent / "gates" / "registry.yaml"
    if not registry.exists():
        print(f"ERROR: Registry not found at {registry}", file=sys.stderr)
        sys.exit(1)

    # Check for duplicate ID
    existing = registry.read_text()
    if f"id: {args.id}" in existing:
        print(f"ERROR: Gate '{args.id}' already exists in registry", file=sys.stderr)
        sys.exit(1)

    # Build gate YAML block
    origin = args.origin or f"{datetime.now(UTC).strftime('%Y-%m-%d')}: added via add_gate.py"
    lines = [
        "",
        f"  - id: {args.id}",
        f"    type: {args.gate_type}",
        f"    file: {args.file}",
    ]

    if args.scope and args.scope != "full":
        lines.append(f"    scope: {args.scope}")
    if args.pattern:
        lines.append(f'    pattern: {_quote(args.pattern)}')
    if args.toml_path:
        lines.append(f"    toml_path: {args.toml_path}")
    if args.command:
        lines.append(f'    command: {_quote(args.command)}')
    if args.tolerance is not None:
        lines.append(f"    tolerance: {args.tolerance}")
    if args.expected:
        lines.append(f'    expected: {_quote(args.expected)}')
    if args.expected_from:
        lines.append(f'    expected_from: {_quote(args.expected_from)}')

    lines.append(f'    description: {_quote(args.description)}')
    lines.append(f'    origin: {_quote(origin)}')

    # Append to registry
    with open(registry, "a") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Gate '{args.id}' added to {registry}")


def _quote(s: str) -> str:
    """Quote a YAML string value if it contains special characters."""
    if any(c in s for c in ":#[]{}|>&*!%@`"):
        return f'"{s}"'
    return f'"{s}"'


if __name__ == "__main__":
    main()
