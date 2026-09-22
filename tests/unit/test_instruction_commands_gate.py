"""An instruction that names a command must name one that can run.

Canonical skills and workflows are instructions to an agent, and an agent does what they
say. When one names a script or module that is not there, the agent gets "no such file"
and either improvises or silently skips a step it was told to take — and the steps
instructions name are disproportionately checks.

WHAT THE GATE FOUND ON THE RUN THAT WROTE IT, all of it real:

    scripts/lint-artifact.py            14 references, never once tracked
    core.gates.evidence_backed_output    2 references, module culled in 67ba10e
    control.research.tools               2 references, module never existed
    design/references/search-*.py        2 references, files never existed
    scripts/{resume_from_handoff,backfill_token_sessions,migrate_to_db}.py
                                         3 references, all moved to interfaces/cli/
    tests/unit/canonical/test_packs_yaml.py
                                         1 reference, renamed and moved

The first is why this is a gate and not a cleanup. `.gitignore` carried an unanchored
`lint-*` and swallowed `lint-artifact.py` silently, so fourteen instructions — one a
`severity: critical` gotcha reading "before every delivery" — pointed at a file that had
never been committed, for four months, because nothing was looking.

The negative cases matter as much as the positive ones. A gate that flags a document for
being correct is one people learn to argue with rather than fix, so three kinds of
reference are deliberately NOT checked, and each has a test below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates.instruction_commands import (
    MODULE_REF,
    SCRIPT_REF,
    _resolve_module,
    _resolve_script,
    unresolved_commands,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# The repository is clean, and stays clean
# --------------------------------------------------------------------------


def test_every_command_canonical_names_can_actually_be_run():
    """The gate's own subject. If this fails, read the output: some instruction now names
    a script or module that is not there, and an agent following it will get an error."""
    findings = unresolved_commands()
    assert findings == [], "\n".join(
        f"  {f['file']}:{f['line']} names {f['names']!r} ({f['kind']})" for f in findings
    )


# --------------------------------------------------------------------------
# What it catches
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("py scripts/lint-artifact.py <output.html>", "scripts/lint-artifact.py"),
        ("py -3.12 scripts/migrate_to_db.py", "scripts/migrate_to_db.py"),
        (
            "Run: py scripts/resume_from_handoff.py --brief",
            "scripts/resume_from_handoff.py",
        ),
        (
            "Run `scripts/lint-artifact.py` on every artifact",
            "scripts/lint-artifact.py",
        ),
        ("./tools/thing.py --flag", "tools/thing.py"),
        (
            "py skills/domains/modes/design/references/search-font-pairings.py 'x'",
            "skills/domains/modes/design/references/search-font-pairings.py",
        ),
    ],
)
def test_an_invoked_path_is_extracted(line, expected):
    assert SCRIPT_REF.findall(line) == [expected]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("py -m core.gates.unverified_claims --staged", "core.gates.unverified_claims"),
        ("python -m interfaces.cli.ds project state", "interfaces.cli.ds"),
        ("py -3.12 -m interfaces.cli.migrate_to_db", "interfaces.cli.migrate_to_db"),
    ],
)
def test_an_invoked_module_is_extracted(line, expected):
    assert MODULE_REF.findall(line) == [expected]


def test_a_module_that_does_not_exist_is_unresolved():
    assert not _resolve_module("core.gates.evidence_backed_output")
    assert not _resolve_module("control.research.tools")


def test_a_module_that_exists_resolves():
    assert _resolve_module("core.gates.unverified_claims")
    assert _resolve_module("interfaces.cli.ds")


# --------------------------------------------------------------------------
# What it deliberately does NOT catch
# --------------------------------------------------------------------------


def test_a_bare_filename_is_not_a_repo_path():
    """`py parse_sarif.py` in the security examples tells the agent to WRITE that file in
    its own working directory. Checking those against this repo would flag a document for
    doing its job."""
    assert SCRIPT_REF.findall("py parse_sarif.py findings.json") == []
    assert SCRIPT_REF.findall("py analyze_netcompat.py") == []


def test_a_path_that_is_only_mentioned_is_not_an_invocation():
    """`quality:harden` carries a checklist row reading "`scripts/bom.py` or equivalent
    BOM script" — a criterion about the project being hardened, not a command this repo
    runs."""
    row = "| 15 | Bill of Materials | `scripts/bom.py` or equivalent BOM script |"
    assert SCRIPT_REF.findall(row) == []


def test_a_third_party_module_is_not_this_repositorys_to_guarantee():
    """`py -m pytest` and `py -m black` are environment concerns, not instruction defects."""
    assert _resolve_module("pytest")
    assert _resolve_module("black")


def test_a_skill_relative_script_resolves_against_its_own_skill():
    """A skill shipping its own `scripts/` directory writes `py scripts/brand-compliance.py`
    meaning its own, which is the shorter and correct thing for it to say."""
    website_skill = (
        REPO_ROOT / "canonical" / "skills" / "domains" / "modes" / "website" / "SKILL.md"
    )
    assert _resolve_script("scripts/brand-compliance.py", website_skill)
    assert _resolve_script("scripts/lint-artifact.py", website_skill)


def test_a_skill_relative_path_does_not_resolve_from_an_unrelated_skill():
    """The reason the fullstack skill's reference was a real finding rather than noise:
    the website skill's linter is not under `scripts/` from where fullstack stands."""
    core_skill = REPO_ROOT / "canonical" / "skills" / "core" / "SKILL.md"
    assert not _resolve_script("scripts/lint-artifact.py", core_skill)


