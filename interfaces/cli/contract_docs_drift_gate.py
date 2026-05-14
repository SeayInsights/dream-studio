#!/usr/bin/env python3
"""Release gate for Contract Atlas and documentation freshness drift."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.shared_intelligence.contract_registry import (  # noqa: E402
    change_impact_report,
    contract_registry,
    validate_contract_registry,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Changed file path. May be supplied multiple times.",
    )
    parser.add_argument(
        "--changed-files",
        default=None,
        help="Newline, semicolon, or comma separated changed file paths.",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Optional base ref for git diff, for example origin/main.",
    )
    parser.add_argument(
        "--docs-reviewed-no-change",
        action="append",
        default=[],
        help="Domain id whose impacted docs/contracts were reviewed and need no change.",
    )
    args = parser.parse_args()

    changed_files = _changed_files(args)
    registry_errors = validate_contract_registry(contract_registry())
    report = change_impact_report(
        changed_files,
        reviewed_no_change_domains=args.docs_reviewed_no_change,
    )
    report["registry_validation_errors"] = registry_errors
    if registry_errors:
        report["status"] = "fail"
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "pass" else 1)


def _changed_files(args: argparse.Namespace) -> list[str]:
    explicit = list(args.changed_file or [])
    if args.changed_files:
        explicit.extend(_split_changed_files(args.changed_files))
    env_value = os.environ.get("DREAM_STUDIO_CHANGED_FILES")
    if env_value:
        explicit.extend(_split_changed_files(env_value))
    if explicit:
        return sorted({item for item in explicit if item})

    base_ref = args.base_ref or os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    if base_ref:
        diff = _git_changed([base_ref + "...HEAD"])
        if diff:
            return diff

    pending = _git_changed(["--cached"]) + _git_changed(["HEAD"]) + _git_untracked()
    return sorted(set(pending))


def _split_changed_files(raw: str) -> list[str]:
    normalized = raw.replace(";", "\n").replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def _git_changed(args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_untracked() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
