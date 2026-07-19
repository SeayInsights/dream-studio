"""WO-AUTOACT-A — synthesized skill-description frontmatter for auto-invocation.

Claude Code's native skill auto-invoker matches a skill's ``description`` field
against the user's request. Canonical SKILL.md files ship with only an H1 title
(no frontmatter), so the installer prepends a synthesized ``name`` + ``description``
block (from packs.yaml + mode metadata.yml triggers) to the *top-level* SKILL.md.

The description is loaded into Claude Code's always-on skill-discovery context, so
it must stay concise — one canonical trigger per mode, NOT every alias. The
_MAX_DESC_CHARS bound guards against a regression back to the alias-dump behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from integrations.compiler.claude_code import synthesize_skill_frontmatter
from integrations.installer.claude_code import _collect_skill_dir_ops

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "canonical"
PACKS_YAML = REPO_ROOT / "packs.yaml"

# The description rides in the always-on discovery context; one trigger per mode
# keeps every pack well under this. The alias-dump regression produced 874–1290.
_MAX_DESC_CHARS = 600


def _routable_skill_ids() -> list[str]:
    packs = (yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8")) or {}).get("packs", {})
    ids: list[str] = []
    for pack_key, cfg in packs.items():
        if not isinstance(cfg, dict):
            continue
        sk = cfg.get("skill", pack_key)
        if not sk.startswith("ds-"):
            sk = f"ds-{sk}"
        ids.append(sk)
    return ids


@pytest.mark.parametrize("skill_id", _routable_skill_ids())
def test_synthesized_frontmatter_is_valid_and_concise(skill_id: str) -> None:
    fm = synthesize_skill_frontmatter(
        skill_id, canonical_root=CANONICAL, packs_yaml_path=PACKS_YAML
    )
    assert fm is not None, f"expected frontmatter for routable pack {skill_id}"
    assert fm.startswith("---\n") and fm.rstrip().endswith("---")

    body = fm.split("---\n", 2)[1]
    data = yaml.safe_load(body)
    assert data["name"] == skill_id
    desc = data["description"]
    assert isinstance(desc, str) and desc.strip(), f"{skill_id} needs a non-empty description"
    # when-to-use text plus at least one trigger keyword (triggers carry a colon).
    assert ":" in desc, f"{skill_id} description must embed at least one trigger keyword"
    assert len(desc) <= _MAX_DESC_CHARS, (
        f"{skill_id} description is {len(desc)} chars (> {_MAX_DESC_CHARS}); keep it to one "
        "trigger per mode, not every alias"
    )


def test_non_pack_skill_gets_no_frontmatter() -> None:
    # ds-bootstrap is a special advisory skill, not a routable pack in packs.yaml.
    assert (
        synthesize_skill_frontmatter(
            "ds-bootstrap", canonical_root=CANONICAL, packs_yaml_path=PACKS_YAML
        )
        is None
    )


def test_collect_skill_dir_ops_prepends_frontmatter_top_level_only(tmp_path: Path) -> None:
    skill_dir = CANONICAL / "skills" / "core"
    assert (skill_dir / "SKILL.md").is_file(), "canonical core skill must exist"

    target_dir = tmp_path / "ds-core"
    ops = _collect_skill_dir_ops(skill_dir, target_dir, "ds-core", tmp_path / "backup")
    by_rel = {op.target.relative_to(target_dir).as_posix(): op for op in ops}

    # Top-level SKILL.md gets the synthesized frontmatter.
    top = by_rel["SKILL.md"]
    assert top.source_content is not None
    assert top.source_content.startswith("---\nname: ds-core\n"), top.source_content[:80]
    assert "Use for:" in top.source_content

    # Mode SKILL.md files must NOT get frontmatter (only the pack skill auto-invokes).
    mode_skills = [r for r in by_rel if r.startswith("modes/") and r.endswith("/SKILL.md")]
    assert mode_skills, "core should have mode SKILL.md files"
    for rel in mode_skills:
        content = by_rel[rel].source_content
        if content is not None:
            assert not content.lstrip().startswith(
                "---\nname: ds-"
            ), f"{rel} unexpectedly received pack frontmatter"
