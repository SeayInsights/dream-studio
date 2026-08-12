"""WO-GRADER-PROVIDER-NEUTRAL (two-layer rule) + gap 3f935dbc: the ds-workorder skill text
is de-vendored — it must not name a specific vendor's grader CLI flag OR describe the grader
in vendor-named terms. The verification plane is provider-neutral (core.adapters.grader_runner
+ config.grader_profiles), so the skill copies must not reintroduce vendor-grader phrasing.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SKILL_COPIES = (
    "canonical/skills/ds-workorder/SKILL.md",
    ".claude/skills/ds-workorder/SKILL.md",
    "dist/plugin/skills/ds-workorder/SKILL.md",
)

# Grader-specific vendor phrasings the skill must not contain. Deliberately narrow so it
# catches vendor-grader language without flagging legitimate mentions (the `--target
# claude|codex` adapter packet, or a `CLAUDE.md` file reference).
_FORBIDDEN_GRADER_PHRASES = (
    "--print",  # the vendor one-shot flag
    "claude grader",  # "claude grader CLI" / "the claude grader"
    "claude` grader",  # "the `claude` grader CLI"
    'which("claude")',  # shutil.which("claude") availability gate
    "claude-less",  # "claude-less CI runner"
)


def test_workorder_skill_is_devendored():
    for rel in _SKILL_COPIES:
        path = REPO / rel
        if not path.is_file():
            continue  # projected copies may be absent in some checkouts
        text = path.read_text(encoding="utf-8")
        for phrase in _FORBIDDEN_GRADER_PHRASES:
            assert phrase not in text, (
                f"{rel} contains vendor-grader phrasing {phrase!r}; the verification plane is "
                "provider-neutral (core.adapters.grader_runner + config.grader_profiles)"
            )
