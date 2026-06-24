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


def test_stale_symbol_ignores_deleted_test_data_literals(tmp_path: Path) -> None:
    """WO d3221b4d: deleting a dead file whose fixture-like string literals coincide
    with an unchanged test's fixtures must NOT flag that test.

    A bare quoted-string literal is not a removed API symbol; only definitions and
    HTML/JS attribute ids are. Without this, large dead-code deletions flood the gate.
    """
    repo = tmp_path
    # An unchanged test that uses 'token-1' / 'sess-1' as its own fixture data.
    _write(
        repo / "tests" / "unit" / "test_ingest.py",
        "def test_ingest():\n"
        "    rows = [{'id': 'token-1'}, {'session': 'sess-1'}]\n"
        "    assert rows[0]['id'] == 'token-1'\n",
    )
    # The diff DELETES a dead non-test source file whose sample data used the same
    # literals (e.g. a removed backfill script) — they are not API symbols.
    diff = (
        "diff --git a/scripts/backfill_components.py b/scripts/backfill_components.py\n"
        "--- a/scripts/backfill_components.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-    sample = {'id': 'token-1', 'session': 'sess-1'}\n"
        "-    return sample\n"
    )

    findings = detect_stale_removed_symbol_tests(diff, repo_root=repo)
    assert not findings, f"deleted test-data literals must not flag tests; got {findings}"


def test_stale_symbol_flags_dotted_patch_target(tmp_path: Path) -> None:
    """WO d3221b4d (recall): a removed def referenced as a DOTTED string target
    (mock.patch("mod.removed_func")) is still genuinely stale and must flag —
    even though it lives inside a string literal."""
    repo = tmp_path
    _write(
        repo / "tests" / "unit" / "test_patches.py",
        "from unittest import mock\n\n"
        "def test_it():\n"
        "    with mock.patch('core.svc.removed_func') as m:\n"
        "        m.return_value = 1\n",
    )
    diff = (
        "diff --git a/core/svc.py b/core/svc.py\n"
        "--- a/core/svc.py\n"
        "+++ b/core/svc.py\n"
        "@@ -1,2 +1,1 @@\n"
        "-def removed_func():\n"
        "-    return 1\n"
        "+pass\n"
    )

    findings = detect_stale_removed_symbol_tests(diff, repo_root=repo)
    flagged = {(f["path"], f["symbol"]) for f in findings}
    assert (
        "tests/unit/test_patches.py",
        "removed_func",
    ) in flagged, f"dotted patch-target of a removed def must be flagged; got {flagged}"


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


def test_stale_symbol_ignores_words_still_in_source(tmp_path: Path) -> None:
    """WO-BLAST-FALSEPOS: a removed line's common word still present in source → NO finding.

    Removing a line containing "failures" must not flag every test mentioning "failures"
    when "failures" still exists elsewhere in non-test source (the PR #374 false positive).
    """
    repo = tmp_path
    # Non-test source still uses the word "failures".
    _write(
        repo / "core" / "svc" / "mod.py",
        "def go(result):\n    return result['failures']\n",
    )
    # A test that merely mentions "failures".
    _write(
        repo / "tests" / "unit" / "test_mentions.py",
        "def test_x():\n    assert 'failures' in {'failures': []}\n",
    )
    # Diff removes a line containing "failures" (still present in mod.py).
    diff = (
        "diff --git a/core/svc/other.py b/core/svc/other.py\n"
        "--- a/core/svc/other.py\n"
        "+++ b/core/svc/other.py\n"
        "@@ -1,2 +1,1 @@\n"
        '-    payload = {"failures": items}\n'
        "+    payload = {}\n"
    )

    findings = detect_stale_removed_symbol_tests(diff, repo_root=repo)
    assert all(
        f["symbol"] != "failures" for f in findings
    ), f"'failures' still in source must not be flagged; got {findings}"


def test_unowned_table_write_skips_authority_tables(tmp_path: Path) -> None:
    """WO-BLAST-FALSEPOS: business_* authority tables are multi-writer; not flagged.

    business_work_orders is written by many work-order mutations by design; a new
    mutation that writes it must not be flagged against the others.
    """
    repo = tmp_path
    # Another legitimate writer of the authority table (the mutation layer).
    _write(
        repo / "core" / "work_orders" / "close.py",
        'def close():\n    conn.execute("UPDATE business_work_orders SET status=? WHERE id=?", (s, i))\n',
    )
    diff = (
        "diff --git a/core/work_orders/mutations.py b/core/work_orders/mutations.py\n"
        "--- a/core/work_orders/mutations.py\n"
        "+++ b/core/work_orders/mutations.py\n"
        "@@ -1,1 +1,2 @@\n"
        '+    conn.execute("UPDATE business_work_orders SET status=? WHERE id=?", (s, i))\n'
    )

    findings = detect_unowned_table_writes(diff, repo_root=repo)
    assert all(
        f["symbol"] != "business_work_orders" for f in findings
    ), f"authority table business_work_orders must not be flagged; got {findings}"


def test_unowned_table_write_skips_migration_ddl_and_one_time_tooling(tmp_path: Path) -> None:
    """Three-store docstore move: migration DDL and one-time CLI tooling are not
    runtime writers, so a runtime owner that shares a table with them must not be
    flagged. (ds_documents move: document_store.py vs 007_*.sql + migrate_*.py.)"""
    repo = tmp_path
    # Historical migration DDL/seed — NOT a runtime writer.
    _write(
        repo / "core" / "event_store" / "migrations" / "007_document_system.sql",
        "INSERT INTO ds_documents (doc_id) VALUES (1);\n",
    )
    # One-time data-migration utility — NOT a runtime writer.
    _write(
        repo / "interfaces" / "cli" / "migrate_docstore_to_files_db.py",
        'def migrate():\n    dst.execute("INSERT INTO ds_documents (doc_id) VALUES (?)", (1,))\n',
    )
    # The diff: the legitimate sole runtime writer adds the write.
    diff = (
        "diff --git a/core/storage/document_store.py b/core/storage/document_store.py\n"
        "--- a/core/storage/document_store.py\n"
        "+++ b/core/storage/document_store.py\n"
        "@@ -1,1 +1,2 @@\n"
        '+    c.execute("INSERT INTO ds_documents (doc_type) VALUES (?)", (t,))\n'
    )
    findings = detect_unowned_table_writes(diff, repo_root=repo)
    assert all(
        f["symbol"] != "ds_documents" for f in findings
    ), f"runtime owner sharing a table only with DDL/one-time tooling must not be flagged; got {findings}"

    # And the one-time migration script itself, when it is the diffed file, must
    # not be flagged as the offending path either.
    diff_migrate = (
        "diff --git a/interfaces/cli/migrate_docstore_to_files_db.py b/interfaces/cli/migrate_docstore_to_files_db.py\n"
        "--- a/interfaces/cli/migrate_docstore_to_files_db.py\n"
        "+++ b/interfaces/cli/migrate_docstore_to_files_db.py\n"
        "@@ -1,1 +1,2 @@\n"
        '+    dst.execute("INSERT INTO ds_documents (doc_id) VALUES (?)", (1,))\n'
    )
    findings_migrate = detect_unowned_table_writes(diff_migrate, repo_root=repo)
    assert (
        findings_migrate == []
    ), f"one-time migration script must not be flagged as an unowned writer; got {findings_migrate}"
