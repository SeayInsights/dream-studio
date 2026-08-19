"""WO-CI-COMPLETENESS: self-checking gate lists + retired string fallback.

The 2026-08-18 audit found the pre-push pin-tests and pr-smoke focused lists
were hardcoded with no completeness check (a deleted file silently stops
guarding anything), and the all_tests_pass gate fell back to a hand-writable
test-results.md containing the string "PASSED".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import core.gates.test_list_completeness as tlc

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── list completeness ───────────────────────────────────────────────────────────


def test_current_lists_are_complete():
    """The repo's own gate lists must have no dead entries (self-application)."""
    assert tlc.missing_listed_files() == []


def test_lists_are_nonempty_and_parsed():
    sources = tlc.listed_test_paths()
    assert len(sources.get("pre-push.yaml", [])) >= 10, sources
    assert len(sources.get("ci.yml", [])) >= 5, sources


def test_missing_listed_file_fails(monkeypatch, capsys):
    """A listed-but-vanished test file is a dead guard — the gate blocks."""
    fake = {"pre-push.yaml": ["tests/unit/definitely_not_a_real_test_file_xyz.py"]}
    monkeypatch.setattr(tlc, "listed_test_paths", lambda: fake)
    rc = tlc.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "dead guards" in out
    assert "definitely_not_a_real_test_file_xyz.py" in out


def test_unlisted_files_are_reported_not_blocking(monkeypatch, capsys):
    """Silent truncation becomes visible: the post-merge-only count is printed."""
    rc = tlc.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "post-merge" in out


def test_impact_relevant_unlisted_names_files(monkeypatch, capsys):
    """Gap WO e3e6b5a9: the gate's printed ADVISORY names the specific unlisted
    impact-relevant file — asserted on main()'s output with the impact set
    monkeypatched (hermetic against future pre-merge list additions)."""
    fake_unlisted = "tests/unit/test_totally_unlisted_impact_target.py"
    monkeypatch.setattr(tlc, "_changed_files", lambda: (["core/some_module.py"], None))
    monkeypatch.setattr(
        "core.gates.blast_radius.compute_impact_set",
        lambda changed, repo_root=None: {"dependent_tests": [fake_unlisted]},
    )
    rc = tlc.main()
    assert rc == 0  # advisory, never blocking
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert fake_unlisted in out


def test_impact_relevant_unlisted_helper_live_graph():
    """Integration proof over the REAL dependency graph: this test file depends
    on core/gates/test_list_completeness.py, so the impact set finds it.
    Explicit empty `sources` keeps the assertion about DEPENDENCY RESOLUTION
    and immune to this file later joining a pre-merge list (gap WO 681b294e)."""
    relevant = tlc.impact_relevant_unlisted(
        ["core/gates/test_list_completeness.py"], {"pre-push.yaml": [], "ci.yml": []}
    )
    assert "tests/unit/test_testlist_completeness.py" in relevant


def test_unreadable_manifest_fails_loudly(monkeypatch, capsys, tmp_path):
    """Gap WO 681b294e (quality rule 2, error severity): a missing/renamed
    manifest previously recorded an EMPTY list — the gate reported 'all
    present' while guarding nothing. It must now fail loudly."""
    monkeypatch.setattr(tlc, "_PRE_PUSH_MANIFEST", tmp_path / "gone" / "pre-push.yaml")
    with pytest.raises(tlc.ManifestUnreadable):
        tlc.listed_test_paths()
    rc = tlc.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "unreadable" in out
    assert "cannot verify lists it cannot read" in out


