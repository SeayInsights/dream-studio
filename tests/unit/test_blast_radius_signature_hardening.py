"""Hardening of the call-compatible signature refinement, from the independent review.

The refinement (tests/unit/test_blast_radius_compatible_signature.py) stops the changed-
signature detector blocking a change no call can notice. The adversarial review of it
found four ways it was weaker than the detector it refined, plus gaps that mutants
survived. Each section here pins one finding with the concrete input that exposed it.

F1  A file that INTROSPECTS the function's signature (inspect.signature, getfullargspec,
    __code__.co_argcount, __signature__, ...) breaks on a compatible change exactly as a
    mock does, and was reported before the refinement.
F2  Two same-named defs in one file: only the LAST pair was classified, so an incompatible
    change followed by a compatible one passed.
F3  ast.parse raises MemoryError on a pathologically nested line; that must fall back to
    the name comparison, never crash and never silence.
F5  A string patch target (`monkeypatch.setattr(mod, "name", ...)`) is a reference, for an
    incompatible change as much as a compatible one.

NOT DETECTED, AND SAID SO: a fake or stub handed in without the function's name appearing
in the file; `inspect.signature(getattr(Cls, method))` where the name is computed;
`_SIG_RE` reads one line, so a def rewritten across lines produces no finding. A registry
or dispatch table that CALLS with the old arity needs no detector: a compatible change
keeps every old call valid. Pinned below where a test can pin them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.gates.hanging_detectors import (
    _inspects_symbol,
    _signature_compatibility,
    detect_changed_signature_callers,
)

CALLER = "tests/unit/test_caller.py"
COMPAT = ("a", "a, *, extra=1")  # call-compatible
BREAKING = ("a", "a, *, extra")  # a new required keyword-only parameter


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff(
    removed: list[str],
    added: list[str],
    *,
    name: str = "do_work",
    path: str = "core/thing.py",
    keyword: str = "def",
) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        + "".join(f"-{keyword} {name}({p}):\n" for p in removed)
        + "".join(f"+{keyword} {name}({p}):\n" for p in added)
    )


def _flagged(tmp_path: Path, caller: str, change: tuple[str, str] = COMPAT) -> bool:
    _write(tmp_path / CALLER, caller)
    diff = _diff([change[0]], [change[1]])
    return CALLER in {f["path"] for f in detect_changed_signature_callers(diff, repo_root=tmp_path)}


# --- F1: introspection ------------------------------------------------------

INTROSPECTING_CALLERS = {
    "signature-parameters": (
        "import inspect\n\ndef test_shape():\n"
        "    sig = inspect.signature(do_work)\n    assert list(sig.parameters) == ['a']\n"
    ),
    "signature-of-attribute": "import inspect\nsig = inspect.signature(thing.do_work)\n",
    "signature-of-class-attribute": (
        "import inspect\nsig = inspect.signature(WorkflowRunner.do_work)\n"
    ),
    "bare-signature-import": "from inspect import signature\nsignature(do_work)\n",
    "getfullargspec": "import inspect\nassert inspect.getfullargspec(do_work).args == ['a']\n",
    "getargspec": "import inspect\nassert inspect.getargspec(do_work).args == ['a']\n",
    "getcallargs": "import inspect\ninspect.getcallargs(do_work, 1)\n",
    "from-callable": "import inspect\ninspect.Signature.from_callable(do_work)\n",
    "co-argcount": "assert do_work.__code__.co_argcount == 1\n",
    "co-varnames": "assert do_work.__code__.co_varnames == ('a',)\n",
    "dunder-signature": "assert str(do_work.__signature__) == '(a)'\n",
    "dunder-defaults": "assert do_work.__defaults__ is None\n",
    "dunder-kwdefaults": "assert do_work.__kwdefaults__ is None\n",
    "through-an-alias": "import inspect\nfn = do_work\nsig = inspect.signature(fn)\n",
    "through-a-loop": ("import inspect\nfor fn in (do_work, other):\n    inspect.signature(fn)\n"),
    "named-by-dotted-string": ("import inspect\ninspect.signature(resolve('pkg.mod.do_work'))\n"),
    "named-by-string": "import inspect\ninspect.signature(getattr(mod, 'do_work'))\n",
}


@pytest.mark.parametrize("caller", INTROSPECTING_CALLERS.values(), ids=INTROSPECTING_CALLERS)
def test_a_file_introspecting_the_function_is_reported_for_a_compatible_change(
    tmp_path: Path, caller: str
) -> None:
    assert _flagged(tmp_path, caller)


def test_the_workflow_runner_shape_is_reported(tmp_path: Path) -> None:
    """The real instance, tests/unit/test_workflow_runner.py: the file asserts
    `list(sig.parameters) == ["self", "node_id", "ynode"]`. It was reported by the old
    detector, and by the refinement only because the same file happened to contain mock
    assertion text."""
    _write(
        tmp_path / CALLER,
        "import inspect\n\n"
        "def test_x():\n"
        "    sig = inspect.signature(WorkflowRunner._verify_completion)\n"
        '    assert list(sig.parameters) == ["self", "node_id", "ynode"]\n',
    )
    diff = _diff(
        ["self, node_id, ynode"], ["self, node_id, ynode, *, extra=None"], name="_verify_completion"
    )
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


NOT_INTROSPECTING_THIS_FUNCTION = {
    "signature-of-another-function": (
        "import inspect\n\ndef test_x():\n    do_work('a')\n    inspect.signature(other_fn)\n"
    ),
    "code-of-another-function": "do_work('a')\nassert other.__code__.co_argcount == 1\n",
    "similar-name": "import inspect\ndo_work('a')\ninspect.signature(do_work_helper)\n",
    "loop-over-others": (
        "import inspect\ndo_work('a')\nfor fn in (one, two):\n    inspect.signature(fn)\n"
    ),
    "result-of-calling-it": (
        "import inspect\nresult = do_work('a')\nsig = inspect.signature(result)\n"
    ),
    "result-of-calling-its-attribute": (
        "import inspect\nresult = mod.do_work('a')\ninspect.signature(result)\n"
    ),
    "string-of-another-name": "import inspect\ndo_work('a')\ninspect.signature(getattr(m, 'x'))\n",
}


@pytest.mark.parametrize(
    "caller", NOT_INTROSPECTING_THIS_FUNCTION.values(), ids=NOT_INTROSPECTING_THIS_FUNCTION
)
def test_introspecting_a_different_function_is_not_a_reference(tmp_path: Path, caller: str) -> None:
    """The negative control: without it `_inspects_symbol` would be 'the file contains
    inspect.signature anywhere', which reports every test that ever inspected anything."""
    assert not _flagged(tmp_path, caller)


