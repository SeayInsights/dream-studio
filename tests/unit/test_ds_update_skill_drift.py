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


def test_an_untouched_tree_compares_clean(tmp_path, monkeypatch) -> None:
    """A machine whose install matches the plan must compare clean.

    Built on a synthetic install rather than a real plan. The earlier version derived a
    manifest from a real plan WITHOUT performing the install, which describes a state
    production cannot reach: a manifest entry exists precisely because a file was
    written. It passed on a machine that happened to have an install and failed on all
    three CI platforms, which have none -- the existence check correctly reported all
    596 planned files as missing. Third time an environment-dependent test in this branch
    passed locally for a reason unrelated to the property under test, so this one owns
    every input it depends on.
    """
    import integrations.installer.claude_code as installer_module

    skills = tmp_path / ".claude" / "skills" / "ds-core"
    (skills / "modes" / "review").mkdir(parents=True)
    top = skills / "SKILL.md"
    top.write_text("# core\n", encoding="utf-8")
    mode = skills / "modes" / "review" / "SKILL.md"
    mode.write_text("# review\n", encoding="utf-8")

    ops = [_FakeOp(top, "hash-top"), _FakeOp(mode, "hash-mode")]
    monkeypatch.setattr(installer_module, "ClaudeCodeInstaller", _fake_installer(ops))

    manifest = {
        "scope": "user",
        "files": [
            {"path": str(top), "operation": "create", "content_hash": "hash-top"},
            {"path": str(mode), "operation": "create", "content_hash": "hash-mode"},
        ],
    }
    assert _canonical_skill_drift(tmp_path, manifest) == []


def test_gate_consults_skills_a_skill_edit_is_drift(tmp_path, monkeypatch) -> None:
    """A changed canonical file must show as drift; before this, nothing looked.

    Hermetic on purpose. An earlier version edited a real canonical file and asserted the
    result appeared in the drift list, which discriminated only on a machine that HAS an
    install: measured on a tree with none, all 595 planned files are already drift because
    every one is missing, so the assertion passed whether or not the edit was detected.
    Here the two files differ ONLY in whether the recorded hash matches, so nothing but
    hash comparison can separate them.
    """
    import integrations.installer.claude_code as installer_module

    skills = tmp_path / ".claude" / "skills" / "ds-core"
    skills.mkdir(parents=True)
    edited = skills / "edited.md"
    edited.write_text("# edited since install\n", encoding="utf-8")
    untouched = skills / "untouched.md"
    untouched.write_text("# same as install\n", encoding="utf-8")

    ops = [_FakeOp(edited, "hash-NEW"), _FakeOp(untouched, "hash-same")]
    monkeypatch.setattr(installer_module, "ClaudeCodeInstaller", _fake_installer(ops))

    manifest = {
        "scope": "user",
        "files": [
            {"path": str(edited), "operation": "create", "content_hash": "hash-OLD"},
            {"path": str(untouched), "operation": "create", "content_hash": "hash-same"},
        ],
    }

    drift = _canonical_skill_drift(tmp_path, manifest)
    assert str(edited) in drift, f"a changed file must be drift, got {drift}"
    assert str(untouched) not in drift, (
        "an unchanged file must NOT be drift, or the check reports everything and "
        f"discriminates nothing: {drift}"
    )


def test_gate_consults_skills_hook_check_alone_stays_silent(tmp_path, monkeypatch) -> None:
    """The counterfactual: the old gate reports nothing on the same edited tree.

    This is the whole defect. Without this assertion the case above could pass against a
    gate that already worked, leaving the fix unproven.
    """
    import integrations.installer.claude_code as installer_module

    skills = tmp_path / ".claude" / "skills" / "ds-core"
    skills.mkdir(parents=True)
    edited = skills / "edited.md"
    edited.write_text("# edited since install\n", encoding="utf-8")

    ops = [_FakeOp(edited, "hash-NEW")]
    monkeypatch.setattr(installer_module, "ClaudeCodeInstaller", _fake_installer(ops))
    manifest = {
        "scope": "user",
        "files": [{"path": str(edited), "operation": "create", "content_hash": "hash-OLD"}],
    }

    assert (
        _canonical_hook_drift(tmp_path, manifest) == []
    ), "hook drift must be blind to a skill edit -- that blindness is the reported bug"
    assert _canonical_skill_drift(tmp_path, manifest), "skill drift must see what hook drift cannot"


