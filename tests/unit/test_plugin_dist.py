"""WO 90a13043: the synthesized plugin artifact is loadable and matches the authoritative
routable skill surface.

The canonical skills ship frontmatter-less, so a raw github-source install can't load them.
build_plugin_dist assembles a real plugin root (synthesized frontmatter + agents + .mcp.json +
manifest) that the marketplace git-subdir source resolves. The skill set is the packs.yaml
ROUTABLE set (the user-facing surface); ds-bootstrap — a passive, non-invocable system
component — is intentionally excluded.
"""

from __future__ import annotations

import json
from pathlib import Path

from integrations.marketplace.plugin_dist import build_plugin_dist, skill_source_dirs
from integrations.marketplace.plugin_manifest import (
    PLUGIN_COMPONENTS,
    skill_ids,
    validate_marketplace_manifest,
    validate_plugin_manifest_component_delivery,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_built_plugin_matches_routable_surface_and_is_loadable(tmp_path: Path):
    out = tmp_path / "plugin"
    build_plugin_dist(out, repo_root=REPO_ROOT)

    # Skill set == the authoritative routable pack surface (packs.yaml), no more, no less.
    built_skills = {p.name for p in (out / "skills").iterdir() if p.is_dir()}
    assert built_skills == set(
        skill_ids()
    ), f"built skills must equal the routable surface; diff={built_skills ^ set(skill_ids())}"

    # ds-bootstrap is a non-routable system component — never shipped as a plugin skill.
    assert "ds-bootstrap" not in built_skills

    # Every skill is loadable: its top SKILL.md carries synthesized YAML frontmatter.
    for skill in built_skills:
        text = (out / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.lstrip().startswith("---"), f"{skill}/SKILL.md missing frontmatter"
        assert f"name: {skill}" in text, f"{skill}/SKILL.md frontmatter missing its name"

    # Every declared component is delivered at the built plugin root.
    manifest = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    problems = validate_plugin_manifest_component_delivery(manifest, out)
    assert problems == [], f"undelivered components: {problems}"

    # Agents + MCP payload present.
    assert list((out / "agents").glob("*.md")), "no agent cards materialized"
    assert (out / ".mcp.json").is_file()


def test_bootstrap_is_the_only_routable_exclusion():
    """ds-bootstrap is the sole installed-canonical skill excluded from the routable surface,
    and it declares itself non-invocable — the documented reason it is excluded."""
    source_map = skill_source_dirs()
    assert "ds-bootstrap" not in source_map, "ds-bootstrap must not be a routable plugin skill"
    bootstrap = (REPO_ROOT / "canonical" / "skills" / "ds-bootstrap" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "not user-invocable" in bootstrap.lower()


def test_marketplace_source_is_git_subdir():
    """The committed marketplace resolves the plugin from the synthesized dist/plugin subdir."""
    marketplace = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert validate_marketplace_manifest(marketplace) == []
    src = marketplace["plugins"][0]["source"]
    assert src["source"] == "git-subdir" and src["path"] == "dist/plugin"


def test_declared_components_are_the_deliverable_set():
    """commands is not declared — Dream Studio ships no top-level commands (skills replace them)."""
    assert "commands" not in PLUGIN_COMPONENTS
    assert set(PLUGIN_COMPONENTS) == {"agents", "skills", ".mcp.json"}
