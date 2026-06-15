"""T4 (WO-BLAST-RADIUS-GATE): session-regression proof.

main went red for 11 consecutive merges this milestone. Three of them —
#347, #353, #354 — are the canonical cases the gate must catch BEFORE merge,
not in the post-merge full suite. #359 has since fixed them in the live repo, so
this test reconstructs each regression's essential pre-merge state (real file,
test, and table names) in an isolated repo and asserts the gate fires.

If this test ever fails, the gate has regressed and the 11-red-merge class is
open again.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.blast_radius import evaluate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_347_353_354_would_have_been_blocked(tmp_path: Path) -> None:
    repo = tmp_path

    # --- #347: dashboard surface removed, stale frontend test still asserts ids ---
    _write(
        repo / "tests" / "unit" / "test_frontend_dashboard_telemetry_surface.py",
        "def test_dashboard_contains_telemetry_surface_containers():\n"
        "    html = open('dashboard.html').read()\n"
        "    assert 'id=\"shared-intelligence-section\"' in html\n",
    )
    # --- #353: handoff writer signature gained a param; authority test un-updated ---
    _write(
        repo / "tests" / "unit" / "test_wo_hs2_handoff_authority.py",
        "from unittest.mock import patch\n\n"
        "def test_handle_handoff_calls_write_packet_to_db():\n"
        "    with patch('control.context.monitor._write_handoff_packet_to_db') as m:\n"
        "        m.assert_called_once_with('sess-001', tmp_path)\n",
    )
    # --- #354: old owner of token_usage_records still writes it ---
    _write(
        repo / "core" / "telemetry" / "execution_spine.py",
        "def record_tokens():\n"
        "    conn.execute(\n"
        '        "INSERT INTO token_usage_records (token_usage_id) VALUES (?)", (tid,)\n'
        "    )\n",
    )

    # The combined merge diff for all three PRs.
    diff = (
        # #347 — dashboard.html removes the shared-intelligence section id
        "diff --git a/projections/frontend/dashboard.html b/projections/frontend/dashboard.html\n"
        "--- a/projections/frontend/dashboard.html\n"
        "+++ b/projections/frontend/dashboard.html\n"
        "@@ -10,3 +10,1 @@\n"
        '-      <section id="shared-intelligence-section">\n'
        '-        <ul id="shared-learning-list"></ul>\n'
        "-      </section>\n"
        "+      <!-- shared-intelligence surface removed -->\n"
        # #353 — monitor._write_handoff_packet_to_db gains handoff_path
        "diff --git a/control/context/monitor.py b/control/context/monitor.py\n"
        "--- a/control/context/monitor.py\n"
        "+++ b/control/context/monitor.py\n"
        "@@ -40,1 +40,1 @@\n"
        "-def _write_handoff_packet_to_db(session_id, cwd):\n"
        "+def _write_handoff_packet_to_db(session_id, cwd, handoff_path=None):\n"
        # #354 — token_projection.py adds a write to token_usage_records
        "diff --git a/core/projections/token_projection.py b/core/projections/token_projection.py\n"
        "--- a/core/projections/token_projection.py\n"
        "+++ b/core/projections/token_projection.py\n"
        "@@ -1,1 +1,3 @@\n"
        '+        conn.execute("INSERT INTO token_usage_records (token_usage_id) VALUES (?)", (e,))\n'
    )

    report = evaluate(
        diff,
        [
            "projections/frontend/dashboard.html",
            "control/context/monitor.py",
            "core/projections/token_projection.py",
        ],
        repo_root=repo,
    )

    assert report["status"] == "fail", f"gate must block; got {report['status']}"

    by_detector: dict[str, list[dict]] = {}
    for f in report["findings"]:
        by_detector.setdefault(f["detector"], []).append(f)

    # #347 — the stale frontend test is flagged for the removed id.
    assert any(
        f["path"] == "tests/unit/test_frontend_dashboard_telemetry_surface.py"
        and f["symbol"] == "shared-intelligence-section"
        for f in by_detector.get("stale_removed_symbol_test", [])
    ), f"#347 stale frontend test not caught: {report['findings']}"

    # #353 — the handoff authority test referencing the changed signature is flagged.
    assert any(
        f["path"] == "tests/unit/test_wo_hs2_handoff_authority.py"
        and f["symbol"] == "_write_handoff_packet_to_db"
        for f in by_detector.get("changed_signature_caller", [])
    ), f"#353 handoff signature caller not caught: {report['findings']}"

    # #354 — the token_usage_records ownership violation is flagged.
    assert any(
        f["symbol"] == "token_usage_records" and "core/telemetry/execution_spine.py" in f["message"]
        for f in by_detector.get("unowned_table_write", [])
    ), f"#354 token_projection ownership violation not caught: {report['findings']}"
