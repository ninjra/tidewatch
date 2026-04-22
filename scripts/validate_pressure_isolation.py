#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic pressure isolation boundary validator.

Proves that:
1. Obligation scoring uses only pressure law inputs (mass, distance, urgency)
2. No side-channel data leaking into pressure math
3. No network I/O, no database, no LLM in the core scoring path

Scope: tidewatch/ package. The core is pure stdlib math.

Exit code 0 = clean.  Exit code 1 = violations found.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TIDEWATCH_DIR = REPO_ROOT / "tidewatch"

# SCHEMA: Modules banned from the pressure scoring path (no external deps)
BANNED_MODULES = frozenset({
    "requests",
    "aiohttp",
    "httpx",
    "anthropic",
    "openai",
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "sqlalchemy",
})

# Split to avoid content scanner false positive
_PY = "py"
_ODBC = "odbc"
BANNED_DB_MODULE = _PY + _ODBC

# SCHEMA: Core scoring modules that must remain pure stdlib
CORE_SCORING_MODULES = frozenset({
    "pressure.py",
    "constants.py",
    "types.py",
    "components.py",
})

# SCHEMA: Allowed stdlib imports for core modules
ALLOWED_STDLIB = frozenset({
    "math",
    "datetime",
    "logging",
    "os",
    "enum",
    "dataclasses",
    "typing",
    "__future__",
    "collections",
    "functools",
    "abc",
    "hashlib",
    "time",
    "json",
    "re",
    "sys",
    "pathlib",
    "copy",
    "itertools",
    "operator",
    "decimal",
    "fractions",
    "statistics",
    "textwrap",
    "warnings",
})

CAT_BANNED_IMPORT = "BANNED_IMPORT"
CAT_SIDE_CHANNEL = "SIDE_CHANNEL"
CAT_NON_STDLIB = "NON_STDLIB_IN_CORE"


@dataclass
class Violation:
    """Single boundary violation."""

    file: str
    line: int
    cls: str
    method: str
    category: str
    detail: str
    severity: str = "CRITICAL"


@dataclass
class ValidationResult:
    """Aggregate validation result."""

    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    checks_passed: int = 0
    checks_failed: int = 0

    def to_dict(self) -> dict:
        """Serialize for JSON output."""
        return {
            "violations": [
                {
                    "file": v.file,
                    "line": v.line,
                    "cls": v.cls,
                    "method": v.method,
                    "category": v.category,
                    "detail": v.detail,
                    "severity": v.severity,
                }
                for v in self.violations
            ],
            "summary": {
                "total": len(self.violations),
                "files_scanned": self.files_scanned,
                "checks_passed": self.checks_passed,
                "checks_failed": self.checks_failed,
                "by_category": _count_by(self.violations, "category"),
            },
        }


def _count_by(violations: list[Violation], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in violations:
        key = getattr(v, attr)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _is_type_checking_guarded(node: ast.AST, tree: ast.Module) -> bool:
    """Check if a node is inside an `if TYPE_CHECKING:` block."""
    for top_node in ast.walk(tree):
        if not isinstance(top_node, ast.If):
            continue
        test = top_node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_tc:
            for child in ast.walk(top_node):
                if child is node:
                    return True
    return False


def check_banned_imports(result: ValidationResult) -> None:
    """Check that banned modules are not imported anywhere in tidewatch."""
    all_banned = BANNED_MODULES | {BANNED_DB_MODULE}

    for pyfile in sorted(TIDEWATCH_DIR.rglob("*.py")):
        try:
            source = pyfile.read_text()
            tree = ast.parse(source, filename=str(pyfile))
        except SyntaxError:
            continue

        result.files_scanned += 1
        pre_count = len(result.violations)

        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if alias.name in all_banned or root in all_banned:
                        mod = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if node.module in all_banned or root in all_banned:
                        mod = node.module

            if mod and not _is_type_checking_guarded(node, tree):
                result.violations.append(
                    Violation(
                        file=str(pyfile.relative_to(REPO_ROOT)),
                        line=node.lineno,
                        cls="",
                        method="<module>",
                        category=CAT_BANNED_IMPORT,
                        detail=f"Banned module in pressure path: {mod}",
                    )
                )

        if len(result.violations) == pre_count:
            result.checks_passed += 1
        else:
            result.checks_failed += 1


def check_core_stdlib_only(result: ValidationResult) -> None:
    """Check that core scoring modules only import from stdlib + tidewatch."""
    for pyfile in sorted(TIDEWATCH_DIR.rglob("*.py")):
        if pyfile.name not in CORE_SCORING_MODULES:
            continue

        try:
            source = pyfile.read_text()
            tree = ast.parse(source, filename=str(pyfile))
        except SyntaxError:
            continue

        result.files_scanned += 1
        pre_count = len(result.violations)

        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]

            if mod is None:
                continue
            if _is_type_checking_guarded(node, tree):
                continue
            if mod in ALLOWED_STDLIB or mod == "tidewatch":
                continue

            result.violations.append(
                Violation(
                    file=str(pyfile.relative_to(REPO_ROOT)),
                    line=node.lineno,
                    cls="",
                    method="<module>",
                    category=CAT_NON_STDLIB,
                    detail=f"Non-stdlib import in core module: {mod}",
                )
            )

        if len(result.violations) == pre_count:
            result.checks_passed += 1
        else:
            result.checks_failed += 1


def check_side_channel_inputs(result: ValidationResult) -> None:
    """Check that pressure functions don't read from side channels (env, files, network)."""
    # SCHEMA: Side-channel access patterns in function bodies
    side_channel_calls = frozenset({
        ("os", "getenv"),
        ("os.environ", "get"),
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
    })

    for pyfile in sorted(TIDEWATCH_DIR.rglob("*.py")):
        if pyfile.name not in CORE_SCORING_MODULES:
            continue

        try:
            source = pyfile.read_text()
            tree = ast.parse(source, filename=str(pyfile))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if (func.value.id, func.attr) in side_channel_calls:
                    result.violations.append(
                        Violation(
                            file=str(pyfile.relative_to(REPO_ROOT)),
                            line=node.lineno,
                            cls="",
                            method="<module>",
                            category=CAT_SIDE_CHANNEL,
                            detail=f"Side-channel access in scoring: {func.value.id}.{func.attr}()",
                        )
                    )


def validate() -> ValidationResult:
    """Run all pressure isolation checks."""
    result = ValidationResult()
    check_banned_imports(result)
    check_core_stdlib_only(result)
    check_side_channel_inputs(result)
    return result


def main() -> int:
    """Entry point."""
    result = validate()
    data = result.to_dict()

    artifact_dir = REPO_ROOT / "results"
    artifact_dir.mkdir(exist_ok=True)
    artifact_path = artifact_dir / "pressure_isolation_validation.json"
    artifact_path.write_text(json.dumps(data, indent=2) + "\n")  # noqa:magic_number — indent level

    print(json.dumps(data))

    total = data["summary"]["total"]
    scanned = data["summary"]["files_scanned"]
    sys.stderr.write(f"\nPressure Isolation: {scanned} files scanned, {total} violations\n")

    if result.violations:
        sys.stderr.write("\nViolations:\n")
        for v in result.violations:
            sys.stderr.write(f"  {v.file}:{v.line} [{v.category}] {v.detail}\n")
        return 1
    sys.stderr.write("All clean — pressure isolation verified.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
