"""ADR system checks (R1, amended by WO 2c60ce5f).

ADR *decision records* are operator-local (the reasoning/thought-process behind the design),
so they live in the file DB docstore, not this repo. The repo hosts only the descriptive
system — the format template + the convention README. These tests validate that template and
guard that no ADR decision body is committed to docs/adr/.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
TEMPLATE = ADR_DIR / "ADR-000-template.md"

# 4-digit ADRs are real decision records; the 3-digit ADR-000 template is excluded.
_ADR_FILE_RE = re.compile(r"^ADR-(\d{4})-[a-z0-9-]+\.md$")

REQUIRED_SECTIONS = (
    "## Context",
    "## Decision",
    "## Consequences",
    "## Breaking changes",
    "## Cross-references",
)


def test_decision_adrs_are_file_db_not_repo():
    """No numbered ADR decision body may be committed to docs/adr/ — they live in the file
    DB docstore (adr/ names). The repo keeps only the template + README."""
    numbered = [p.name for p in ADR_DIR.glob("ADR-*.md") if _ADR_FILE_RE.match(p.name)]
    assert numbered == [], (
        "ADR decision records must live in the operator-local file DB (ds files ... adr/), "
        f"not the repo; found committed under docs/adr/: {sorted(numbered)}"
    )
    # The descriptive system remains in the repo.
    assert TEMPLATE.is_file(), "the ADR format template must remain in the repo"
    assert (ADR_DIR / "README.md").is_file(), "the ADR convention README must remain in the repo"


def test_template_has_all_required_sections():
    """The template carries every required section so authored ADRs inherit them."""
    body = TEMPLATE.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in body, f"ADR template missing section: {section}"
    assert (
        "| ---" in body.split("## Breaking changes", 1)[1]
    ), "template has no Breaking-changes table"
