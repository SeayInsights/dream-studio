"""WO-P20-MARKETPLACE T1/T2: plugin manifest + namespaced skill IDs."""

from __future__ import annotations

import json
from pathlib import Path

from core.skills.invocation import load_skill_content
from integrations.marketplace.plugin_manifest import (
    PLUGIN_COMPONENTS,
    build_plugin_manifest,
    namespaced_skill_ids,
    skill_ids,
    validate_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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
