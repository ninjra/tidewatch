# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Gate runner — loads and executes gates from the YAML registry.

Each gate is a dict with a 'type' field that determines the assertion.
The runner is called by the golden pipeline test via parametrize.

Portable: works against any repo with a gates/registry.yaml.
Callable as CLI: python3 gates/runner.py [--repo /path/to/repo]

Stdlib only — no runtime dependencies.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

# Module-level repo root — set by set_repo_root() or defaults to this file's repo
_REPO_ROOT: Path = Path(__file__).parent.parent


def set_repo_root(path: Path) -> None:
    """Set the repo root for path resolution. Used for cross-repo validation."""
    global _REPO_ROOT
    _REPO_ROOT = path

# ── Scope extraction ─────────────────────────────────────────────────────────

_SCOPE_PATTERNS: dict[str, tuple[str, str]] = {
    "abstract": (r"\\begin\{abstract\}", r"\\end\{abstract\}"),
    "intro": (r"\\section\{Introduction\}", r"\\section\{"),
    "discussion": (r"\\section\{Discussion\}", r"\\section\{"),
    "conclusion": (r"\\section\{Conclusion\}", r"\\(?:section|bibliography)\{"),
}


def _extract_scope(text: str, scope: str) -> str:
    """Extract text between scope markers."""
    if scope == "full" or scope not in _SCOPE_PATTERNS:
        return text
    start_pat, end_pat = _SCOPE_PATTERNS[scope]
    start_match = re.search(start_pat, text)
    if start_match is None:
        return ""
    remaining = text[start_match.end():]
    end_match = re.search(end_pat, remaining)
    if end_match is None:
        return remaining
    return remaining[:end_match.start()]


# ── Gate registry loading ────────────────────────────────────────────────────

