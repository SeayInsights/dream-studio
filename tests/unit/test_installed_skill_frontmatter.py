"""The installer must give a pack's SKILL.md the frontmatter that lets it auto-invoke.

Claude Code's native auto-invoker matches a skill's ``description`` against the user's
request. Canonical SKILL.md files ship frontmatter-less on purpose -- one source of truth
is packs.yaml plus metadata.yml -- so the INSTALLER prepends a synthesized block
(WO-AUTOACT-A). A pack installed without it cannot be picked automatically at all; it can
only be invoked by name.

Untested until now, and it is the lane that decides whether a skill fires. It was surfaced
by `untested-fallback` when WO becfca00 touched this module, which is the gate working as
intended: the branch runs only for a frontmatter-less top-level SKILL.md, which is the
condition nobody develops in.

The re-hash inside the branch is asserted too, and it is not incidental (WO-AUTOACT-A-FIX):
an already-installed SKILL.md has the CANONICAL, frontmatter-less hash recorded, so without
re-hashing the prepended content the change-detector compares the canonical hash to the
canonical file, finds them equal, and skips the rewrite -- leaving the installed skill
permanently without a description.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from integrations.installer.claude_code_fileops import _collect_skill_dir_ops

REPO_ROOT = Path(__file__).resolve().parents[2]

# NAMES THE SYMBOLS ON PURPOSE. `untested-fallback` clears a symbol on a textual mention
# anywhere under tests/, and says so about itself: it "proves a name is KNOWN to the tests,
# not that any test enters the branch". The two it flagged here are `_fm` and the re-hashed
# `file_hash` in integrations/installer/claude_code_fileops.py. These tests do enter that
# branch -- they build a frontmatter-less SKILL.md and assert on the prepended content and
# its hash -- so the mention below states what is already true rather than buying silence.


def _ops_for(skill_dir: Path, tmp_path: Path, skill_id: str):
    return _collect_skill_dir_ops(
        skill_dir, tmp_path / "skills" / skill_id, skill_id, tmp_path / "backup"
    )


def _top_level_skill_op(ops):
    return next(op for op in ops if Path(op.target).name == "SKILL.md")


def test_top_level_skill_md_is_installed_with_frontmatter(tmp_path: Path) -> None:
    """A routable pack's SKILL.md arrives with a description, or it never auto-invokes."""
    skill_dir = tmp_path / "canonical" / "ds-project"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-project\n\nBody.\n", encoding="utf-8")

    op = _top_level_skill_op(_ops_for(skill_dir, tmp_path, "ds-project"))

    assert op.source_content is not None
    assert op.source_content.lstrip().startswith("---"), (
        "the installed SKILL.md carries no frontmatter, so Claude Code's auto-invoker has "
        "no description to match and the pack can only be invoked by name"
    )
    assert "description:" in op.source_content.split("---")[1]


def test_the_prepended_content_is_rehashed(tmp_path: Path) -> None:
    """WO-AUTOACT-A-FIX: hashing the canonical file would make the rewrite a no-op."""
    skill_dir = tmp_path / "canonical" / "ds-project"
    skill_dir.mkdir(parents=True)
    canonical = "# ds-project\n\nBody.\n"
    (skill_dir / "SKILL.md").write_text(canonical, encoding="utf-8")

    op = _top_level_skill_op(_ops_for(skill_dir, tmp_path, "ds-project"))

    assert op.source_hash == hashlib.sha256(op.source_content.encode("utf-8")).hexdigest()
    assert op.source_hash != hashlib.sha256(canonical.encode("utf-8")).hexdigest(), (
        "the recorded hash still describes the canonical file, so an already-installed "
        "SKILL.md would be skipped and keep its missing description forever"
    )


def test_an_already_framed_skill_is_left_alone(tmp_path: Path) -> None:
    """The branch is guarded on absence -- a skill that ships its own frontmatter is
    not given a second block."""
    skill_dir = tmp_path / "canonical" / "ds-project"
    skill_dir.mkdir(parents=True)
    already = "---\nname: ds-project\ndescription: mine\n---\n\n# ds-project\n"
    (skill_dir / "SKILL.md").write_text(already, encoding="utf-8")

    op = _top_level_skill_op(_ops_for(skill_dir, tmp_path, "ds-project"))

    assert op.source_content == already
    assert op.source_content.count("description:") == 1


def test_mode_skill_files_are_not_framed(tmp_path: Path) -> None:
    """Only the pack's top-level SKILL.md auto-invokes; modes are reached through it.

    Framing every mode would enter them all into the auto-invoker as competing
    candidates.
    """
    skill_dir = tmp_path / "canonical" / "ds-project"
    (skill_dir / "modes" / "resume").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-project\n", encoding="utf-8")
    (skill_dir / "modes" / "resume" / "SKILL.md").write_text("# resume\n", encoding="utf-8")

    ops = _ops_for(skill_dir, tmp_path, "ds-project")
    mode_op = next(op for op in ops if "modes" in Path(op.target).parts)

    assert mode_op.source_content == "# resume\n"


# ── a skill that declares itself passive must stay out of the auto-invoker ───


def _declares_itself_passive(skill_md: Path) -> bool:
    """True when a SKILL.md says it is not reachable through the Skill tool."""
    head = skill_md.read_text(encoding="utf-8", errors="replace")[:1200].lower()
    return "not user-invocable" in head or "passive context only" in head


def test_a_skill_that_declares_itself_passive_is_not_framed() -> None:
    """Frontmatter is what enters a skill into the auto-invoker, so a passive one must
    not receive any.

    NOT A GAP, WHICH IS THE POINT OF PINNING IT. `ds-bootstrap` installs with no
    frontmatter and that is correct: its own SKILL.md says "Invocation: Passive context
    only — not user-invocable via Skill tool". It is a context document that tells the
    host AI Dream Studio exists; framing it would enter prose into the auto-invoker as a
    candidate competing with real skills, and it would win on requests it cannot serve.

    Pinned because the current exclusion is INCIDENTAL, not declared (WO 54d7a2e2, "make
    the answer visible"): `synthesize_skill_frontmatter` returns None only because
    ds-bootstrap is absent from packs.yaml. Adding it there for any unrelated reason --
    routing, docs, an inventory -- would start framing it, and nothing would say so. This
    test reads the declaration out of the skill itself, so the file that states the
    intent is the file that enforces it.
    """
    from integrations.compiler.claude_code import synthesize_skill_frontmatter

    passive = [
        d
        for d in sorted((REPO_ROOT / "canonical" / "skills").iterdir())
        if (d / "SKILL.md").is_file() and _declares_itself_passive(d / "SKILL.md")
    ]
    assert passive, "no skill declares itself passive — has the declaration been reworded?"

    for skill_dir in passive:
        for skill_id in (skill_dir.name, f"ds-{skill_dir.name}"):
            assert synthesize_skill_frontmatter(skill_id) is None, (
                f"{skill_dir.name} declares itself passive/not user-invocable but would be "
                "installed with frontmatter, which enters it into Claude Code's "
                "auto-invoker as a candidate competing with real skills"
            )


def test_a_routable_pack_is_still_framed() -> None:
    """The positive control. Without it, a synthesizer that returned None for everything
    would satisfy the passive-skill assertion and silently stop every skill
    auto-invoking."""
    from integrations.compiler.claude_code import synthesize_skill_frontmatter

    fm = synthesize_skill_frontmatter("ds-project")
    assert fm and "description:" in fm
