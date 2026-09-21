"""Gate: nothing ships that should not leave this machine.

REVIEW LANE ``docs-style-and-attribution`` (canonical/review_lanes.yml).

WHAT THIS AGGREGATES. The lane asked for aggregation rather than new detection, in its
own words:

    measurement: "Every one of these is mechanically checkable and Dream Studio already
    gates most of them -- operator_absolute_path, docs-drift and the atlas-leak gate -- so
    the detector here is aggregation rather than new detection."

    why: "The constituent checks exist as separate gates already; what is missing is one
    lane that names them as a family so a new member is added here rather than invented
    somewhere else."

So the private-content half is not reimplemented here. It calls
``core.release.repo_publication_readiness``, which owns ``PRIVATE_CONTENT_RULES`` --
``operator_absolute_path``, ``appdata_absolute_path``, ``dream_studio_live_backup_path`` and
the credential patterns derived from the single credential source. A second regex for the
same thing is the "second copy of a rule that must agree with the first" that the code
quality lane exists to refuse, and writing one here would have been that defect committed
inside the gate meant to catch its family.

THE ONE THING THAT WAS GENUINELY MISSING. Attribution trailers on commits are gated
nowhere. The lane's precedent records that this repo "removed five Co-Authored-By trailers
from main on 2026-09-10 for exactly this reason" -- removed by hand, with nothing preventing
the sixth. That check is new here because nothing else owns it; everything else is a call.

WHY DIFF-SCOPED FOR CONTENT. ``build_repo_publication_readiness`` scans the whole tracked
tree, which is right for a pre-publication gate and wrong for a review lane: a standing
backlog in long-lived docs would make this a wall on day one and get it switched off. The
public API takes ``tracked_files``, so the same rules run against the change set only -- the
ratchet ``normative-baseline`` and ``untested-fallback`` already use. History and
ignored-status scanning are skipped for the same reason; the publication gate owns those.

WHAT IT DEFERS, so a reader knows it is uncovered rather than clean:

* AN ENTRY-POINT LINK THAT 404s. Needs the network. A seat is handed ``git``, ``grep`` and
  ``pytest``, so this clause cannot be answered from a worktree and stays with the reader.
* A section missing from SECURITY.md, where the lane says one is required. By whom? This repo declares no
  section list, and a first cut that assumed GitHub's template failed this repo's own
  SECURITY.md -- which has "Reporting a Vulnerability" and "Scope" and is fine. Encoding one
  template's headings as a universal requirement is the "verifying the caps a guard
  DECLARES" shape this bench exists to refuse. Convert when a list is declared somewhere.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Trailers and advertisements that must not reach a commit message. The rule is written
#: down in CONTRIBUTING; this is the first thing that enforces it.
_ATTRIBUTION = re.compile(
    r"(?im)^\s*(?:co-authored-by:\s*(?:claude|chatgpt|gpt-|copilot|gemini|cursor|codex)"
    r"|(?:\N{ROBOT FACE}\s*)?generated with\s*\[?(?:claude|chatgpt|copilot|cursor|codex))",
)


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _merge_base(root: Path) -> str:
    for base in ("origin/main", "main", "origin/master", "master"):
        out = _git(root, "merge-base", "HEAD", base).strip()
        if out:
            return out
    return ""


def _changed_files(root: Path, base: str) -> list[str]:
    if not base:
        return []
    out = _git(root, "diff", "--name-only", "--diff-filter=d", f"{base}...HEAD")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _attribution_offenders(root: Path, base: str) -> list[dict]:
    """The one check this gate owns outright, because nothing else does."""
    if not base:
        return []
    log = _git(root, "log", "--format=%H%x00%s%x00%b%x1e", f"{base}..HEAD")
    offenders = []
    for record in log.split("\x1e"):
        if not record.strip():
            continue
        parts = record.strip().split("\x00")
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0], parts[1], parts[2]
        hit = _ATTRIBUTION.search(body) or _ATTRIBUTION.search(subject)
        if hit:
            offenders.append(
                {
                    "finding_type": "attribution_trailer",
                    "commit": sha[:12],
                    "subject": subject[:80],
                    "matched": hit.group(0).strip()[:60],
                }
            )
    return offenders


def _private_content_offenders(root: Path, changed: list[str]) -> list[dict]:
    """Delegate to the owner of PRIVATE_CONTENT_RULES, scoped to the change set."""
    if not changed:
        return []
    try:
        from core.release.repo_publication_readiness import build_repo_publication_readiness
    except ImportError:
        # The lane is portable: convened against a project that does not vendor Dream
        # Studio's release module, this half has no owner to call. Say so rather than
        # report clean, which is the compared-nothing-reported-clean shape the registry
        # exists to refuse.
        return [
            {
                "finding_type": "private_content_scan_unavailable",
                "detail": "core.release.repo_publication_readiness is not importable; the private-content half did not run",
            }
        ]
    packet = build_repo_publication_readiness(
        root,
        tracked_files=changed,
        history_paths=[],
        ignored_status={},
    )
    findings = packet.get("private_content_findings") or []
    if not findings:
        # Older packet shapes nest them; take whatever the owner reports rather than
        # assuming a key.
        findings = [
            item
            for item in (packet.get("content_findings") or [])
            if item.get("finding_type") != "secret_pattern"
        ]
    return list(findings)


def run(argv: list[str] | None = None, root: Path | None = None) -> dict:
    root = Path(root) if root else REPO_ROOT
    base = _merge_base(root)
    changed = _changed_files(root, base)
    offenders = [
        *_attribution_offenders(root, base),
        *_private_content_offenders(root, changed),
    ]
    return {
        "status": "fail" if offenders else "pass",
        "merge_base": base[:12],
        "files_checked": changed,
        "offenders": offenders,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report anything shipping that should not leave this machine (aggregates existing gates)."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Review THIS tree instead of the one this gate lives in. The round table"
            " appends it when convening against another project; without it the gate"
            " scans its own install, which would report another project's result as"
            " clean."
        ),
    )
    args = parser.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else None

    result = run(None, root)
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nshipped-artifact-hygiene: FAILED - {len(result['offenders'])} item(s) that"
            " should not ship.",
            file=sys.stderr,
        )
        return 1
    checked = result["files_checked"]
    if not checked:
        print("shipped-artifact-hygiene: OK - no file changed against the merge base.")
    else:
        print(
            f"shipped-artifact-hygiene: OK - {len(checked)} changed file(s), no attribution"
            " trailer and no private content."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
