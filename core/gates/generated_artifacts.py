"""Every checked-in artifact with a generator must match what its generator emits.

THE DEFECT THIS EXISTS FOR, three times in one day:

  canonical/review_lanes.yml   A commit deleted 13 gate modules and removed four
                               lanes from this file -- which is GENERATED from
                               scripts/seat_lanes_data.py, and that was never
                               touched. Three weeks later a render restored
                               exactly the 115 deleted lines. The resurrected
                               lanes read as unfinished work and 1,665 lines of
                               detectors were rewritten before the history showed
                               they had been deleted on purpose.

  AGENTS.md                    `check_agents_md_fresh` has existed and worked the
                               whole time. It is in no manifest, so nothing ran it.

  .github/workflows/ci.yml     Not generated, but the same shape: a cull removed a
                               test file and left the reference, and the step
                               failed on a missing path rather than on the change.

An edit to a generated artifact is not a change -- it is a change that will be
silently discarded by the next render, and in the meantime the artifact and its
generator disagree about what is true. The cost is not the drift itself. It is
that the next reader cannot tell a deliberate deletion from an unfinished one.

WHY ONLY THREE ARTIFACTS. 57 checked-in files carry a GENERATED or DO-NOT-EDIT
banner, but only these three name a generator that can actually be run and
compared. The rest assert generation with no reproducible command, so their claim
cannot be checked at all -- and a gate that reported 54 unverifiable banners
would be a wall. They are worth fixing, one at a time, by giving each a real
generator or dropping the banner; `unverifiable_generated_claims()` lists them
for whoever does that, and is deliberately not part of the gate's verdict.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A file claiming to be generated says so with one of these.
_BANNER = re.compile(r"GENERATED|DO NOT EDIT|generated from|Regenerate with", re.IGNORECASE)

_SKIP_PARTS = {".git", "dist", "node_modules", "__pycache__", ".venv", "target"}


def _check_agents_md() -> tuple[bool, str]:
    from integrations.compiler.agents_md import check_agents_md_fresh

    result = check_agents_md_fresh()
    return bool(result.get("ok")), str(result.get("reason") or "")


def _check_review_lanes() -> tuple[bool, str]:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import seat_lanes_data
    finally:
        sys.path.pop(0)

    path = REPO_ROOT / "canonical" / "review_lanes.yml"
    if not path.is_file():
        return False, "canonical/review_lanes.yml is missing"
    expected = seat_lanes_data.render()
    actual = path.read_text(encoding="utf-8")
    if actual == expected:
        return True, "matches its generator"
    return False, "does not match scripts/seat_lanes_data.py -- re-run it, and edit the GENERATOR"


def _check_plugin_dist() -> tuple[bool, str]:
    """dist/plugin's file SET, which is what a stale build actually loses.

    Deliberately not a byte comparison: rebuilding writes 650 files and this gate
    runs before every push. A file that should ship and does not is the failure
    that matters -- two new analyst seats went missing from the plugin this way.
    """
    from integrations.marketplace.plugin_manifest import skill_ids

    out = REPO_ROOT / "dist" / "plugin"
    if not out.is_dir():
        return False, "dist/plugin is missing"
    shipped = {p.name for p in (out / "skills").iterdir()} if (out / "skills").is_dir() else set()
    expected = set(skill_ids())
    missing = sorted(expected - shipped)
    if missing:
        return False, f"dist/plugin is missing skills: {missing}"
    return True, f"{len(shipped)} skill packs shipped"


def _check_agents() -> tuple[bool, str]:
    """The nine bundled subagents, each compiled from its declaration plus its skill.

    An agent's body IS its knowledge now rather than a pointer to it, so a skill edited
    without recompiling leaves a subagent answering from text that has moved on -- the same
    silent staleness the pointer form had, relocated. This is the check that stops it.
    """
    from integrations.compiler.agents import check as _agents_check
    from integrations.compiler.agents import meta_files

    total = len(meta_files())
    if total == 0:
        return False, "no agent declarations found"
    stale = _agents_check()
    if stale:
        return False, f"{len(stale)} of {total} stale: {', '.join(stale)}"
    return True, f"{total} agents match their declarations"


#: (artifact, generator command a human should run, freshness check)
ARTIFACTS: tuple[tuple[str, str, Callable[[], tuple[bool, str]]], ...] = (
    ("AGENTS.md", "py -m integrations.compiler.agents_md --write", _check_agents_md),
    ("canonical/review_lanes.yml", "py scripts/seat_lanes_data.py", _check_review_lanes),
    ("canonical/agents", "py -m integrations.compiler.agents --write", _check_agents),
    (
        "dist/plugin",
        'py -c "from pathlib import Path; from integrations.marketplace.plugin_dist import'
        " build_plugin_dist; build_plugin_dist(Path('dist/plugin'))\"",
        _check_plugin_dist,
    ),
)


def unverifiable_generated_claims(root: Path | None = None) -> list[str]:
    """Files asserting they are generated while naming no runnable generator.

    Reported, never failed on. Each is a real problem -- an unverifiable claim of
    generation is worth no more than no claim -- but there are dozens and fixing
    them is its own piece of work, not a reason to block a push.
    """
    base = root or REPO_ROOT
    known = {a for a, _, _ in ARTIFACTS}
    out = []
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".yml", ".yaml", ".json"}:
            continue
        rel = path.relative_to(base)
        if any(part in _SKIP_PARTS for part in rel.parts):
            continue
        if rel.as_posix() in known:
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:600]
        except OSError:
            continue
        if _BANNER.search(head):
            out.append(rel.as_posix())
    return sorted(out)


def run() -> dict:
    stale: list[dict] = []
    checked: list[str] = []
    for artifact, command, check in ARTIFACTS:
        try:
            fresh, detail = check()
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is a finding
            stale.append(
                {"artifact": artifact, "command": command, "detail": f"{type(exc).__name__}: {exc}"}
            )
            continue
        checked.append(artifact)
        if not fresh:
            stale.append({"artifact": artifact, "command": command, "detail": detail})
    return {
        "status": "fail" if stale else "pass",
        "checked": checked,
        "stale": stale,
        "unverifiable_claims": len(unverifiable_generated_claims()),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify every checked-in artifact that has a generator still matches it."
    )
    parser.add_argument(
        "--list-unverifiable",
        action="store_true",
        help="List files claiming to be generated while naming no runnable generator.",
    )
    args = parser.parse_args(argv)

    if args.list_unverifiable:
        for rel in unverifiable_generated_claims():
            print(rel)
        return 0

    result = run()
    if result["status"] == "fail":
        print(json.dumps(result, indent=2, sort_keys=True))
        print("", file=sys.stderr)
        for item in result["stale"]:
            print(
                f"generated-artifacts: {item['artifact']} does not match its generator."
                f"\n  {item['detail']}"
                f"\n  Regenerate: {item['command']}"
                f"\n  Then EDIT THE GENERATOR, not the artifact -- an edit to the artifact is"
                " discarded by the next render.",
                file=sys.stderr,
            )
        return 1
    print(
        f"generated-artifacts: OK - {len(result['checked'])} artifact(s) match their generators"
        f" ({result['unverifiable_claims']} other files claim generation with no runnable"
        " command; see --list-unverifiable)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
