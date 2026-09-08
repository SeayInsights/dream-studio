"""The fail-open-probe gate must fail on the defect it was built for.

A gate no test can make FAIL is indistinguishable from a gate that checks nothing, so
every case here that expects a clean result is paired with one that expects a catch. The
last test mutates the REAL ``runtime/lib/enforcement.py`` rather than a fixture, because a
gate bound only to fixtures proves the fixtures, not the repo.

Defect of record, 2026-09-05: ``authority_write_since`` consults five independent signals
under one function-level handler that returns ``True``. Two probes had their own handler;
three did not. A query against a column absent from an older schema raised, the
function-level handler caught it, and the function reported "an authority write happened"
for every work order on the machine -- stop enforcement silently disabled while telling
the operator its condition was satisfied.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import fail_open_probe

# The historical shape: probe one unguarded, probe two guarded. The difference between
# the two is exactly what was invisible in review.
_DEFECT = """
import sqlite3


def authority_write_since(work_order_id, since):
    conn = sqlite3.connect("authority.db")
    try:
        rows = conn.execute(
            "SELECT updated_at FROM business_tasks WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchall()
        if rows:
            return True
        try:
            created = conn.execute(
                "SELECT created_at FROM business_tasks WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        except sqlite3.Error:
            created = []
        if created:
            return True
    except sqlite3.Error:
        return True
    return False
"""

# Same five-signal shape, every probe isolated. Nothing to report.
_FIXED = """
import sqlite3


def authority_write_since(work_order_id, since):
    conn = sqlite3.connect("authority.db")
    try:
        try:
            rows = conn.execute(
                "SELECT updated_at FROM business_tasks WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        if rows:
            return True
        try:
            created = conn.execute(
                "SELECT created_at FROM business_tasks WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        except sqlite3.Error:
            created = []
        if created:
            return True
    except sqlite3.Error:
        return True
    return False
"""

# One probe. The function-level handler IS that probe's handler; there is no sibling
# signal for it to answer on behalf of. This is `docstore_record_since`'s real shape and
# flagging it would be noise, not a finding.
_SINGLE_PROBE = """
import sqlite3


def docstore_record_since(name_hint, since):
    conn = sqlite3.connect("files.db")
    try:
        rows = conn.execute(
            "SELECT created_at FROM ds_files WHERE name LIKE ?",
            (name_hint,),
        ).fetchall()
    except sqlite3.Error:
        return True
    return bool(rows)
"""

# Two unguarded probes, but the handler answers in the CONSERVATIVE direction. An error
# here reports "nothing found", which blocks rather than passes -- visible, not silent.
_FAILS_CLOSED = """
import sqlite3


def latest_write(work_order_id):
    conn = sqlite3.connect("authority.db")
    try:
        a = conn.execute("SELECT 1 FROM business_tasks WHERE id = ?", (work_order_id,)).fetchall()
        b = conn.execute("SELECT 2 FROM business_work_orders WHERE id = ?", (work_order_id,)).fetchall()
        return bool(a or b)
    except sqlite3.Error:
        return False
"""


def _tree(tmp_path: Path, source: str, *, rel: str = "core/probe_site.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def test_catches_the_historical_defect(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _DEFECT))
    assert result["status"] == "fail"
    assert len(result["offenders"]) == 1
    assert result["offenders"][0]["function"] == "authority_write_since"


def test_names_the_unguarded_probe_not_the_guarded_one(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _DEFECT))
    flagged = result["offenders"][0]["line"]
    source_lines = _DEFECT.splitlines()
    # The flagged line must be the FIRST probe (the unguarded one). The guarded probe
    # assigns to `created`; naming that line instead would send the author to the one
    # site that was already correct.
    assert "rows = conn.execute(" in source_lines[flagged - 1]


def test_message_states_how_many_probes_share_the_handler(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _DEFECT))
    message = result["offenders"][0]["message"]
    assert "4 independent signals" in message
    assert "answers for all" in message


def test_passes_when_every_probe_is_isolated(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _FIXED))
    assert result["status"] == "pass", result["offenders"]


def test_single_probe_function_is_not_a_finding(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _SINGLE_PROBE))
    assert result["status"] == "pass", result["offenders"]


def test_conservative_handler_is_not_a_finding(tmp_path):
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _FAILS_CLOSED))
    assert result["status"] == "pass", result["offenders"]


def test_chained_execute_fetchall_reports_one_probe_not_two(tmp_path):
    # `conn.execute(...).fetchall()` is two ast.Call nodes on one line. Counting nodes
    # reported every probe twice, which made a 3-defect function read as 6 and an
    # operator's first instinct "the gate is broken".
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _DEFECT))
    lines = [o["line"] for o in result["offenders"]]
    assert len(lines) == len(set(lines))


def test_test_files_are_not_scanned(tmp_path):
    tree = _tree(tmp_path, _DEFECT, rel="core/test_probe_site.py")
    result = fail_open_probe.run(repo_root=tree)
    assert result["status"] == "pass"
    assert result["files_scanned"] == 0


def test_out_of_repo_path_does_not_crash_the_report(tmp_path):
    # An earlier gate crashed on `relative_to` when handed a path outside the repo.
    result = fail_open_probe.run(repo_root=_tree(tmp_path, _DEFECT))
    assert result["offenders"][0]["path"]


def test_real_repository_is_clean():
    result = fail_open_probe.run()
    assert result["status"] == "pass", result["offenders"]
    assert result["files_scanned"] > 100, "scan found almost nothing -- roots are wrong"


def test_gate_is_bound_to_the_real_enforcement_module(tmp_path):
    """Reintroducing the defect into the REAL source must make the gate fail.

    This is the whole point. `test_real_repository_is_clean` passes just as readily if the
    gate silently stopped looking at `authority_write_since`; only mutating that actual
    function proves the gate still watches it.
    """
    real = Path(fail_open_probe.REPO_ROOT) / "runtime" / "lib" / "enforcement.py"
    source = real.read_text(encoding="utf-8")
    marker = "    try:\n        # 1. A completed task"
    assert marker in source, "authority_write_since no longer has the shape this locks"
    mutated = source.replace(
        marker,
        '    try:\n        conn.execute("SELECT 1 FROM business_tasks", ())\n'
        "        # 1. A completed task",
        1,
    )
    target = tmp_path / "runtime" / "lib" / "enforcement.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")

    result = fail_open_probe.run(repo_root=tmp_path)
    assert result["status"] == "fail"
    assert {o["function"] for o in result["offenders"]} == {"authority_write_since"}
