"""WO-GRADER-PROVIDER-NEUTRAL (two-layer rule): the ds-workorder skill text is
de-vendored — it must not name a specific vendor's grader CLI flag.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SKILL_COPIES = (
    "canonical/skills/ds-workorder/SKILL.md",
    ".claude/skills/ds-workorder/SKILL.md",
    "dist/plugin/skills/ds-workorder/SKILL.md",
)


def test_workorder_skill_has_no_provider_flag():
    for rel in _SKILL_COPIES:
        path = REPO / rel
        if not path.is_file():
            continue  # projected copies may be absent in some checkouts
        assert "--print" not in path.read_text(encoding="utf-8"), (
            f"{rel} names a vendor grader CLI flag; the verification plane is "
            "provider-neutral (core.adapters.grader_runner)"
        )
