"""How a skill mode can be entered, and which ones cannot be.

WHAT "DEAD" MEANS HERE, AND WHY IT IS NOT USAGE. The obvious test is "has anyone run
it", and that data does not exist: skill-usage telemetry is written by a hook, the hook
only fires on an installed runtime, and the spool on a developer machine holds gate
events and nothing else. A detector built on absent telemetry would report every skill
dead, which is the reported-clean-by-not-looking shape inverted.

So this asks a question the repository can answer from itself: **is there any route in?**
A mode is reachable when at least one of three things is true.

  trigger  an operator word routes to it -- it reaches the generated routing table
  agent    a compiled subagent carries it, so a dispatch can select it
  cli      its pack is entered through a `ds` command group
  pack     its own pack's SKILL.md routes to it by name

A mode with none of the three can only be run by a human typing its exact name, which
means nothing in the product can ever lead them to it.

WHAT THIS FOUND. 18 of 72 modes declared no `triggers:` in metadata.yml and documented
them in the SKILL.md `## Trigger` section instead -- including `security/scan`, the front
door of the entire security pack, whose section reads ``scan:``, ``scan org:``. The
router read only metadata.yml, so those eighteen were written down and unreachable.
Teaching the router to read the documented section took the unreachable set from 18 to
10.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "canonical" / "skills"
COVERAGE = REPO_ROOT / "canonical" / "agents" / "coverage.yml"

#: A pack whose modes are entered through a `ds` command group rather than a trigger.
#: `ds-workorder/start` is reached by `ds work-order start`; it needs no trigger word,
#: and calling it unreachable would be the detector not knowing how the product works.
PACK_TO_CLI_GROUP = {
    "ds-project": "project",
    "ds-workorder": "work-order",
    "analyze": "analyze",
    "setup": "install",
}


def _routed_names() -> set[str]:
    from interfaces.cli.generate_routing import collect_skills

    return {s["name"] for s in collect_skills(SKILLS_DIR)}


def _agented_modes() -> set[str]:
    import yaml

    if not COVERAGE.is_file():
        return set()
    data = yaml.safe_load(COVERAGE.read_text(encoding="utf-8")) or {}
    rows = data.get("modes") or data.get("agents") or []
    return {r["mode"] for r in rows if isinstance(r, dict) and r.get("agent")}


def _cli_groups() -> set[str]:
    """The command groups `ds` actually exposes, read from its own help.

    Read rather than listed, so a group removed from the CLI stops counting as a route
    without anyone remembering to edit a constant here.
    """
    try:
        help_text = subprocess.run(
            [sys.executable, "-m", "interfaces.cli.ds", "--help"],
            capture_output=True,
            text=True,
            # Explicit, because the platform codec would raise in subprocess's reader
            # thread and hand this function returncode=0 with stdout=None -- which reads
            # as "the CLI exposes no groups" and would report every CLI-backed mode
            # unreachable. The locale-decode gate caught exactly this.
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(REPO_ROOT),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    head = help_text.split("\n\n", 1)[0]
    return set(re.findall(r"[{,]([a-z][a-z-]+)", head))


def _pack_routed_modes() -> set[str]:
    """Modes their own pack's SKILL.md dispatches to, by `modes/<name>/SKILL.md`.

    THE FOURTH ROUTE, and the detector was wrong without it. `ds-website` carries a Mode
    Routing Table naming all nine of its sub-modes with their own trigger words --

        | discover | `discover:` … | `modes/discover/SKILL.md` |
        | animate  | `animate:`  … | `modes/animate/SKILL.md`  |

    -- so `website/animate` is reachable: the operator says `animate:` and the pack
    dispatches. Counting only triggers, agents and CLI groups reported ten such modes as
    having no way in, which would have read as "these are dead" when they are the ordinary
    way a pack with sub-modes works.

    It became visible only when `website` and `fullstack` stopped living inside the
    `domains` tree: at three levels deep their modes did not match the `*/modes/*` glob at
    all, so eleven modes were not merely unreachable, they were uncounted.
    """
    routed: set[str] = set()
    for pack_skill in SKILLS_DIR.glob("*/SKILL.md"):
        pack = pack_skill.parent.name
        try:
            body = pack_skill.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r"modes/([a-z0-9-]+)/SKILL\.md", body):
            routed.add(f"{pack}/{match.group(1)}")
    return routed


def routes() -> list[dict[str, Any]]:
    """Every mode with the routes into it, `routes` empty when there are none."""
    routed = _routed_names()
    agented = _agented_modes()
    groups = _cli_groups()
    pack_routed = _pack_routed_modes()

    out: list[dict[str, Any]] = []
    for skill_md in sorted(SKILLS_DIR.glob("*/modes/*/SKILL.md")):
        pack = skill_md.parent.parent.parent.name
        mode = skill_md.parent.name
        key = f"{pack}/{mode}"
        ways: list[str] = []
        if mode in routed or key in routed:
            ways.append("trigger")
        if key in agented:
            ways.append("agent")
        if PACK_TO_CLI_GROUP.get(pack) in groups:
            ways.append("cli")
        if key in pack_routed:
            ways.append("pack")
        out.append({"mode": key, "pack": pack, "routes": ways})
    return out


def unreachable() -> list[str]:
    """Modes nothing in the product can lead an operator to."""
    return [row["mode"] for row in routes() if not row["routes"]]
