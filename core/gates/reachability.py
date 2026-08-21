"""Does code added by this change set have a caller? (WO-DEAD-ON-ARRIVAL)

THE PATTERN, measured across 2026-08-19/21: five separate verify findings, all the
same shape — a mechanism written, its wiring omitted, and the mechanism then described
as the outcome.

  - ``merge_readiness()`` / ``record_merge_override()``: no production call site at
    all. The grader quoted the work order's own diagnosis back: "a gate that exists,
    is correct, and sits where it cannot stop the thing it was built to stop".
  - ``declare_reviewed_no_change()``: a Python function while the skill text
    documented it as a remedy an operator could perform.
  - ``currency_evidence()``: still zero callers as this gate was written.
  - ``_envelope_required``: a comment claiming "this gate and the other artifact
    gates" while the code touched one of three.
  - close-mode brief guidance: named by a task, marked done unwritten.

WHY NOT JUST TIGHTEN VULTURE. ``core/gates/leanness.py`` already runs
``vulture --min-confidence 80`` on every push and is ADVISORY: it printed
"dead symbols (vulture >=80%): 8" on ~26 consecutive pushes while those functions sat
unreachable, because they scored 60%. Lowering the threshold to 60 is not the fix — at
60 vulture also flags ``currency_failure``, which IS called, via a lazy import inside a
function body. DS uses lazy imports deliberately and widely (a module-level import
freezes the reference and silently defeats ``patch(...)``), so static call-graph
analysis cannot see through them and a 60% threshold would punish an idiom the codebase
requires.

SO: DIFF-SCOPED, AND REFERENCE-BASED. Only symbols this change set ADDED are examined,
which keeps the 387 pre-existing advisory findings out of it and this signal
actionable. Reachability is decided by whether the name is REFERENCED anywhere in
production code — including inside function bodies — which makes the lazy-import idiom
safe by construction rather than by exemption.

Deterministic by design (operator directive 2026-08-21: anything that can be verified
deterministically should be). "Does this name appear in production code" is a
computation, not a judgement. It was previously left to an LLM grader to notice after
the fact, which it did — five times, always after the code had shipped.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories whose Python is product code. A symbol referenced only by tests is NOT
# dead on arrival — it may be a deliberate fixture seam — so tests are excluded from
# the ADDED set, but they are also excluded from the reference search: a helper whose
# only caller is a test is exactly the case this gate must not bless.
PRODUCTION_ROOTS = (
    "control",
    "core",
    "emitters",
    "integrations",
    "interfaces",
    "projections",
    "runtime",
    "spool",
)

# An intentional definition-before-caller says so inline, and the gate PRINTS every
# exemption on every run — an exemption nobody can see is the same shape as the defect
# it exempts (the rule locale_decode_gate established).
EXEMPT_MARKER = "reachability-gate: intentional"


@dataclass
class UnreachableSymbol:
    """A public symbol this change set added that nothing in production references."""

    file: str
    line: int
    name: str
    kind: str  # "function" | "class"
    exempt: bool = False
    exempt_reason: str = ""


class SourceUnreadable(RuntimeError):
    """A file in the change set could not be read or parsed.

    Raised rather than swallowed: a gate that silently skips what it cannot read
    reports clean on exactly the files most likely to be wrong.
    """


def added_symbol_names(diff_text: str) -> set[str]:
    """Names whose ``def``/``class`` line was ADDED by this diff.

    Reads the diff rather than comparing two trees: a signature line prefixed with
    ``+`` is the unambiguous evidence that this change set introduced the definition,
    and it costs one command instead of a checkout.
    """
    names: set[str] = set()
    pattern = re.compile(r"^\+\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return names


def module_level_public_symbols(source: str, *, path: str) -> list[tuple[str, str, int, bool, str]]:
    """Module-level public defs/classes: ``(name, kind, lineno, exempt, reason)``.

    MODULE LEVEL ONLY. A method is reached through its class and an override has no
    direct caller by design, so walking into class bodies would produce noise that
    gets the gate routed around.

    DECORATED DEFINITIONS ARE SKIPPED. A decorator IS a registration mechanism — a
    FastAPI route, a pytest fixture, a click command — so "no Python caller" is the
    normal, correct state for them and flagging it would be wrong.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SourceUnreadable(f"{path}: {exc}") from exc

    lines = source.splitlines()
    found: list[tuple[str, str, int, bool, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function"
        elif isinstance(node, ast.ClassDef):
            kind = "class"
        else:
            continue
        if node.name.startswith("_"):
            continue  # private by convention; single-module use is normal
        if node.decorator_list:
            continue  # registered by its decorator, not called by name

        exempt, reason = False, ""
        # The marker may sit on the definition line or the line above it.
        for probe in (node.lineno - 1, node.lineno - 2):
            if 0 <= probe < len(lines) and EXEMPT_MARKER in lines[probe]:
                exempt = True
                reason = (
                    lines[probe].split(EXEMPT_MARKER, 1)[1].strip(" #:-") or "(no reason given)"
                )
                break
        found.append((node.name, kind, node.lineno, exempt, reason))
    return found


def code_identifiers(source: str) -> list[str]:
    """Every identifier this module actually USES, from the AST — not its prose.

    THE FIRST CUT OF THIS GATE WAS A TEXT SEARCH AND IT DEFEATED ITSELF. This module's
    own docstring names ``currency_evidence()`` as an example of a dead symbol; the
    line-based search counted that sentence as a call site, so the gate reported the
    corpus clean while the symbol it cited sat unreferenced. A prose mention is not a
    reference, and a gate whose evidence is a substring cannot tell them apart —
    exactly the grep-standing-in-for-the-real-thing substitution this gate exists to
    stop, reproduced inside it.

    Collected here, deliberately, because each IS a way DS reaches code:

    - ``Name``/``Attribute`` — ordinary calls and lookups, at any nesting depth, so a
      lazy import inside a function body counts (the idiom that makes tightening
      vulture unworkable);
    - ``import`` aliases — both the imported name and its ``as`` binding;
    - string CONSTANTS in expression position — ``__all__`` entries, ``getattr(x, "y")``,
      a dispatch-table key.

    Excluded: comments (absent from the AST) and docstrings — a bare string statement
    is documentation, not use.
    """
    tree = ast.parse(source)

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
                if isinstance(child.value.value, str):
                    docstrings.add(id(child.value))

    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.alias):
            names.append(node.name.split(".")[-1])
            if node.asname:
                names.append(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                names.append(node.value)
    return names


def reference_count(name: str, sources: dict[str, str], *, defining_file: str) -> int:
    """How many times ``name`` is referenced in production CODE.

    The symbol's own ``def``/``class`` statement is not a use of itself, so the defining
    module is counted by its identifier uses only — a recursive call or a sibling
    function's call still counts, which is correct: both mean the code is reachable.

    A file that cannot be parsed falls back to a whole-word text count. That direction
    is deliberate: over-counting yields a false NEGATIVE (a dead symbol slips through),
    while under-counting would block a push over a file this gate simply failed to
    read, which is how a gate gets routed around.
    """
    word = re.compile(r"\b" + re.escape(name) + r"\b")
    total = 0
    for path, source in sources.items():
        try:
            identifiers = code_identifiers(source)
        except SyntaxError:
            total += sum(len(word.findall(line)) for line in source.splitlines())
            continue
        total += sum(1 for identifier in identifiers if identifier == name)
        if path == defining_file:
            # ast.FunctionDef/ClassDef carry the name as an attribute, not as a Name
            # node, so the definition never entered `identifiers` — nothing to subtract.
            continue
    return total


def unreachable_symbols(
    *,
    changed_sources: dict[str, str],
    added_names: set[str],
    search_sources: dict[str, str],
) -> list[UnreachableSymbol]:
    """Public symbols added by this change set with no production reference.

    ``changed_sources`` are the production files this change set touched;
    ``search_sources`` is every production file to search for references (a superset —
    a new function is usually called from a file the change set did not modify).
    """
    findings: list[UnreachableSymbol] = []
    for path, source in sorted(changed_sources.items()):
        for name, kind, lineno, exempt, reason in module_level_public_symbols(source, path=path):
            if name not in added_names:
                continue  # pre-existing; out of scope by design
            if reference_count(name, search_sources, defining_file=path) == 0:
                findings.append(
                    UnreachableSymbol(
                        file=path,
                        line=lineno,
                        name=name,
                        kind=kind,
                        exempt=exempt,
                        exempt_reason=reason,
                    )
                )
    return findings


def is_production_python(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if not normalized.endswith(".py"):
        return False
    return normalized.split("/", 1)[0] in PRODUCTION_ROOTS


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        timeout=30,
    )
    if not isinstance(result.returncode, int) or result.returncode != 0:
        return ""
    return result.stdout or ""


def _untracked_production_python() -> list[str]:
    """Production ``.py`` files git does not track yet.

    ``git diff`` NEVER reports an untracked file, so a brand-new module's symbols were
    invisible to this gate until they were staged — measured on the gate's own first
    dry run, which reported "nothing to check" while two new files sat in the tree. In
    the pre-push context the commit exists so the diff covers them, but a gate whose
    local answer differs from its CI answer is a gate people stop believing.
    """
    output = _git(["ls-files", "--others", "--exclude-standard"])
    return [f.strip() for f in output.splitlines() if f.strip() and is_production_python(f.strip())]


def _collect_search_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for root in PRODUCTION_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for file in base.rglob("*.py"):
            if "__pycache__" in file.parts:
                continue
            try:
                rel = file.relative_to(REPO_ROOT).as_posix()
                sources[rel] = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return sources


def main() -> int:
    # Inside CI the branch has already been pushed; this gate is a pre-push check and
    # the matrix is the authority there (same convention as migration_risk).
    if os.environ.get("GITHUB_ACTIONS"):
        return 0

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    diff = _git(["diff", "-U0", f"{base_ref}...HEAD"]) or _git(["diff", "-U0", "HEAD"])

    changed = [
        f.strip()
        for f in (
            _git(["diff", "--name-only", f"{base_ref}...HEAD"])
            or _git(["diff", "--name-only", "HEAD"])
        ).splitlines()
        if f.strip() and is_production_python(f.strip())
    ]

    changed_sources: dict[str, str] = {}
    for rel in changed:
        file = REPO_ROOT / rel
        if file.is_file():
            changed_sources[rel] = file.read_text(encoding="utf-8", errors="replace")

    # An untracked file is entirely new, so every definition in it is added. Without
    # this the gate is blind to exactly the files most likely to contain a mechanism
    # with no caller — a brand-new module.
    added_names = added_symbol_names(diff)
    for rel in _untracked_production_python():
        file = REPO_ROOT / rel
        if not file.is_file():
            continue
        source = file.read_text(encoding="utf-8", errors="replace")
        changed_sources[rel] = source
        try:
            added_names.update(
                name for name, *_rest in module_level_public_symbols(source, path=rel)
            )
        except SourceUnreadable as exc:
            print(f"reachability: FAIL — a new file could not be parsed: {exc}")
            return 1

    if not added_names:
        print("reachability: no public definitions added — nothing to check")
        return 0
    if not changed_sources:
        print("reachability: no production Python changed — nothing to check")
        return 0

    try:
        findings = unreachable_symbols(
            changed_sources=changed_sources,
            added_names=added_names,
            search_sources=_collect_search_sources(),
        )
    except SourceUnreadable as exc:
        print(f"reachability: FAIL — a changed file could not be parsed: {exc}")
        return 1

    exempted = [f for f in findings if f.exempt]
    blocking = [f for f in findings if not f.exempt]

    # Printed on pass AND fail: an exemption nobody can see is the defect it exempts.
    for finding in exempted:
        print(
            f"reachability: EXEMPT {finding.file}:{finding.line} {finding.name} "
            f"— {finding.exempt_reason}"
        )

    if not blocking:
        print(
            f"reachability: OK — {len(added_names)} added definition(s) checked, "
            f"{len(exempted)} exempt"
        )
        return 0

    print()
    print("reachability: FAIL — code added by this change set has no production caller:")
    for finding in blocking:
        print(f"  {finding.file}:{finding.line}  {finding.kind} {finding.name}()")
    print()
    print("  A mechanism with no call site cannot do the thing it was built to do.")
    print("  Wire it to the surface that should use it, or delete it. If the definition")
    print("  genuinely precedes its caller, say why inline:")
    print(f"    # {EXEMPT_MARKER}: <reason>")
    print("  (every exemption is printed on every run).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