def test_introspection_is_reported_for_an_incompatible_change_too(tmp_path: Path) -> None:
    assert _flagged(
        tmp_path, "import inspect\ninspect.signature(getattr(mod, 'do_work'))\n", BREAKING
    )


def test_an_unparseable_file_falls_back_to_a_textual_match() -> None:
    broken = "def broken(:\n    pass\nimport inspect\ninspect.signature(do_work)\n"
    assert _inspects_symbol(broken, "do_work")
    assert not _inspects_symbol(broken.replace("do_work", "other"), "do_work")


@pytest.mark.parametrize("exc", [SyntaxError, ValueError, RecursionError, MemoryError])
def test_every_way_ast_can_refuse_a_file_falls_back_to_text(
    monkeypatch: pytest.MonkeyPatch, exc
) -> None:
    def refuse(*_a, **_k):
        raise exc("refused")

    monkeypatch.setattr(ast, "parse", refuse)
    assert _inspects_symbol("inspect.signature(do_work)\n", "do_work")
    assert not _inspects_symbol("inspect.signature(other)\n", "do_work")


def test_a_non_python_file_is_matched_textually() -> None:
    assert _inspects_symbol("x = inspect.signature(do_work)\n<<<\n", "do_work")


def test_known_blind_spot_a_computed_name_is_not_detected(tmp_path: Path) -> None:
    """tests/unit/test_eval_live_optin_guard.py does `inspect.signature(getattr(EvalRunner,
    method))`. The name is a variable; no static reading can tie it to this function. Pinned
    so that a change in this behaviour is a decision, not an accident."""
    assert not _flagged(
        tmp_path,
        "import inspect\ndo_work('a')\nfor method in METHODS:\n"
        "    inspect.signature(getattr(Runner, method))\n",
    )


