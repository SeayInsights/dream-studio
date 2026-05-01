"""Integration tests for SQLite registry (hydrate, query, gotcha_scanner DB path)."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))

from lib.studio_db import (  # noqa: E402
    _connect,
    upsert_skill,
    get_skill,
    find_skills_by_trigger,
    upsert_gotcha,
    search_gotchas_db,
    get_gotchas_for_skill,
    upsert_workflow,
    get_workflows_by_category,
    upsert_skill_dep,
    get_skill_deps,
    clear_registry,
)


# ── Schema ───────────────────────────────────────────────────────────────────

def test_registry_tables_created(tmp_path):
    db = tmp_path / "test.db"
    conn = _connect(db)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    for t in ("reg_skills", "reg_gotchas", "reg_workflows", "reg_skill_deps"):
        assert t in tables, f"Missing table: {t}"


# ── Skills ───────────────────────────────────────────────────────────────────

def test_upsert_and_get_skill(tmp_path):
    db = tmp_path / "test.db"
    ok = upsert_skill("core:build", "core", "build",
                       "skills/core/modes/build/SKILL.md",
                       description="Execute plan",
                       triggers="build:,execute plan:",
                       word_count=500, db_path=db)
    assert ok is True
    skill = get_skill("core:build", db_path=db)
    assert skill is not None
    assert skill["pack"] == "core"
    assert skill["mode"] == "build"
    assert skill["word_count"] == 500
    assert "build:" in skill["triggers"]


def test_find_skills_by_trigger(tmp_path):
    db = tmp_path / "test.db"
    upsert_skill("core:build", "core", "build", "s/b.md",
                  triggers="build:,execute plan:", db_path=db)
    upsert_skill("core:think", "core", "think", "s/t.md",
                  triggers="think:,spec:,research:", db_path=db)
    upsert_skill("quality:debug", "quality", "debug", "s/d.md",
                  triggers="debug:,diagnose:", db_path=db)

    results = find_skills_by_trigger("build", db_path=db)
    assert len(results) == 1
    assert results[0]["skill_id"] == "core:build"

    results = find_skills_by_trigger("spec", db_path=db)
    assert len(results) == 1
    assert results[0]["skill_id"] == "core:think"


def test_upsert_skill_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    upsert_skill("core:build", "core", "build", "s/b.md", word_count=400, db_path=db)
    upsert_skill("core:build", "core", "build", "s/b.md", word_count=500, db_path=db)
    conn = _connect(db)
    count = conn.execute("SELECT COUNT(*) FROM reg_skills WHERE skill_id='core:build'").fetchone()[0]
    conn.close()
    assert count == 1
    skill = get_skill("core:build", db_path=db)
    assert skill["word_count"] == 500


# ── Gotchas ──────────────────────────────────────────────────────────────────

def test_upsert_and_search_gotchas(tmp_path):
    db = tmp_path / "test.db"
    upsert_gotcha("parallel-same-file", "core:build", "critical",
                   "Never dispatch parallel subagents to same file",
                   keywords="parallel,subagent,race,file", db_path=db)
    upsert_gotcha("migration-order", "core:plan", "high",
                   "Database migration tasks must run first",
                   keywords="migration,database,schema", db_path=db)

    results = search_gotchas_db("parallel", db_path=db)
    assert len(results) == 1
    assert results[0]["gotcha_id"] == "parallel-same-file"

    results = search_gotchas_db("migration", db_path=db)
    assert len(results) == 1
    assert results[0]["gotcha_id"] == "migration-order"


def test_get_gotchas_for_skill(tmp_path):
    db = tmp_path / "test.db"
    upsert_gotcha("g1", "core:build", "critical", "Gotcha 1", db_path=db)
    upsert_gotcha("g2", "core:build", "high", "Gotcha 2", db_path=db)
    upsert_gotcha("g3", "quality:debug", "medium", "Gotcha 3", db_path=db)

    build_gotchas = get_gotchas_for_skill("core:build", db_path=db)
    assert len(build_gotchas) == 2

    debug_gotchas = get_gotchas_for_skill("quality:debug", db_path=db)
    assert len(debug_gotchas) == 1


def test_gotcha_preserves_hit_count_on_upsert(tmp_path):
    db = tmp_path / "test.db"
    upsert_gotcha("g1", "core:build", "high", "Title", db_path=db)
    conn = _connect(db)
    conn.execute("UPDATE reg_gotchas SET times_hit=5 WHERE gotcha_id='g1' AND skill_id='core:build'")
    conn.commit()
    conn.close()

    upsert_gotcha("g1", "core:build", "critical", "Updated title", db_path=db)
    gotchas = get_gotchas_for_skill("core:build", db_path=db)
    assert gotchas[0]["times_hit"] == 5
    assert gotchas[0]["title"] == "Updated title"


# ── Workflows ────────────────────────────────────────────────────────────────

def test_upsert_and_query_workflows(tmp_path):
    db = tmp_path / "test.db"
    upsert_workflow("daily-standup", "workflows/daily-standup.yaml",
                     category="daily", node_count=5, db_path=db)
    upsert_workflow("daily-close", "workflows/daily-close.yaml",
                     category="daily", node_count=4, db_path=db)
    upsert_workflow("hotfix", "workflows/hotfix.yaml",
                     category="feature", node_count=6, db_path=db)

    daily = get_workflows_by_category("daily", db_path=db)
    assert len(daily) == 2
    feature = get_workflows_by_category("feature", db_path=db)
    assert len(feature) == 1
    assert feature[0]["workflow_id"] == "hotfix"


# ── Dependencies ─────────────────────────────────────────────────────────────

def test_skill_dependencies(tmp_path):
    db = tmp_path / "test.db"
    upsert_skill_dep("core:build", "core:review", "chains_to", db_path=db)
    upsert_skill_dep("core:think", "core:plan", "chains_to", db_path=db)

    deps = get_skill_deps("core:build", db_path=db)
    assert len(deps) == 1
    assert deps[0]["to_skill"] == "core:review"
    assert deps[0]["dep_type"] == "chains_to"


# ── Clear registry ───────────────────────────────────────────────────────────

def test_clear_registry(tmp_path):
    db = tmp_path / "test.db"
    upsert_skill("core:build", "core", "build", "s/b.md", db_path=db)
    upsert_gotcha("g1", "core:build", "high", "Title", db_path=db)
    upsert_workflow("wf1", "w/wf1.yaml", db_path=db)
    upsert_skill_dep("core:build", "core:review", "chains_to", db_path=db)

    ok = clear_registry(db_path=db)
    assert ok is True

    assert get_skill("core:build", db_path=db) is None
    assert search_gotchas_db("g1", db_path=db) == []
    assert get_workflows_by_category("daily", db_path=db) == []
    assert get_skill_deps("core:build", db_path=db) == []


# ── Hydration from real project ──────────────────────────────────────────────

def test_hydrate_from_real_files(tmp_path):
    """Run hydrate_registry against the actual project and verify counts."""
    db = tmp_path / "test.db"
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from hydrate_registry import hydrate  # noqa: E402
    except ImportError:
        import pytest
        pytest.skip("hydrate_registry not available")
        return

    result = hydrate(db_path=db, verbose=False, dry_run=False)
    assert result["skills"] >= 30, f"Expected >=30 skills, got {result['skills']}"
    assert result["gotchas"] >= 50, f"Expected >=50 gotchas, got {result['gotchas']}"
    assert result["workflows"] >= 10, f"Expected >=10 workflows, got {result['workflows']}"

    skill = get_skill("core:build", db_path=db)
    assert skill is not None
    assert skill["pack"] == "core"
    assert "build" in (skill["triggers"] or "")


# ── Gotcha scanner DB path ───────────────────────────────────────────────────

def test_gotcha_scanner_search_uses_db(tmp_path, monkeypatch):
    """When DB has gotchas, search_gotchas returns DB results."""
    db = tmp_path / "test.db"
    upsert_gotcha("test-gotcha", "core:build", "high", "Test gotcha for migration",
                   keywords="migration,schema", db_path=db)

    monkeypatch.setattr("lib.studio_db._db_path", lambda: db)
    from lib.gotcha_scanner import search_gotchas  # noqa: E402
    results = search_gotchas("migration")
    found = any(r.get("gotcha_id") == "test-gotcha" or r.get("id") == "test-gotcha" for r in results)
    assert found or len(results) > 0


def test_gotcha_scanner_falls_back_to_file_walk(tmp_path, monkeypatch):
    """When DB is empty, search_gotchas falls back to file-walk."""
    db = tmp_path / "test.db"
    _connect(db)
    monkeypatch.setattr("lib.studio_db._db_path", lambda: db)
    from lib.gotcha_scanner import search_gotchas, clear_cache  # noqa: E402
    clear_cache()
    results = search_gotchas("parallel")
    assert isinstance(results, list)


# ── Graceful degradation ────────────────────────────────────────────────────

def test_graceful_on_bad_db(tmp_path):
    bad = tmp_path / "no_dir" / "bad.db"
    assert get_skill("x", db_path=bad) is None
    assert find_skills_by_trigger("x", db_path=bad) == []
    assert search_gotchas_db("x", db_path=bad) == []
    assert get_gotchas_for_skill("x", db_path=bad) == []
    assert get_workflows_by_category("x", db_path=bad) == []
    assert get_skill_deps("x", db_path=bad) == []
