"""WO-DEP-CVE-BUMP (7f9085e7): guard the transitive-CVE floor constraints.

The Full CI ``security`` gate (pip-audit) flagged ``mcp 1.23.3``
(CVE-2026-52870 / -52869 / -59950, all fixed in 1.28.1) and ``click 8.1.8``
(PYSEC-2026-2132, fixed in 8.3.3). Both are transitive (mcp via semgrep/fastmcp;
click via uvicorn/fastapi/typer/etc). Floor constraints in the requirements files
force non-vulnerable versions.

These tests fail if a floor is ever dropped, so the CVE gate cannot silently
regress. The *definitive* audit runs in Full CI on Linux — ``pip-audit`` cannot
resolve the requirements on Windows because ``semgrep`` has no Windows wheel.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _requirements(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_click_floor_past_pysec_2026_2132() -> None:
    # click 8.3.3 fixes PYSEC-2026-2132; the resolver picks the latest (>=8.4.2).
    assert "click>=8.3.3" in _requirements("requirements.txt")


def test_mcp_floor_past_cve_2026_series() -> None:
    # mcp 1.28.1 fixes CVE-2026-52870 / -52869 / -59950.
    assert "mcp>=1.28.1" in _requirements("requirements-dev.txt")