def test_a_never_installed_mode_file_counts_as_drift(tmp_path, monkeypatch) -> None:
    """The operator's exact case: a mode file the install has never seen.

    Distinct from the changed-file case above: this file is PLANNED but has no manifest
    entry at all, so it is caught by the ``was is None`` arm rather than by a hash
    mismatch. Hermetic for the same reason as its siblings -- on a tree with no install
    every planned file is already drift, so a membership assertion proves nothing there.
    """
    import integrations.installer.claude_code as installer_module

    review = tmp_path / ".claude" / "skills" / "ds-core" / "modes" / "review"
    review.mkdir(parents=True)
    known = review / "SKILL.md"
    known.write_text("# known to the manifest\n", encoding="utf-8")
    added = review / "EXTRA.md"
    added.write_text("# a mode file added after the last install\n", encoding="utf-8")

    ops = [_FakeOp(known, "hash-known"), _FakeOp(added, "hash-added")]
    monkeypatch.setattr(installer_module, "ClaudeCodeInstaller", _fake_installer(ops))
    manifest = {
        "scope": "user",
        "files": [{"path": str(known), "operation": "create", "content_hash": "hash-known"}],
    }

    drift = _canonical_skill_drift(tmp_path, manifest)
    assert str(added) in drift, f"a never-installed skill file must be drift, got {drift}"
    assert str(known) not in drift, f"a recorded, present, unchanged file must not be: {drift}"


