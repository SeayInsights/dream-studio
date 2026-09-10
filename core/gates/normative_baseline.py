"""Gate: the substrate's unclassified normative statements may only go down.

WHY THIS EXISTS. Operator, on the substrate: rules are "a lot of prose laid on top of each
other as suggestions with no rules, evals, or really any real test that doing anything they
are supposed to". ``canonical/rules.yml`` answers that one rule at a time and cannot answer
it at scale -- classifying by hand drifts, and nothing stopped the pile growing again the
next day.

A NUMBER THIS FILE EXISTS TO CORRECT. The figure "2,172 normative statements" circulated in
this repo (and into the rules.yml header) as if it were a backlog of unwritten rules. It is
not. It was a count of WORD OCCURRENCES under one pattern, and most occurrences are ordinary
English inside explanatory prose -- "the runner must be the sole writer" in a docstring
describing a design is not an unenforced rule. Measured 2026-09-07: the same corpus yields
**188** SHOUTED statements (MUST / MUST NOT / NEVER / ALWAYS / REQUIRED / DO NOT / SHALL /
MAY NOT) and **5,752** any-case occurrences. Treating either as a rule backlog is a category
error; 5,752 rules would be absurd and 188 is tractable. This gate counts the shouted form,
because writing a rule in capitals is a deliberate act and the deliberate ones are the ones
that are load-bearing.

WHAT THE COUNT MEANS PER LANE, because the enforcement substrate differs by kind:

* ``code`` -- constraints ON the machine. These become gates, like the four added on
  2026-09-07. A static check can settle them.
* ``canonical/skills`` -- instructions to a MODEL at runtime. No static check can enforce
  "ask one question at a time"; these need EVALS, and ``tests/evals/`` plus the
  ``eval_registry`` table already exist to hold them. This is the largest genuinely
  unenforced lane.
* ``docs`` -- mostly DESCRIPTIONS of the machine, which should be generated from it or
  deleted, not restated as rules. ``AGENTS.md`` is already generated from ``packs.yaml``. A
  hand-written second copy of behaviour is what rots, which is why this repo's own note says
  the roadmap doc lags code by design.
* ``canonical/workflows`` -- gate declarations, largely enforced already.
* ``root instructions`` -- operating rules; small, and should stay small.

THE RATCHET. The baseline in ``canonical/normative_baseline.json`` records today's count per
lane. A change set may not raise it: a new shouted statement must be classified in
``canonical/rules.yml``, converted to an eval, generated, or deleted. A change set that
LOWERS it must lower the baseline too, in the same change set -- otherwise the recorded
number drifts above reality and the ceiling stops meaning anything. Both directions fail
loudly and ``--update`` re-seeds, so the number always reflects the substrate.

This is deliberately a count, not a statement-to-rule mapping. Mapping 188 statements onto
rules by identity would need a stable identifier for a sentence, and a sentence gets
reworded; the count is coarse but it cannot silently drift, which is the property that
matters for a ceiling.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "canonical" / "normative_baseline.json"

#: The SHOUTED forms only. Lowercase "must" is ordinary English and counting it produced the
#: 5,752 figure that made the problem look intractable; capitals are a deliberate act.
_NORMATIVE = re.compile(r"\b(MUST NOT|MUST|MAY NOT|NEVER|ALWAYS|REQUIRED|DO NOT|SHALL)\b")

_SUFFIXES = frozenset({".md", ".yml", ".yaml", ".py"})

#: lane -> paths. A lane is a group that shares an enforcement substrate, so the number is
#: actionable: an increase in `code` wants a gate, in `canonical/skills` an eval.
_LANES: dict[str, tuple[str, ...]] = {
    "canonical/skills": ("canonical/skills",),
    "canonical/workflows": ("canonical/workflows",),
    "docs": ("docs",),
    "root instructions": ("CLAUDE.md", "AGENTS.md"),
    "code": ("core", "runtime", "interfaces", "integrations", "projections"),
}

#: Files that QUOTE normative statements as their subject matter. The registry states each
#: rule it classifies, and this gate and its test quote the vocabulary they match -- counting
#: them would mean classifying a rule raises the very count that classifying is meant to
#: lower.
_EXCLUDED = frozenset(
    {
        "canonical/rules.yml",
        "core/gates/normative_baseline.py",
        "tests/unit/test_normative_baseline_gate.py",
    }
)


def _rel(path: Path, repo_root: Path) -> str:
    try:
        out = str(path.relative_to(repo_root))
    except ValueError:
        out = str(path)
    return out.replace(chr(92), "/")


def _targets(repo_root: Path, spec: str) -> list[Path]:
    base = repo_root / spec
    if base.is_file():
        return [base]
    if not base.is_dir():
        return []
    return [
        f
        for f in base.rglob("*")
        if f.suffix in _SUFFIXES and f.is_file() and "__pycache__" not in f.parts
    ]


def _tracked(repo_root: Path) -> set[str]:
    """Repo-relative paths git knows about.

    A RATCHET MUST MEASURE WHAT A FRESH CHECKOUT CONTAINS. This gate walked the filesystem,
    so it counted untracked files -- measured at 38 untracked docs files here, contributing
    4 shouted words -- and the recorded baseline therefore encoded one machine's working
    tree. Locally the numbers matched; on CI they could not, and full-ci on main failed on
    every push for days as a result.

    Deliberately the opposite of `untested_fallback._test_corpus`, which includes untracked
    files on purpose: a corpus answers "does anything test this", and a test written in the
    same change set counts even before it is committed. A ratchet answers "is this number
    still true of what ships", and only tracked content ships.

    Returns an empty set when git cannot be read, and the caller then falls back to the
    filesystem walk -- a measurement taken is better than none, and the mismatch it can
    cause is loud rather than silent.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if out.returncode != 0:
        return set()
    return {line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()}


