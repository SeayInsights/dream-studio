"""E19 — the skill eval-coverage census, and that it actually catches something.

Every case that expects clean is paired with one that expects a catch, same convention as
``test_fail_open_census_gate.py``: a gate no test can make FAIL is indistinguishable from a
gate that checks nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.gates import skill_eval_coverage_census as gate


def _write_skill(root: Path, rel: str) -> None:
    path = root / "canonical" / "skills" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# a skill\n", encoding="utf-8")


def _write_registry(root: Path, skills: dict) -> None:
    path = root / "canonical" / "skill_eval_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"skills": skills}), encoding="utf-8")


def _write_test_file(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_x():\n    assert True\n", encoding="utf-8")


def test_clean_repo_with_every_status_passes(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pack/SKILL.md")
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_skill(tmp_path, "pack/modes/audited/SKILL.md")
    _write_test_file(tmp_path, "tests/evals/test_thing.py")
    _write_registry(
        tmp_path,
        {
            "pack/SKILL.md": {
                "status": "no_output",
                "reason": "pure router, delegates to modes/<mode>/SKILL.md entirely",
            },
            "pack/modes/leaf/SKILL.md": {
                "status": "gap",
                "reason": "not yet audited for real eval coverage, tracked debt only",
            },
            "pack/modes/audited/SKILL.md": {
                "status": "covered",
                "covered_by": ["tests/evals/test_thing.py"],
            },
        },
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "pass", result
    assert result["total_skills"] == 3
    assert result["counts"] == {"no_output": 1, "covered": 1, "gap": 1}


def test_a_new_skill_file_with_no_registry_entry_fails(tmp_path: Path) -> None:
    """The actual point of this gate: a skill added after the registry was seeded, with
    nobody recording a coverage decision for it, must be caught -- not silently invisible."""
    _write_skill(tmp_path, "pack/SKILL.md")
    _write_skill(tmp_path, "pack/modes/new-mode/SKILL.md")
    _write_registry(
        tmp_path,
        {
            "pack/SKILL.md": {
                "status": "no_output",
                "reason": "pure router, no capability of its own",
            },
            # pack/modes/new-mode/SKILL.md has no entry at all.
        },
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert result["unregistered"] == ["pack/modes/new-mode/SKILL.md"]


def test_a_covered_claim_whose_test_file_was_deleted_fails(tmp_path: Path) -> None:
    """A stale covered_by (the named test file no longer exists) must be caught -- otherwise
    a claim of coverage outlives the test that ever backed it, forever."""
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_registry(
        tmp_path,
        {
            "pack/modes/leaf/SKILL.md": {
                "status": "covered",
                "covered_by": ["tests/evals/test_deleted.py"],
            },
        },
    )
    # Deliberately do NOT write tests/evals/test_deleted.py.

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert len(result["stale_covered"]) == 1
    assert "test_deleted.py" in result["stale_covered"][0]["detail"]


def test_covered_status_with_an_empty_covered_by_list_is_malformed(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_registry(
        tmp_path,
        {"pack/modes/leaf/SKILL.md": {"status": "covered", "covered_by": []}},
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert len(result["malformed"]) == 1


def test_gap_status_with_a_short_reason_is_malformed(tmp_path: Path) -> None:
    """The 20-char minimum matches this repo's other enforce-or-declare gates
    (agent_coverage's no_agent, rule_enforcement's unenforced) -- a one-word 'reason'
    is not a reason."""
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_registry(
        tmp_path,
        {"pack/modes/leaf/SKILL.md": {"status": "gap", "reason": "todo"}},
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert len(result["malformed"]) == 1


def test_no_output_status_with_a_short_reason_is_malformed(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pack/SKILL.md")
    _write_registry(
        tmp_path,
        {"pack/SKILL.md": {"status": "no_output", "reason": "router"}},
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert len(result["malformed"]) == 1


def test_an_unknown_status_value_is_malformed(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_registry(
        tmp_path,
        {"pack/modes/leaf/SKILL.md": {"status": "maybe"}},
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert len(result["malformed"]) == 1


def test_missing_registry_file_treats_every_skill_as_unregistered(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    # No registry file written at all.

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "fail", result
    assert result["unregistered"] == ["pack/modes/leaf/SKILL.md"]


def test_a_node_id_covered_by_entry_checks_the_file_part_only(tmp_path: Path) -> None:
    """covered_by may name a specific test function via ``path.py::test_name`` -- the gate
    checks the FILE exists, not that pytest can collect that exact node id (that's what
    test-suite/pin-tests do by actually running the suite)."""
    _write_skill(tmp_path, "pack/modes/leaf/SKILL.md")
    _write_test_file(tmp_path, "tests/evals/test_thing.py")
    _write_registry(
        tmp_path,
        {
            "pack/modes/leaf/SKILL.md": {
                "status": "covered",
                "covered_by": ["tests/evals/test_thing.py::test_specific_case"],
            },
        },
    )

    result = gate.run(repo_root=tmp_path)
    assert result["status"] == "pass", result


def test_the_real_repo_registry_is_currently_clean() -> None:
    """The actual, committed registry and skill tree must pass right now -- this is the
    fixture-vs-reality check every ratcheted gate in this repo carries."""
    result = gate.run()
    assert result["status"] == "pass", result
    assert result["unregistered"] == []
    assert result["malformed"] == []
    assert result["stale_covered"] == []
