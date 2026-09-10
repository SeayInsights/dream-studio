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


#: The module that actually writes to the spool.
_WRITER_MODULE = "spool.writer"


def _dotted(node: ast.AST) -> str:
    """`a.b.c` for an attribute chain, `a` for a name, "" for anything else."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _is_type_checking(test: ast.AST) -> bool:
    """Is this `if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:`?

    The one guard that means "the names bound in here do not exist at runtime".
    """
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _writer_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names in this file that an import actually bound to the spool writer.

    Returns `(module_aliases, direct_names)` — receivers whose `.write_event(...)` is a
    real emission, and bare names that ARE `write_event`.

    A NAME ALLOWLIST WAS NOT ENOUGH, and an independent reviewer proved it by running it
    rather than reading it: with the receiver merely required to be spelled `writer`,
    `spool` or `_spool_writer`, three constructions slipped through as compliant -- an
    ordinary parameter named `writer`, one named `spool`, and a local bound to an
    unrelated object named `_spool_writer` -- each doing a raw INSERT with no emission at
    all. Those are unremarkable names in this codebase's own vocabulary, so the collision
    is likely rather than contrived, and the direction of the error is the unsafe one:
    the gate blessing a row no replay can rebuild.

    Provenance is therefore read from the import statements. A receiver counts only if
    THIS FILE imported the writer under that name.

    AN IMPORT UNDER `if TYPE_CHECKING:` DOES NOT COUNT, because that constant is false at
    runtime -- the name is simply not bound when the code executes, so a call through it
    would raise NameError. Treating it as provenance let a non-emitting function read as
    compliant (found by an independent reviewer, by execution).

    A `try:`-guarded import DOES count, and the distinction is not a hedge. This
    codebase's real emitters are written `try: import spool.writer as _spool_writer` with
    a fallback, so the import genuinely executes; distrusting every conditional import
    would flag every true positive in the tree and turn a blocking gate red on correct
    code. `TYPE_CHECKING` is the one guard that means "this does not exist at runtime".
    """
    type_checking_only = {
        node
        for guard in ast.walk(tree)
        if isinstance(guard, ast.If) and _is_type_checking(guard.test)
        for node in ast.walk(guard)
    }
    module_aliases: set[str] = set()
    direct_names: set[str] = set()
    for node in ast.walk(tree):
        if node in type_checking_only:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _WRITER_MODULE:
                    # `import spool.writer as w` binds `w`; plain `import spool.writer`
                    # binds `spool`, and the call is then written out in full.
                    module_aliases.add(alias.asname or _WRITER_MODULE)
                    if alias.asname is None:
                        module_aliases.add(_WRITER_MODULE)
        elif isinstance(node, ast.ImportFrom):
            source = node.module or ""
            if source == _WRITER_MODULE:
                for alias in node.names:
                    if alias.name in _EMITTERS:
                        direct_names.add(alias.asname or alias.name)
            elif source == "spool":
                for alias in node.names:
                    if alias.name == "writer":
                        module_aliases.add(alias.asname or "writer")
    return module_aliases, direct_names


def _shadowed_anywhere(tree: ast.AST) -> set[str]:
    """Every name this file binds by any means OTHER than an import.

    ENUMERATING THE SHADOW FORMS DID NOT WORK, and an independent reviewer proved it by
    execution three times over. A first version checked parameters plus
    `Assign`/`AnnAssign`/`AugAssign` inside the calling function, and missed a
    module-level rebind (it only walked the function), a `for _spool_writer in things:`
    target and a `with ctx as _spool_writer:` binding -- both of which are different AST
    shapes it never looked at. Each one let an unrelated object's `.write_event(...)`
    read as a real emission.

    A list of the shapes to check is the wrong instrument, because the next shape is
    whatever nobody thought of -- a comprehension target, a walrus, an `except ... as`,
    a match capture. So the question is inverted: any Store-context binding of a name,
    anywhere in the file, makes that name untrustworthy as the writer. Store context is
    how Python itself marks "this name is being bound", so new syntax is covered without
    being enumerated. Comprehension targets, walrus and `except ... as` were all verified
    covered by that inversion without being named.

    MATCH PATTERNS ARE THE EXCEPTION, and needed handling because they do not use
    `ast.Name` at all: `case _spool_writer:` binds through a string field on the pattern
    node (`MatchAs.name`, `MatchStar.name`, `MatchMapping.rest`). An independent reviewer
    found that gap by execution after the inversion above had already closed four others.
    Rather than add the one shape they found, every `Match*` node's string `name`/`rest`
    is read -- so the sub-patterns inside `MatchClass`/`MatchSequence`, and any future
    pattern node shaped the same way, are covered without being enumerated either.

    This is deliberately FILE-WIDE and conservative. If any function in a file uses
    `writer` as a local, the gate stops believing `writer.write_event(...)` everywhere in
    that file, and those writes get reported. Over-reporting is the safe direction for a
    gate whose whole subject is rows that look durable and are not.
    """
    shadowed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            shadowed.add(node.id)
        elif isinstance(node, ast.arg):
            shadowed.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            shadowed.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # `def write_event(...)` in this file is a local definition, not the import.
            shadowed.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            shadowed.update(node.names)
        elif type(node).__name__.startswith("Match"):
            # Pattern nodes carry their captures as plain strings, not Name nodes.
            for field in ("name", "rest"):
                bound = getattr(node, field, None)
                if isinstance(bound, str):
                    shadowed.add(bound)
    return shadowed


