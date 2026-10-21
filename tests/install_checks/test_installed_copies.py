"""Install checks: is what is installed on THIS machine what this checkout would install?

These are not tests of the code. Each asserts a fact about one computer -- the operator's
Claude Code config root and whatever Dream Studio installed there -- so the answer changes
with the machine, not with the commit. They used to live in the unit suite as tests that
read ``~/.claude`` and skipped when it was empty, which meant they could not fail on CI,
failed on a stale install for reasons no change in the diff caused, and passed or skipped
on the same commit depending on who ran them. The code those checks were guarding is
covered by tests that build their own install in a temporary directory (see the
dependency-chain evals, ``test_hook_write_accounting`` and ``test_hook_drift``).

NOT COLLECTED BY DEFAULT. ``tests/conftest.py`` deselects ``install_check`` unless it is
asked for by name::

    py -m pytest -m install_check tests/install_checks

and they FAIL, rather than skip, when the install is absent: the person running this
asked whether the install is right, and "there is no install" is the answer.

The config root is resolved the way Dream Studio resolves it (``CLAUDE_CONFIG_DIR``, else
``~/.claude``), so a second Claude Code identity is checked at its own root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config.paths import claude_config_root

pytestmark = pytest.mark.install_check

REPO_ROOT = Path(__file__).resolve().parents[2]


def _installed(*parts: str) -> Path:
    path = claude_config_root().joinpath(*parts)
    assert path.is_file(), (
        f"{path} does not exist: Dream Studio is not installed at this config root. "
        "Install it with `ds update` (or `ds integrate install`), or do not run the install checks."
    )
    return path


def test_installed_claude_md_carries_the_routing_table():
    """The installed CLAUDE.md names the skill routing, directly or through ``@AGENTS.md``,
    and an ``@AGENTS.md`` import is never left dangling."""
    content = _installed("CLAUDE.md").read_text(encoding="utf-8")
    assert "MANDATORY" in content or "Skill Routing" in content, "CLAUDE.md missing routing markers"
    if "workflow:" in content:
        return
    assert "@AGENTS.md" in content, "workflow: trigger keyword absent from installed CLAUDE.md"
    agents_md = _installed("AGENTS.md").read_text(encoding="utf-8")
    assert "workflow:" in agents_md, "workflow: trigger keyword absent from installed AGENTS.md"


def test_installed_mode_skills_are_complete():
    """Zero mode skills is not an install; one or two is a partial pack."""
    skills_dir = claude_config_root() / "skills"
    mode_skills = list(skills_dir.rglob("modes/*/SKILL.md")) if skills_dir.is_dir() else []
    assert (
        len(mode_skills) >= 3
    ), f"expected at least 3 mode-level SKILL.md files under {skills_dir}, found {len(mode_skills)}"


def test_installed_review_skill_names_the_round_table():
    """The review skill the operator's own sessions read must mention the round table.

    The dispatch rule lives in three places: canonical, the shipped ``dist/plugin``
    projection (both tested against fixtures), and this local install. A subagent
    dispatched through an install that lacks these markers invents a checklist instead of
    convening the table.
    """
    text = _installed("skills", "ds-core", "modes", "review", "SKILL.md").read_text(
        encoding="utf-8", errors="replace"
    )
    missing = [
        marker
        for marker in ("core.gates.round_table", "ASKED OF YOU", "not examined")
        if marker not in text
    ]
    assert not missing, (
        f"the installed review skill is behind canonical and lacks {missing}. "
        "Refresh the install with `ds update`."
    )


def test_installed_hook_copies_match_canonical():
    """Every hook-projection file deployed at the config root, and in this checkout's own
    ``.claude/hooks`` when it has one, matches canonical byte for byte (line endings
    aside). A stale copy runs outdated enforcement; both trees fire."""
    from core.health.doctor_checks import _check_hook_freshness

    trees = [claude_config_root(), REPO_ROOT / ".claude"]
    present = [t for t in trees if (t / "hooks").is_dir()]
    assert present, f"no hook projection at any of {[str(t) for t in trees]}"
    for tree in present:
        result = _check_hook_freshness(REPO_ROOT, tree)
        assert result["ok"], f"the hook projection under {tree} is stale: {result['stale']}"
