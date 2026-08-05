"""Native verified-secret scanner (R4 T2) — no external dependency.

TruffleHog-style scanners run two ways: broad regex (noisy) and *verified* (call the
provider to confirm the secret is live). Live verification means network calls to AWS /
GitHub / Stripe / … from CI — rate-limited, flaky, and a data-exfil surface. Dream Studio
owns everything (no bolt-on deps), so this scanner reaches "verified-grade" a different
way: it matches only **structurally self-verifying, high-entropy credential formats**
(``AKIA…`` + 16, ``ghp_`` + 36, PEM ``PRIVATE KEY`` blocks, ``sk_live_…``, …). Those
prefixes/lengths/charsets are near-zero false-positive without any network call — a match
is a real credential shape, not a guess — so the scanner blocks with high confidence and
no provider round-trip.

Scope vs the atlas-leak gate: **no overlap.** ``atlas-leak``
(interfaces/cli/contract_atlas_lifecycle_gate.py) is the Contract Atlas *lifecycle* gate —
it detects PRD/contract text leaking into unauthorized projection surfaces, an
authority-integrity check. It does not scan for credentials or read git history. Secret
scanning was genuinely missing; this adds it.

``find_secrets`` is pure (text in, findings out) and unit-tested. ``main`` scans the
tracked working tree by default (fast — a secret currently in the repo); ``--history``
scans every added line across ``git log --all`` so a secret that was committed and later
deleted is still caught. The scheduled CI baseline runs ``--history``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from core.gates.credential_patterns import (
    CREDENTIAL_PATTERNS as _PATTERNS,
    SCANNER_EXCLUDED_PATH_SUBSTRINGS as _EXCLUDED_PATH_SUBSTRINGS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Patterns and the scan-exclusion policy come from the single source (WO ed3aa5db):
# core/gates/credential_patterns.py — shared with repo_publication_readiness and the
# generated-code linter so credential detection cannot drift across surfaces.

# A line carrying this pragma is skipped — the escape hatch for an unavoidable literal.
_ALLOWLIST_PRAGMA = "allowlist secret"


def _excluded(source: str) -> bool:
    return any(sub in source.replace("\\", "/") for sub in _EXCLUDED_PATH_SUBSTRINGS)


def _redact(match: str) -> str:
    """Show only enough to locate the finding — never the full credential."""
    first = match.splitlines()[0]
    return (first[:6] + f"…[{len(first)} chars]") if len(first) > 10 else "…"


def find_secrets(text: str, source: str = "") -> list[dict[str, str]]:
    """Return one finding per high-confidence credential match in ``text`` (redacted).

    Scanned line-by-line so an inline ``allowlist secret`` pragma can waive a line.
    """
    if _excluded(source):
        return []
    findings: list[dict[str, str]] = []
    for line in text.splitlines():
        if _ALLOWLIST_PRAGMA in line:
            continue
        for rule, pattern in _PATTERNS.items():
            for match in pattern.finditer(line):
                findings.append({"rule": rule, "match": _redact(match.group(0)), "source": source})
    return findings


class SecretScanError(RuntimeError):
    """The scan could not run (git missing, timed out, or errored). A security gate MUST
    fail CLOSED on this — never treat "could not scan" as "no credentials found"."""


def _git(args: list[str]) -> str:
    """Run a git command and return stdout. Raises SecretScanError on any failure so the
    gate fails loud, instead of returning "" and reporting a false all-clear."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            encoding="utf-8",
            errors="ignore",
            cwd=REPO_ROOT,
            timeout=300,
        )
    except Exception as exc:  # missing git / timeout / OSError
        raise SecretScanError(f"git {' '.join(args[:2])} could not run: {exc}") from exc
    if result.returncode != 0:
        raise SecretScanError(
            f"git {' '.join(args[:2])} exited {result.returncode}: "
            f"{(result.stderr or '').strip()[:200]}"
        )
    return result.stdout or ""


def scan_history() -> list[dict[str, str]]:
    """Scan every added (+) line across all of git history for credentials."""
    diff = _git(["log", "--all", "--no-color", "-p", "-U0", "--format=%H"])
    findings: list[dict[str, str]] = []
    commit = ""
    path = ""
    for line in diff.splitlines():
        if re.fullmatch(r"[0-9a-f]{40}", line):
            commit = line[:12]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            if _excluded(path):
                continue
            findings.extend(find_secrets(line[1:], source=f"{path}@{commit}"))
    return findings


def scan_tree() -> list[dict[str, str]]:
    """Scan the tracked working-tree files for credentials."""
    findings: list[dict[str, str]] = []
    for rel in _git(["ls-files"]).splitlines():
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(find_secrets(text, source=rel))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        action="store_true",
        help="Scan all of git history (the scheduled deep scan); default scans the working tree",
    )
    args = parser.parse_args(argv)

    try:
        findings = scan_history() if args.history else scan_tree()
    except SecretScanError as exc:
        # Fail CLOSED: the scan could not run, so we cannot claim the repo is clean.
        print(f"::error::secret scan could not run — {exc}")
        return 2
    if not findings:
        print("secret-scan: no credentials found")
        return 0
    print(f"SECRET SCAN: {len(findings)} high-confidence credential(s) found")
    for f in findings[:50]:
        print(f"  [{f['rule']}] {f['match']}  ({f['source']})")
    print("Rotate the credential and purge it from history (git filter-repo / BFG).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