def measure(repo_root: Path = REPO_ROOT) -> dict[str, int]:
    """Shouted normative statements per lane, over TRACKED files only.

    Tracked-only because this number is compared against a fresh checkout. Counting
    untracked files made the local measurement disagree with CI permanently and baked one
    machine's working tree into the shipped baseline -- see `_tracked`.
    """
    counts: dict[str, int] = {}
    tracked = _tracked(repo_root)
    for lane, specs in _LANES.items():
        total = 0
        for spec in specs:
            for path in _targets(repo_root, spec):
                rel = _rel(path, repo_root)
                if rel in _EXCLUDED:
                    continue
                # An empty `tracked` means git could not be read; fall back to the walk
                # rather than measuring nothing, which would read as a clean zero.
                if tracked and rel.replace("\\", "/") not in tracked:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                total += len(_NORMATIVE.findall(text))
        counts[lane] = total
    return counts


def _load_baseline(path: Path) -> tuple[dict[str, int] | None, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"no baseline at {_rel(path, REPO_ROOT)} -- seed it with --update"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"baseline unreadable: {type(exc).__name__}: {exc}"
    lanes = raw.get("lanes")
    if not isinstance(lanes, dict):
        return None, "baseline has no `lanes` object"
    return {str(k): int(v) for k, v in lanes.items()}, ""


def run(repo_root: Path = REPO_ROOT, baseline_path: Path | None = None) -> dict:
    baseline_path = baseline_path or BASELINE_PATH
    measured = measure(repo_root)
    baseline, why = _load_baseline(baseline_path)
    if baseline is None:
        return {
            "status": "fail",
            "measured": measured,
            "total_measured": sum(measured.values()),
            "errors": [why],
        }

    errors: list[str] = []
    for lane, count in sorted(measured.items()):
        recorded = baseline.get(lane)
        if recorded is None:
            errors.append(
                f"{lane}: no ceiling recorded ({count} measured). Add the lane to"
                f" {_rel(baseline_path, repo_root)} with --update; an unrecorded lane has no"
                " ceiling at all."
            )
        elif count > recorded:
            errors.append(
                f"{lane}: {count} shouted normative statements against a ceiling of"
                f" {recorded} (+{count - recorded}). A new one must be CLASSIFIED in"
                " canonical/rules.yml (with a runnable enforced_by, or guidance plus a"
                " why), turned into an eval under tests/evals/ if it instructs a model"
                " rather than constrains the code, generated from the thing it describes,"
                " or deleted. Raising the ceiling is a reviewable act: --update, in the"
                " same change set as the rule that earns it."
            )
        elif count < recorded:
            errors.append(
                f"{lane}: {count} measured against a ceiling of {recorded}"
                f" (-{recorded - count}). Lower the ceiling in this change set (--update)."
                " A ceiling left above reality drifts upward silently and stops meaning"
                " anything -- which is how the pile grew the first time."
            )

    for lane in sorted(set(baseline) - set(measured)):
        errors.append(
            f"{lane}: recorded in the baseline but is not a known lane. Remove it with"
            " --update, or restore the lane definition it belonged to."
        )

    return {
        "status": "fail" if errors else "pass",
        "measured": measured,
        "baseline": baseline,
        "total_measured": sum(measured.values()),
        "total_baseline": sum(baseline.values()),
        "errors": errors,
    }


def update(repo_root: Path = REPO_ROOT, baseline_path: Path | None = None) -> dict:
    """Re-seed the ceiling from what is actually there."""
    baseline_path = baseline_path or BASELINE_PATH
    measured = measure(repo_root)
    previous, _ = _load_baseline(baseline_path)
    payload = {
        "_comment": (
            "Ceiling on SHOUTED normative statements per lane, enforced by"
            " core/gates/normative_baseline.py. It may only go DOWN. A new statement must be"
            " classified in canonical/rules.yml, converted to an eval, generated from what it"
            " describes, or deleted. Regenerate with"
            " `py -m core.gates.normative_baseline --update` in the same change set."
        ),
        "lanes": measured,
        "total": sum(measured.values()),
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "updated",
        "path": _rel(baseline_path, repo_root),
        "lanes": measured,
        "total": sum(measured.values()),
        "previous_total": sum(previous.values()) if previous else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--update", action="store_true", help="re-seed the ceiling from the current tree"
    )
    args = parser.parse_args(argv)

    if args.update:
        result = update()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nnormative-baseline: FAILED - {len(result['errors'])} lane(s) off their"
            " ceiling. The ceiling may only go down.",
            file=sys.stderr,
        )
        return 1
    print(
        "normative-baseline: OK - "
        f"{result['total_measured']} shouted normative statement(s), at or under every"
        " lane ceiling."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
