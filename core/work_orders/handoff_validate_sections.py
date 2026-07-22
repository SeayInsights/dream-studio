"""WO-SPLIT-HANDOFF: handoff prompt section parsing (leaf module).

Isolated on its own to break the handoff_build <-> handoff_validate cycle:
handoff_build's build_handoff_sections needs parse_prompt_sections indirectly
via self_validate_generated_handoff, while handoff_validate's other modules
need build_handoff_prompt from handoff_build.
"""

from __future__ import annotations
import re


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def parse_prompt_sections(prompt_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in prompt_text.splitlines():
        if line.startswith("## "):
            current = _normalize_heading(line[3:])
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}