def load_gates(
    registry_path: Path | None = None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load gates from the YAML registry file.

    Args:
        registry_path: Path to registry.yaml. Default: gates/registry.yaml
            relative to repo_root.
        repo_root: Repository root for path resolution. When set, also
            updates the module-level _REPO_ROOT for gate execution.

    Uses a minimal YAML subset parser (no PyYAML dependency) for simple
    key-value and list structures. Falls back to PyYAML if available.
    """
    if repo_root is not None:
        set_repo_root(repo_root)
    if registry_path is None:
        registry_path = _REPO_ROOT / "gates" / "registry.yaml"
    if not registry_path.exists():
        return []

    text = registry_path.read_text()

    # Try PyYAML first (available in dev environments)
    try:
        import yaml
        data = yaml.safe_load(text)
        return data.get("gates", []) if data else []
    except ImportError:
        pass

    # Minimal fallback: parse the YAML subset we use
    return _parse_gates_minimal(text)


def _parse_gates_minimal(text: str) -> list[dict[str, Any]]:
    """Parse the gate registry YAML without PyYAML.

    Handles the specific subset used in registry.yaml:
    - Top-level 'gates:' key with list of dicts
    - String values (quoted or unquoted)
    - Numeric values (float)
    - List values [a, b]
    """
    gates: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_gates = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "gates:":
            in_gates = True
            continue

        if not in_gates:
            continue

        # New gate entry
        if stripped.startswith("- id:"):
            if current is not None:
                gates.append(current)
            current = {"id": stripped[5:].strip().strip('"').strip("'")}
            continue

        # Key-value within current gate
        if current is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            # Handle list values [a, b]
            if val.startswith("[") and val.endswith("]"):
                items = val[1:-1].split(",")
                val = [item.strip().strip('"').strip("'") for item in items]
                # Try to convert to numbers
                import contextlib
                with contextlib.suppress(ValueError, TypeError):
                    val = [int(x) if x.isdigit() else float(x) for x in val]
            else:
                # Try numeric
                try:
                    val = float(val)
                    if val == int(val):
                        val = int(val)
                except ValueError:
                    pass

            current[key] = val

    if current is not None:
        gates.append(current)

    return gates


# ── Gate execution ───────────────────────────────────────────────────────────

def _resolve_path(file_path: str) -> Path:
    """Resolve a gate file path relative to repo root."""
    return _REPO_ROOT / file_path


def run_gate(gate: dict[str, Any]) -> tuple[bool, str]:
    """Execute a single gate assertion.

    Returns:
        (passed: bool, message: str)
    """
    gate_type = gate.get("type", "")
    try:
        if gate_type == "regex_present":
            return _gate_regex_present(gate)
        elif gate_type == "regex_absent":
            return _gate_regex_absent(gate)
        elif gate_type == "regex_consistent":
            return _gate_regex_consistent(gate)
        elif gate_type == "count_drift":
            return _gate_count_drift(gate)
        elif gate_type == "toml_equals":
            return _gate_toml_equals(gate)
        elif gate_type == "toml_empty":
            return _gate_toml_empty(gate)
        elif gate_type == "command_passes":
            return _gate_command_passes(gate)
        else:
            return False, f"Unknown gate type: {gate_type}"
    except Exception as e:
        return False, f"Gate {gate.get('id', '?')} raised: {e}"


def _gate_regex_present(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"
    text = path.read_text()
    scope = gate.get("scope", "full")
    scoped = _extract_scope(text, scope)
    if not scoped:
        return False, f"Scope '{scope}' not found in {gate['file']}"
    pattern = gate["pattern"]
    if re.search(pattern, scoped):
        return True, "Pattern found"
    return False, f"Pattern {pattern!r} not found in {gate['file']} scope={scope}"


def _gate_regex_absent(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"
    text = path.read_text()
    scope = gate.get("scope", "full")
    scoped = _extract_scope(text, scope)
    pattern = gate["pattern"]
    if re.search(pattern, scoped):
        return False, f"Pattern {pattern!r} found in {gate['file']} scope={scope} (should be absent)"
    return True, "Pattern correctly absent"


def _gate_regex_consistent(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"
    text = path.read_text()
    scope = gate.get("scope", "full")
    scoped = _extract_scope(text, scope)
    pattern = gate["pattern"]
    matches = re.findall(pattern, scoped)
    if not matches:
        return False, f"No matches for {pattern!r} in {gate['file']}"
    if len(set(matches)) > 1:
        return False, f"Inconsistent values: {matches}"
    return True, f"All {len(matches)} matches consistent: {matches[0]}"


def _gate_count_drift(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"
    text = path.read_text()
    pattern = gate["pattern"]
    tolerance = gate.get("tolerance", 0.10)

    # Extract claimed value from file
    match = re.search(pattern, text)
    if match is None:
        return False, f"Pattern {pattern!r} not found in {gate['file']}"

    # Handle multi-group patterns (e.g., "2{,}378" → groups 1,2 → "2378")
    groups = gate.get("pattern_groups")
    claimed = int("".join(match.group(g) for g in groups)) if groups else int(match.group(1))

    # Get actual value from command
    command = gate.get("command", "")
    if not command:
        return False, "No command specified for count_drift gate"

    result = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        cwd=str(_REPO_ROOT), timeout=60,
    )
    actual_str = result.stdout.strip()
    try:
        actual = int(actual_str)
    except ValueError:
        return False, f"Command output is not an integer: {actual_str!r}"

    drift = abs(actual - claimed) / claimed if claimed > 0 else 0
    if drift > tolerance:
        return False, (
            f"Count drift {drift:.0%} exceeds {tolerance:.0%}: "
            f"paper claims {claimed}, actual is {actual}"
        )
    return True, f"Count OK: paper={claimed}, actual={actual}, drift={drift:.1%}"


def _gate_toml_equals(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"

    with open(path, "rb") as f:
        data = tomllib.load(f)

    toml_path = gate["toml_path"]
    value = data
    for key in toml_path.split("."):
        value = value[key]

    expected_from = gate.get("expected_from", "")
    if "." in expected_from:
        # Dynamic import: "module.attr" → import module, getattr(module, attr)
        import importlib
        mod_name, attr = expected_from.rsplit(".", 1)
        mod = importlib.import_module(mod_name)
        expected = getattr(mod, attr)
    else:
        expected = gate.get("expected")

    if value != expected:
        return False, f"{toml_path}={value!r} != expected {expected!r}"
    return True, f"{toml_path}={value!r} matches"


def _gate_toml_empty(gate: dict) -> tuple[bool, str]:
    path = _resolve_path(gate["file"])
    if not path.exists():
        return False, f"File not found: {path}"

    with open(path, "rb") as f:
        data = tomllib.load(f)

    toml_path = gate["toml_path"]
    value = data
    for key in toml_path.split("."):
        value = value[key]

    if value != []:
        return False, f"{toml_path}={value!r} is not empty"
    return True, f"{toml_path} is empty"


def _gate_command_passes(gate: dict) -> tuple[bool, str]:
    command = gate["command"]
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        cwd=str(_REPO_ROOT), timeout=120,
    )
    if result.returncode != 0:
        return False, f"Command failed (exit {result.returncode}): {result.stderr[:200]}"
    return True, "Command passed"


# ── CLI — run gates against any repo ─────────────────────────────────────────


def run_all(repo_root: Path | None = None) -> tuple[int, int, list[str]]:
    """Run all gates for a repo. Returns (passed, failed, failure_messages)."""
    gates = load_gates(repo_root=repo_root)
    if not gates:
        return 0, 0, ["No gates found in registry"]

    passed = 0
    failed = 0
    failures: list[str] = []
    for gate in gates:
        ok, msg = run_gate(gate)
        if ok:
            passed += 1
        else:
            failed += 1
            failures.append(f"  FAIL {gate.get('id', '?')}: {msg}")
    return passed, failed, failures


def main() -> None:
    """CLI entry point: run gates against a repo."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Run pipeline gates against a repo",
        epilog="Any repo with a gates/registry.yaml can be validated.",
    )
    parser.add_argument(
        "--repo", type=Path, default=None,
        help="Repository root (default: this file's repo)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print failures",
    )
    args = parser.parse_args()

    repo = args.repo or _REPO_ROOT
    if not (repo / "gates" / "registry.yaml").exists():
        print(f"No gates/registry.yaml in {repo}")
        sys.exit(0)

    gates = load_gates(repo_root=repo)
    passed = 0
    failed = 0
    for gate in gates:
        ok, msg = run_gate(gate)
        if ok:
            passed += 1
            if not args.quiet:
                print(f"  PASS {gate.get('id', '?')}")
        else:
            failed += 1
            print(f"  FAIL {gate.get('id', '?')}: {msg}")

    total = passed + failed
    print(f"\n{passed}/{total} gates passed in {repo.name}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
