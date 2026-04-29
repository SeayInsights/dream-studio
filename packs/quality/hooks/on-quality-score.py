#!/usr/bin/env python3
"""Hook: on-quality-score — advisory scoring after a milestone completes.

Trigger: Stop (ordering matters in hooks.json — run before on-milestone-end).
When a milestone marker exists, scan the git diff since the milestone
started for: test coverage proxy, debug leftovers, potential secrets,
large files, and scope. Prints a summary, appends a row to
`~/.dream-studio/meta/quality-log.md`, and writes the overall score to
`~/.dream-studio/meta/quality-score.json`. Never blocks — Director
decides.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402

DEBUG_PATTERNS = [
    re.compile(r"console\.log\(", re.IGNORECASE),
    re.compile(r"print\s*\(\s*['\"]debug", re.IGNORECASE),
    re.compile(r"breakpoint\(\)"),
    re.compile(r"debugger\b"),
    re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|api[_-]?secret|auth[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}", re.IGNORECASE),
    re.compile(r"(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,}|AKIA[A-Z0-9]{16})"),
]

TEST_FILE_PATTERNS = [
    re.compile(r"test[_.]"),
    re.compile(r"[_.]test\."),
    re.compile(r"[_.]spec\."),
    re.compile(r"__tests__"),
]

LARGE_FILE_THRESHOLD = 200


def git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def changed_files(cwd: Path, since_iso: str) -> list[str]:
    files = git(["log", f"--since={since_iso}", "--name-only", "--pretty=format:"], cwd)
    if not files:
        files = git(["diff", "--name-only", "HEAD~1", "HEAD"], cwd)
    return [f for f in files.splitlines() if f.strip()]


def diff_content(cwd: Path, since_iso: str) -> str:
    diff = git(["log", f"--since={since_iso}", "-p", "--pretty=format:"], cwd)
    return diff or git(["diff", "HEAD~1", "HEAD"], cwd)


def check_tests(files: list[str]) -> tuple[str, int, str]:
    source = [f for f in files if not any(p.search(f) for p in TEST_FILE_PATTERNS)]
    test = [f for f in files if any(p.search(f) for p in TEST_FILE_PATTERNS)]
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".gd"}
    new_source = [f for f in source if Path(f).suffix in code_exts]
    if not new_source:
        return "PASS", 10, "No new source files"
    if test:
        ratio = len(test) / len(new_source)
        score = min(10, int(ratio * 10) + 5)
        return "PASS", score, f"{len(test)} test file(s) for {len(new_source)} source file(s)"
    return "FLAG", 3, f"{len(new_source)} source file(s) with no test files"


def check_debug(diff: str) -> tuple[str, int, str]:
    added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    hits = []
    for line in added:
        for p in DEBUG_PATTERNS:
            if p.search(line):
                hits.append(line[1:60].strip())
                break
    if not hits:
        return "PASS", 10, "No debug leftovers"
    if len(hits) <= 3:
        return "FLAG", 6, f"{len(hits)} debug leftover(s): {hits[0][:40]}..."
    return "FLAG", 3, f"{len(hits)} debug leftovers found"


def check_secrets(diff: str) -> tuple[str, int, str]:
    added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    hits = []
    for line in added:
        for p in SECRET_PATTERNS:
            if p.search(line):
                hits.append(line[1:40].strip() + "...")
                break
    if not hits:
        return "PASS", 10, "No secret patterns detected"
    return "FAIL", 0, f"POTENTIAL SECRETS: {len(hits)} match(es) — review before shipping"


def check_large(files: list[str], cwd: Path) -> tuple[str, int, str]:
    large = []
    for f in files:
        p = cwd / f
        if not p.exists():
            continue
        try:
            lines = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
            if lines > LARGE_FILE_THRESHOLD:
                large.append(f"{f} ({lines} lines)")
        except Exception:
            continue
    if not large:
        return "PASS", 10, f"All files under {LARGE_FILE_THRESHOLD} lines"
    if len(large) <= 2:
        return "FLAG", 7, f"{len(large)} large file(s): {large[0]}"
    return "FLAG", 4, f"{len(large)} large files — consider splitting"


def check_scope(files: list[str]) -> tuple[str, int, str]:
    count = len(files)
    if count == 0:
        return "PASS", 10, "No files changed"
    if count <= 10:
        return "PASS", 10, f"{count} files — focused scope"
    if count <= 25:
        return "FLAG", 7, f"{count} files — consider whether scope is right"
    return "FLAG", 4, f"{count} files changed — wide scope, review carefully"


def calculate_overall(results: dict[str, tuple[str, int, str]]) -> tuple[float, str]:
    weights = {"tests": 2, "debug": 1, "secrets": 3, "large_files": 1, "scope": 1}
    total = sum(weights.values())
    score = sum(results[k][1] * weights.get(k, 1) for k in results) / total
    if score >= 8:
        label = "ship-ready"
    elif score >= 6:
        label = "shippable with caveats"
    else:
        label = "review before shipping"
    return round(score, 1), label


def main() -> None:
    marker_path = paths.state_dir() / "milestone-active.txt"
    if not marker_path.exists():
        return

    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        return

    command = marker.get("command", "unknown")
    started_at = marker.get("started_at", "")
    if not started_at:
        return

    cwd = paths.project_root()
    files = changed_files(cwd, started_at)
    if not files:
        return
    diff = diff_content(cwd, started_at)

    results = {
        "tests": check_tests(files),
        "debug": check_debug(diff),
        "secrets": check_secrets(diff),
        "large_files": check_large(files, cwd),
        "scope": check_scope(files),
    }

    overall_score, label = calculate_overall(results)
    timestamp = datetime.now(timezone.utc).isoformat()

    print(f"\n[dream-studio] QUALITY SCORE — {command[:50]}", flush=True)
    for name, (status, score, detail) in results.items():
        print(f"  {status:4s} {name:12s} {score:2d}/10  {detail}", flush=True)
    print(f"  {'':4s} {'OVERALL':12s} {overall_score}/10  — {label}", flush=True)
    print("  Advisory only — Director decides.\n", flush=True)

    try:
        score_path = paths.meta_dir() / "quality-score.json"
        score_path.write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "command": command,
                    "overall_score": overall_score,
                    "label": label,
                    "results": {k: {"status": v[0], "score": v[1], "detail": v[2]} for k, v in results.items()},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        log_path = paths.meta_dir() / "quality-log.md"
        if not log_path.exists():
            log_path.write_text(
                "# Quality Score Log\n\n"
                "| Date | Command | Score | Label | Files | Flags |\n"
                "|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        flags = [n for n, (s, _, _) in results.items() if s != "PASS"]
        flag_str = ", ".join(flags) if flags else "none"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"| {timestamp[:10]} | {command[:40]} | {overall_score}/10 | {label} | {len(files)} | {flag_str} |\n"
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
