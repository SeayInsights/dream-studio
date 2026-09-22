"""A skill's imports reach the agent, not just the skill.

WHY THE COMPILER EXISTS AT ALL. Every bundled agent used to be a persona plus "your full
set of patterns is in `~/.claude/skills/<file>`. Read it completely before responding" —
an instruction, not a mechanism. Nothing made a subagent read the file, and when it did
not, the answer came from general knowledge, fluent and indistinguishable from a good one.
The fix was to inline the skill at build time.

IT STOPPED ONE LEVEL SHORT. A skill that carries its own `## Imports` list naming sibling
reference documents left those dangling — by RELATIVE paths, which resolve from the
skill's directory and mean nothing from `canonical/agents/` where the compiled agent
stands. `domains/power-platform` imports three `powerbi/*.md` files holding the DAX,
M-query and TMDL rules. Measured before this: `CALCULATE` appeared **0 times** in that
agent, while the skill told it to read `../../powerbi/dax-patterns.md`.
"""

from __future__ import annotations

import pathlib
import re

from integrations.compiler.agents import _coverage, build_agent

SKILLS = pathlib.Path("canonical/skills")


def _rows_with_imports():
    out = []
    for row in _coverage():
        skill = SKILLS / row["skill"]
        if not skill.is_file():
            continue
        body = skill.read_text(encoding="utf-8", errors="replace")
        imports = re.findall(r"^[-*]\s+(\.\.?/[^\s`]+\.md)", body, re.MULTILINE)
        resolved = [(rel, (skill.parent / rel).resolve()) for rel in imports]
        resolved = [(rel, p) for rel, p in resolved if p.is_file()]
        if resolved:
            out.append((row, skill, resolved))
    return out


def test_at_least_one_skill_imports_something():
    """Guard the guard: if no skill imports anything, every case below is vacuous — the
    exact shape this repository keeps finding."""
    assert _rows_with_imports(), "no skill names a resolvable import; has the layout moved?"


def test_every_imported_document_is_inlined_into_the_agent():
    for row, _skill, resolved in _rows_with_imports():
        agent = build_agent(row)
        for rel, target in resolved:
            assert rel in agent, f"{row['agent']} does not name its import {rel}"
            # A NAME IS NOT THE CONTENT. The relative path was always printed; what was
            # missing is the document behind it.
            sample = _distinctive_line(target)
            assert sample in agent, (
                f"{row['agent']} names {rel} but does not carry its content"
                f" (looked for {sample!r}) — the agent is told to read a file it cannot"
                " reach from canonical/agents/"
            )


def _distinctive_line(path: pathlib.Path) -> str:
    """A line long enough to be unique to that document."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if len(stripped) > 40 and not stripped.startswith(("#", "-", "|", ">")):
            return stripped[:60]
    raise AssertionError(f"no distinctive line found in {path}")


def test_the_power_platform_agent_carries_its_dax_rules():
    """The measured case, named so a regression says what broke rather than which
    assertion failed."""
    row = next(r for r in _coverage() if r["agent"] == "domains-power-platform")
    agent = build_agent(row)
    assert "CALCULATE" in agent, "the DAX reference is not inlined"
    assert "Imported by that skill" in agent
