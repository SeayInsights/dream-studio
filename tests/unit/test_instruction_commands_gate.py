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
        ("Run: py scripts/resume_from_handoff.py --brief", "scripts/resume_from_handoff.py"),
        ("Run `scripts/lint-artifact.py` on every artifact", "scripts/lint-artifact.py"),
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
