"""A declared module boundary is stored and parsed as declared.

The filter on both sides required a boundary entry to contain ``/`` or ``.``, so a bare
top-level directory -- ``docs``, ``schemas``, ``config``, ``tests``, ``dist`` -- was dropped
silently, with nothing said to the author. Measured on the live authority: a work order
created with 15 declared paths was stored owning 12.

The consequence is not cosmetic. Edits under a dropped directory match no boundary the work
order declared, so ``in_progress_work_order`` attributes them to whichever OTHER in-progress
work orders happen to spell a covering path, and the stop hook then demands an authority
write against work orders the session never touched. The two honest responses are marking a
task done that is not done, or bypassing the hook -- the pair that function's own docstring
says it exists to avoid.

Whitespace is not the discriminator: an absolute path on this operator's machine contains a
space (``C:/Users/Dannis Seay/.codex/config.toml``), and six such entries sit on a live work
order today.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.work_orders.mutations import _is_boundary_path as producer_keeps
from core.work_orders.mutations import compose_module_boundary
from runtime.lib.enforcement import _is_boundary_path as consumer_keeps
from runtime.lib.enforcement import boundary_globs

BARE_DIRECTORIES = ["docs", "schemas", "config", "tests", "dist"]

PATHS_WITH_A_SPACE = [
    "C:/Users/Dannis Seay/.codex/config.toml",
    "C:/Users/Dannis Seay/.agents/skills",
]

NOT_PATHS = [
    "MAIN'S FULL CI HAS BEEN RED FOR SEVEN CONSECUTIVE MERGES",
    "the runner must be the sole writer",
    "",
]


def _clause(text: str) -> str:
    return "Module boundary: " + text + "."


# --- the defect itself -------------------------------------------------------------


@pytest.mark.parametrize("name", BARE_DIRECTORIES)
def test_a_bare_directory_survives_composition(name):
    composed = compose_module_boundary("Body.", f"core/gates, {name}")
    assert name in composed.split("Module boundary: ")[1]


@pytest.mark.parametrize("name", BARE_DIRECTORIES)
def test_a_bare_directory_survives_parsing(name):
    assert name in boundary_globs(_clause(f"core/gates, {name}"))


def test_a_full_declaration_round_trips_intact():
    """15 declared paths were stored as 12; nothing may be lost between the two ends."""
    declared = (
        "canonical/skills, canonical/skill_vocabulary.json, packs.yaml, schemas, "
        "core/gates, core/learning, core/event_store, core/skills, config, "
        "interfaces/cli, runtime/hooks/meta, runtime/lib, canonical/workflows, docs, "
        "STRUCTURE.md"
    )
    expected = [p.strip() for p in declared.split(",")]
    composed = compose_module_boundary("Body.", declared)
    assert boundary_globs(composed) == expected


# --- what it may not start accepting ----------------------------------------------


@pytest.mark.parametrize("prose", NOT_PATHS)
def test_prose_is_still_refused(prose):
    assert not consumer_keeps(prose)
    assert not producer_keeps(prose)


@pytest.mark.parametrize("path", PATHS_WITH_A_SPACE)
def test_an_absolute_path_containing_a_space_is_kept(path):
    """A no-whitespace rule would have been the obvious fix and would have lost these."""
    assert consumer_keeps(path)
    assert producer_keeps(path)


def test_a_clause_stops_at_a_newline():
    """One live work order's last entry had two newlines and a shouted sentence glued on."""
    description = (
        "Body.\n\nModule boundary: core/gates, tests/unit/test_wo_verify.py\n\n"
        "MAIN'S FULL CI HAS BEEN RED FOR SEVEN CONSECUTIVE MERGES"
    )
    globs = boundary_globs(description)
    assert globs == ["core/gates", "tests/unit/test_wo_verify.py"]
    assert not any("\n" in g for g in globs)


def test_a_boundary_of_pure_prose_still_declares_nothing():
    """An unparseable boundary stays undeclared rather than being stored as a lie."""
    assert compose_module_boundary("Body.", "MAIN IS RED, the runner") == "Body."


# --- the two ends may not drift ----------------------------------------------------


@pytest.mark.parametrize(
    "entry", BARE_DIRECTORIES + PATHS_WITH_A_SPACE + NOT_PATHS + ["core/gates", "a.b", "_x"]
)
def test_producer_and_consumer_agree(entry):
    """compose_module_boundary writes what boundary_globs reads, or the boundary lies."""
    assert producer_keeps(entry) == consumer_keeps(entry)


# --- the third copy: the amend path --------------------------------------------------


def test_amending_a_boundary_keeps_bare_directories(tmp_path):
    """amend_module_boundary carried its own inline copy of the drop rule.

    It verified that ``docs`` exists on disk and then discarded it, so the command reported
    success while storing less than the operator typed -- observed twice on the live
    authority before this was found. Driven end to end against a temporary authority.
    """
    import sqlite3

    from core.config.sqlite_bootstrap import bootstrap_database
    from core.work_orders.amend_boundary import amend_module_boundary
    from interfaces.cli.ds import resolve_installed_runtime_paths

    repo_root = Path(__file__).resolve().parents[2]
    resolved = resolve_installed_runtime_paths(source_root=repo_root, dream_studio_home=tmp_path)
    resolved.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(resolved.sqlite_path)

    conn = sqlite3.connect(str(resolved.sqlite_path))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, title, description, status)"
        " VALUES (?, ?, ?, ?, ?)",
        ("wo-amend-test", "proj-1", "t", "Body.\n\nModule boundary: core/gates.", "in_progress"),
    )
    conn.commit()
    conn.close()

    result = amend_module_boundary(
        work_order_id="wo-amend-test",
        module_boundary="core/gates, docs, schemas, tests/unit",
        reason="Restoring the bare directory names this command used to discard silently.",
        source_root=repo_root,
        dream_studio_home=tmp_path,
    )

    assert result["ok"], result.get("error")
    assert result["module_boundary"] == ["core/gates", "docs", "schemas", "tests/unit"]
