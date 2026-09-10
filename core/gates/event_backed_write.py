"""Gate: a row written into a projection must be reconstructable from events.

THE DEFECT THIS EXISTS FOR, measured 2026-09-10 on the live authority:

    493 of 949 work orders  have no `work_order.created` canonical event
    1706 of 3286 tasks      have no `task.created` canonical event

`business_work_orders` and `business_tasks` are PROJECTIONS. Neither
`WorkOrderProjection` nor `TaskProjection` overrides `pre_rebuild`, so both resolve to
`core/projections/framework_projection.py`, whose default does `DELETE FROM` each target
table before replaying events. A row with no creation event therefore cannot come back: a
rebuild deletes 52% of the authority's work orders and tasks.

AND A REBUILD IS THE DISASTER-RECOVERY TOOL. There is no operator subcommand for it, only
`engine.rebuild()` / `rebuild_all()` in code — so the risk is latent, not active. It is also
worst exactly when it is reached for: recovering from corruption would silently discard
half the record, including every remediation work order a review has ever spawned.

THE SOURCE WAS ONE UNFIXED SIBLING, which is why this gate is about the CLASS and not the
instance. `_insert_gap_work_orders` writes both tables with no event. Its sibling
`_attach_gap_tasks` was fixed and carries a comment saying the author "copied the shape of
the sibling-spawn INSERT instead of the task-creation path in mutations.py" — the fix note
names this exact function as the wrong shape it copied, and nobody came back to it.

THE TARGET TABLES ARE DERIVED, NOT LISTED. Each projection declares `target_tables`, and
that declaration is what `pre_rebuild` truncates — so reading it is reading the actual
blast radius. A hardcoded list would have covered the two tables this defect was found in
and silently exempted the other four, which is the same subset-of-what-it-writes shape as
WO b56cca8a (`ds update` checking drift only under `skills/`).

MEASURED REACH: 6 target tables derived; 214 functions INSERT into one; 211 emit no event;
4 of those are outside `tests/`. Test fixtures build rows directly on purpose — that is
what a fixture is — so `tests/` is out of scope, and the gate starts at a number small
enough to hold at zero.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import pkgutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Declared at the finding site, at least this many characters of reason. Same contract as
#: `security-scan` and `--why` on `add-task`: one repo, one shape for "I cannot satisfy this
#: rule, and here is why". A bare marker costs nothing and becomes the norm.
EXEMPT_MARKER = "# event-backed-write:"
_MIN_REASON = 20

#: How a function says it wrote to the event substrate.
#:
#: `CanonicalEventEnvelope` ALONE IS NOT AN EMISSION, and treating it as one made this gate
#: grep where it should check. `spool.writer.write_event` takes a DICT; passing the envelope
#: object raises TypeError from its payload validation. `_attach_gap_tasks` did exactly that
#: -- the emission was added, a comment said the rows would survive a rebuild, the
#: surrounding handler swallowed the TypeError, and the call never once succeeded. This gate
#: reported that function compliant, which is a grep standing in for a drive inside the gate
#: built to catch writes no event can reconstruct.
_EMITTERS = ("write_event",)

#: The envelope class whose instances `write_event` cannot accept.
_ENVELOPE_CLASS = "CanonicalEventEnvelope"


def _broken_emission(node: ast.AST) -> bool:
    """Is there a `write_event(CanonicalEventEnvelope(...))` here, with no `.to_dict()`?

    PARSED, NOT MATCHED. A first cut used a negative lookahead and could not see past the
    constructor's own closing parenthesis, so it flagged
    `write_event(CanonicalEventEnvelope(...).to_dict())` -- the CORRECT form -- as broken.
    A gate that fires on the fix is worse than one that misses the defect, because it
    teaches that the fix is wrong. `security_scan` records the same lesson: parsing has no
    window to get wrong.

    A static gate cannot run the call. It can see that the argument is the envelope class
    itself rather than a mapping, and that is the exact defect that shipped: `write_event`
    takes a dict, so an envelope instance raises TypeError from its payload validation, the
    caller's handler swallows it, and the row is as unreconstructable as one with no
    emission -- while reading as compliant.
    """
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
        if name != "write_event" or not call.args:
            continue
        arg = call.args[0]
        # `X(...).to_dict()` and `x.to_dict()` are Attribute calls -- fine.
        if isinstance(arg, ast.Call):
            inner = getattr(arg.func, "attr", None) or getattr(arg.func, "id", None)
            if inner == _ENVELOPE_CLASS:
                return True
    return False


def projection_targets() -> dict[str, set[str]]:
    """``{table: {projection names}}``, read from each projection's own declaration.

    This is the set `pre_rebuild` truncates, so it is the set at risk. Derived rather than
    listed so a projection added later is covered without being named here.
    """
    targets: dict[str, set[str]] = {}
    package = importlib.import_module("core.projections")
    for module in pkgutil.iter_modules(package.__path__):
        try:
            loaded = importlib.import_module(f"core.projections.{module.name}")
        except Exception:  # noqa: BLE001 - a projection that cannot import declares nothing
            continue
        for name in dir(loaded):
            declared = getattr(getattr(loaded, name), "target_tables", None)
            if isinstance(declared, (list, tuple)) and declared:
                for table in declared:
                    if isinstance(table, str):
                        targets.setdefault(table, set()).add(f"{module.name}.{name}")
    return targets


def _tracked_python(repo_root: Path) -> list[Path]:
    """Tracked Python files, or a raise -- never a silent empty list.

    TWO FAIL-OPENS LIVED HERE, and `locale-decode` caught the first on this gate's own
    first chain run. Without `encoding=`, child output is decoded with the platform codec
    (cp1252 on Windows); one unmapped byte raises inside subprocess's reader thread, `run`
    returns returncode=0 with stdout=None, and the caller is handed success plus no output.
    This gate would then examine ZERO files and report every write site clean -- the
    compared-nothing-reported-clean shape, inside a gate written to catch it.

    The second is the empty listing itself. `git ls-files` returning nothing means this is
    not a git repo, or git is absent, or the call failed -- none of which is "no Python
    files here". Raising makes the gate fail rather than pass, because a sweep that examined
    nothing has not found compliance.
    """
    proc = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    names = (proc.stdout or "").split()
    if not names:
        raise RuntimeError(
            f"git ls-files listed no Python files under {repo_root} (exit"
            f" {proc.returncode}). A sweep that examined nothing is not a clean sweep, so"
            " this fails rather than reporting no offenders."
        )
    return [repo_root / name for name in names]


def _exempt(segment: str) -> bool:
    for line in segment.splitlines():
        stripped = line.strip()
        if stripped.startswith(EXEMPT_MARKER):
            reason = stripped[len(EXEMPT_MARKER) :].strip()  # noqa: E203
            if len(reason) >= _MIN_REASON:
                return True
    return False


def offenders(repo_root: Path | None = None) -> dict[str, object]:
    """Functions that insert into a projection target without emitting its event."""
    root = repo_root or REPO_ROOT
    targets = projection_targets()
    found: list[dict[str, object]] = []
    examined = 0

    for path in _tracked_python(root):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        # A fixture building rows directly is what a fixture IS. Excluding tests keeps the
        # gate about production writes; the 211-of-214 measurement is almost entirely them.
        if relative.startswith("tests/"):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = ast.get_source_segment(source, node) or ""
            written = sorted(
                table
                for table in targets
                if f"INSERT INTO {table}" in segment or f"INSERT OR REPLACE INTO {table}" in segment
            )
            if not written:
                continue
            examined += 1
            # AN EMISSION THAT CANNOT SUCCEED IS NOT AN EMISSION. A raw envelope handed
            # to `write_event` raises, the caller's handler swallows it, and the row is
            # exactly as unreconstructable as one with no emission at all -- while reading
            # as compliant.
            if _broken_emission(node):
                found.append(
                    {
                        "file": relative,
                        "function": node.name,
                        "line": node.lineno,
                        "tables": written,
                        "detail": (
                            "write_event is handed a CanonicalEventEnvelope object; it takes"
                            " a dict, so this raises and the row is not reconstructable."
                            " Add .to_dict()."
                        ),
                    }
                )
                continue
            if any(emitter in segment for emitter in _EMITTERS):
                continue
            if _exempt(segment):
                continue
            found.append(
                {
                    "file": relative,
                    "function": node.name,
                    "line": node.lineno,
                    "tables": written,
                }
            )

    return {
        "target_tables": sorted(targets),
        "examined": examined,
        "offenders": found,
    }


def _render(report: dict[str, object]) -> str:
    tables = report["target_tables"]
    found = report["offenders"]
    lines = [
        f"event-backed-write: {len(tables)} projection target table(s) derived,"
        f" {report['examined']} production write site(s) examined."
    ]
    if not found:
        # SAYS WHAT IT CHECKED EVEN WHEN CLEAN. A ratchet that prints nothing on a clean
        # run is indistinguishable from one that measured nothing.
        lines.append("  OK - every write site emits its creation event.")
        return "\n".join(lines)
    for item in found:  # type: ignore[union-attr]
        lines.append(
            f"  FOUND {item['file']}:{item['line']} {item['function']}()"
            f" -> {', '.join(item['tables'])}"
        )
    lines.append("")
    lines.append(
        "A row written straight into a projection cannot be replayed. Every one of these"
        " tables is truncated by `pre_rebuild` before events are replayed, so these rows"
        " are deleted by any rebuild -- and a rebuild is the recovery tool."
    )
    lines.append(
        "Emit the creation event beside the insert (see core/work_orders/mutations.py), or"
        f" declare at the site: `{EXEMPT_MARKER} <at least {_MIN_REASON} characters of why"
        " this row is deliberately not reconstructable>`."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report projection writes that no event can reconstruct."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Review THIS tree instead of the one this gate lives in. `offenders()` always"
            " took a root; this flag was missing, so the round table could not point the"
            " lane at another project -- and said so rather than scanning its own install"
            " and reporting that as the other project's result."
        ),
    )
    args = parser.parse_args(argv)

    report = offenders(Path(args.repo_root) if args.repo_root else None)
    if args.json:
        import json

        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render(report))
    return 1 if report["offenders"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
