"""R1 — ADR system drift check.

Every numbered ADR under docs/adr/ (ADR-NNNN-*.md, 4-digit; the ADR-000 template is
excluded) must be listed in the index (docs/adr/README.md) and carry the required
sections, and the index must have no phantom entries. Keeps the human-readable ADR
projection honest. See docs/adr/ADR-0001-record-architecture-decisions.md.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
TEMPLATE = ADR_DIR / "ADR-000-template.md"
INDEX = ADR_DIR / "README.md"

# 4-digit ADRs are real records; the 3-digit ADR-000 template is excluded.
_ADR_FILE_RE = re.compile(r"^ADR-(\d{4})-[a-z0-9-]+\.md$")
_INDEX_LINK_RE = re.compile(r"\[(\d{4})\]\(ADR-\d{4}-[a-z0-9-]+\.md\)")

REQUIRED_SECTIONS = (
    "## Context",
    "## Decision",
    "## Consequences",
    "## Breaking changes",
    "## Cross-references",
)
REQUIRED_META = ("- **Status:**", "- **Date:**", "- **Author:**")


def _numbered_adr_files() -> dict[str, Path]:
    """Map zero-padded ADR number -> file, for every real ADR (excludes the template)."""
    out: dict[str, Path] = {}
    for path in sorted(ADR_DIR.glob("ADR-*.md")):
        match = _ADR_FILE_RE.match(path.name)
        if match:
            out[match.group(1)] = path
    return out


def _indexed_numbers() -> set[str]:
    text = INDEX.read_text(encoding="utf-8")
    return {m.group(1) for m in _INDEX_LINK_RE.finditer(text)}


def test_adr_index_matches_files():
    """Bidirectional: every ADR file is indexed and every indexed ADR has a file;
    every ADR carries all required metadata + sections + a breaking-changes table."""
    files = _numbered_adr_files()
    assert files, "no numbered ADRs found under docs/adr/ (expected at least ADR-0001)"

    indexed = _indexed_numbers()
    file_numbers = set(files)

    missing_from_index = file_numbers - indexed
    assert (
        not missing_from_index
    ), f"ADR files not listed in docs/adr/README.md: {sorted(missing_from_index)}"

    phantom_in_index = indexed - file_numbers
    assert not phantom_in_index, f"index lists ADRs with no file: {sorted(phantom_in_index)}"

    for number, path in files.items():
        body = path.read_text(encoding="utf-8")
        for meta in REQUIRED_META:
            assert meta in body, f"ADR-{number} ({path.name}) missing metadata line: {meta}"
        for section in REQUIRED_SECTIONS:
            assert section in body, f"ADR-{number} ({path.name}) missing section: {section}"
        # Breaking-changes table: a markdown table separator following the section.
        after = body.split("## Breaking changes", 1)[1]
        assert "| ---" in after, f"ADR-{number} ({path.name}) has no Breaking-changes table"


def test_template_has_all_required_sections():
    """The template itself carries every required section so authored ADRs inherit them."""
    body = TEMPLATE.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in body, f"ADR template missing section: {section}"
    assert (
        "| ---" in body.split("## Breaking changes", 1)[1]
    ), "template has no Breaking-changes table"