def test_scope_mismatch_does_not_flag_the_whole_tree(canonical_copy: Path) -> None:
    """A user-scope manifest must be compared against the user tree.

    Standing in the repo the detector reports ``project`` (<repo>/.claude) while a
    manifest written by a user-scope install records ~/.claude. Those two trees share no
    path, and the first draft of this check duly called all 616 skill files drifted. A
    comparison whose paths cannot meet is broken, not strict.

    Asserts the MECHANISM -- which root the plan was built for -- rather than a drift
    count. The count depends on whether the machine running the test happens to have an
    install, which is exactly why the earlier count-based form passed locally and failed
    on all three CI platforms. Where the planned targets live does not.

    An empty file list is deliberate: every planned target is then unrecorded, so the
    drift list is the full set of planned targets and their common root is directly
    observable.
    """
    drift = _canonical_skill_drift(canonical_copy, {"scope": "user", "files": []})
    user_root = str(Path.home() / ".claude")

    assert drift, "an empty manifest must flag planned files as never installed"
    strays = [p for p in drift if not p.startswith(user_root)]
    assert not strays, (
        f"a user-scope manifest was compared against a different tree; {len(strays)} of "
        f"{len(drift)} planned targets fall outside {user_root}, e.g. {strays[:3]}"
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


class _FakeOp:
    """One planned file operation, enough of FileOp for the drift comparison."""

    def __init__(self, target: Path, source_hash: str, op: str = "create") -> None:
        self.target = target
        self.source_hash = source_hash
        self.op = op


class _FakePlan:
    def __init__(self, ops: list[_FakeOp]) -> None:
        self.ops = ops


def _fake_installer(ops: list[_FakeOp]):
    """A stand-in for ClaudeCodeInstaller whose plan() returns *ops*."""

    class _Installer:
        def __init__(self, *_a, **_k) -> None:
            pass

        def plan(self):
            return _FakePlan(ops)

    return _Installer


def test_a_deleted_installed_file_is_drift(tmp_path, monkeypatch) -> None:
    """A file the manifest records but disk no longer has must count as drift.

    THE REPORTED SYMPTOM CLASS. The comparison was recorded-hash against planned-hash,
    which answers "has the source changed" and never "is the file still there" -- so an
    entry present in the manifest and absent from disk matched and read as clean, and
    `ds update` said already_current about an install missing the files a mode needs.

    Found by the falsification analyst in `ds work-order verify`, then reproduced against
    the live manifest: deleting ds-analyze/DOMAIN_ANALYZER_GUIDE.md left the drift count
    unchanged at 34 with the deleted file unreported.

    The two ops below differ ONLY in whether the file exists, and their recorded hashes
    both match, so nothing but the existence check can separate them.
    """
    import integrations.installer.claude_code as installer_module

    skills = tmp_path / ".claude" / "skills" / "ds-core"
    skills.mkdir(parents=True)
    present = skills / "present.md"
    present.write_text("# present\n", encoding="utf-8")
    absent = skills / "deleted-by-someone.md"  # deliberately never created

    ops = [_FakeOp(present, "hash-a"), _FakeOp(absent, "hash-b")]
    # Patched on the source module: _canonical_skill_drift imports ClaudeCodeInstaller
    # inside the function body, so the name resolves there at call time.
    monkeypatch.setattr(installer_module, "ClaudeCodeInstaller", _fake_installer(ops))

    manifest = {
        "scope": "user",
        "files": [
            {"path": str(present), "operation": "create", "content_hash": "hash-a"},
            {"path": str(absent), "operation": "create", "content_hash": "hash-b"},
        ],
    }

    drift = _canonical_skill_drift(tmp_path, manifest)
    assert str(absent) in drift, f"a recorded file missing from disk must be drift, got {drift}"
    assert str(present) not in drift, (
        "an unchanged file that is still present must NOT be drift, or the check reports "
        f"everything and discriminates nothing: {drift}"
    )


def test_an_unreadable_manifest_does_not_report_clean(tmp_path, monkeypatch, capsys) -> None:
    """A deleted, truncated or corrupt manifest must not print already_current.

    ``read_manifest`` swallows JSONDecodeError and OSError into None, so this path left
    the drift list empty and reported clean -- and we only reach it because a version
    stamp exists, meaning an install DID happen. The one state where re-projection is
    most needed was the state that reported clean.
    """
    import integrations.manifest as manifest_module
    from interfaces.cli.commands import system_health

    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "VERSION").write_text("155\n", encoding="utf-8")
    ds_home = tmp_path / "ds-home"
    (ds_home / "state").mkdir(parents=True)
    (ds_home / "state" / "installed-version").write_text("155\n", encoding="utf-8")

    monkeypatch.setattr(manifest_module, "read_manifest", lambda *a, **k: None)

    exit_code = system_health._update_command(
        source_root=source_root, dream_studio_home=ds_home, dry_run=True
    )
    out = capsys.readouterr().out

    assert "already_current" not in out, (
        "an unreadable manifest reported a clean install; empty must mean "
        f"compared-and-clean, never could-not-compare. Output: {out[:400]}"
    )
    assert "update_available" in out, f"expected a reinstall to be indicated, got {out[:400]}"
    assert exit_code == 0, f"dry-run reports without failing, got {exit_code}"


