"""WO-DEP-CVE-BUMP (7f9085e7): guard against reintroducing the broken CVE floors.

The Full CI ``security`` gate (pip-audit) flags two dev-only transitive packages:

* ``click 8.1.8`` — PYSEC-2026-2132 (fixed in 8.3.3)
* ``mcp 1.23.3`` — CVE-2026-52870 / -52869 / -59950 (fixed in 1.28.1)

**Neither can be bumped with a requirements floor.** ``semgrep`` (a dev dependency) pins
``click~=8.1.8`` (caps <8.2) and ``mcp==1.23.3`` (exact), so *any* floor forces pip to backtrack
semgrep to a source-only release with no Windows wheel ("Semgrep does not support Windows yet"),
which breaks the Windows dev install — same constraint class as the PyJWT note in
requirements.txt. The initial floor attempt did exactly that (broke PR #512), so it was reverted.

These tests fail if a floor is reintroduced, so the regression cannot recur. The pip-audit
security-gate *suppression* for these four un-bumpable CVEs is handled with the Full-CI recovery
in WO ac814dc3 (coupled with the migration release), not in this change set — keeping it off the
release_publication_gate docs surface.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _requirement_lines(rel: str) -> list[str]:
    return [
        ln.strip()
        for ln in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def test_click_not_floored_because_semgrep_caps_it() -> None:
    # A click floor in requirements.txt backtracks semgrep (dev) to a source-only build.
    for line in _requirement_lines("requirements.txt"):
        assert not line.lower().startswith("click"), line


def test_mcp_not_floored_because_semgrep_caps_it() -> None:
    for line in _requirement_lines("requirements-dev.txt"):
        assert not line.lower().startswith("mcp"), line
