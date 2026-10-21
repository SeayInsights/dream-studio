"""A rule that claims enforcement must name an enforcer that exists.

`canonical/rules.yml` is the register that separates the statements something enforces
from the ones nothing does. Its own header says why it was written: the substrate was
"a lot of prose laid on top of each other as suggestions with no rules, evals, or really
any real test that doing anything they are supposed to". Every rule carries an
`enforced_by` list naming the modules and pytest nodes that hold it up.

Those names were checked by `core/gates/rule_registry.py`, and that gate was culled in
`67ba10e` in the same sweep that removed several of the enforcers it would have been
checking. So the register kept asserting enforcement for gates that no longer existed,
and the one thing that could have noticed went with them.

MEASURED WHEN THIS WAS WRITTEN: 21 of 102 `enforced_by` references across 7 of 34 rules
named a module or a test file that is not in the tree. A register of enforcement claims
that nobody verifies is the failure it was built to prevent, one level up.

A NODE IS RESOLVED TO THE TEST, NOT JUST THE FILE. Until #896 a `file::name` reference
counted as resolved once `file` existed, so a test renamed or deleted underneath a rule
left the rule claiming enforcement by nothing and the gate still printed OK; two rules
were found that way. The module is now parsed with `ast` -- never imported, so no test
module runs on a push -- and the `Class::name` path must be defined there as a function
or class. A parametrised id (`name[a-b]`) resolves when `name` does, because the ids are
generated at collection time; an assignment is not a test and does not resolve; a file
that does not parse is reported as a failure naming the line, never a crash.

THE DECLARATION IS THE OTHER HALF. Five of those seven lost their enforcement because the
gate holding them up was deliberately removed as repo bookkeeping. Deleting the rules
would lose the statements; leaving them claiming enforcement would keep lying. So a rule
may instead declare `unenforced:` with a reason, which this gate accepts and COUNTS --
the register's whole purpose is to make the unenforced pile visible, and a pile nobody
can see is the state it was written to end.

Same contract as `admission.py`'s `--why` and the security-scan exemption: enforce, or
declare in writing why you cannot. One repo, one shape for "I cannot enforce this".
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "canonical" / "rules.yml"

#: Minimum characters for a declared reason. Mirrors `admission._MIN_WHY` deliberately:
#: an author who has met one has met them all, and a reason shorter than this is a shrug.
MIN_REASON = 20

_CODE_SUFFIXES = (".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt")


def _definitions(body: list[ast.stmt]) -> dict[str, ast.stmt]:
    """The functions and classes a scope defines, by name.

    Definitions sitting under a module-level `if`/`try`/`with` are still defined in that
    scope, so they are found there too. Only `def` and `class` count: pytest does not run
    an assignment, and a rule that points at `test_x = something` is pointing at nothing.
    When a name is defined twice the later one wins, as it does at import time.
    """
    found: dict[str, ast.stmt] = {}
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[stmt.name] = stmt
        elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith)):
            nested = list(stmt.body) + list(getattr(stmt, "orelse", []))
            nested += list(getattr(stmt, "finalbody", []))
            for handler in getattr(stmt, "handlers", []):
                nested += list(handler.body)
            found.update(_definitions(nested))
    return found


def _parse(path: Path, cache: dict[Path, ast.Module | str]) -> ast.Module | str:
    """The parsed module, or the reason it cannot be. Parsed once per audit, never imported."""
    if path not in cache:
        try:
            cache[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            cache[path] = f"test file does not parse (line {exc.lineno})"
        except (UnicodeDecodeError, ValueError):
            cache[path] = "test file is not readable as utf-8 source"
    return cache[path]


def _resolve_node(reference: str, cache: dict[Path, ast.Module | str]) -> str | None:
    """Resolve `file.py::Class::name[param]` by reading the file, never importing it."""
    file_part, _, node_part = reference.partition("::")
    # A parametrised id (`name[a-b]`) resolves when the function does. The parameter ids
    # are generated at collection time and can hold `::` themselves, so the bracket is cut
    # off before the path is split.
    node_part = node_part.split("[", 1)[0]

    path = REPO_ROOT / file_part
    if not path.is_file():
        return "no such test file"
    if path.suffix != ".py":
        return "node id into a non-python file"

    segments = node_part.split("::")
    if not all(segments):
        return "empty segment in node id"

    tree = _parse(path, cache)
    if isinstance(tree, str):
        return tree

    body: list[ast.stmt] = tree.body
    for position, name in enumerate(segments):
        node = _definitions(body).get(name)
        if node is None:
            scope = "::".join(segments[:position]) or file_part
            return f"no `{name}` defined in {scope}"
        if position < len(segments) - 1:
            if not isinstance(node, ast.ClassDef):
                # pytest collects methods of a class, not functions nested in a function.
                return f"`{name}` is a function, not a class holding tests"
            body = node.body
    return None


def _resolve(reference: str, cache: dict[Path, ast.Module | str] | None = None) -> str | None:
    """None when the reference resolves; otherwise why it does not."""
    ref = str(reference).strip()
    if not ref:
        return "empty reference"

    if "::" in ref:  # a pytest node id: the file AND the test inside it must exist
        return _resolve_node(ref, {} if cache is None else cache)

    if "/" in ref or ref.endswith(_CODE_SUFFIXES):  # a path
        return None if (REPO_ROOT / ref).exists() else "no such path"

    if "." in ref:  # a dotted module
        target = REPO_ROOT.joinpath(*ref.split("."))
        if target.with_suffix(".py").is_file() or (target / "__init__.py").is_file():
            return None
        return "no such module"

    return "unrecognised reference"


def audit(registry_path: Path | None = None) -> dict[str, Any]:
    """Every rule whose enforcement claim does not hold, plus the declared ones."""
    import yaml

    path = registry_path or REGISTRY
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else data

    broken: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    guidance: list[dict[str, Any]] = []
    checked = 0
    parsed: dict[Path, ast.Module | str] = {}

    for rule in rules or []:
        rule_id = rule.get("id", "<no id>")
        reason = str(rule.get("unenforced") or "").strip()
        references = list(rule.get("enforced_by") or [])
        guidance_why = str(rule.get("why") or "").strip()

        # GUIDANCE IS NOT A REGRESSION. `unenforced` records that something used to hold a
        # rule up and a named commit removed it, so that list is a debt that should shrink.
        # `guidance` records that no static check can settle the statement at all -- an
        # instruction to the model, answerable only by an eval. Filing the second under the
        # first inflates the regression count with rules nothing ever enforced, and the
        # reason can never name a commit because none exists.
        if rule.get("guidance") is True:
            if reason or references:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(guidance declaration)",
                        "why": "declares guidance AND unenforced/enforced_by; pick one",
                    }
                )
            elif len(guidance_why) < MIN_REASON:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(guidance declaration)",
                        "why": f"why is {len(guidance_why)} characters, {MIN_REASON} required",
                    }
                )
            else:
                guidance.append({"rule": rule_id, "why": guidance_why})
            continue

        if reason:
            # A DECLARATION IS NOT A BYPASS. It must say something, and it must not sit
            # beside a claim of enforcement -- a rule cannot be both held up and not.
            if len(reason) < MIN_REASON:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(unenforced declaration)",
                        "why": f"reason is {len(reason)} characters, {MIN_REASON} required",
                    }
                )
            elif references:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(unenforced declaration)",
                        "why": "declares unenforced AND lists enforced_by; pick one",
                    }
                )
            else:
                declared.append({"rule": rule_id, "reason": reason})
            continue

        if not references:
            broken.append(
                {
                    "rule": rule_id,
                    "reference": "(none)",
                    "why": "no enforced_by, no unenforced declaration, no guidance",
                }
            )
            continue

        for reference in references:
            checked += 1
            why = _resolve(reference, parsed)
            if why:
                broken.append({"rule": rule_id, "reference": reference, "why": why})

    return {
        "rules": len(rules or []),
        "references_checked": checked,
        "broken": broken,
        "declared": declared,
        "guidance": guidance,
    }


def main() -> int:
    report = audit()
    declared = report["declared"]

    if report["broken"]:
        print("[rule-enforcement] FAIL - a rule claims an enforcer that is not there")
        print()
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for item in report["broken"]:
            by_rule.setdefault(item["rule"], []).append(item)
        for rule_id, items in by_rule.items():
            print(f"  {rule_id}")
            for item in items:
                print(f"      {item['reference']}")
                print(f"          -> {item['why']}")
        print()
        print("  Point the rule at the enforcer that survived, or declare which it is:")
        print(f"    unenforced: <at least {MIN_REASON} chars> - an enforcer existed and a")
        print("                named commit removed it; this pile is a debt that shrinks.")
        print("    guidance: true")
        print(f"    why: <at least {MIN_REASON} chars> - no static check can settle this at")
        print("                all; it is an instruction to the model, answerable by an eval.")
        print("  Exactly one, and remove its enforced_by. A rule cannot be both held up and not.")
        return 1

    print(
        f"[rule-enforcement] OK - {report['references_checked']} enforcement reference(s) "
        f"across {report['rules']} rule(s) all resolve"
    )
    # THE UNENFORCED PILE IS PRINTED EVERY RUN, PASS OR FAIL. The register exists to make
    # it visible; a declaration that only shows up in a failure is a pile nobody sees.
    if declared:
        print(f"\n  {len(declared)} rule(s) UNENFORCED (an enforcer was removed):")
        for item in declared:
            print(f"    {item['rule']}")
            print(f"        {item['reason'][:150]}")
    # PRINTED APART, because the two counts mean different things. The pile above is a
    # debt and should shrink; the one below is a classification and will not, since no
    # static check can settle a statement about how the model should behave.
    if report["guidance"]:
        print(f"\n  {len(report['guidance'])} rule(s) GUIDANCE (no check can settle it):")
        for item in report["guidance"]:
            print(f"    {item['rule']}")
            print(f"        {item['why'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
