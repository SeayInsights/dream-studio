"""Run the suite named after each module the change touched.

WHY THIS EXISTS, measured on the session that wrote it. A change to
``core/gates/task_criteria_baseline.py`` was pushed through three suites --
``test_admission``, ``test_verify_gaps``, ``test_gap_fanout`` -- and never through
``tests/unit/test_task_criteria_baseline.py``, the file named after the module it edited.
Five tests there were red, and the failure was not cosmetic: the edit put a new query
inside the gate's primary ``try``, so the whole blocking gate reported UNKNOWN and would
have refused every push. It was found by an independent reviewer reading the diff, not by
any gate.

THE STATIC COMPLEMENT ALREADY EXISTS AND CANNOT COVER THIS. ``pin-tests`` runs a hardcoded
list, and ``test-list-completeness`` exists because that list rots. A hardcoded list
answers "did the suites someone remembered still pass"; it cannot answer "did the suite
covering the file you just edited run at all". This derives the answer from the diff, so a
module added tomorrow is covered without an edit.

WHAT IT DELIBERATELY DOES NOT DO. It does not try to establish that a session ran a suite
-- nothing durable records that, and a gate that guesses would be worse than none. It RUNS
them, which is the only form of the question that has an answer at push time.

The mapping is deliberately literal: ``core/gates/foo.py`` -> ``tests/unit/test_foo.py``,
and a module with no such file is reported as unmapped rather than treated as covered. An
absent suite is not a passing one, and collapsing those two is how a gate starts reporting
clean for the wrong reason.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Trees whose modules are expected to carry a same-named unit suite. Tests, canonical
#: data and generated projections are excluded: they are not modules with behaviour of
#: their own, and demanding a `test_test_x.py` would be noise.
SOURCE_ROOTS = ("core", "control", "interfaces", "integrations", "runtime", "spool")

UNIT_DIR = Path("tests") / "unit"


def suite_for(path: str) -> str | None:
    """The unit suite bearing this module's name, when the repo has one."""
    p = Path(path)
    if p.suffix != ".py" or p.name == "__init__.py":
        return None
    if not p.parts or p.parts[0] not in SOURCE_ROOTS:
        return None
    candidate = UNIT_DIR / f"test_{p.stem}.py"
    return candidate.as_posix() if (REPO_ROOT / candidate).is_file() else None


def changed_files(base: str) -> list[str]:
    """Files this branch changed against `base`, as repo-relative posix paths."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def measure(base: str = "origin/main") -> dict[str, object]:
    """Which suites this change implicates, and which modules have none."""
    files = changed_files(base)
    if not files:
        # "I could not read the diff" and "nothing changed" have different remedies, and
        # a gate that reports clean for the first is the shape this repo keeps finding.
        return {"status": "unknown", "reason": f"no diff against {base}"}

    mapped: dict[str, str] = {}
    unmapped: list[str] = []
    for f in files:
        suite = suite_for(f)
        if suite:
            mapped[suite] = f
        elif Path(f).suffix == ".py" and Path(f).parts and Path(f).parts[0] in SOURCE_ROOTS:
            unmapped.append(f)

    return {
        "status": "computed",
        "base": base,
        "changed": len(files),
        "suites": sorted(mapped),
        "covers": {k: mapped[k] for k in sorted(mapped)},
        "unmapped_modules": sorted(unmapped),
    }


def run(base: str = "origin/main") -> dict[str, object]:
    report = measure(base)
    if report["status"] != "computed":
        # FAILS rather than passes: a gate that could not measure has not found compliance.
        report["ok"] = False
        return report

    suites = list(report["suites"])  # type: ignore[arg-type]
    if not suites:
        report["ok"] = True
        report["reason"] = "no changed module has a same-named unit suite"
        return report

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *suites, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    report["ok"] = proc.returncode == 0
    report["pytest_returncode"] = proc.returncode
    if proc.returncode != 0:
        tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-15:]
        report["reason"] = "a suite named after a module this change edited is red: " + " | ".join(
            tail[-3:]
        )
        report["output_tail"] = tail
    return report


def _render(report: dict[str, object]) -> str:
    if report["status"] != "computed":
        return f"changed-module-suites: UNKNOWN - {report.get('reason')}"
    suites = report["suites"]  # type: ignore[index]
    head = f"changed-module-suites: {len(suites)} suite(s) cover this change"  # type: ignore[arg-type]
    body = "".join(f"\n    {s}  <- {report['covers'][s]}" for s in suites)  # type: ignore[index]
    unmapped = report.get("unmapped_modules") or []
    if unmapped:
        body += f"\n  {len(unmapped)} changed module(s) have no same-named suite: " + ", ".join(
            unmapped[:5]
        )  # type: ignore[index]
    if report.get("ok"):
        return head + body + "\n  OK - every mapped suite passes."
    return head + body + "\n  " + str(report.get("reason"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the unit suite named after each module this change edited."
    )
    parser.add_argument("--base", default="origin/main", help="Ref to diff against.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    report = run(args.base)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
