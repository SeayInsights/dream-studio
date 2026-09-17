"""Every hook handler must match the contract the dispatcher actually uses.

control/execution/dispatch_tracking.py::run_handlers dispatches a handler like
this, for every handler, with no exceptions:

    sys.stdin = io.StringIO(raw_payload)
    mod.main()                      # <-- ZERO arguments

A handler that declares `def main(payload)` therefore raises TypeError on every
single dispatch. The dispatcher catches BaseException so the failure never
propagates; it is recorded as status="failed" and nothing else happens. Nothing
reads those rows, so the handler is simply dead, silently, indefinitely.

That is not hypothetical. Measured from the operator's own event store on
2026-09-17:

    on_prompt_route      8,767 dispatches   8,767 failed  (100.0%)
    on_context_inject    8,767 dispatches   8,767 failed  (100.0%)

Both with the same error: "main() missing 1 required positional argument:
'payload'". on-prompt-route is the only mechanism that pushes the model toward
invoking a skill, and on-context-inject is what injects project memory into a
prompt. Neither had ever run. Two further handlers (on-memory-retrieve,
on-token-log) carried the same defect.

Separately and still UNEXPLAINED: on_skill_complete, on_skill_metrics and
on_skill_load have zero execution rows of any status since 2026-07-02 while
the Skill tool kept firing. Their files exist in both the repo and the
installed copies, and the PostToolUse path does route through run_handlers,
so the unresolved-handler branch does NOT explain it. That is an open defect,
not something this module fixes.

The reason it shipped and survived is that the unit tests called
`route.main({...})` directly — passing the argument production never passes.
Testing a handler by a calling convention the dispatcher does not use proves
nothing about whether the handler runs.

This module enforces the contract statically across every handler, so the next
one cannot regress the same way.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_ROOT = REPO_ROOT / "runtime" / "hooks"


def _handler_files() -> list[Path]:
    return [
        p
        for p in sorted(HOOKS_ROOT.rglob("*.py"))
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    ]


def _module_level_main(path: Path) -> ast.FunctionDef | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    return None


def _required_parameters(fn: ast.FunctionDef) -> list[str]:
    """Positional parameters with no default — what mod.main() cannot supply."""
    args = fn.args
    positional = [a.arg for a in (*args.posonlyargs, *args.args)]
    n_defaulted = len(args.defaults)
    required = positional[: len(positional) - n_defaulted] if n_defaulted else positional
    return [a for a in required if a not in ("self", "cls")]


_WITH_MAIN = [p for p in _handler_files() if _module_level_main(p) is not None]


def test_some_handlers_were_discovered():
    """Guard the guard — an empty glob would make the parametrized test vacuous."""
    assert HOOKS_ROOT.is_dir(), f"{HOOKS_ROOT} does not exist"
    assert len(_WITH_MAIN) >= 20, (
        f"expected to find many hook handlers under {HOOKS_ROOT}, found {len(_WITH_MAIN)} — "
        "the discovery glob has drifted and this suite is no longer guarding anything"
    )


@pytest.mark.parametrize("path", _WITH_MAIN, ids=lambda p: p.stem)
def test_handler_main_takes_no_required_arguments(path: Path):
    """The dispatcher calls mod.main() with zero arguments — always."""
    fn = _module_level_main(path)
    assert fn is not None
    required = _required_parameters(fn)
    assert not required, (
        f"{path.relative_to(REPO_ROOT)} declares main({', '.join(required)}). "
        "control/execution/dispatch_tracking.py calls mod.main() with no "
        "arguments, so every dispatch of this handler will raise TypeError, be "
        "swallowed, and recorded as failed — the handler will never run. Read "
        "the payload from sys.stdin inside main() instead."
    )


def test_dispatcher_still_calls_main_with_no_arguments():
    """If the dispatcher's convention ever changes, this suite must be revisited.

    Without this, someone could 'fix' the contract by changing the dispatcher
    and leave the assertions above silently guarding the wrong thing.
    """
    src = (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").read_text(encoding="utf-8")
    assert "mod.main()" in src, (
        "dispatch_tracking.py no longer calls mod.main() with zero arguments — "
        "the handler contract asserted in this module is out of date"
    )
