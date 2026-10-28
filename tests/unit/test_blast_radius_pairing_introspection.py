"""Issue #926: the shape-set rule, more introspection forms, cost, and the mutant gaps.

H1  Same-named removed and added defs of different counts were compared as SETS of name
    lists, so a changed definition that reused an old shape stayed silent:

        -def do_work(a):            +def do_work(a, b):   # gained a required parameter
        -def do_work(a, b):         +def do_work(a, b):   # moved
                                    +def do_work(a):      # newly added, reuses the old shape

    Main reports that. The comparison is now a MULTISET of the full parameter text: any
    parameter list present more often on the added side than on the removed side is a new
    or changed definition, reported with no compatibility verdict. (It also catches a
    kind-only change, `(a, b)` -> `(a, *, b)`, which names alone cannot show.)
H2  Introspection forms that went unflagged: an aliased import of `signature`, an aliased
    import of the function, `__annotations__`, typing.get_type_hints, dir(), functools.wraps.
    A computed name stays a documented limit.
COST The incompatible-change scan parsed every file containing the name and an introspection
    token, once per name, even when the call-site check had already decided.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.gates import hanging_detectors as hd
from core.gates.hanging_detectors import _inspects_symbol, detect_changed_signature_callers

CALLER = "tests/unit/test_caller.py"
PLAIN = "def test_it():\n    do_work('a')\n"
MOCKING = "def test_it(m):\n    do_work('a')\n    m.assert_called_once_with('a')\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff(removed: list[str], added: list[str], path: str = "core/thing.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        + "".join(f"-def do_work({p}):\n" for p in removed)
        + "".join(f"+def do_work({p}):\n" for p in added)
    )


def _findings(tmp_path: Path, removed: list[str], added: list[str], caller: str = PLAIN):
    _write(tmp_path / CALLER, caller)
    return detect_changed_signature_callers(_diff(removed, added), repo_root=tmp_path)


def _flagged(tmp_path: Path, removed: list[str], added: list[str], caller: str = PLAIN) -> bool:
    return CALLER in {f["path"] for f in _findings(tmp_path, removed, added, caller)}


# --- H1: the multiset rule --------------------------------------------------


def test_the_issue_926_diff_is_reported(tmp_path: Path) -> None:
    """The exact diff from the issue: main blocks it, the shape-set rule passed it."""
    assert _flagged(tmp_path, ["a", "a, b"], ["a, b", "a, b", "a"])


def test_a_kind_only_change_with_unequal_counts_is_reported(tmp_path: Path) -> None:
    assert _flagged(tmp_path, ["a, b"], ["a, *, b", "a, *, b"])
    assert _flagged(tmp_path, ["a, b", "c"], ["a, *, b"])


def test_an_added_duplicate_shape_is_reported(tmp_path: Path) -> None:
    assert _flagged(tmp_path, ["a"], ["a", "a"])


def test_a_dropped_duplicate_of_a_surviving_shape_is_silent(tmp_path: Path) -> None:
    """Fewer definitions of a shape that still exists introduce nothing a caller could meet."""
    assert not _flagged(tmp_path, ["a", "a"], ["a"])
    assert not _flagged(tmp_path, ["a, b", "a", "a, b"], ["a, b", "a"])


def test_a_shape_that_disappears_is_reported(tmp_path: Path) -> None:
    """`(a, b)` no longer exists anywhere: that is a signature change, not a dropped duplicate
    (issue #926 residuals, tests/unit/test_blast_radius_verifier_round.py)."""
    assert _flagged(tmp_path, ["a", "a, b"], ["a"])


def test_the_comparison_ignores_whitespace_but_not_content(tmp_path: Path) -> None:
    assert not _flagged(tmp_path, ["a,b", "a, b"], ["a,  b"])
    assert _flagged(tmp_path, ["a, b"], ["a, b", "a, c"])


def test_the_unequal_count_message_names_the_last_shapes(tmp_path: Path) -> None:
    findings = _findings(tmp_path, ["a, x", "a, y"], ["a, p", "a, q", "a, r"])
    messages = [f["message"] for f in findings if f["path"] == CALLER]
    assert messages, findings
    assert "['a', 'y'] -> ['a', 'r']" in messages[0], messages[0]


# --- pairing order (mutant gap) ---------------------------------------------


def test_equal_counts_are_paired_in_order_compatible_only(tmp_path: Path) -> None:
    """In order: unchanged, then compatible. A reversed pairing would see the second old
    shape against the first new one and report a different thing."""
    assert not _flagged(tmp_path, ["a", "a, b"], ["a", "a, b, c=1"])
    assert _flagged(tmp_path, ["a", "a, b"], ["a", "a, b, c=1"], MOCKING)


def test_equal_counts_are_paired_in_order_incompatible(tmp_path: Path) -> None:
    """In order: ('a' -> 'a, b, c=1') is compatible but ('a, b' -> 'a') drops a parameter.
    Reversed, the pairs would be unchanged and compatible and nothing would be reported."""
    assert _flagged(tmp_path, ["a", "a, b"], ["a, b, c=1", "a"])


def test_equal_counts_second_pair_decides(tmp_path: Path) -> None:
    assert _flagged(tmp_path, ["a", "a"], ["a", "a, *, b"])
    assert _flagged(tmp_path, ["a", "a"], ["a, *, b", "a"])


# --- H2: more introspection forms -------------------------------------------

FORMS = {
    "aliased-signature-import": "from inspect import signature as sig\nsig(do_work)\n",
    "aliased-function-import": (
        "import inspect\nfrom mod import do_work as dw\ninspect.signature(dw)\n"
    ),
    "aliased-function-import-then-alias": (
        "import inspect\nfrom mod import do_work as dw\nx = dw\ninspect.signature(x)\n"
    ),
    "typing-extensions-alias": (
        "from typing_extensions import get_type_hints as gth\ngth(do_work)\n"
    ),
    "dotted-module-alias": "from inspect import signature as sig\nsig(mod.do_work)\n",
    "aliased-module-attribute": "import inspect as insp\ninsp.signature(do_work)\n",
    "dunder-annotations": "print(do_work.__annotations__)\n",
    "dunder-wrapped": "print(do_work.__wrapped__)\n",
    "get-type-hints": "import typing\ntyping.get_type_hints(do_work)\n",
    "bare-get-type-hints": "from typing import get_type_hints\nget_type_hints(do_work)\n",
    "aliased-get-type-hints": "from typing import get_type_hints as gth\ngth(do_work)\n",
    "get-annotations": "import inspect\ninspect.get_annotations(do_work)\n",
    "dir": "print(dir(do_work))\n",
    "wraps-decorator": (
        "import functools\n\n@functools.wraps(do_work)\ndef wrapper(*a):\n    pass\n"
    ),
    "bare-wraps": "from functools import wraps\n\n@wraps(do_work)\ndef wrapper(*a):\n    pass\n",
    "aliased-wraps": "from functools import wraps as w\n\n@w(do_work)\ndef wrapper(*a):\n    pass\n",
    "update-wrapper": "import functools\nfunctools.update_wrapper(wrapper, do_work)\n",
    "three-alias-hops": ("import inspect\nx1 = do_work\nx2 = x1\nx3 = x2\ninspect.signature(x3)\n"),
    "alias-hops-in-reverse-order": (
        "import inspect\n\ndef f():\n    return inspect.signature(x5)\n\n"
        "x5 = x4\nx4 = x3\nx3 = x2\nx2 = x1\nx1 = do_work\n"
    ),
    "annotated-assignment": ("import inspect\nfn: Callable = do_work\ninspect.signature(fn)\n"),
    "walrus": "import inspect\nif (fn := do_work):\n    inspect.signature(fn)\n",
    "keyword-argument": "import inspect\ninspect.signature(obj=do_work)\n",
    "keyword-argument-getfullargspec": "import inspect\ninspect.getfullargspec(func=do_work)\n",
    "second-positional-argument": "import typing\ntyping.get_type_hints(obj, do_work)\n",
    "comprehension-target": (
        "import inspect\nsigs = [inspect.signature(f) for f in (do_work, other)]\n"
    ),
}


@pytest.mark.parametrize("caller", FORMS.values(), ids=FORMS)
def test_an_introspection_form_is_reported_for_a_compatible_change(
    tmp_path: Path, caller: str
) -> None:
    assert _flagged(tmp_path, ["a"], ["a, *, extra=1"], caller)


NOT_OURS = {
    "signature-imported-from-somewhere-else": (
        "from other_lib import signature as sig\nsig(do_work)\n"
    ),
    "wraps-imported-from-somewhere-else": (
        "from other_lib import wraps as w\n\n@w(do_work)\ndef wrapper(*a):\n    pass\n"
    ),
    "dir-of-another": "print(dir(other))\ndo_work('a')\n",
    "bare-dir": "print(dir())\ndo_work('a')\n",
    "wraps-of-another": (
        "from functools import wraps\n\n@wraps(other)\ndef w(*a):\n    pass\ndo_work('a')\n"
    ),
    "aliased-signature-of-another": (
        "from inspect import signature as sig\nsig(other)\ndo_work('a')\n"
    ),
    "aliased-import-of-another": (
        "import inspect\nfrom mod import other as dw\ninspect.signature(dw)\ndo_work('a')\n"
    ),
    "annotations-of-another": "print(other.__annotations__)\ndo_work('a')\n",
    "hint-of-another": "import typing\ntyping.get_type_hints(other)\ndo_work('a')\n",
    "unrelated-alias": ("import inspect\nfn = other\ninspect.signature(fn)\ndo_work('a')\n"),
    "walrus-of-another": (
        "import inspect\nif (fn := other):\n    inspect.signature(fn)\ndo_work('a')\n"
    ),
    "annotated-of-another": (
        "import inspect\nfn: Callable = other\ninspect.signature(fn)\ndo_work('a')\n"
    ),
    "keyword-of-another": "import inspect\ninspect.signature(obj=other)\ndo_work('a')\n",
}


@pytest.mark.parametrize("caller", NOT_OURS.values(), ids=NOT_OURS)
def test_introspecting_something_else_is_not_a_reference(tmp_path: Path, caller: str) -> None:
    assert not _flagged(tmp_path, ["a"], ["a, *, extra=1"], caller)


def test_a_computed_name_is_still_a_documented_limit(tmp_path: Path) -> None:
    caller = "from inspect import signature as sig\ndo_work('a')\nsig(getattr(Cls, method))\n"
    assert not _flagged(tmp_path, ["a"], ["a, *, extra=1"], caller)


# --- the textual fallback (a file that is not parseable Python) -------------


def test_the_textual_fallback_reads_an_attribute_form() -> None:
    broken = "def broken(:\n    pass\nprint(do_work.__code__.co_argcount)\n"
    assert _inspects_symbol(broken, "do_work")
    assert _inspects_symbol(broken.replace("__code__", "__annotations__"), "do_work")
    assert _inspects_symbol(broken.replace("__code__", "__defaults__"), "do_work")
    assert _inspects_symbol(broken.replace("__code__", "__wrapped__"), "do_work")
    assert _inspects_symbol(broken.replace("__code__", "__signature__"), "do_work")


def test_the_textual_fallback_needs_a_word_boundary_before_the_name() -> None:
    broken = "def broken(:\n    pass\n"
    assert not _inspects_symbol(broken + "print(my_do_work.__code__)\n", "do_work")
    assert not _inspects_symbol(broken + "inspect.signature(xdo_work)\n", "do_work")
    assert not _inspects_symbol(broken + "inspect.signature(do_work_two)\n", "do_work")
    assert _inspects_symbol(broken + "inspect.signature(mod.do_work)\n", "do_work")
    assert _inspects_symbol(broken + "inspect.signature(  do_work)\n", "do_work")


@pytest.mark.parametrize(
    "call",
    ["signature", "getfullargspec", "getargspec", "getcallargs", "from_callable"]
    + ["get_type_hints", "get_annotations", "dir", "wraps", "update_wrapper"],
)
def test_the_textual_fallback_reads_every_call_form(call: str) -> None:
    broken = "def broken(:\n    pass\n"
    assert _inspects_symbol(broken + f"x = {call}(do_work)\n", "do_work")
    assert not _inspects_symbol(broken + f"x = {call}(other)\n", "do_work")


# --- cost: decide early, parse once -----------------------------------------


def test_a_file_is_parsed_once_however_many_names_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"n{i}" for i in range(20)]
    text = "import inspect\n" + "".join(f"{n}(1)\n" for n in names) + "inspect.signature(other)\n"
    _write(tmp_path / "tests" / "unit" / "test_big.py", text)
    removed = "".join(f"-def {n}(a):\n" for n in names)
    added = "".join(f"+def {n}(a, *, e=1):\n" for n in names)
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n--- a/core/thing.py\n+++ b/core/thing.py\n"
        "@@ -1,1 +1,1 @@\n" + removed + added
    )
    real_parse = ast.parse
    seen = []

    def counting(source, *a, **k):
        if source == text:
            seen.append(1)
        return real_parse(source, *a, **k)

    monkeypatch.setattr(ast, "parse", counting)
    detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert len(seen) <= 1, f"the same file was parsed {len(seen)} times for 20 names"


