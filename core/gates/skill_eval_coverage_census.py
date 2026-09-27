"""Gate: every skill's declared output has a coverage decision on record (E19).

WHY THIS EXISTS. `docs/contracts/skill-contract.md` requires every active skill to declare
an "output contract". A 2026-09-26 manual inventory found 104 `canonical/skills/**/SKILL.md`
files, of which only 4 had ANY behavioral test verifying their declared output actually
does what it says (`tests/evals/test_skill_contract_evals.py`). PR #828 raised that to 17 by
hand, and a follow-on pass (PR #830) gave 16 previously-undeclared skills a real output
section. Both passes were one-time, manual audits -- nothing re-ran them, and nothing would
have noticed the 105th skill someone adds next month shipping with a real, undeclared, or
untested output.

This gate is the "systemic" half: `canonical/skill_eval_registry.json` records, per skill
file, an enforce-or-declare decision -- `no_output` (router/reference/exempt, genuinely
produces nothing of its own), `covered` (a real behavioral test exercises its declared
output, naming which file), or `gap` (a real output exists with no verified test yet --
tracked debt, not a release blocker, the exact ratchet `fail_open_census.py` already uses
for its own baseline: existing gaps are fine, a NEW one is not). The gate's only hard
requirement is that EVERY `canonical/skills/**/SKILL.md` file has SOME entry and that every
`covered` entry's test file(s) actually exist on disk -- a new skill with no entry at all,
or a `covered` claim whose test file was deleted out from under it, is what fails.

WHAT THIS GATE DELIBERATELY DOES NOT DO. It does not try to verify a `covered` claim is
STILL ACCURATE (that the named test still exercises the same behavior, or wasn't gutted to
an empty stub) -- that would need running the test, which this gate (fast, no subprocess,
matching `review_lane_registry.py`'s reasoning) does not do; `test-suite`/`pin-tests`
already run the real suite elsewhere in pre-push. It does not classify a skill file's real
output for you -- that judgment (is this a router? does the "outputs" prose accurately
describe reality?) is exactly what took a human reading each of the 104 files by hand this
session, and a mechanical heuristic re-deriving it would be guessing, not enforcing. A `gap`
entry with a two-line honest reason is worth more than a script inventing a plausible-looking
`covered_by` for a file it never actually understood.

ADVISORY, not blocking. Per the two-tier model (AD-3): this is hygiene/informational, not
correctness/safety/authority-integrity. A skill with a documentation gap does not corrupt
state or break a build; demanding it be closed before every unrelated push would make this
gate the wall the fail-open-census docstring warns against becoming.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "canonical" / "skill_eval_registry.json"
SKILLS_ROOT = REPO_ROOT / "canonical" / "skills"

_VALID_STATUSES = {"no_output", "covered", "gap"}


def _all_skill_files(skills_root: Path = SKILLS_ROOT) -> list[str]:
    if not skills_root.is_dir():
        return []
    return sorted(
        str(p.relative_to(skills_root)).replace("\\", "/") for p in skills_root.rglob("SKILL.md")
    )


def _load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"skills": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"skills": {}}


def run(*, repo_root: Path | str = REPO_ROOT) -> dict[str, Any]:
    root = Path(repo_root)
    skills_root = root / "canonical" / "skills"
    registry = _load_registry(root / "canonical" / "skill_eval_registry.json")
    entries: dict[str, Any] = registry.get("skills", {})

    unregistered: list[str] = []
    malformed: list[dict[str, str]] = []
    stale_covered: list[dict[str, str]] = []
    counts = {"no_output": 0, "covered": 0, "gap": 0}

    for rel in _all_skill_files(skills_root):
        entry = entries.get(rel)
        if entry is None:
            unregistered.append(rel)
            continue

        status = entry.get("status")
        if status not in _VALID_STATUSES:
            malformed.append({"path": rel, "detail": f"unknown status {status!r}"})
            continue

        counts[status] += 1

        if status == "covered":
            covered_by = entry.get("covered_by") or []
            if not covered_by:
                malformed.append({"path": rel, "detail": "status=covered with no covered_by list"})
                continue
            for test_ref in covered_by:
                test_path = root / test_ref.split("::", 1)[0]
                if not test_path.is_file():
                    stale_covered.append(
                        {"path": rel, "detail": f"covered_by file missing: {test_ref}"}
                    )
        elif status == "gap":
            if not entry.get("reason") or len(entry["reason"]) < 20:
                malformed.append(
                    {"path": rel, "detail": "status=gap needs a reason of 20+ characters"}
                )
        elif status == "no_output":
            if not entry.get("reason") or len(entry["reason"]) < 20:
                malformed.append(
                    {"path": rel, "detail": "status=no_output needs a reason of 20+ characters"}
                )

    status = "pass" if not (unregistered or malformed or stale_covered) else "fail"
    return {
        "status": status,
        "total_skills": len(_all_skill_files(skills_root)),
        "counts": counts,
        "unregistered": unregistered,
        "malformed": malformed,
        "stale_covered": stale_covered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", default=None, help="Repo root to check (defaults to this repo)."
    )
    args = parser.parse_args(argv)

    result = run(repo_root=args.repo_root or REPO_ROOT)
    print(json.dumps(result, indent=2))

    if result["status"] == "fail":
        lines = ["skill-eval-coverage-census: FAILED"]
        if result["unregistered"]:
            lines.append(
                f"  {len(result['unregistered'])} skill file(s) with no registry entry: "
                + ", ".join(result["unregistered"][:10])
                + (" ..." if len(result["unregistered"]) > 10 else "")
            )
        for m in result["malformed"]:
            lines.append(f"  malformed entry: {m['path']} -- {m['detail']}")
        for s in result["stale_covered"]:
            lines.append(f"  stale covered_by: {s['path']} -- {s['detail']}")
        lines.append(
            "  Add a canonical/skill_eval_registry.json entry (status: no_output/covered/gap) "
            "for every new skill file, or fix the malformed/stale entry named above."
        )
        print("\n".join(lines), file=sys.stderr)

    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