def test_hook_drift_survives_a_skill_comparison_fault(tmp_path, monkeypatch, capsys) -> None:
    """Proven hook drift must not be discarded when the skill comparison raises.

    The merged line concatenated both calls in one expression, so a raising skill
    comparison threw away already-detected hook drift with the left operand and returned
    1 -- and the reinstall the hook drift called for never happened. The previous ``or``
    short-circuited and never had this failure; the concatenation introduced it.
    """
    import integrations.manifest as manifest_module
    from interfaces.cli.commands import system_health

    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "VERSION").write_text("155\n", encoding="utf-8")
    ds_home = tmp_path / "ds-home"
    (ds_home / "state").mkdir(parents=True)
    (ds_home / "state" / "installed-version").write_text("155\n", encoding="utf-8")

    monkeypatch.setattr(
        manifest_module, "read_manifest", lambda *a, **k: {"scope": "user", "files": []}
    )
    monkeypatch.setattr(system_health, "_canonical_hook_drift", lambda *a, **k: ["on-stop.py"])

    def _explode(*_a, **_k):
        raise FileNotFoundError("canonical/skills gone")

    monkeypatch.setattr(system_health, "_canonical_skill_drift", _explode)

    exit_code = system_health._update_command(
        source_root=source_root, dream_studio_home=ds_home, dry_run=True
    )
    captured = capsys.readouterr()
    out, err = captured.out, captured.err

    assert exit_code != 1, (
        "a skill-comparison fault discarded hook drift that was already proven, so the "
        f"reinstall it called for never happens. Output: {out[:400]}"
    )
    assert "update_available" in out, f"the reinstall must still be indicated, got {out[:400]}"
    # STDERR, deliberately. stdout is this CLI's machine-readable channel and every
    # command prints exactly ONE JSON document there; emitting the warning to stdout put
    # a second document on it, so json.loads(captured.out) raised "Extra data" and broke
    # two pre-existing tests in test_version_check.py. The warning still has to be SAID --
    # proceeding on partial evidence without saying so is the compared-nothing shape --
    # it just belongs on the diagnostic stream.
    assert "skill drift could not be determined" in err, (
        "proceeding on partial evidence must SAY what could not be compared, or the "
        f"operator cannot tell a full comparison from a partial one. stderr: {err[:400]}"
    )
    import json as _json

    _json.loads(out), "stdout must remain exactly one parseable JSON document"


def test_a_hook_comparison_fault_also_reports_the_envelope(tmp_path, monkeypatch, capsys) -> None:
    """The hook side must fail the same way the skill side does.

    The first cut of the fault handling wrapped only the SKILL comparison, so an OSError
    from `_canonical_hook_drift` -- a PermissionError on read_text, or a handler that
    disappears between glob() and read_text() -- escaped uncaught and produced exactly the
    raw traceback the handling exists to prevent, on the other branch. Fixed for one
    caller and left open for its sibling is the recurring shape here, so this pins both.

    Reproduced by an independent verifier before the fix: monkeypatching
    `_canonical_hook_drift` to raise let the exception propagate out of `_update_command`.
    """
    import integrations.manifest as manifest_module
    from interfaces.cli.commands import system_health

    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "VERSION").write_text("155\n", encoding="utf-8")
    ds_home = tmp_path / "ds-home"
    (ds_home / "state").mkdir(parents=True)
    (ds_home / "state" / "installed-version").write_text("155\n", encoding="utf-8")

    monkeypatch.setattr(
        manifest_module, "read_manifest", lambda *a, **k: {"scope": "user", "files": []}
    )

    def _explode(*_a, **_k):
        raise PermissionError("runtime/hooks/meta/on-stop-enforce.py: access denied")

    monkeypatch.setattr(system_health, "_canonical_hook_drift", _explode)
    # The skill side must never be consulted: the hook fault is a hard stop, because
    # nothing has been proven yet and there is no partial evidence to proceed on.
    monkeypatch.setattr(
        system_health,
        "_canonical_skill_drift",
        lambda *a, **k: pytest.fail("skill drift ran after a hook fault should have stopped"),
    )

    try:
        exit_code = system_health._update_command(
            source_root=source_root, dream_studio_home=ds_home, dry_run=True
        )
    except PermissionError:  # pragma: no cover - this is the defect under test
        raise AssertionError(
            "a hook-comparison fault escaped the command boundary as a bare exception"
        ) from None

    out = capsys.readouterr().out
    assert exit_code == 1, f"an unresolvable comparison must exit non-zero, got {exit_code}"
    assert '"ok": false' in out.lower(), f"expected the standard error envelope, got {out[:400]}"
    assert "already_current" not in out, "a fault must never degrade into reporting a clean tree"