def test_a_file_is_tokenized_once_however_many_names_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"n{i}" for i in range(20)]
    text = "import inspect\n" + "".join(f"{n}(1)\n" for n in names)
    _write(tmp_path / "tests" / "unit" / "test_big.py", text)
    removed = "".join(f"-def {n}(a):\n" for n in names)
    added = "".join(f"+def {n}(a, *, e=1):\n" for n in names)
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n--- a/core/thing.py\n+++ b/core/thing.py\n"
        "@@ -1,1 +1,1 @@\n" + removed + added
    )
    real = hd._code_only
    seen = []

    def spy(source):
        if source == text:
            seen.append(1)
        return real(source)

    monkeypatch.setattr(hd, "_code_only", spy)
    detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert len(seen) <= 1, f"the same file was tokenized {len(seen)} times for 20 names"


def test_the_memo_is_off_outside_a_detector_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A direct call must never see a stale entry from an earlier call with the same string
    object: two direct calls parse twice."""
    real = ast.parse
    seen = []

    def counting(source, *a, **k):
        seen.append(1)
        return real(source, *a, **k)

    monkeypatch.setattr(ast, "parse", counting)
    text = "import inspect\ninspect.signature(do_work)\n"
    assert _inspects_symbol(text, "do_work")
    assert _inspects_symbol(text, "do_work")
    assert len(seen) == 2
    assert hd._Memo.active is False


def test_the_memo_is_switched_off_even_when_the_scan_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path / CALLER, PLAIN)

    def boom(root):
        raise RuntimeError("a file could not be read")

    monkeypatch.setattr(hd, "_iter_code_files", boom)
    with pytest.raises(RuntimeError):
        detect_changed_signature_callers(_diff(["a"], ["a, *, extra"]), repo_root=tmp_path)
    assert hd._Memo.active is False
    assert hd._Memo.tree_of is None and hd._Memo.code_of is None


def test_an_incompatible_change_decided_by_a_call_site_never_looks_further(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    real = hd._string_reference

    def spy(text, name):
        calls.append(name)
        return real(text, name)

    monkeypatch.setattr(hd, "_string_reference", spy)
    findings = _findings(tmp_path, ["a"], ["a, *, extra"], "import inspect\ndo_work('a')\n")
    assert CALLER in {f["path"] for f in findings}
    assert calls == [], "a strict finding decided by the call site still searched for strings"


def test_a_compatible_change_looks_further_only_when_it_must(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    real = hd._string_reference

    def spy(text, name):
        calls.append(name)
        return real(text, name)

    monkeypatch.setattr(hd, "_string_reference", spy)
    assert not _flagged(tmp_path, ["a"], ["a, *, extra=1"], PLAIN)
    assert calls, "a compatible change must still look for mocks and introspection"
    assert len(calls) <= 1, f"string references were computed {len(calls)} times for one file"


def test_a_file_without_the_name_is_not_even_tokenized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(30):
        _write(tmp_path / "core" / f"unrelated_{i}.py", f"def other_{i}():\n    return {i}\n")
    _write(tmp_path / CALLER, PLAIN)
    real = hd._code_only
    seen = []

    def spy(text):
        seen.append(text)
        return real(text)

    monkeypatch.setattr(hd, "_code_only", spy)
    detect_changed_signature_callers(_diff(["a"], ["a, *, extra"]), repo_root=tmp_path)
    assert not [t for t in seen if "do_work" not in t], "a file without the name was tokenized"
