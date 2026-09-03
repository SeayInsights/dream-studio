"""`ds update` must notice a canonical SKILL change, not hook changes alone.

WO 789df02b. Operator symptom: another Dream Studio install "couldn't do the reviews
because it didn't have some of the files needed". Cause: when the VERSION stamp matched,
the update gate consulted ``_canonical_hook_drift`` only -- which filters manifest
entries to hook meta handlers -- so a skill change without a version bump printed
``already_current`` and installed nothing.

Every case here carries its counterfactual. A test that only shows the new code agreeing
with itself cannot fail, and that is the defect class this branch keeps producing; so
each case either mutates a file and demands the verdict CHANGE, or shows the old check
staying silent on input the new one flags.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from integrations.installer.claude_code_fileops import _collect_skill_dir_ops
from interfaces.cli.commands.system_health import (
    _canonical_hook_drift,
    _canonical_skill_drift,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_MODE = ("canonical", "skills", "core", "modes", "review", "SKILL.md")


def _plan_for(source_root: Path):
    from integrations.detector import detect_claude_code
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    detected = detect_claude_code()
    plan = ClaudeCodeInstaller(
        detected.config_root,
        detected.scope,
        canonical_root=source_root / "canonical",
        ds_home=get_ds_home(),
    ).plan()
    return detected, plan


def _manifest_from_plan(source_root: Path) -> dict:
    """A manifest recording exactly what a plan over ``source_root`` would install.

    This represents a machine that is genuinely up to date, so any drift reported against
    it afterwards comes from a real change rather than from a mismatched baseline.
    """
    detected, plan = _plan_for(source_root)
    return {
        "scope": detected.scope,
        "files": [
            {"path": str(op.target), "operation": op.op, "content_hash": op.source_hash}
            for op in plan.ops
            if op.op != "skip"
        ],
    }


@pytest.fixture
def canonical_copy(tmp_path: Path) -> Path:
    """A source root whose canonical/ is a real copy, so plan() behaves as in production."""
    src = REPO_ROOT / "canonical"
    if not src.is_dir():
        pytest.skip("no canonical/ tree in this checkout")
    shutil.copytree(
        src,
        tmp_path / "canonical",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return tmp_path


def test_an_untouched_tree_compares_clean(canonical_copy: Path) -> None:
    """The baseline every other case rests on. If this fails they prove nothing."""
    manifest = _manifest_from_plan(canonical_copy)
    assert _canonical_skill_drift(canonical_copy, manifest) == []


def test_gate_consults_skills_a_skill_edit_is_drift(canonical_copy: Path) -> None:
    """Editing a canonical SKILL.md must show as drift; before this, nothing looked."""
    manifest = _manifest_from_plan(canonical_copy)
    target = canonical_copy.joinpath(*REVIEW_MODE)
    assert target.is_file(), f"expected the review mode to exist at {target}"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n<!-- a rule added without a version bump -->\n",
        encoding="utf-8",
    )

    drift = _canonical_skill_drift(canonical_copy, manifest)
    assert any(
        "review" in p and p.endswith("SKILL.md") for p in drift
    ), f"the edited review mode must appear in {drift}"


def test_gate_consults_skills_hook_check_alone_stays_silent(canonical_copy: Path) -> None:
    """The counterfactual: the old gate reports nothing on the same edited tree.

    This is the whole defect. Without this assertion the case above could pass against a
    gate that already worked, leaving the fix unproven.
    """
    manifest = _manifest_from_plan(canonical_copy)
    target = canonical_copy.joinpath(*REVIEW_MODE)
    target.write_text(target.read_text(encoding="utf-8") + "\n<!-- edit -->\n", encoding="utf-8")

    assert (
        _canonical_hook_drift(canonical_copy, manifest) == []
    ), "hook drift must be blind to a skill edit -- that blindness is the reported bug"
    assert _canonical_skill_drift(
        canonical_copy, manifest
    ), "skill drift must see what hook drift cannot"


def test_a_never_installed_mode_file_counts_as_drift(canonical_copy: Path) -> None:
    """The operator's exact case: a mode file the install has never seen."""
    manifest = _manifest_from_plan(canonical_copy)
    canonical_copy.joinpath(*REVIEW_MODE).with_name("EXTRA.md").write_text(
        "# a mode file added after the last install\n", encoding="utf-8"
    )

    drift = _canonical_skill_drift(canonical_copy, manifest)
    assert any(
        p.endswith("EXTRA.md") for p in drift
    ), f"a never-installed skill file must be drift, got {drift}"


def test_scope_mismatch_does_not_flag_the_whole_tree(canonical_copy: Path) -> None:
    """A user-scope manifest must be compared against the user tree.

    Standing in the repo the detector reports ``project`` (<repo>/.claude) while a
    manifest written by a user-scope install records ~/.claude. Those two trees share no
    path, and the first draft of this check duly called all 616 skill files drifted. A
    comparison whose paths cannot meet is broken, not strict.
    """
    detected, plan = _plan_for(canonical_copy)
    user_root = Path.home() / ".claude"
    files = []
    for op in plan.ops:
        if op.op == "skip":
            continue
        target = Path(str(op.target))
        try:
            rel = target.relative_to(detected.config_root)
        except ValueError:
            continue
        files.append(
            {
                "path": str(user_root / rel),
                "operation": op.op,
                "content_hash": op.source_hash,
            }
        )
    manifest = {"scope": "user", "files": files}

    total = sum(1 for e in files if "skills" in e["path"])
    assert total, "fixture built no skill entries, so this asserts nothing"
    drift = _canonical_skill_drift(canonical_copy, manifest)
    assert len(drift) < total, (
        f"comparing a user-scope manifest flagged {len(drift)} of {total} skill files -- "
        "the plan and the manifest are describing different trees"
    )


