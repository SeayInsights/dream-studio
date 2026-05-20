"""Tests for WS 8c-4: Documentation Overhaul."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

README = REPO_ROOT / "README.md"
SCHEMA_DOC = REPO_ROOT / "docs" / "schema" / "README.md"
SKILLS_GUIDE = REPO_ROOT / "docs" / "authoring" / "skills.md"

# ── README.md ─────────────────────────────────────────────────────────────────

REQUIRED_README_SECTIONS = [
    "## Architecture Overview",
    "## Quick Start",
    "## CLI Reference",
    "## How a Build Works",
    "## Directory Structure",
    "## Skill Packs",
    "## Adding a New AI Tool Target",
    "## Development and Testing",
    "## ",  # at least 9 sections total — any 9th ##
]

REQUIRED_README_HEADERS = [
    "## Architecture Overview",
    "## Quick Start",
    "## CLI Reference",
    "## How a Build Works",
    "## Directory Structure",
    "## Skill Packs",
    "## Adding a New AI Tool Target",
    "## Development and Testing",
]


def test_readme_exists():
    assert README.is_file(), f"README.md not found at {README}"


def test_readme_contains_all_required_sections():
    content = README.read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_README_HEADERS if s not in content]
    assert missing == [], f"README.md missing sections: {missing}"


def test_readme_has_at_least_nine_level2_sections():
    content = README.read_text(encoding="utf-8")
    sections = [l for l in content.splitlines() if l.startswith("## ")]
    assert len(sections) >= 9, f"README.md has only {len(sections)} ## sections (need ≥9)"


def test_readme_does_not_contain_skills_path_without_canonical():
    content = README.read_text(encoding="utf-8")
    lines = content.splitlines()
    bad_lines = [
        l
        for l in lines
        if "skills/" in l
        and "canonical/skills/" not in l
        and "ds-bootstrap/SKILL" not in l
        and not l.strip().startswith("#")
    ]
    # Allow references that clearly are user-facing (like ~/.claude/skills/)
    truly_bad = [
        l
        for l in bad_lines
        if "skills/" in l
        and "canonical/" not in l
        and ".claude" not in l
        and "canonical/skills" not in l
    ]
    assert truly_bad == [], f"README.md has bare skills/ references: {truly_bad}"


def test_readme_does_not_contain_interfaces_adapters():
    content = README.read_text(encoding="utf-8")
    assert "interfaces/adapters" not in content


def test_readme_does_not_call_product_a_plugin():
    content = README.read_text(encoding="utf-8").lower()
    # "is a plugin" or "it's a plugin" would be the wrong identity claim
    # "not a plugin" is the correct negation and must be allowed
    assert "is a plugin" not in content, "README.md describes product as 'a plugin'"
    assert "it's a plugin" not in content


def test_readme_size_greater_than_5000_bytes():
    size = README.stat().st_size
    assert size > 5000, f"README.md is only {size} bytes (need > 5000)"


# ── docs/schema/README.md ─────────────────────────────────────────────────────


def test_schema_doc_exists():
    assert SCHEMA_DOC.is_file(), f"docs/schema/README.md not found at {SCHEMA_DOC}"


def test_schema_doc_mentions_ds_projects():
    content = SCHEMA_DOC.read_text(encoding="utf-8")
    assert "ds_projects" in content


def test_schema_doc_mentions_ds_work_orders():
    content = SCHEMA_DOC.read_text(encoding="utf-8")
    assert "ds_work_orders" in content


def test_schema_doc_mentions_ds_design_briefs():
    content = SCHEMA_DOC.read_text(encoding="utf-8")
    assert "ds_design_briefs" in content


# ── docs/authoring/skills.md ──────────────────────────────────────────────────


def test_skills_guide_exists():
    assert SKILLS_GUIDE.is_file(), f"docs/authoring/skills.md not found at {SKILLS_GUIDE}"


def test_skills_guide_contains_gate_artifact_section():
    content = SKILLS_GUIDE.read_text(encoding="utf-8")
    assert "gate artifact" in content.lower() or "Gate Artifact" in content


# ── None of the three docs contain quality:secure ────────────────────────────


def test_readme_does_not_contain_quality_secure():
    content = README.read_text(encoding="utf-8")
    assert "quality:secure" not in content


def test_schema_doc_does_not_contain_quality_secure():
    content = SCHEMA_DOC.read_text(encoding="utf-8")
    assert "quality:secure" not in content


def test_skills_guide_does_not_contain_quality_secure():
    content = SKILLS_GUIDE.read_text(encoding="utf-8")
    assert "quality:secure" not in content
