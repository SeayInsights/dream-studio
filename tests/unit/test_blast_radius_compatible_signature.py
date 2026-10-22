"""The changed-signature detector must not block a CALL-COMPATIBLE signature change.

PR #918 (migration 161) changed the signature of record_execution_event from
``(conn, **values)`` to ``(conn, *, spool=True, **values)``, and the blast-radius gate
blocked it: five emitters and two tests reference the function and were "not updated".
They did not need to be. (The docstring is worded so that no line reads like a second
definition: the detector counts definitions of a name to decide whether it is ambiguous.) `spool` is keyword-only WITH a default,
so every existing call still binds exactly as it did. The detector compared only the TUPLE
OF PARAMETER NAMES, so any added parameter -- even one no caller can notice -- was
reported as a signature change.

The detector now parses the old and new parameter lists with ``ast`` and asks whether any
call that was valid before is still valid and still binds the same way. These tests pin
that decision table, the corner that is deliberately NOT silenced (a file that MOCKS the
function can still break on a compatible change -- that is #353), and the fallbacks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates.hanging_detectors import (
    _signature_compatibility,
    detect_changed_signature_callers,
)

CALLER = "tests/unit/test_caller.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff(old: str, new: str, name: str = "do_work", path: str = "core/thing.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        f"-def {name}({old}):\n"
        f"+def {name}({new}):\n"
    )


def _flagged(
    tmp_path: Path,
    old: str,
    new: str,
    *,
    caller: str = "def test_it():\n    do_work('a')\n",
) -> bool:
    _write(tmp_path / CALLER, caller)
    findings = detect_changed_signature_callers(_diff(old, new), repo_root=tmp_path)
    return CALLER in {f["path"] for f in findings}


# --- the real change -------------------------------------------------------


def test_the_918_record_execution_event_change_is_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "telemetry" / "emitters_activity.py",
        "from core.telemetry.execution_spine import record_execution_event\n\n"
        "def emit(conn):\n    record_execution_event(conn, event_id='e', kind='k')\n",
    )
    _write(
        tmp_path / "tests" / "unit" / "test_telemetry_read_models.py",
        "def test_x(conn):\n    record_execution_event(conn, event_id='e')\n",
    )
    diff = _diff(
        "conn: sqlite3.Connection, **values: Any",
        "conn: sqlite3.Connection, *, spool: bool = True, **values: Any",
        name="record_execution_event",
        path="core/telemetry/execution_spine.py",
    )
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


# --- compatible: not reported ----------------------------------------------


@pytest.mark.parametrize(
    "old,new",
    [
        pytest.param("conn, **values", "conn, *, spool=True, **values", id="kwonly-default"),
        pytest.param("conn", "conn, *, spool=True", id="kwonly-default-no-kwargs"),
        pytest.param("a, b", "a, b, c=None", id="positional-default-appended"),
        pytest.param("a, b", "a, b, *args", id="args-added"),
        pytest.param("a, b", "a, b, **kwargs", id="kwargs-added"),
        pytest.param("a, b", "a, b, *args, **kwargs", id="both-added"),
        pytest.param("a, b", "a, b=1", id="required-gains-default"),
        pytest.param("a, b=1", "a, b=2", id="default-value-changed"),
        pytest.param("a: int, b", "a: int | None, b", id="annotation-only"),
        pytest.param(
            "relation_type: Union[RelationType, str]",
            "relation_type: RelationType | str",
            id="union-modernised",
        ),
    ],
)
def test_call_compatible_change_is_not_reported(tmp_path: Path, old: str, new: str) -> None:
    assert not _flagged(tmp_path, old, new)


# --- incompatible: reported -------------------------------------------------


@pytest.mark.parametrize(
    "old,new",
    [
        pytest.param("a, b", "a, b, *, c", id="kwonly-required-added"),
        pytest.param("a, b", "a, b, c", id="positional-required-appended"),
        pytest.param("a, b", "a, c=1, b", id="unparseable-default-before-required"),
        pytest.param("a, b=1", "a, c=1, b=1", id="positional-default-inserted-in-the-middle"),
        pytest.param("a, b", "c=None, a=None, b=None", id="positional-default-inserted-first"),
        pytest.param("a, b", "a", id="removed"),
        pytest.param("a, b", "a, bee", id="renamed"),
        pytest.param("a, b", "b, a", id="reordered"),
        pytest.param("a, b=1", "a, b", id="default-removed"),
        pytest.param("a, *, b=1", "a, *, b", id="kwonly-default-removed"),
        pytest.param("a, b", "a, *, b", id="positional-or-keyword-to-keyword-only"),
        pytest.param("a, *, b", "a, b", id="keyword-only-to-positional-or-keyword"),
        pytest.param("a, b", "a, b, /", id="positional-or-keyword-to-positional-only"),
        pytest.param("a, **kwargs", "a", id="kwargs-removed"),
        pytest.param("a, *args", "a", id="args-removed"),
        pytest.param("a, **kwargs", "a, **opts", id="kwargs-renamed"),
        pytest.param("a, *args", "a, b=1, *args", id="positional-default-steals-from-args"),
        pytest.param("a, b", "a, *args, b", id="args-inserted-before-positional"),
    ],
)
def test_call_incompatible_change_is_reported(tmp_path: Path, old: str, new: str) -> None:
    assert _flagged(tmp_path, old, new)


def test_unparseable_signature_falls_back_to_reporting(tmp_path: Path) -> None:
    """A parameter list `ast` cannot parse is never silenced. `_SIG_RE` stops at the first
    `)`, and a parameter list that is not valid Python gets today's name comparison."""
    assert _flagged(tmp_path, "a, b", "a, b, c d")


