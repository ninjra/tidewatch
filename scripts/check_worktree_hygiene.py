#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Fail a commit that leaves unstaged or untracked leftovers behind."""

from __future__ import annotations

import argparse
import subprocess
import sys


def _porcelain_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _has_unstaged_leftover(line: str) -> bool:
    if line.startswith("??"):
        return True
    if len(line) < 2:
        return False
    index_status, worktree_status = line[0], line[1]
    if index_status == "U" or worktree_status == "U":
        return True
    return worktree_status not in {" ", ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-commit", action="store_true")
    parser.parse_args(argv)

    leftovers = [line for line in _porcelain_status() if _has_unstaged_leftover(line)]
    if leftovers:
        print("worktree-hygiene: failed pre_commit_no_unstaged_leftovers", file=sys.stderr)
        for line in leftovers:
            print(line, file=sys.stderr)
        return 1
    print("worktree-hygiene: ok pre_commit_no_unstaged_leftovers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
