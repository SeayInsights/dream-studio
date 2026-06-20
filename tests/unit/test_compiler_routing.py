"""Tests for WS 8c-2: Compiler reads packs.yaml dynamically."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _get_build_routing_table():
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from integrations.compiler.claude_code import _build_routing_table

    return _build_routing_table


def _get_compile_pack():
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from integrations.compiler.claude_code import compile_pack

    return compile_pack


# ── Routing table generation ──────────────────────────────────────────────────


def test_build_routing_table_reads_packs_yaml_and_produces_one_row_per_pack(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  core:\n    description: Build lifecycle\n    skill: core\n    modes: [think, plan]\n"
        "  quality:\n    description: Code quality\n    skill: quality\n    modes: [debug, pr-security-scan]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-core" in result
    assert "ds-quality" in result
    # One row per pack (count pipes)
    rows = [
        l for l in result.splitlines() if l.startswith("|") and "Pack" not in l and "----" not in l
    ]
    assert len(rows) == 2


def test_ds_core_row_contains_build_plan_think_keywords(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  core:\n    description: Build lifecycle\n    skill: core\n    modes: [think, plan, build]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "think" in result
    assert "plan" in result
    assert "build" in result


def test_ds_quality_row_contains_pr_security_scan_not_secure(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  quality:\n    description: Code quality\n    skill: quality\n"
        "    modes: [debug, polish, harden, pr-security-scan, structure-audit, learn, coach, audit]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "pr-security-scan" in result
    # The old name should NOT appear
    lines = [l for l in result.splitlines() if "ds-quality" in l]
    for line in lines:
        assert "quality:secure" not in line


def test_ds_website_present_as_top_level_pack(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  website:\n    description: Website builder\n    skill: ds-domains-website\n"
        "    skill_path: canonical/skills/domains/modes/website\n"
        "    modes: [discover, page, prototype]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-domains-website" in result


def test_ds_fullstack_present_as_top_level_pack(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  fullstack:\n    description: Fullstack builder\n    skill: ds-domains-fullstack\n"
        "    skill_path: canonical/skills/domains/modes/fullstack\n"
        "    modes: [frontend, backend, integrate, secure]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-domains-fullstack" in result


def test_ds_domains_does_not_handle_website_fullstack_as_modes(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  domains:\n    description: Domain builders\n    skill: domains\n"
        "    modes: [game-dev, saas-build, mcp-build]\n"
        "  website:\n    description: Website builder\n    skill: ds-domains-website\n"
        "    modes: [discover, page]\n"
        "  fullstack:\n    description: Fullstack builder\n    skill: ds-domains-fullstack\n"
        "    modes: [frontend, backend]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    # domains row should not contain website or fullstack mode keywords
    domain_rows = [
        l
        for l in result.splitlines()
        if "ds-domains`" in l and "website" not in l.split("`ds-domains`")[0]
    ]
    for row in domain_rows:
        assert "website:" not in row
        assert "fullstack:" not in row


def test_ds_setup_present(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  setup:\n    description: Platform setup\n    skill: ds-setup\n"
        "    modes: [wizard, status, jit]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-setup" in result


def test_ds_project_present(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  ds-project:\n    description: Project scoping\n    skill: ds-project\n"
        "    modes: [scope]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-project" in result


def test_new_pack_appears_after_adding_to_packs_yaml(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  core:\n    description: Build lifecycle\n    skill: core\n    modes: [think]\n"
        "  new-pack:\n    description: New capability\n    skill: new-pack\n    modes: [alpha, beta]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-new-pack" in result
    assert "alpha" in result


def test_renamed_pack_uses_new_name(tmp_path):
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  renamed-pack:\n    description: Renamed capability\n    skill: renamed-pack\n    modes: [foo]\n"
    )
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "ds-renamed-pack" in result
    assert "ds-old-name" not in result


# ── Compiler output structure ─────────────────────────────────────────────────


def test_compiled_claude_md_contains_begin_auto_routing_marker():
    compile_pack = _get_compile_pack()
    pack = compile_pack()
    claude_md = pack["files"]["CLAUDE.md"]
    assert "<!-- BEGIN AUTO-ROUTING -->" in claude_md


def test_compiled_claude_md_contains_end_auto_routing_marker():
    compile_pack = _get_compile_pack()
    pack = compile_pack()
    claude_md = pack["files"]["CLAUDE.md"]
    assert "<!-- END AUTO-ROUTING -->" in claude_md


def test_content_between_markers_is_agents_md_import():
    # Phase 20: CLAUDE.md no longer embeds the table — markers carry the @AGENTS.md
    # import; the generated table lives in AGENTS.md.
    compile_pack = _get_compile_pack()
    pack = compile_pack()
    claude_md = pack["files"]["CLAUDE.md"]
    begin = "<!-- BEGIN AUTO-ROUTING -->"
    end = "<!-- END AUTO-ROUTING -->"
    begin_idx = claude_md.find(begin)
    end_idx = claude_md.find(end)
    between = claude_md[begin_idx + len(begin) : end_idx]  # noqa: E203
    assert "@AGENTS.md" in between, "markers must carry the @AGENTS.md import"
    assert "<!-- ROUTING TABLE GENERATED BY COMPILER -->" not in between
    # The actual table is generated into AGENTS.md.
    from integrations.compiler.agents_md import build_agents_md

    assert "| Pack | Skill | Mode keywords |" in build_agents_md()


def test_adapter_projection_source_contains_placeholder_not_hardcoded_table():
    projection_path = REPO_ROOT / "adapter-projections" / "claude" / "CLAUDE.md"
    content = projection_path.read_text(encoding="utf-8")
    assert "<!-- ROUTING TABLE GENERATED BY COMPILER -->" in content
    # Should NOT contain a hardcoded pack routing table inline
    lines = content.splitlines()
    table_rows = [l for l in lines if l.startswith("| ") and "Pack" not in l and "----" not in l]
    assert len(table_rows) == 0, f"Hardcoded table rows found: {table_rows}"


# ── metadata.yml triggers integration ────────────────────────────────────────


def test_metadata_yml_triggers_override_mode_name(tmp_path):
    """If metadata.yml has triggers: list, those keywords replace the mode name."""
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  ds-project:\n    description: Project\n    skill: ds-project\n"
        "    modes: [resume]\n"
    )
    # Create metadata.yml with custom triggers
    meta_dir = tmp_path / "skills" / "ds-project" / "modes" / "resume"
    meta_dir.mkdir(parents=True)
    (meta_dir / "metadata.yml").write_text('triggers:\n  - "start building:"\n  - "what next:"\n')
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert (
        "start building" in result
    ), f"Expected 'start building' from metadata.yml triggers, got: {result}"


def test_mode_with_no_metadata_uses_mode_name_as_keyword(tmp_path):
    """If no metadata.yml exists for a mode, the mode name itself becomes the keyword."""
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  core:\n    description: Build lifecycle\n    skill: core\n"
        "    modes: [think, plan]\n"
    )
    # No metadata.yml created — should fall back to mode names
    build_routing_table = _get_build_routing_table()
    result = build_routing_table(tmp_path, packs_yaml)
    assert "think:" in result, f"Expected mode name 'think:' as fallback keyword, got: {result}"
    assert "plan:" in result


def test_ds_project_row_contains_scope_and_resume_keywords():
    """The generated AGENTS.md routing table for ds-project must include scope + resume."""
    from integrations.compiler.agents_md import build_agents_md

    agents_md = build_agents_md()
    assert "scope" in agents_md, "routing table missing 'scope' for ds-project"
    assert "resume" in agents_md, "routing table missing 'resume' for ds-project"


def test_ds_project_resume_triggers_from_metadata_yml():
    """Generated AGENTS.md routing table contains 'start building' from resume metadata.yml."""
    from integrations.compiler.agents_md import build_agents_md

    assert (
        "start building" in build_agents_md()
    ), "routing table should include 'start building' trigger from resume metadata.yml"


def test_meta_pack_uses_workflow_keyword_not_meta(tmp_path):
    """Meta pack (no modes) reads pack-level metadata.yml for triggers — must emit 'workflow:' not 'meta:'."""
    build_routing = _get_build_routing_table()
    # Build minimal packs.yaml with only the meta pack
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text(
        "schema_version: 2\npacks:\n"
        "  meta:\n"
        "    description: Test\n"
        "    skill: workflow\n"
        "    skill_path: canonical/skills/workflow\n",
        encoding="utf-8",
    )
    # Create pack-level metadata.yml with workflow triggers
    skill_dir = tmp_path / "canonical" / "skills" / "workflow"
    skill_dir.mkdir(parents=True)
    (skill_dir / "metadata.yml").write_text(
        'triggers:\n  - "workflow:"\n  - "run workflow:"\n', encoding="utf-8"
    )
    canonical_root = tmp_path / "canonical"
    result = build_routing(canonical_root, packs_yaml)
    assert "workflow:" in result, f"Expected 'workflow:' in routing table, got: {result}"
    assert "meta:" not in result, f"'meta:' must not appear in routing table row, got: {result}"


def test_meta_pack_workflow_keyword_in_live_compile():
    """Generated AGENTS.md routing table contains 'workflow:' for the meta/workflow pack."""
    from integrations.compiler.agents_md import build_agents_md

    assert (
        "workflow:" in build_agents_md()
    ), "routing table should include 'workflow:' trigger from workflow pack-level metadata.yml"