def test_known_blind_spot_a_fake_without_the_name_is_not_detected(tmp_path: Path) -> None:
    assert not _flagged(tmp_path, "def test_x(fake):\n    run(fake)\n    assert fake.seen == 1\n")


def test_a_caller_that_passes_the_old_arity_through_a_table_is_correctly_silent(
    tmp_path: Path,
) -> None:
    """A dispatch table that CALLS with the old arity is not a break: a compatible change
    keeps every old call valid. Only introspection and mocks can see the new shape."""
    assert not _flagged(tmp_path, "TABLE = {'k': do_work}\n\ndef go():\n    TABLE['k']('a')\n")


@pytest.mark.parametrize(
    "token",
    [
        "inspect.signature",
        "getfullargspec",
        "__code__",
        "__signature__",
        "__defaults__",
    ],
)
def test_the_cheap_prefilter_does_not_hide_a_token(tmp_path: Path, token: str) -> None:
    """`_inspects_symbol` skips the AST parse when no introspection token appears at all;
    each token that matters must get past that filter."""
    sources = {
        "inspect.signature": "inspect.signature(do_work)\n",
        "getfullargspec": "getfullargspec(do_work)\n",
        "__code__": "do_work.__code__\n",
        "__signature__": "do_work.__signature__\n",
        "__defaults__": "do_work.__defaults__\n",
    }
    assert _inspects_symbol(sources[token], "do_work")


# --- F2: every same-named def in a file -------------------------------------


def _flagged_pairs(
    tmp_path: Path, removed: list[str], added: list[str], caller: str | None = None
) -> bool:
    _write(tmp_path / CALLER, caller or "def test_it():\n    do_work('a')\n")
    findings = detect_changed_signature_callers(_diff(removed, added), repo_root=tmp_path)
    return CALLER in {f["path"] for f in findings}


def test_an_incompatible_def_followed_by_a_compatible_one_is_reported(tmp_path: Path) -> None:
    """The reviewer's input: `-def do_work(a):` twice, `+def do_work(a, b):` then
    `+def do_work(a, b=1):`. The old detector blocked; the refinement classified only the
    LAST pair and passed."""
    assert _flagged_pairs(tmp_path, ["a", "a"], ["a, b", "a, b=1"])


def test_a_compatible_def_followed_by_an_incompatible_one_is_reported(tmp_path: Path) -> None:
    assert _flagged_pairs(tmp_path, ["a", "a"], ["a, b=1", "a, b"])


def test_two_compatible_defs_with_a_plain_caller_are_not_reported(tmp_path: Path) -> None:
    assert not _flagged_pairs(tmp_path, ["a", "a"], ["a, b=1", "a, *, c=2"])


def test_two_compatible_defs_still_report_a_mock(tmp_path: Path) -> None:
    caller = "def test_x():\n    m.assert_called_once_with('a')\n    do_work('a')\n"
    assert _flagged_pairs(tmp_path, ["a", "a"], ["a, b=1", "a, *, c=2"], caller)


def test_an_unchanged_def_beside_an_incompatible_one_is_reported(tmp_path: Path) -> None:
    assert _flagged_pairs(tmp_path, ["a", "a"], ["a", "a, b"])


def test_the_pairs_are_taken_in_order(tmp_path: Path) -> None:
    """Different old shapes: the first pair is compatible, the second drops a parameter."""
    assert _flagged_pairs(tmp_path, ["a", "a, b"], ["a, c=1", "a"])