# --------------------------------------------------------------------------
# The gate runs
# --------------------------------------------------------------------------


def test_the_gate_is_registered_in_the_pre_push_manifest():
    """A gate that exists in no manifest is exactly the defect it was built to catch —
    this repo's most-repeated one, and the reason a check is not done until it runs."""
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    gates = manifest["gates"] if isinstance(manifest, dict) else manifest
    entry = next((g for g in gates if g.get("id") == "instruction-commands"), None)
    assert entry is not None, "instruction-commands is not registered in pre-push.yaml"
    assert entry["command"] == ["py", "-m", "core.gates.instruction_commands"]
    assert entry["tier"] == "blocking"
    assert "fail_hint" in entry, "a blocking gate must tell the operator what to do"


# ---------------------------------------------------------------------------------------
# A generated projection is not a second instruction.
#
# Compiled agents inline their skill's text verbatim. A skill's relative paths resolve from
# the skill's own directory -- `py modes/repo/analyze-repos.py` is correct in
# canonical/skills/analyze/modes/repo/SKILL.md and meaningless from canonical/agents/.
# Scanning both copies flagged the source's instruction against the wrong base path: the
# gate arguing with a document that is right, which is how a gate gets switched off.
# ---------------------------------------------------------------------------------------


def test_a_generated_projection_is_not_scanned(tmp_path):
    """Found by running this gate after the agent compiler landed: seven references in one
    compiled agent, every one of them valid in the skill it was compiled from."""
    import core.gates.instruction_commands as gate

    generated = tmp_path / "canonical" / "agents"
    generated.mkdir(parents=True)
    (generated / "some-agent.md").write_text(
        "---\nname: some-agent\n---\n\n"
        "<!-- GENERATED by integrations/compiler/agents.py from a coverage row -->\n\n"
        "py modes/repo/analyze-repos.py <repo>\n",
        encoding="utf-8",
    )
    (tmp_path / "canonical" / "hand-written.md").write_text(
        "py modes/repo/analyze-repos.py <repo>\n", encoding="utf-8"
    )

    from unittest import mock

    with mock.patch.object(gate, "REPO_ROOT", tmp_path):
        findings = gate.unresolved_commands()

    files = {f["file"] for f in findings}
    assert (
        "canonical/agents/some-agent.md" not in files
    ), "a generated projection was scanned; its inlined paths resolve from the source skill"
    assert "canonical/hand-written.md" in files, (
        "the skip is too broad -- an ordinary file with the same dangling command must "
        "still be caught"
    )


def test_the_real_source_skill_is_still_scanned():
    """The skip must not lose coverage. The skill that OWNS the instruction is an ordinary
    canonical file and is still read, which is where a genuinely dangling command has to be
    fixed anyway."""
    source = REPO_ROOT / "canonical" / "skills" / "analyze" / "modes" / "repo" / "SKILL.md"
    assert source.is_file()
    assert (
        "GENERATED by" not in source.read_text(encoding="utf-8")[:600]
    ), "the source skill carries a generated banner, which would exempt it too"


# ---------------------------------------------------------------------------------------
# A function a skill tells an agent to CALL.
#
# `ds-project:brownfield` instructed `from core.projects.mutations import
# defer_project_audit` and promised "a notice will appear the next time the project is
# activated". Commit 2963b58 retired the `pending_audits` table, removed that function, and
# removed `_get_pending_audits_for_project` from the start path -- so the import raised and
# the promised notice had no reader left. An agent following it scheduled nothing and told
# the operator it had.
#
# Same rule as a script path or a `py -m` module, one level finer.
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "`core.projects.mutations.set_project_vision(project_id, vision)` — capture it",
            ("core.projects.mutations", "set_project_vision"),
        ),
        (
            "Call core.milestones.close.close_milestone(milestone_id=x) to finish",
            ("core.milestones.close", "close_milestone"),
        ),
    ],
)
def test_a_called_function_is_extracted(line, expected):
    from core.gates.instruction_commands import FUNCTION_REF

    assert FUNCTION_REF.findall(line) == [expected]


def test_a_dotted_path_that_is_not_a_call_is_left_alone():
    """The paren must follow IMMEDIATELY. `quality:architecture`'s rules carry a worked
    example of a layering violation -- "core/domain/user.py imports interfaces.api.routes.users
    (rank 3)" -- and allowing a space before the paren read that as a call, flagging a
    document for illustrating the rule it exists to teach."""
    from core.gates.instruction_commands import FUNCTION_REF

    assert FUNCTION_REF.findall("imports interfaces.api.routes.users (rank 3)") == []
    assert FUNCTION_REF.findall("see core.projects.mutations for the writers") == []


