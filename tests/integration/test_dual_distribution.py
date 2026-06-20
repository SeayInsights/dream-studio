"""WO-P20-MARKETPLACE T3/T4: direct install and plugin layout are at parity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_direct_and_plugin_install_parity():
    """The plugin's declared skills equal the skills the direct install exposes
    (both derive from packs.yaml + canonical), modulo the plugin namespace."""
    from integrations.compiler.agents_md import build_agents_md
    from integrations.marketplace.plugin_manifest import namespaced_skill_ids, skill_ids

    plugin_skills = skill_ids()
    assert plugin_skills, "plugin must declare skills"

    # Every plugin skill appears in the direct-install routing table (AGENTS.md).
    routing = build_agents_md()
    for sid in plugin_skills:
        assert f"`{sid}`" in routing, f"direct install missing skill {sid} present in plugin"

    # Namespaced ids strip cleanly back to the bare set (functional equivalence).
    stripped = [n.split(":", 1)[1] for n in namespaced_skill_ids()]
    assert stripped == plugin_skills


def test_end_to_end(tmp_path):
    """Generate the manifest fresh, validate it, confirm namespacing + .mcp.json."""
    from core.skills.invocation import load_skill_content
    from integrations.marketplace.plugin_manifest import (
        build_plugin_manifest,
        validate_manifest,
        write_plugin_manifest,
    )

    out = write_plugin_manifest(tmp_path / ".claude-plugin" / "plugin.json")
    assert out.is_file()
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert validate_manifest(manifest) == []
    assert manifest == build_plugin_manifest()

    # Both invocation forms resolve to the same skill (marketplace ⇔ direct).
    a = load_skill_content(specifier="ds-core:build", source_root=REPO_ROOT)
    b = load_skill_content(specifier="dream-studio:ds-core:build", source_root=REPO_ROOT)
    assert a["ok"] and b["ok"] and a["skill_path"] == b["skill_path"]

    # .mcp.json is valid JSON.
    mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert isinstance(mcp.get("mcpServers"), dict)