def test_unequal_counts_are_unpairable_and_use_the_name_comparison(tmp_path: Path) -> None:
    """Two defs removed, one added with a different name list: no pairing is possible, so
    the changed names are reported rather than guessed at."""
    assert _flagged_pairs(tmp_path, ["a", "a"], ["a, b"])


def test_unequal_counts_with_the_same_shapes_are_not_reported(tmp_path: Path) -> None:
    assert not _flagged_pairs(tmp_path, ["a", "a"], ["a"])
    assert not _flagged_pairs(tmp_path, ["a"], ["a", "a"])


def test_a_def_added_beside_an_unchanged_one_with_a_new_shape_is_reported(
    tmp_path: Path,
) -> None:
    assert _flagged_pairs(tmp_path, ["a"], ["a", "a, b"])


def test_the_same_name_in_two_files_keeps_the_stricter_verdict(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    one = _diff(["a"], ["a, *, extra=1"], path="core/one.py")
    two = _diff(["a"], ["a, *, extra"], path="core/two.py")
    unchanged = _diff(["a"], ["a"], path="core/three.py")
    for diff in (one + two, two + one, unchanged + two, two + unchanged, one + unchanged + two):
        findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
        assert CALLER in {f["path"] for f in findings}


def test_the_same_name_compatible_in_two_files_is_not_reported(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    one = _diff(["a"], ["a, *, extra=1"], path="core/one.py")
    two = _diff(["a"], ["a, b=2"], path="core/two.py")
    assert detect_changed_signature_callers(one + two, repo_root=tmp_path) == []


# --- F3: a parser that gives up ---------------------------------------------


@pytest.mark.parametrize("exc", [SyntaxError, ValueError, RecursionError, MemoryError])
def test_every_way_ast_can_refuse_falls_back(monkeypatch: pytest.MonkeyPatch, exc) -> None:
    """Each exception is exercised on its own, so narrowing the except clause around the
    parse to fewer types fails here."""

    def refuse(*_a, **_k):
        raise exc("refused")

    monkeypatch.setattr(ast, "parse", refuse)
    assert _signature_compatibility("a", "a, *, b=1") == "unparseable"


def test_a_pathologically_nested_line_does_not_crash_and_is_not_silenced(
    tmp_path: Path,
) -> None:
    """50,000 `not` operators on one line make ast.parse raise MemoryError ('Parser stack
    overflowed'). The detector must neither crash nor treat the change as compatible."""
    deep = "not " * 50_000 + "x"
    assert _signature_compatibility("a, b=" + deep, "a, b=" + deep + ", c=1") == "unparseable"
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    # `_SIG_RE` stops at the first `)`; this line has none until its end, so it is captured.
    diff = _diff(["a, b=" + deep], ["a, b=" + deep + ", c"])
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_pathologically_nested_line_with_unchanged_names_keeps_todays_silence(
    tmp_path: Path,
) -> None:
    deep = "not " * 50_000 + "x"
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    diff = _diff(["a, b=" + deep], ["a, b=" + deep + " or y"])
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


# --- F5: a string patch target is a reference -------------------------------

STRING_TARGETS = {
    "monkeypatch-setattr": "def test_x(monkeypatch):\n    monkeypatch.setattr(mod, 'do_work', fake)\n",
    "setattr": "def test_x():\n    setattr(mod, 'do_work', fake)\n",
    "delattr": "def test_x():\n    delattr(mod, 'do_work')\n",
    "patch-object": "def test_x():\n    with patch.object(mod, 'do_work') as m:\n        run()\n",
    "double-quoted": 'def test_x(monkeypatch):\n    monkeypatch.setattr(mod, "do_work", fake)\n',
}


@pytest.mark.parametrize("change", [COMPAT, BREAKING], ids=["compatible", "incompatible"])
@pytest.mark.parametrize("caller", STRING_TARGETS.values(), ids=STRING_TARGETS)
def test_a_string_patch_target_is_flagged_whatever_the_change(
    tmp_path: Path, caller: str, change: tuple[str, str]
) -> None:
    """BEFORE: an incompatible change did not flag a file whose only reference was a
    `monkeypatch.setattr(mod, "name", ...)` string, because the string is blanked by
    `_code_only` and the string check was applied to compatible changes alone. The two
    paths now agree: a string patch target IS a dependency."""
    assert _flagged(tmp_path, caller, change)


def test_a_string_naming_another_function_is_not_a_target(tmp_path: Path) -> None:
    assert not _flagged(
        tmp_path,
        "def test_x(monkeypatch):\n    monkeypatch.setattr(mod, 'other', fake)\n",
        BREAKING,
    )


# --- gaps the mutants exposed -----------------------------------------------


def test_a_positional_only_parameter_inserted_between_old_ones_is_incompatible() -> None:
    """Old `(a=0, b=2, /)`; new `(a=0, x=1, b=2, /)`: a call f(1, 2) now binds 2 to x, so
    b silently takes its default. Every old parameter is positional-only, so only the
    positional-only kind can tell. (A default cannot precede a required parameter, so the
    old parameters carry defaults to make the inserted one syntactically possible.)"""
    old = "a=0, b=2, /"
    assert _signature_compatibility(old, "a=0, x=1, b=2, /") == "incompatible"
    assert _signature_compatibility(old, "x=1, a=0, b=2, /") == "incompatible"
    assert _signature_compatibility(old, "a=0, b=2, x=1, /") == "compatible"
    assert _signature_compatibility("a, b, /", "a, b, x=1, /") == "compatible"


@pytest.mark.parametrize(
    "attribute",
    [
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_not_called",
        "call_args",
        "call_args_list",
        "call_count",
        "mock_calls",
        "method_calls",
        "called",
    ],
)
def test_every_mock_assertion_family_member_makes_a_reference_a_mock(
    tmp_path: Path, attribute: str
) -> None:
    assert _flagged(tmp_path, f"def test_x(m):\n    do_work('a')\n    assert m.{attribute}\n")


def test_an_attribute_that_only_starts_like_a_mock_one_is_not_a_mock(tmp_path: Path) -> None:
    assert not _flagged(tmp_path, "def test_x(m):\n    do_work('a')\n    assert m.callable\n")


def test_a_function_keyword_in_a_python_file_is_text_not_a_definition(tmp_path: Path) -> None:
    """A line spelled `function f(a)` inside a Python file is a JS snippet in a string or
    heredoc: Python files take only a statement-start `def`
    (tests/unit/test_blast_radius_string_literal_defs.py). Before that rule this was read
    through the name comparison and reported."""
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    diff = _diff(["a"], ["a, b = 1"], keyword="function")
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


def test_a_def_in_a_non_python_file_is_not_analysed_as_python(tmp_path: Path) -> None:
    _write(tmp_path / "lib" / "caller.ts", "def go\n  do_work(1)\nend\n")
    diff = _diff(["a"], ["a, b = 1"], path="lib/thing.ts")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "lib/caller.ts" in {f["path"] for f in findings}


def test_multi_line_parameter_text_is_classified_as_written() -> None:
    old = "a,\n    b,\n"
    new = "a,\n    b,\n    *,\n    c: int = 3,\n"
    assert _signature_compatibility(old, new) == "compatible"
    assert _signature_compatibility(old, "a,\n    b,\n    *,\n    c: int,\n") == "incompatible"


def test_a_def_rewritten_across_lines_produces_no_finding_today(tmp_path: Path) -> None:
    """KNOWN LIMIT, pinned honestly: `_SIG_RE` reads one line and needs a closing `)` on it,
    so `def do_work(` alone never matches. A breaking change made while re-wrapping a def
    across lines is therefore not detected, before and after the refinement. Widening
    detection is a separate change; this test makes any such widening deliberate."""
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n"
        "--- a/core/thing.py\n"
        "+++ b/core/thing.py\n"
        "@@ -1,1 +1,5 @@\n"
        "-def do_work(a):\n"
        "+def do_work(\n"
        "+    a,\n"
        "+    b,\n"
        "+):\n"
    )
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []
