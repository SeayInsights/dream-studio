"""Every skill mode either has a specialist, or says why it has none.

WHAT THIS IS FOR. `packs.yaml` declares 86 modes. Nine had an agent. The eleven audit
modes sitting beside `quality/accessibility` -- which HAS one -- had none, and nothing in
the repository recorded whether that was a decision or an oversight. A gap nobody wrote
down is indistinguishable from a choice nobody made.

ENFORCE OR DECLARE, the contract this repository already runs on for acceptance criteria,
for security-scan exemptions, and for rules that lost their enforcer. Every mode under
`canonical/skills/**/modes/*/SKILL.md` appears in `canonical/agents/coverage.yml` exactly
once: it either names the agent compiled from it, or carries a written reason it has none.

THE RULE THE DECLARATIONS ARE JUDGED AGAINST. A mode wants an agent when it can answer a
bounded question in isolation -- consultative knowledge another skill could ask something
of. It does not when it owns state, sequence, or a conversation with the operator: a
subagent cannot hold a lifecycle step, because the step IS the caller's process.

This gate does not judge which side of that line a mode falls on -- that is a person's
call and it is recorded in the file. It refuses a mode that has not been placed on either
side, an agent named but not compiled, and a reason too short to be one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "canonical" / "skills"
AGENTS_DIR = REPO_ROOT / "canonical" / "agents"
COVERAGE = AGENTS_DIR / "coverage.yml"

#: Minimum characters for a declared reason. The same floor as `admission.py`'s `--why`
#: and the rule registry's `unenforced:`. One repository, one shape for "I cannot do this,
#: and here is why" -- an author who has satisfied one has satisfied them all.
MIN_REASON = 20


def declared_modes() -> list[dict[str, Any]]:
    import yaml

    data = yaml.safe_load(COVERAGE.read_text(encoding="utf-8")) or {}
    return list(data.get("modes") or [])


def modes_on_disk() -> set[str]:
    out = set()
    for path in SKILLS.rglob("modes/*/SKILL.md"):
        parts = path.relative_to(SKILLS).as_posix().split("/")
        pack = parts[0]
        mode = "/".join(x for x in parts[1:-1] if x != "modes")
        out.add(f"{pack}/{mode}")
    return out


def audit() -> dict[str, Any]:
    rows = declared_modes()
    declared = {str(r.get("mode")) for r in rows}
    on_disk = modes_on_disk()

    problems: list[str] = []
    for mode in sorted(on_disk - declared):
        problems.append(
            f"{mode}: on disk but not in coverage.yml. Name the agent compiled from it, "
            f"or add `no_agent:` saying why it has none."
        )
    for mode in sorted(declared - on_disk):
        problems.append(f"{mode}: in coverage.yml but no such skill on disk.")

    agents = 0
    for row in rows:
        mode = str(row.get("mode"))
        name = str(row.get("agent") or "").strip()
        reason = " ".join(str(row.get("no_agent") or "").split())
        if name and reason:
            problems.append(f"{mode}: declares both an agent and a reason for having none.")
            continue
        if name:
            agents += 1
            if not (AGENTS_DIR / f"{name}.md").is_file():
                problems.append(
                    f"{mode}: names agent {name!r}, which is not compiled. "
                    "Run `py -m integrations.compiler.agents --write`."
                )
            if not str(row.get("installed_skill") or "").strip():
                problems.append(f"{mode}: names an agent but no installed_skill to compile from.")
        elif reason:
            if len(reason) < MIN_REASON:
                problems.append(
                    f"{mode}: the reason for having no agent is {len(reason)} characters; "
                    f"{MIN_REASON} are required, because a reason shorter than that is a shrug."
                )
        else:
            problems.append(f"{mode}: neither an agent nor a reason for having none.")

    return {
        "modes": len(on_disk),
        "with_agent": agents,
        "declared_without": len(rows) - agents,
        "problems": problems,
    }


def main() -> int:
    report = audit()
    if report["modes"] == 0:
        print("[agent-coverage] FAIL - no skill modes found; this gate would pass vacuously")
        return 1

    if report["problems"]:
        print("[agent-coverage] FAIL - a mode is neither answered nor accounted for")
        print()
        for problem in report["problems"]:
            print(f"  {problem}")
        print()
        print("  A gap nobody wrote down is indistinguishable from a choice nobody made.")
        return 1

    print(
        f"[agent-coverage] OK - {report['modes']} mode(s): {report['with_agent']} with a "
        f"specialist, {report['declared_without']} declared without"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