def test_advisory_failure_never_breaks_the_gate(monkeypatch, capsys):
    """The blast_radius advisory is best-effort: an analysis failure or an
    undeterminable change set reports itself and exits 0 (gap WO 681b294e)."""
    monkeypatch.setattr(tlc, "_changed_files", lambda: ([], "git diff against origin/main failed"))
    assert tlc.main() == 0
    assert "ADVISORY UNAVAILABLE" in capsys.readouterr().out

    monkeypatch.setattr(tlc, "_changed_files", lambda: (["core/x.py"], None))
    monkeypatch.setattr(
        tlc,
        "impact_relevant_unlisted",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert tlc.main() == 0
    assert "boom" in capsys.readouterr().out


# ── Path B fallback retired ─────────────────────────────────────────────────────


def test_path_b_fallback_removed(tmp_path):
    """A test-results.md containing 'PASSED' never satisfies all_tests_pass —
    without executable TEST-CHECKs the gate reports UNVERIFIED explicitly."""
    from core.work_orders.close_gates import run_gate_check

    wo_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    wo_dir = tmp_path / ".planning" / "work-orders" / wo_id
    wo_dir.mkdir(parents=True)
    (wo_dir / "test-results.md").write_text("All checks PASSED\n", encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    try:
        passed, reason = run_gate_check(
            "all_tests_pass",
            planning_root=tmp_path / ".planning",
            work_order_id=wo_id,
            project_id="p",
            conn=conn,
            db_path=None,
        )
    finally:
        conn.close()
    assert passed is False
    assert "UNVERIFIED" in reason
    assert "TEST-CHECK" in reason


def test_no_surface_still_advertises_the_retired_fallback():
    """Gap WO 83acb055: the Path-B retirement must hold at the surfaces
    operators read, not only in the executing code path. Two gate-reference
    tables and run_gate_check's own docstring kept telling operators a
    test-results.md containing 'PASSED' satisfies all_tests_pass — the same
    false-reassurance class the retirement removed."""
    from core.work_orders import close_gates

    for rel in ("docs/reference/gates.md", "docs/operations/gates.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "all_tests_pass" in line and "test-results.md" in line:
                assert "retired" in line.lower(), f"{rel} still advertises the fallback: {line}"

    doc = close_gates.run_gate_check.__doc__ or ""
    assert "falls back to the legacy file-presence check" not in doc
    assert "UNVERIFIED" in doc

    # In-BODY comments too (gap WO 83acb055 re-review): a comment inside the
    # all_tests_pass branch still described the fallback as current behavior,
    # contradicting the UNVERIFIED return it sat above.
    #
    # The unit of meaning is the contiguous comment BLOCK, not the line — a
    # per-line scan false-positives on any block whose "retired" qualifier
    # wraps onto a later line.
    import inspect
    import re as _re

    src = inspect.getsource(close_gates.run_gate_check)
    branch = src.split('if gate_name == "all_tests_pass":', 1)[1].split("if gate_name ==", 1)[0]
    blocks: list[str] = []
    current: list[str] = []
    for line in branch.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            current.append(stripped.lstrip("#").strip())
        elif current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))

    for block in blocks:
        # "fall back", "falls back", and the single-word "fallback" all count.
        if _re.search(r"falls?\s*back", block, _re.IGNORECASE):
            lowered = block.lower()
            assert (
                "retired" in lowered or "no file-presence" in lowered
            ), f"all_tests_pass comment describes a fallback as current behavior: {block}"


# ── symptom visibility ──────────────────────────────────────────────────────────


def test_all_tests_pass_positive_path_with_executable_check(tmp_path):
    """The POSITIVE path the Path-B retirement left uncovered (gap WO 681b294e):
    a task carrying a passing executable TEST-CHECK satisfies all_tests_pass."""
    from core.config.sqlite_bootstrap import bootstrap_database
    from core.work_orders.close_gates import run_gate_check

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    project_id = "11111111-2222-3333-4444-555555555555"
    wo_id = "66666666-7777-8888-9999-aaaaaaaaaaaa"
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, project_path, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", str(REPO_ROOT), now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','in_progress','deployment',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
        "  status, created_at, updated_at)"
        " VALUES ('t1',?,?,'T1','do',?, 'complete', ?, ?)",
        (wo_id, project_id, 'TEST-CHECK: cmd: py -c "pass"', now, now),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(db))
    try:
        passed, reason = run_gate_check(
            "all_tests_pass",
            planning_root=tmp_path / ".planning",
            work_order_id=wo_id,
            project_id=project_id,
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert passed is True, reason


def test_symptom_check_detail_surfaces_sql_and_flags_trivial(tmp_path):
    from core.work_orders.close_gates import symptom_check_detail

    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE things (n INTEGER)")
    conn.execute("INSERT INTO things VALUES (1)")
    conn.commit()
    conn.close()

    symptom = (
        "Root cause prose here.\n"
        "SQL-CHECK: SELECT COUNT(*) FROM things\n"
        "SQL-CHECK: SELECT 1\n"
        "SQL-CHECK: SELECT COUNT(*) FROM missing_table\n"
    )
    details = symptom_check_detail(symptom, db)
    assert len(details) == 3
    real, trivial, broken = details
    assert real["passed"] is True and real["trivially_true"] is False
    assert trivial["passed"] is True and trivial["trivially_true"] is True
    assert broken["passed"] is False and "error" in broken
    # Without git evidence, diff-relatedness is undeterminable — never a false verdict.
    assert real["diff_related"] is None


def test_symptom_diff_relatedness(tmp_path, monkeypatch):
    """Gap WO ade31afb: each check reports whether the tables its SQL reads
    appear in the WO's diff — a symptom asserting only untouched tables is the
    decorative-symptom pattern."""
    from core.work_orders.close_gates import symptom_check_detail

    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE things (n INTEGER)")
    conn.execute("CREATE TABLE unrelated (n INTEGER)")
    conn.execute("INSERT INTO things VALUES (1)")
    conn.execute("INSERT INTO unrelated VALUES (1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "core.work_orders.verify_git._collect_git_commits",
        lambda root, wo_id, title=None: "=== commit abc ===\n+INSERT INTO things ...\n",
    )
    symptom = (
        "SQL-CHECK: SELECT COUNT(*) FROM things\n"
        "SQL-CHECK: SELECT COUNT(*) FROM unrelated\n"
        "SQL-CHECK: SELECT 1\n"
    )
    details = symptom_check_detail(
        symptom, db, work_order_id="wo-x", project_root=tmp_path, title="T"
    )
    related, decorative, trivial = details
    assert related["diff_related"] is True
    assert decorative["diff_related"] is False  # tables untouched by the diff
    assert trivial["diff_related"] is None and trivial["trivially_true"] is True


def test_diff_relatedness_uses_word_boundaries(tmp_path, monkeypatch):
    """Gap WO 681b294e: a substring match let table `things` be 'related' to a
    diff mentioning only `somethings` — false reassurance."""
    from core.work_orders.close_gates import symptom_check_detail

    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE things (n INTEGER)")
    conn.execute("INSERT INTO things VALUES (1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "core.work_orders.verify_git._collect_git_commits",
        lambda root, wo_id, title=None: "+ def count_somethings(): pass\n",
    )
    details = symptom_check_detail(
        "SQL-CHECK: SELECT COUNT(*) FROM things",
        db,
        work_order_id="wo-x",
        project_root=tmp_path,
        title="T",
    )
    assert details[0]["diff_related"] is False