def test_unparseable_signature_with_equal_names_keeps_todays_silence(tmp_path: Path) -> None:
    """The fallback IS the previous behaviour, no more and no less: names equal -> no
    finding, exactly as before. (`_SIG_RE` captures `a, b=f(x` here: it stops at the
    first `)`, so this really is an unparseable pair.)"""
    assert not _flagged(tmp_path, "a, b=f(x)", "a, b=g(x)")


def test_the_helper_says_it_cannot_tell_rather_than_guessing() -> None:
    assert _signature_compatibility("a, b=f(", "a, b=f(, c") == "unparseable"
    assert _signature_compatibility("a, b", "a, b, c d") == "unparseable"


# --- the helper's verdicts --------------------------------------------------


def test_helper_distinguishes_compatible_from_unchanged_from_incompatible() -> None:
    assert _signature_compatibility("a, b", "a, b") == "unchanged"
    assert _signature_compatibility("a: int", "a: str") == "unchanged"
    assert _signature_compatibility("a, b", "a, b, *, c=1") == "compatible"
    assert _signature_compatibility("a, b", "a, b, *, c") == "incompatible"
    assert _signature_compatibility("a, b=1", "a, b") == "incompatible"
    assert _signature_compatibility("a, b=(1, 2)", "a, b=(1, 2), *, c={'k': [1, 2]}") == (
        "compatible"
    )


def test_adding_a_required_keyword_only_parameter_breaks_callers_helper() -> None:
    assert _signature_compatibility("conn, **values", "conn, *, spool, **values") == "incompatible"


def test_a_key_callers_pass_through_kwargs_is_still_compatible() -> None:
    """DECIDED EDGE. A caller that passes `spool=...` today lands it in **values; after
    the change it binds to the new parameter instead. That is a semantic shift for the one
    key whose name the author chose, and the author is the one who chose it: the diff that
    adds `spool` is the diff that decides what a `spool` key means. Every other call is
    untouched, and reporting every caller of every **kwargs function that gains a named
    keyword is what blocked #918. Compatible, and documented in the detector docstring."""
    assert _signature_compatibility("conn, **values", "conn, *, spool=True, **values") == (
        "compatible"
    )


