"""Gate: a mode's card is checkable, and its vocabulary stays closed.

WHY THIS EXISTS. Every carded mode carries the same nine-field ``dream_studio`` frontmatter
block, and a census on 2026-09-18 found all 51 of them complete. That uniformity was held by
convention alone -- nothing read the block, so nothing noticed when one drifted. Two fields
were missing from the convention entirely:

* ``write_posture`` -- ``capabilities_required`` records what a mode CAN reach, not what it
  may do with it unattended. A mode that lists Bash is either running the test suite or
  deploying, and the card could not tell those apart. The posture names the blast radius:
  ``read-only`` observes, ``independent`` makes reversible changes inside the work boundary,
  ``hitl`` reaches a step the operator approves before it takes effect. The distinction is
  the one Fulcrum's persona charts draw -- opening a pull request is reversible and ungated,
  merging it is not.
* ``lifecycle`` -- packs.yaml shows modes accreting over several phases with no way to mark
  one superseded short of deleting it, which breaks any invocation still naming it.

WHAT IT CHECKS, and why each check is scoped the way it is:

  1. A changed carded mode validates against ``schemas/skill_card.schema.json``.
  2. Its ``skill_id``/``pack``/``mode`` agree with where the file actually sits. A card that
     misreports its own coordinates routes wrong while reading fine.
  3. Every ``inputs`` token is produced by some mode's ``outputs`` or is registered in
     ``canonical/skill_vocabulary.json``. Measured before writing this: 123 of 135 input
     tokens had no producing mode, so requiring a producer outright would have been a wall
     on day one. The registry records those 123 as root inputs -- supplied by the operator,
     the repo or the environment -- and the check becomes a ratchet: a new token is either
     produced by a mode or added to the registry deliberately.
  4. Every pack in packs.yaml declares a non-empty ``invariants`` list. Same enforce-or-
     declare contract canonical/rules.yml runs on, so the repo keeps one contract shape.

DIFF-SCOPED by default. 34 of the 85 modes packs.yaml declares carry no card at all, one of
them (``ds-project:resume``) having no SKILL.md whatsoever. Whole-tree enforcement would
refuse every push until all 34 were authored, which is the shape this repo has twice
declined -- see workflow-node-verification and untested-fallback. Those 34 drain as they are
touched. ``--all`` audits the whole tree on demand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "skill_card.schema.json"
VOCAB_PATH = REPO_ROOT / "canonical" / "skill_vocabulary.json"
PACKS_PATH = REPO_ROOT / "packs.yaml"

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _changed_card_files(base_ref: str | None = None) -> set[str]:
    """SKILL.md paths this change set touches, staged, committed or untracked.

    Untracked files are included because ``git diff`` never reports one and a newly authored
    card is exactly what this gate most needs to see.
    """
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF") or "origin/main"
    paths: set[str] = set()
    for argv in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            name = line.strip().replace(chr(92), "/")
            if name.endswith("SKILL.md"):
                paths.add(name)
    return paths


def _mode_dir(pack: str, info: dict) -> Path:
    if info.get("skill_path"):
        return REPO_ROOT / info["skill_path"] / "modes"
    return REPO_ROOT / "canonical" / "skills" / pack / "modes"


def _card(path: Path) -> dict | None:
    """The ``dream_studio`` block of a SKILL.md, or None when the file carries no card."""
    try:
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return None
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    card = (data or {}).get("dream_studio") if isinstance(data, dict) else None
    return card if isinstance(card, dict) else None


def _all_cards() -> list[tuple[str, str, Path, dict]]:
    """Every (pack, mode, path, card) packs.yaml declares that carries a card."""
    packs = (yaml.safe_load(PACKS_PATH.read_text(encoding="utf-8")) or {}).get("packs", {})
    found: list[tuple[str, str, Path, dict]] = []
    for pack, info in packs.items():
        for mode in info.get("modes", []) or []:
            path = _mode_dir(pack, info) / mode / "SKILL.md"
            card = _card(path) if path.is_file() else None
            if card is not None:
                found.append((pack, mode, path, card))
    return found


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace(chr(92), "/")
    except ValueError:
        return str(path)


def _root_inputs() -> set[str]:
    try:
        return set(json.loads(VOCAB_PATH.read_text(encoding="utf-8")).get("root_inputs", []))
    except (OSError, json.JSONDecodeError):
        return set()


def run(base_ref: str | None = None, *, scope_all: bool = False) -> dict:
    """Validate the cards in scope and report every offender."""
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    cards = _all_cards()
    produced = {token for _, _, _, c in cards for token in (c.get("outputs") or [])}
    known_inputs = produced | _root_inputs()

    if scope_all:
        in_scope = cards
    else:
        changed = _changed_card_files(base_ref)
        in_scope = [c for c in cards if _rel(c[2]) in changed]

    offenders: list[dict] = []
    for pack, mode, path, card in in_scope:
        where = f"{pack}:{mode}"
        for err in validator.iter_errors({"dream_studio": card}):
            field = ".".join(str(p) for p in err.absolute_path) or "dream_studio"
            offenders.append(
                {"mode": where, "file": _rel(path), "field": field, "problem": err.message}
            )
        if card.get("pack") != pack or card.get("mode") != mode:
            offenders.append(
                {
                    "mode": where,
                    "file": _rel(path),
                    "field": "pack/mode",
                    "problem": (
                        f"card says {card.get('pack')}:{card.get('mode')}, "
                        f"but the file sits at {where}"
                    ),
                }
            )
        for token in card.get("inputs") or []:
            if token not in known_inputs:
                offenders.append(
                    {
                        "mode": where,
                        "file": _rel(path),
                        "field": "inputs",
                        "problem": (
                            f"{token} is produced by no mode and is not a registered root "
                            f"input - add it to {_rel(VOCAB_PATH)} or name the mode that "
                            f"produces it"
                        ),
                    }
                )

    packs = (yaml.safe_load(PACKS_PATH.read_text(encoding="utf-8")) or {}).get("packs", {})
    for pack, info in packs.items():
        invariants = info.get("invariants")
        if not isinstance(invariants, list) or not invariants:
            offenders.append(
                {
                    "mode": pack,
                    "file": "packs.yaml",
                    "field": "invariants",
                    "problem": (
                        "pack declares no invariants - state what holds for every mode in "
                        "it, or say why nothing does"
                    ),
                }
            )

    return {
        "status": "fail" if offenders else "pass",
        "scope": "all" if scope_all else "diff",
        "cards_checked": [f"{p}:{m}" for p, m, _, _ in in_scope],
        "offenders": offenders,
    }


def _update_vocabulary() -> int:
    """Re-seed the root-input registry from the tree."""
    cards = _all_cards()
    produced = {t for _, _, _, c in cards for t in (c.get("outputs") or [])}
    consumed = {t for _, _, _, c in cards for t in (c.get("inputs") or [])}
    doc = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    doc["root_inputs"] = sorted(consumed - produced)
    VOCAB_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"skill-card: re-seeded {len(doc['root_inputs'])} root input(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dream Studio skill mode cards.")
    parser.add_argument("--all", action="store_true", help="audit every card, not the diff")
    parser.add_argument("--update", action="store_true", help="re-seed the root-input registry")
    args = parser.parse_args()

    if args.update:
        return _update_vocabulary()

    result = run(scope_all=args.all)
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nskill-card: FAILED - {len(result['offenders'])} card problem(s).",
            file=sys.stderr,
        )
        return 1
    checked = result["cards_checked"]
    if not checked:
        print("skill-card: OK - no mode card changed.")
    else:
        print(f"skill-card: OK - {len(checked)} card(s) valid, vocabulary closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
