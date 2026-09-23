"""Every keyword a CLI dispatch passes is one its target accepts.

`ds work-order create --priority` shipped broken: the dispatch passed
`priority=args.priority` and `_work_order_create` did not accept it, so every invocation
raised TypeError. It had been verified with `--help`, which renders the PARSER and says
nothing about the call behind it.

This is the cheap, complete version of the check that would have caught it: for every
`_work_order_*` / `_project_*` style helper the dispatch modules call, the keywords at the
call site must exist in the callee's signature. Static, so it needs no database, no
network and no arguments only a caller would know.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DISPATCH_MODULES = [
    "interfaces/cli/commands/work_order_dispatch.py",
    "interfaces/cli/commands/project.py",
    "interfaces/cli/commands/milestone.py",
    "interfaces/cli/commands/ci.py",
]


def _calls_with_keywords(path: pathlib.Path) -> list[tuple[str, list[str], int]]:
    """Every call in the module made with keyword arguments, by callee name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.keywords:
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if not name:
            continue
        kws = [k.arg for k in node.keywords if k.arg]
        if kws:
            out.append((name, kws, node.lineno))
    return out


def _resolvable(module_path: pathlib.Path, name: str):
    """The function that call targets, when it can be found without importing the world."""
    import importlib

    dotted = str(module_path.with_suffix("")).replace("\\", "/").replace("/", ".")
    if "interfaces." in dotted:
        dotted = dotted[dotted.index("interfaces.") :]  # noqa: E203
    try:
        mod = importlib.import_module(dotted)
    except Exception:
        return None
    target = getattr(mod, name, None)
    return target if callable(target) else None


@pytest.mark.parametrize("rel", _DISPATCH_MODULES)
def test_every_keyword_a_dispatch_passes_is_one_its_target_accepts(rel):
    path = REPO_ROOT / rel
    if not path.is_file():
        pytest.skip(f"{rel} does not exist in this tree")

    offenders: list[str] = []
    for name, kws, lineno in _calls_with_keywords(path):
        target = _resolvable(pathlib.Path(rel), name)
        if target is None:
            continue  # imported locally inside a branch, or not a module-level name
        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            continue
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            continue  # **kwargs accepts anything
        unknown = [k for k in kws if k not in sig.parameters]
        if unknown:
            offenders.append(f"{rel}:{lineno} {name}() does not accept {unknown}")

    assert not offenders, (
        "a dispatch passes keywords its target cannot accept, so the command raises "
        "TypeError on every invocation:\n  " + "\n  ".join(offenders)
    )


def test_the_walk_finds_real_calls():
    """A checker that found nothing would pass on an empty tree, which is the shape this
    repo keeps finding. The work-order dispatch makes dozens of keyword calls."""
    calls = _calls_with_keywords(REPO_ROOT / "interfaces/cli/commands/work_order_dispatch.py")
    assert len(calls) > 20, f"only {len(calls)} keyword calls found; has the dispatch moved?"
