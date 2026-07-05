#!/usr/bin/env python3
"""Compare flake8 output against the committed Dream Studio lint baseline."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import re
import subprocess
import sys
from pathlib import Path
from collections.abc import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = REPO_ROOT / "runtime" / "config" / "release-gates" / "flake8-baseline.txt"

FINDING_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+): (?P<code>[A-Z]\d{3,4}) (?P<message>.*)$"
)


@dataclass(frozen=True)
class Flake8Finding:
    path: str
    line: int
    column: int
    code: str
    message: str

    @property
    def normalized(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"

    @property
    def identity(self) -> str:
        return f"{self.path}|{self.code}|{self.message}"


def normalize_path(raw: str) -> str:
    path = raw.strip().replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("."):
        path = path[1:]
    if path.startswith("/"):
        path = path[1:]

    maybe_path = Path(raw)
    if maybe_path.is_absolute():
        try:
            path = maybe_path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            path = maybe_path.as_posix()

    return path


def parse_finding(line: str) -> Flake8Finding | None:
    match = FINDING_RE.match(line.strip())
    if not match:
        return None
    return Flake8Finding(
        path=normalize_path(match.group("path")),
        line=int(match.group("line")),
        column=int(match.group("column")),
        code=match.group("code"),
        message=match.group("message").strip(),
    )


def normalized_findings(output: str) -> list[str]:
    findings: list[str] = []
    for line in output.splitlines():
        finding = parse_finding(line)
        if finding is not None:
            findings.append(finding.normalized)
    return sorted(findings)


def finding_identities(lines: Iterable[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for line in lines:
        finding = parse_finding(line)
        if finding is not None:
            counter[finding.identity] += 1
    return counter


def load_baseline(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def run_flake8() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return normalized_findings(result.stdout + result.stderr)


def compare_to_baseline(current: list[str], baseline: list[str]) -> dict[str, object]:
    current_counts = finding_identities(current)
    baseline_counts = finding_identities(baseline)

    new_counts = current_counts - baseline_counts
    resolved_counts = baseline_counts - current_counts

    new_findings = []
    for line in current:
        finding = parse_finding(line)
        if finding is not None and new_counts[finding.identity] > 0:
            new_findings.append(line)
            new_counts[finding.identity] -= 1

    resolved_baseline_identities = sorted(resolved_counts.elements())

    return {
        "status": "pass" if not new_findings else "fail",
        "current_findings": len(current),
        "current_finding_identities": sum(current_counts.values()),
        "baseline_findings": len(baseline),
        "baseline_finding_identities": sum(baseline_counts.values()),
        "new_findings": new_findings,
        "new_finding_count": len(new_findings),
        "resolved_baseline_identities": resolved_baseline_identities,
        "resolved_baseline_count": len(resolved_baseline_identities),
    }


def write_baseline(path: Path, findings: list[str]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Dream Studio flake8 baseline.",
        "# Existing findings are tracked debt, not release blockers unless they increase.",
        "# Regenerate with: python interfaces/cli/lint_baseline.py write-baseline",
        "",
    ]
    path.write_text("\n".join(header + findings) + "\n", encoding="utf-8")
    return {
        "status": "written",
        "baseline_path": path.relative_to(REPO_ROOT).as_posix(),
        "baseline_findings": len(findings),
        "baseline_finding_identities": sum(finding_identities(findings).values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "write-baseline"], nargs="?", default="check")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    current = run_flake8()

    if args.command == "write-baseline":
        result = write_baseline(args.baseline, current)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    baseline = load_baseline(args.baseline)
    result = compare_to_baseline(current, baseline)
    result["baseline_path"] = args.baseline.relative_to(REPO_ROOT).as_posix()
    if not args.baseline.is_file():
        result["status"] = "fail"
        result["missing_baseline"] = True
        result["new_findings"] = current
        result["new_finding_count"] = len(current)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
