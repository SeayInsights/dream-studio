"""WO-P20-MARKETPLACE T1/T2: plugin manifest + namespaced skill IDs."""

from __future__ import annotations

import json
from pathlib import Path

from core.skills.invocation import load_skill_content
from integrations.marketplace.plugin_manifest import (
    MARKETPLACE_REPO,
    PLUGIN_COMPONENTS,
    build_marketplace_manifest,
    build_plugin_manifest,
    namespaced_skill_ids,
    skill_ids,
    validate_manifest,
    validate_marketplace_manifest,
    write_marketplace_manifest,
    write_plugin_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_write_manifests_emit_valid_json_matching_the_generators(tmp_path):
    """WO 433edfa7: write_plugin_manifest / write_marketplace_manifest write to disk exactly
    what their generators produce, as valid JSON."""
    plugin_path = write_plugin_manifest(tmp_path / "plugin.json")
    market_path = write_marketplace_manifest(tmp_path / "marketplace.json")

    assert plugin_path.is_file() and market_path.is_file()
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    market = json.loads(market_path.read_text(encoding="utf-8"))

    assert plugin == build_plugin_manifest()
    assert market == build_marketplace_manifest()
    assert validate_manifest(plugin) == []
    assert validate_marketplace_manifest(market) == []


def test_manifest_valid_and_layout_present():
    """The committed .claude-plugin/plugin.json is valid and the layout is backed
    by real canonical sources + a .mcp.json."""
    manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.is_file(), ".claude-plugin/plugin.json must exist"

    committed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert validate_manifest(committed) == [], f"manifest invalid: {validate_manifest(committed)}"

    # Committed manifest matches the generator (no drift).
    assert committed == build_plugin_manifest(), "plugin.json is stale — regenerate it"

    # Declared component slots + backing sources present.
    assert set(PLUGIN_COMPONENTS) <= set(committed["components"])
    assert (REPO_ROOT / ".mcp.json").is_file(), ".mcp.json must exist for the layout"
    assert (REPO_ROOT / "canonical" / "skills").is_dir(), "skills source must back the layout"
    assert (REPO_ROOT / "canonical" / "agents").is_dir(), "agents source must back the layout"

    # .mcp.json is valid JSON with an mcpServers map (empty is honest — no servers yet).
    mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert "mcpServers" in mcp and isinstance(mcp["mcpServers"], dict)

    # Skill set is non-empty and namespacing is consistent.
    assert skill_ids(), "manifest must declare skills"
    assert namespaced_skill_ids() == [f"dream-studio:{s}" for s in skill_ids()]


def test_marketplace_manifest_public_source_and_parity():
    """WO-REL-PACKAGING T1/T3: the committed marketplace.json resolves the plugin
    from the public canonical repo (never a local path) and stays at parity with the
    generator and the plugin manifest."""
    marketplace_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert marketplace_path.is_file(), ".claude-plugin/marketplace.json must exist"

    committed = json.loads(marketplace_path.read_text(encoding="utf-8"))
    assert (
        validate_marketplace_manifest(committed) == []
    ), f"marketplace.json invalid: {validate_marketplace_manifest(committed)}"

    # Committed marketplace manifest matches the generator (no drift).
    assert committed == build_marketplace_manifest(), "marketplace.json is stale — regenerate it"

    entry = committed["plugins"][0]
    # Public distribution: a hosted git-subdir source pointing at the synthesized plugin root
    # (the raw repo root is not a loadable plugin layout — canonical skills are frontmatter-less).
    assert entry["source"]["source"] == "git-subdir"
    assert MARKETPLACE_REPO in entry["source"]["url"]
    assert entry["source"]["path"] == "dist/plugin"

    # Name + description are at parity with the plugin manifest (single source of truth).
    plugin = build_plugin_manifest()
    assert entry["name"] == plugin["name"]
    assert entry["description"] == plugin["description"]


def test_namespaced_and_bare_ids_resolve():
    """A skill resolves identically via the bare pack id, the bare skill id, and the
    plugin-namespaced id — so marketplace and direct installs invoke the same skill."""
    bare_pack = load_skill_content(specifier="core:build", source_root=REPO_ROOT)
    bare_skill = load_skill_content(specifier="ds-core:build", source_root=REPO_ROOT)
    namespaced = load_skill_content(specifier="dream-studio:ds-core:build", source_root=REPO_ROOT)

    assert bare_pack["ok"], f"bare pack id must resolve: {bare_pack.get('error')}"
    assert bare_skill["ok"], f"bare skill id must resolve: {bare_skill.get('error')}"
    assert namespaced["ok"], f"namespaced id must resolve: {namespaced.get('error')}"

    # All three point at the same SKILL.md.
    assert bare_pack["skill_path"] == bare_skill["skill_path"] == namespaced["skill_path"]

    # A bogus namespace prefix does not smuggle in an unknown skill.
    bad = load_skill_content(specifier="dream-studio:nope:nope", source_root=REPO_ROOT)
    assert bad["ok"] is False