def test_a_function_the_module_does_not_have_is_unresolved():
    from core.gates.instruction_commands import _resolve_function

    assert _resolve_function("core.projects.mutations", "defer_project_audit")
    assert _resolve_function("core.projects.nowhere", "anything") == "no such module"


def test_a_function_that_exists_resolves():
    from core.gates.instruction_commands import _resolve_function

    assert _resolve_function("core.projects.mutations", "register_project") is None
    assert _resolve_function("core.milestones.mutations", "create_milestone") is None


def test_a_reexported_function_counts():
    """Imported rather than read off the source, because a function re-exported through a
    package __init__ is as callable as one defined there. Telling an author their working
    call is broken is how a gate gets argued with instead of fixed."""
    from core.gates.instruction_commands import _resolve_function

    assert _resolve_function("core.event_store.studio_db", "insert_lesson") is None


def test_the_scan_actually_reports_a_missing_function(tmp_path):
    """The wiring, not the pieces.

    A mutant that disabled the function scan entirely passed all twenty-six tests above,
    because every one of them exercised the regex or the resolver directly and none proved
    `unresolved_commands` consults either. That is the disconnected-verification shape --
    inside the test file for the gate whose whole subject is disconnected verification, for
    the third time in one session.
    """
    from unittest import mock

    import core.gates.instruction_commands as gate

    tree = tmp_path / "canonical" / "skills"
    tree.mkdir(parents=True)
    (tree / "SKILL.md").write_text(
        "Call `core.projects.mutations.a_function_that_does_not_exist(project_id)` to do it.\n",
        encoding="utf-8",
    )

    with mock.patch.object(gate, "REPO_ROOT", tmp_path):
        findings = gate.unresolved_commands()

    names = {f["names"] for f in findings}
    assert (
        "core.projects.mutations.a_function_that_does_not_exist" in names
    ), f"the scan did not report a missing function: {findings}"
    kinds = {f["kind"] for f in findings}
    assert any(k.startswith("function") for k in kinds), f"kind not recorded: {kinds}"


# ---------------------------------------------------------------------------
# A dispatch must name a subagent that exists
# ---------------------------------------------------------------------------


def _tree_with(tmp_path, skill_text: str, agents=("domains-power-platform",)):
    (tmp_path / "canonical" / "skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / "canonical" / "agents").mkdir(parents=True, exist_ok=True)
    for a in agents:
        (tmp_path / "canonical" / "agents" / f"{a}.md").write_text("x", encoding="utf-8")
    (tmp_path / "canonical" / "skills" / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return tmp_path


def _scan(tmp_path):
    from unittest import mock

    import core.gates.instruction_commands as gate

    with mock.patch.object(gate, "REPO_ROOT", tmp_path):
        return gate.unresolved_commands()


def test_a_dispatch_to_an_agent_that_does_not_ship_is_reported(tmp_path):
    """THE DEFECT. `domains/power-platform` said "For any Power BI work involving `.pbip`
    files ... dispatch a `bi-developer` subagent. Do not handle inline." No such agent
    ever shipped -- it was one of six in a `~/.claude/agents/` directory on the author's
    machine -- so on every other installation the instruction named nothing and the step
    it guarded was silently skipped. `core/REGISTRY.md` had written the consequence down
    and enforced it with nothing.
    """
    root = _tree_with(tmp_path, "For .pbip work, dispatch a `bi-developer` subagent.\n")
    names = {f["names"] for f in _scan(root)}
    assert "bi-developer" in names


def test_a_dispatch_to_a_real_agent_is_not_reported(tmp_path):
    root = _tree_with(tmp_path, "Dispatch the `domains-power-platform` subagent.\n")
    names = {f["names"] for f in _scan(root)}
    assert "domains-power-platform" not in names


def test_prose_about_an_agent_is_not_a_dispatch(tmp_path):
    """Only a dispatch counts, the same way a script reference needs an interpreter in
    front of it. A gate that flagged every mention would argue with documents that are
    correct -- including the ones that explain a phantom agent was REMOVED."""
    root = _tree_with(
        tmp_path,
        "The `bi-developer` agent was retired.\n"
        "This section used to name a `bi-developer` subagent and forbid inline work.\n",
    )
    assert not [f for f in _scan(root) if f["names"] == "bi-developer"]


def test_the_scan_reports_the_kind_so_a_reader_knows_what_broke(tmp_path):
    root = _tree_with(tmp_path, "dispatch a `no-such-agent` subagent\n")
    kinds = {f["kind"] for f in _scan(root) if f["names"] == "no-such-agent"}
    assert any("subagent" in k for k in kinds), kinds


def test_the_repository_dispatches_only_agents_it_ships():
    """The live assertion. This is what would have caught `bi-developer` in April."""
    import core.gates.instruction_commands as gate

    phantom = [f for f in gate.unresolved_commands() if "subagent" in str(f["kind"])]
    assert not phantom, f"canonical/ dispatches agents that do not ship: {phantom}"
