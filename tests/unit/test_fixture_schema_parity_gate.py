"""The fixture-schema-parity gate must fail on an invented column.

Both directions are asserted, and the exemptions matter as much as the catches: a
drift-detection fixture MUST build drift, so a gate that refused it would delete the
scenario instead of protecting it.

The schema is injected in most cases so these tests do not pay for a full migration run
each time; two tests deliberately use the real bootstrapped schema, because a gate whose
authority is only ever a fixture proves the fixture.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import fixture_schema_parity as parity

# A small stand-in authority. `business_tasks` intentionally HAS `created_at` here: the
# 2026-09-05 defect was a fixture that lacked it, and omission must stay legal.
_SCHEMA = {
    "business_tasks": {"task_id", "work_order_id", "status", "created_at", "updated_at"},
    "business_projects": {"project_id", "name", "status"},
}


def _tree(tmp_path: Path, source: str, *, rel: str = "tests/unit/test_subject.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def _run(tmp_path: Path, source: str, **kw) -> dict:
    return parity.run(repo_root=_tree(tmp_path, source, **kw), schema=_SCHEMA)


def test_invented_column_fails(tmp_path):
    source = 'DDL = "CREATE TABLE business_projects (name TEXT, id TEXT, status TEXT)"\n'
    result = _run(tmp_path, source)
    assert result["status"] == "fail"
    assert result["offenders"][0]["table"] == "business_projects"
    assert result["offenders"][0]["columns"] == ["id"]


def test_omitting_columns_is_allowed(tmp_path):
    # A minimal fixture is a focused fixture. Demanding full parity would turn every
    # schema addition into a sweep of hundreds of test files for no gain.
    source = 'DDL = "CREATE TABLE business_tasks (task_id TEXT)"\n'
    assert _run(tmp_path, source)["status"] == "pass"


def test_exact_match_is_allowed(tmp_path):
    source = 'DDL = "CREATE TABLE business_projects (project_id TEXT, name TEXT, status TEXT)"\n'
    assert _run(tmp_path, source)["status"] == "pass"


def test_table_outside_the_authority_is_ignored(tmp_path):
    # `ds_files` lives in files.db. Dream Studio is a three-store model, and a table this
    # schema does not describe is not this gate's business -- dropped tables reappearing
    # are core/gates/test_fixture_resurrection_guard.py's job.
    source = 'DDL = "CREATE TABLE ds_files (whatever TEXT, invented TEXT)"\n'
    assert _run(tmp_path, source)["status"] == "pass"


def test_sql_comments_are_not_columns(tmp_path):
    # A commented column read as a column named `--`, and the words after it as more
    # columns (`so`, `or`, `session`) -- 20 phantom findings across 8 files.
    source = (
        "DDL = '''CREATE TABLE business_tasks (\n"
        "    task_id TEXT,  -- so this is the id we use for the session\n"
        "    status TEXT\n"
        ")'''\n"
    )
    assert _run(tmp_path, source)["status"] == "pass"


def test_inline_table_constraint_is_not_a_column(tmp_path):
    # `UNIQUE(a, b)` has no space before the paren, so the whole call read as a column.
    source = (
        "DDL = '''CREATE TABLE business_tasks (\n"
        "    task_id TEXT,\n"
        "    status TEXT,\n"
        "    UNIQUE(task_id, status)\n"
        ")'''\n"
    )
    assert _run(tmp_path, source)["status"] == "pass"


def test_primary_key_constraint_clause_is_not_a_column(tmp_path):
    source = (
        "DDL = '''CREATE TABLE business_tasks (\n"
        "    task_id TEXT,\n"
        "    PRIMARY KEY (task_id)\n"
        ")'''\n"
    )
    assert _run(tmp_path, source)["status"] == "pass"


def test_reasoned_exemption_is_honoured(tmp_path):
    source = (
        "# fixture-schema-parity: allow business_projects.id -- legacy shape pinned on"
        " purpose to prove the drift routes degrade correctly\n"
        'DDL = "CREATE TABLE business_projects (name TEXT, id TEXT, status TEXT)"\n'
    )
    assert _run(tmp_path, source)["status"] == "pass"


def test_exemption_without_a_real_reason_is_itself_a_finding(tmp_path):
    # Otherwise the escape hatch quietly becomes the norm, which is how a rule turns back
    # into prose.
    source = (
        "# fixture-schema-parity: allow business_projects.id -- legacy\n"
        'DDL = "CREATE TABLE business_projects (name TEXT, id TEXT, status TEXT)"\n'
    )
    result = _run(tmp_path, source)
    assert result["status"] == "fail"
    assert "states no usable reason" in result["offenders"][0]["message"]


def test_exemption_is_specific_to_one_column(tmp_path):
    # Exempting `id` must not silently cover a second invented column.
    source = (
        "# fixture-schema-parity: allow business_projects.id -- legacy shape pinned on"
        " purpose to prove the drift routes degrade correctly\n"
        'DDL = "CREATE TABLE business_projects (name TEXT, id TEXT, bogus TEXT)"\n'
    )
    result = _run(tmp_path, source)
    assert result["status"] == "fail"
    assert result["offenders"][0]["columns"] == ["bogus"]


def test_multiline_concatenated_ddl_is_seen_whole(tmp_path):
    # Nearly every fixture in this suite writes DDL as implicitly concatenated literals.
    source = (
        "conn.execute(\n"
        '    "CREATE TABLE business_projects("\n'
        '    "project_id TEXT, name TEXT, nope TEXT)"\n'
        ")\n"
    )
    result = _run(tmp_path, source)
    assert result["status"] == "fail"
    assert result["offenders"][0]["columns"] == ["nope"]


def test_canonical_schema_comes_from_the_real_migration_chain():
    schema = parity.canonical_schema()
    # Spot-check the tables enforcement actually reads, including the column whose absence
    # from one fixture caused the 2026-09-05 fail-open.
    assert "created_at" in schema["business_tasks"]
    assert "description" in schema["business_work_orders"]
    assert len(schema) > 40, "the bootstrapped schema looks empty -- authority is wrong"


def test_real_test_suite_is_clean():
    result = parity.run()
    assert result["status"] == "pass", result["offenders"]
    assert result["files_scanned"] > 300, "scan found almost nothing -- tests root is wrong"