def _is_writer_call(func: ast.AST, bindings: tuple[set[str], set[str]]) -> bool:
    """Is this call the spool writer, rather than something else spelled the same?

    `logger.write_event("inserted")` on an unrelated telemetry object is not an emission,
    and neither is `writer.write_event(...)` where `writer` is a parameter. The name must
    have been bound to the writer by an import IN THIS FILE and never rebound in it.
    """
    module_aliases, direct_names = bindings
    if isinstance(func, ast.Name):
        return func.id in direct_names
    if isinstance(func, ast.Attribute) and func.attr in _EMITTERS:
        return _dotted(func.value) in module_aliases
    return False


def _own_nodes(func: ast.AST):
    """Nodes belonging to this function, NOT descending into a nested function or lambda.

    `ast.walk` on a FunctionDef descends into every nested `def` and `lambda`, so a
    function was credited with emitting because a helper defined inside it -- AND NEVER
    CALLED -- contained the writer call. Found by an independent reviewer, and the worst
    of the false negatives here because it needs no adversarial name at all: an ordinary
    dead inner helper is enough, and the outer function's own raw INSERT then passes as
    reconstructable.

    Excluding nested scopes is not a loss of coverage, because a nested function is
    itself walked at module level and gets its own entry in the call graph. If the outer
    function actually CALLS it, the fixed point credits the outer through that call --
    which is the real question, and the one lexical nesting cannot answer.
    """
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _emission_reachers(tree: ast.AST) -> set[str]:
    """Names of functions in this module that reach an emission, directly or via a helper.

    A TEXT MATCH ON `write_event` PUNISHES THE CORRECT REFACTOR, which is how this
    function came to exist. Two siblings in `verify_gaps.py` each carried their own copy
    of the emission block; the fix for WO 17466550 collapsed them into one
    `_emit_creation` helper -- and this gate promptly flagged BOTH, including the one that
    was already correct, because neither function contains the literal string any more.
    A check that reports the fix as the defect trains people to undo the fix, or to paste
    the block a third time to satisfy it. That third copy is precisely the condition that
    produced the original bug.

    So reachability is resolved instead of matched: a function is emitting if it calls the
    writer itself, or calls something in this module that does. Iterated to a fixed point,
    so a helper calling a helper still counts.

    THE LIMIT, STATED RATHER THAN HIDDEN: only calls resolvable WITHIN this module are
    followed. A function emitting through a helper imported from elsewhere still reports
    as an offender. That errs toward reporting, not toward silence, which is the safe
    direction for a gate whose whole subject is writes that look durable and are not.

    THE RECEIVER IS CHECKED, NOT JUST THE METHOD NAME. `logger.write_event("inserted")`
    on some unrelated telemetry object is not an emission, and counting it would be a
    false NEGATIVE -- the gate silently blessing a row that no replay can rebuild. The
    text match this replaced had the same hole; it is closed here rather than inherited.
    """
    module_aliases, direct_names = _writer_bindings(tree)
    # A name this file rebinds by ANY means is no longer the imported writer. Applied
    # once, file-wide, rather than re-derived per call site.
    shadowed = _shadowed_anywhere(tree)
    bindings = (module_aliases - shadowed, direct_names - shadowed)

    calls: dict[str, set[str]] = {}
    reach: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called: set[str] = set()
        emits = False
        # OWN SCOPE ONLY -- a nested `def` or `lambda` is walked separately and earns its
        # own entry below, so the outer function is credited only if it actually calls it.
        for call in _own_nodes(node):
            if not isinstance(call, ast.Call):
                continue
            name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
            if name:
                called.add(name)
            if _is_writer_call(call.func, bindings):
                emits = True
        calls[node.name] = called
        if emits:
            reach.add(node.name)

    changed = True
    while changed:
        changed = False
        for name, called in calls.items():
            if name not in reach and called.intersection(reach):
                reach.add(name)
                changed = True
    return reach


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

        reachers = _emission_reachers(tree)

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
            # RESOLVED, NOT MATCHED — see `_emission_reachers`. The literal-text check
            # this replaces reported a function as non-emitting the moment its emission
            # moved into a shared helper, so the gate scored the correct refactor as the
            # defect it exists to catch.
            if node.name in reachers:
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
