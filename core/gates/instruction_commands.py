"""An instruction that names a command must name one that can run.

WHAT THIS IS FOR. Canonical skills and workflows are instructions to an agent, and an
agent does what they say. When one names a script or a module that is not there, the
agent runs it, gets "no such file", and either improvises or silently skips a step it was
told to take -- and the step that gets skipped is disproportionately a check, because
checks are what instructions tell you to run.

WHAT IT FOUND ON THE RUN THAT WROTE IT:

    scripts/lint-artifact.py            14 references, never once tracked
    core.gates.evidence_backed_output    2 references, module does not exist
    control.research.tools               2 references, module does not exist
    scripts/resume_from_handoff.py       1 reference, moved to interfaces/cli/
    scripts/backfill_token_sessions.py   1 reference, moved to interfaces/cli/
    scripts/migrate_to_db.py             1 reference, moved to interfaces/cli/

The first is why this gate exists rather than a one-time cleanup. `.gitignore` carried an
unanchored `lint-*` and swallowed `lint-artifact.py` silently, so fourteen instructions --
one of them a `severity: critical` gotcha reading "before every delivery" -- pointed at a
file that had never been committed. Nothing noticed for four months, because nothing was
looking. A cleanup fixes the six; this fixes the next one.

WHAT IT DELIBERATELY DOES NOT CHECK. Third-party modules (`py -m pytest`, `py -m black`)
are not this repo's to guarantee and their absence is an environment problem, not an
instruction problem. Argument placeholders (`<file.html>`, `<output.html>`) are not paths.
A reference inside a fenced example that illustrates a failure is still checked, because
distinguishing an example from an instruction needs judgement, and a gate that guesses at
intent is one people learn to argue with rather than fix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Where instructions live. Both are read by agents as things to do.
#: JSON is in the list because a data file's own comment is an instruction too:
#: canonical/normative_baseline.json told a reader to regenerate it with a module
#: culled in 3b2dc373, and this gate did not see it while it read only prose.
SEARCH_GLOBS = (
    "canonical/**/*.md",
    "canonical/**/*.yaml",
    "canonical/**/*.yml",
    "canonical/**/*.json",
)

#: Top-level packages this repository owns. A `py -m` naming anything else is a
#: third-party tool whose presence is an environment concern, not an instruction defect.
FIRST_PARTY = (
    "canonical",
    "control",
    "core",
    "integrations",
    "interfaces",
    "projections",
    "runtime",
    "scripts",
    "spool",
)

#: ONLY AN INVOCATION COUNTS, not every mention of a path. `quality:harden` carries a
#: checklist row reading "`scripts/bom.py` or equivalent BOM script" -- a criterion about
#: the project being hardened, not a command this repo runs, and flagging it would make
#: the gate argue with a document that is correct. So a reference is only checked when it
#: is preceded by an interpreter (`py`, `python`, `py -3.12`), a `./`, or the word "Run".
#: ANY invoked .py path, not only `scripts/`. Restricting it to one directory would
#: leave a hole exactly where a cross-skill reference lives -- the fullstack skill names
#: the website skill's linter, which is not under `scripts/` from where it stands.
#: A PATH, WHICH MEANS AT LEAST ONE SLASH. A bare `py parse_sarif.py` names a file the
#: instruction is telling the agent to WRITE in its own working directory -- the security
#: examples are full of them -- and checking those against this repo would flag a document
#: that is doing its job. A path with a directory in it is a claim about where something
#: lives, and that claim is checkable.
#:
#: Not restricted to `scripts/`, because the hole would sit exactly where cross-skill
#: references live: the fullstack skill names the website skill's linter.
#: `py -3.12` is the Windows launcher's version selector and appears in the workflows
#: verbatim, so the interpreter fragment has to allow it. A test pins both spellings:
#: without it the tightened pattern silently stopped matching two real references, which
#: would have been a gate that reported clean by not looking.
_INTERPRETER = r"\bpy(?:thon)?(?:3(?:\.\d+)?)?(?:\s+-3(?:\.\d+)?)?"

SCRIPT_REF = re.compile(
    r"(?:" + _INTERPRETER + r"\s+|\bRun:?\s+`?|\./)" r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.py)\b"
)
MODULE_REF = re.compile(_INTERPRETER + r"\s+-m\s+([A-Za-z0-9_.]+)")


def _resolve_script(ref: str, source: Path) -> bool:
    """A `scripts/x.py` reference resolves from the repo root OR the naming skill.

    Both are legitimate. A skill that ships its own `scripts/` directory writes
    `py scripts/brand-compliance.py` meaning its own, and that is the shorter, correct
    thing for it to say; a workflow at the repo root means the repo's. Walking up from
    the naming file finds the first that exists.
    """
    if (REPO_ROOT / ref).is_file():
        return True
    for parent in source.resolve().parents:
        if (parent / ref).is_file():
            return True
        if parent == REPO_ROOT:
            break
    return False


def _resolve_module(dotted: str) -> bool:
    """True when a first-party dotted module exists as a file or a package."""
    if dotted.split(".")[0] not in FIRST_PARTY:
        return True  # third-party: not this repository's to guarantee
    target = REPO_ROOT.joinpath(*dotted.split("."))
    return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()


def unresolved_commands() -> list[dict[str, object]]:
    """Every command a canonical instruction names that cannot be run."""
    findings: list[dict[str, object]] = []
    for glob in SEARCH_GLOBS:
        for source in sorted(REPO_ROOT.glob(glob)):
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # A GENERATED PROJECTION IS NOT A SECOND INSTRUCTION. Compiled agents inline
            # their skill's text verbatim, and a skill's relative paths resolve from the
            # skill's own directory -- `py modes/repo/analyze-repos.py` is correct where it
            # was written and meaningless from canonical/agents/. Scanning both copies
            # flags the source file's instruction against the wrong base path, which is the
            # gate arguing with a document that is right. The source is scanned; that is
            # where a real dangling command has to be fixed anyway.
            if "GENERATED by" in text[:600]:
                continue
            rel = source.relative_to(REPO_ROOT).as_posix()
            for number, line in enumerate(text.splitlines(), start=1):
                for ref in SCRIPT_REF.findall(line):
                    if not _resolve_script(ref, source):
                        findings.append(
                            {"file": rel, "line": number, "names": ref, "kind": "script"}
                        )
                for dotted in MODULE_REF.findall(line):
                    if not _resolve_module(dotted):
                        findings.append(
                            {"file": rel, "line": number, "names": dotted, "kind": "module"}
                        )
    return findings


def main() -> int:
    findings = unresolved_commands()
    if not findings:
        print("[instruction-commands] every command named in canonical/ resolves")
        return 0

    by_name: dict[str, list[dict[str, object]]] = {}
    for f in findings:
        by_name.setdefault(str(f["names"]), []).append(f)

    print("[instruction-commands] FAIL — canonical instructions name commands that cannot run")
    print()
    for name, hits in sorted(by_name.items(), key=lambda kv: -len(kv[1])):
        print(f"  {name}  ({len(hits)} reference{'s' if len(hits) != 1 else ''})")
        for hit in hits[:5]:
            print(f"      {hit['file']}:{hit['line']}")
        if len(hits) > 5:
            print(f"      ... and {len(hits) - 5} more")
    print()
    print("  An agent does what an instruction says. A command that cannot run is a step")
    print("  silently skipped, and the steps instructions name are disproportionately checks.")
    print("  Write the thing, correct the path, or remove the instruction.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
