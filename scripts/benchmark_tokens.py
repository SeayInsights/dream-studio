#!/usr/bin/env python3
"""Compute per-category token overhead from the session token log.

Usage:
    py scripts/benchmark_tokens.py --run-label <label>
    py scripts/benchmark_tokens.py --run-label <label> --publish

Reads ~/.dream-studio/meta/token-log.md, groups rows by run label (session name
prefix), computes per-category overhead estimates, and writes a benchmark report
to ~/.dream-studio/meta/token-benchmark.md.

With --publish, copies the report to docs/token-overhead.md in the repo.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from lib import paths  # noqa: E402

BYTES_PER_TOKEN = 4  # rough estimate: 4 bytes ≈ 1 token

CATEGORY_SOURCES = {
    "routing_table": "~/.claude/CLAUDE.md",
    "memories": "~/.claude/projects/{slug}/memory/MEMORY.md",
    "skills": "skills/",
}


def parse_log(log_path: Path, run_label: str) -> list[dict]:
    if not log_path.exists():
        return []
    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line or "Timestamp" in line:
            continue
        parts = [c.strip() for c in line.strip("|").split("|")]
        if len(parts) < 6:
            continue
        session = parts[1]
        if run_label and run_label.lower() not in session.lower():
            continue
        try:
            rows.append(
                {
                    "timestamp": parts[0],
                    "session": session,
                    "model": parts[2],
                    "prompt": int(parts[3] or 0),
                    "completion": int(parts[4] or 0),
                    "total": int(parts[5] or 0),
                    "hook_output_bytes": int(parts[6] if len(parts) > 6 else 0),
                    "hook_overhead_est": int(parts[7] if len(parts) > 7 else 0),
                }
            )
        except (ValueError, IndexError):
            continue
    return rows


def estimate_static_tokens(repo_root: Path) -> dict[str, int]:
    estimates: dict[str, int] = {}

    claude_md = Path("~/.claude/CLAUDE.md").expanduser()
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8", errors="ignore")
        start = text.find("Routing table")
        if start == -1:
            start = text.find("| Intent")
        section = text[start:start + 8000] if start != -1 else text[:8000]
        estimates["routing_table"] = len(section) // BYTES_PER_TOKEN
    else:
        estimates["routing_table"] = 0

    memory_glob = list(Path("~/.claude/projects").expanduser().rglob("MEMORY.md"))
    if memory_glob:
        total_mem_bytes = sum(f.stat().st_size for f in memory_glob)
        estimates["memories"] = total_mem_bytes // BYTES_PER_TOKEN
    else:
        estimates["memories"] = 0

    skills_dir = repo_root / "skills"
    if skills_dir.exists():
        total_skill_bytes = sum(f.stat().st_size for f in skills_dir.glob("*.py"))
        estimates["skills"] = total_skill_bytes // BYTES_PER_TOKEN
    else:
        estimates["skills"] = 0

    return estimates


def build_report(run_label: str, rows: list[dict], static: dict[str, int]) -> str:
    n = len(rows)
    if n == 0:
        avg_hook_bytes = 0
        avg_hook_est = 0
        avg_total = 0
    else:
        avg_hook_bytes = sum(r["hook_output_bytes"] for r in rows) // n
        avg_hook_est = sum(r["hook_overhead_est"] for r in rows) // n
        avg_total = sum(r["total"] for r in rows) // n

    hook_tokens = avg_hook_est if avg_hook_est > 0 else avg_hook_bytes // BYTES_PER_TOKEN

    categories = [
        ("hooks", hook_tokens, "on-token-log.py `hook_overhead_est`"),
        ("routing_table", static.get("routing_table", 0), "CLAUDE.md routing section"),
        ("memories", static.get("memories", 0), "MEMORY.md files"),
        ("skills", static.get("skills", 0), "skills/*.py loaded on invocation"),
    ]

    total_overhead = sum(c[1] for c in categories)
    overhead_pct = f"{(total_overhead / avg_total * 100):.1f}%" if avg_total > 0 else "n/a"

    lines = [
        "# Token Overhead Benchmark",
        "",
        f"**Run label**: `{run_label}`  ",
        f"**Sessions matched**: {n}  ",
        f"**Avg total tokens/session**: {avg_total:,}  ",
        f"**Est. overhead tokens**: {total_overhead:,} ({overhead_pct} of avg session)",
        "",
        "## Per-Category Overhead",
        "",
        "| Category | Est. Tokens | % of Overhead | Source |",
        "|---|---|---|---|",
    ]

    for name, tokens, source in categories:
        pct = f"{(tokens / total_overhead * 100):.1f}%" if total_overhead > 0 else "n/a"
        lines.append(f"| {name} | {tokens:,} | {pct} | {source} |")

    lines += [
        "",
        "## Methodology",
        "",
        "- **hooks**: avg `hook_overhead_est` from token-log.md (bytes ÷ 4 if field absent)",
        "- **routing_table**: chars in CLAUDE.md routing section ÷ 4",
        "- **memories**: total bytes across MEMORY.md files ÷ 4",
        "- **skills**: total bytes of skills/*.py ÷ 4",
        "",
        "Regenerate: `py scripts/benchmark_tokens.py --run-label <label> --publish`",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark dream-studio token overhead")
    parser.add_argument("--run-label", required=True, help="Session name substring to filter on")
    parser.add_argument(
        "--publish", action="store_true", help="Copy report to docs/token-overhead.md"
    )
    args = parser.parse_args()

    log_path = paths.meta_dir() / "token-log.md"
    rows = parse_log(log_path, args.run_label)
    if not rows:
        print(f"[benchmark] no rows matched run-label '{args.run_label}' in {log_path}")
        print("[benchmark] writing empty-baseline report")

    repo_root = Path(__file__).resolve().parents[1]
    static = estimate_static_tokens(repo_root)
    report = build_report(args.run_label, rows, static)

    out_path = paths.meta_dir() / "token-benchmark.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"[benchmark] wrote {out_path}")

    if args.publish:
        docs_path = repo_root / "docs" / "token-overhead.md"
        shutil.copy(out_path, docs_path)
        print(f"[benchmark] published to {docs_path}")


if __name__ == "__main__":
    main()