def test_a_comparison_that_cannot_run_raises_instead_of_reporting_clean(
    canonical_copy: Path,
) -> None:
    """An unexaminable tree must raise, not come back empty.

    Empty means compared-and-clean. The first draft swallowed planning faults into
    ``return []``, and an argument mismatch then made it report 0 drift on a tree holding
    an uncommitted skill edit -- a check that cannot fail, reporting a tree it never read.

    An earlier version of this test asserted a "planned nothing" sentinel instead. An
    independent run showed that branch was unreachable -- the plan dies in
    ``compile_pack`` well before it could return empty -- so the sentinel was dead code
    and the assertion was aimed at behaviour that could not happen. What is actually
    guaranteed, and what this pins, is propagation.
    """
    manifest = _manifest_from_plan(canonical_copy)
    shutil.rmtree(canonical_copy / "canonical" / "skills")

    # Named rather than bare `Exception`: a broad catch here would also pass if this
    # test's own setup were broken, which is the failure mode being guarded against.
    with pytest.raises(FileNotFoundError):
        _canonical_skill_drift(canonical_copy, manifest)


def test_bytecode_is_not_installed_as_skill_content(tmp_path: Path) -> None:
    """__pycache__/*.pyc is build output, not skill content.

    rglob("*") swept 20 bytecode files into the install and recorded them in the
    manifest. A .pyc is rewritten on import, so its hash never settles -- which would
    leave any content-hash drift check over the skill tree permanently dirty.
    """
    skill_dir = tmp_path / "demo"
    (skill_dir / "__pycache__").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (skill_dir / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (skill_dir / "__pycache__" / "helper.cpython-312.pyc").write_bytes(b"\x00\x01bytecode")
    (skill_dir / "stray.pyc").write_bytes(b"\x00\x01bytecode")

    ops = _collect_skill_dir_ops(skill_dir, tmp_path / "out", "ds-demo", tmp_path / "backups")
    installed = {Path(str(op.target)).name for op in ops}

    assert (
        "SKILL.md" in installed and "helper.py" in installed
    ), f"real skill content must still install, got {installed}"
    assert not any(
        name.endswith(".pyc") for name in installed
    ), f"bytecode must not be installed, got {installed}"
    assert not any(
        "__pycache__" in Path(str(op.target)).parts for op in ops
    ), "no op may target a __pycache__ directory"


def test_a_planning_fault_reports_the_standard_error_envelope(
    tmp_path, monkeypatch, capsys
) -> None:
    """An unreadable canonical tree must not crash `ds update` with a raw traceback.

    WO 789df02b task 40754f1d. `_canonical_skill_drift` raises rather than returning `[]`
    when it cannot compare, which is the intended contract. But ds.py main() catches only
    RuntimeError, sqlite3.Error and ValueError, and nothing between the call site and the
    operator caught anything else -- so a broken checkout produced a Python traceback
    instead of the {"ok": false, ...} envelope every other CLI failure uses.

    The catch lives at the command boundary, never inside the drift function, and the
    third assertion below is the one that matters: reporting the fault must not degrade
    into reporting a CLEAN tree. An earlier draft swallowed exactly this fault into `[]`
    and printed already_current on a tree with an uncommitted skill edit.
    """
    import integrations.manifest as manifest_module
    from interfaces.cli.commands import system_health

    # Hermetic, because the drift branch is only REACHED when the installed version
    # equals the repo version. A first draft relied on this machine's real VERSION and
    # real installed manifest, so on a fresh CI runner -- no manifest, no
    # installed-version file -- the branch would be skipped entirely and the test would
    # fail for a reason having nothing to do with the defect.
    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "VERSION").write_text("155\n", encoding="utf-8")
    ds_home = tmp_path / "ds-home"
    (ds_home / "state").mkdir(parents=True)
    (ds_home / "state" / "installed-version").write_text("155\n", encoding="utf-8")

    # Patched on integrations.manifest, NOT on system_health: _update_command imports
    # read_manifest INSIDE the function body, so `from integrations.manifest import
    # read_manifest` resolves the attribute on the source module at call time and a
    # system_health attribute would never be consulted.
    monkeypatch.setattr(
        manifest_module, "read_manifest", lambda *a, **k: {"scope": "user", "files": []}
    )
    monkeypatch.setattr(system_health, "_canonical_hook_drift", lambda *a, **k: [])

    def _explode(*_args, **_kwargs):
        raise FileNotFoundError("canonical/skills/ds-bootstrap/SKILL.md not found")

    monkeypatch.setattr(system_health, "_canonical_skill_drift", _explode)

    try:
        exit_code = system_health._update_command(
            source_root=source_root, dream_studio_home=ds_home, dry_run=True
        )
    except FileNotFoundError:  # pragma: no cover - this is the defect under test
        raise AssertionError(
            "the planning fault escaped the command boundary as a bare exception"
        ) from None

    out = capsys.readouterr().out
    assert exit_code == 1, f"a fault must exit non-zero, got {exit_code}"
    assert '"ok": false' in out.lower(), f"expected the standard error envelope, got: {out[:400]}"
    assert (
        "already_current" not in out
    ), "reporting a fault must never degrade into reporting a clean tree"