# --- #353: a compatible signature still breaks a MOCK of the function --------


def test_a_compatible_change_still_flags_a_patch_target(tmp_path: Path) -> None:
    """#353 was exactly a compatible widening: `(session_id, cwd)` gained
    `handoff_path=None`. The break was a test asserting the OLD CALL SHAPE through a
    mock.patch target, which a compatible signature does not protect. So compatibility
    silences ordinary references and nothing that mocks the function."""
    _write(
        tmp_path / CALLER,
        "from unittest.mock import patch\n\n"
        "def test_calls_writer():\n"
        "    with patch('pkg.mod.do_work') as m:\n"
        "        run()\n"
        "        m.assert_called_once_with('a')\n",
    )
    diff = _diff("a", "a, extra=None")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_compatible_change_still_flags_a_monkeypatched_name(tmp_path: Path) -> None:
    _write(
        tmp_path / CALLER,
        "def test_x(monkeypatch):\n    monkeypatch.setattr(mod, 'do_work', fake)\n    run()\n",
    )
    findings = detect_changed_signature_callers(_diff("a", "a, *, extra=1"), repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_compatible_change_still_flags_a_mock_assertion_on_the_name(tmp_path: Path) -> None:
    _write(
        tmp_path / CALLER,
        "def test_x():\n    m = Mock()\n    run(m)\n    m.assert_called_once_with('a')\n"
        "    do_work('a')\n",
    )
    findings = detect_changed_signature_callers(_diff("a", "a, *, extra=1"), repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_plain_caller_of_a_compatible_change_is_not_flagged(tmp_path: Path) -> None:
    """The other direction: without it the mock carve-out would be indistinguishable from
    not having made the refinement at all."""
    assert not _flagged(tmp_path, "a", "a, *, extra=1")


def test_an_incompatible_change_flags_a_plain_caller(tmp_path: Path) -> None:
    assert _flagged(tmp_path, "a", "a, *, extra")


def test_one_incompatible_def_wins_over_a_compatible_def_of_the_same_name(
    tmp_path: Path,
) -> None:
    """Two files change a function of the same name, one compatibly and one not. The
    stricter verdict must stand whichever order the diff lists them."""
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    one = _diff("a", "a, *, extra=1", path="core/one.py")
    two = _diff("a", "a, *, extra", path="core/two.py")
    for diff in (one + two, two + one):
        findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
        assert CALLER in {f["path"] for f in findings}


def test_a_def_in_a_non_python_file_keeps_the_name_comparison(tmp_path: Path) -> None:
    """The `.py` guard on its own: a `def` line outside a Python file (a template or a
    code sample in a scanned suffix) parses as Python but is not analysed as Python."""
    _write(tmp_path / "lib" / "caller.ts", "def go\n  build(1)\nend\n")
    diff = (
        "diff --git a/lib/thing.ts b/lib/thing.ts\n"
        "--- a/lib/thing.ts\n"
        "+++ b/lib/thing.ts\n"
        "@@ -1,1 +1,1 @@\n"
        "-def build(a)\n"
        "+def build(a, b = 1)\n"
    )
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "lib/caller.ts" in {f["path"] for f in findings}


def test_non_python_signatures_keep_the_name_comparison(tmp_path: Path) -> None:
    """`function f(a, b)` in a .js file is parsed by no Python rule: adding a parameter
    there is reported as before, because a default is not a keyword-only contract in JS."""
    _write(tmp_path / "web" / "caller.js", "function go() { build(1); }\n")
    diff = (
        "diff --git a/web/lib.js b/web/lib.js\n"
        "--- a/web/lib.js\n"
        "+++ b/web/lib.js\n"
        "@@ -1,1 +1,1 @@\n"
        "-function build(a) {\n"
        "+function build(a, b = 1) {\n"
    )
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "web/caller.js" in {f["path"] for f in findings}
