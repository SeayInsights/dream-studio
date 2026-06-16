"""T2 (WO-BLAST-RADIUS-GATE): nothing-left-hanging detectors.

Each test models one of the three regressions that broke main this milestone and
asserts the matching detector flags it, with a negative control proving the
detector does not fire on an unrelated change.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.hanging_detectors import (
    detect_changed_signature_callers,
    detect_stale_removed_symbol_tests,
    detect_unowned_table_writes,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_detects_stale_removed_symbol_test(tmp_path: Path) -> None:
    """#347 class: a test asserts an HTML id the diff removed and did not re-add."""
    repo = tmp_path
    # Stale test still asserting the removed id.
    _write(
        repo / "tests" / "unit" / "test_dash_surface.py",
        "def test_surface():\n"
        "    html = open('dashboard.html').read()\n"
        "    assert 'id=\"shared-intel-section\"' in html\n",
    )
    # Unrelated test — must NOT be flagged.
    _write(
        repo / "tests" / "unit" / "test_other.py",
        "def test_other():\n    assert 'still-present-widget' is not None\n",
    )
    diff = (
        "diff --git a/projections/frontend/dashboard.html b/projections/frontend/dashboard.html\n"
        "--- a/projections/frontend/dashboard.html\n"
        "+++ b/projections/frontend/dashboard.html\n"
        "@@ -1,2 +1,2 @@\n"
        '-      <section id="shared-intel-section">old</section>\n'
        "+      <section>new</section>\n"
    )

    findings = detect_stale_removed_symbol_tests(diff, repo_root=repo)
    flagged = {(f["path"], f["symbol"]) for f in findings}
    assert (
        "tests/unit/test_dash_surface.py",
        "shared-intel-section",
    ) in flagged, f"stale removed-symbol test not flagged; got {flagged}"
    assert all(
        f["path"] != "tests/unit/test_other.py" for f in findings
    ), "unrelated test must not be flagged"


def test_detects_changed_signature_caller(tmp_path: Path) -> None:
    """#353 class: a function gains a parameter; an un-updated caller still references it."""
    repo = tmp_path
    # Caller outside the diff that still references the function.
    _write(
        repo / "tests" / "unit" / "test_handoff_authority.py",
        "from unittest.mock import patch\n\n"
        "def test_calls_writer():\n"
        "    with patch('control.context.monitor._write_handoff_packet_to_db') as m:\n"
        "        _write_handoff_packet_to_db('sess-001', tmp_path)\n"
        "        m.assert_called_once_with('sess-001', tmp_path)\n",
    )
    # Unrelated module referencing a different, unchanged function.
    _write(
        repo / "core" / "unrelated.py",
        "def caller():\n    return some_other_function(1)\n",
    )
    diff = (
        "diff --git a/control/context/monitor.py b/control/context/monitor.py\n"
        "--- a/control/context/monitor.py\n"
        "+++ b/control/context/monitor.py\n"
        "@@ -10,1 +10,1 @@\n"
        "-def _write_handoff_packet_to_db(session_id, cwd):\n"
        "+def _write_handoff_packet_to_db(session_id, cwd, handoff_path=None):\n"
    )

    findings = detect_changed_signature_callers(diff, repo_root=repo)
    flagged = {f["path"] for f in findings}
    assert (
        "tests/unit/test_handoff_authority.py" in flagged
    ), f"un-updated caller of changed signature not flagged; got {flagged}"
    assert "core/unrelated.py" not in flagged, "unrelated module must not be flagged"


def test_detects_unowned_table_write(tmp_path: Path) -> None:
    """#354 class: the diff adds a write to a table another unchanged module also writes."""
    repo = tmp_path
    # Pre-existing writer of token_usage_records (the old owner).
    _write(
        repo / "core" / "telemetry" / "execution_spine.py",
        "def record():\n" '    conn.execute("INSERT INTO token_usage_records (id) VALUES (1)")\n',
    )
    # A table written only by the changed file (control — must NOT be flagged).
    _write(
        repo / "core" / "telemetry" / "lonely.py",
        "def noop():\n    return None\n",
    )
    diff = (
        "diff --git a/core/projections/token_projection.py b/core/projections/token_projection.py\n"
        "--- a/core/projections/token_projection.py\n"
        "+++ b/core/projections/token_projection.py\n"
        "@@ -1,1 +1,3 @@\n"
        '+    conn.execute("INSERT INTO token_usage_records (id) VALUES (2)")\n'
        '+    conn.execute("INSERT INTO sole_owner_table (id) VALUES (3)")\n'
    )

    findings = detect_unowned_table_writes(diff, repo_root=repo)
    by_symbol = {f["symbol"]: f for f in findings}
    assert (
        "token_usage_records" in by_symbol
    ), f"duplicate-writer table not flagged; got {list(by_symbol)}"
    assert (
        "core/telemetry/execution_spine.py" in by_symbol["token_usage_records"]["message"]
    ), "finding should name the conflicting writer"
    assert "sole_owner_table" not in by_symbol, "a table with a single writer must not be flagged"
