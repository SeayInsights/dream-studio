"""The untested-fallback detector the lane declared and nobody wrote.

`an-untested-fallback-lane` named `py -m core.gates.untested_fallback`, which was
a ModuleNotFoundError.

The test that matters most here is `test_ordinary_error_handling_is_not_a_fallback`.
The first cut of this detector treated every non-reraising `except` as a fallback
and reported 685 sites whole-tree against the lane's predicted 14. Most handlers
log and carry on; they take no alternative path. Narrowing to "catches the
primary path being UNAVAILABLE and supplies it another way" measures 7. A gate
reporting 685 is a wall, and a wall gets switched off in its first week -- which
is the same outcome as never having written it.
"""

from __future__ import annotations

import textwrap

from core.gates import untested_fallback as gate


def _tree(root, product: str, tests: str = ""):
    (root / "core").mkdir(parents=True, exist_ok=True)
    (root / "core" / "w.py").write_text(textwrap.dedent(product), encoding="utf-8")
    td = root / "tests"
    td.mkdir(parents=True, exist_ok=True)
    (td / "test_w.py").write_text(
        textwrap.dedent(tests or "def test_nothing():\n    pass\n"), encoding="utf-8"
    )
    return root


def _run(root):
    return gate.run(root, all_files=True)


def test_import_fallback_no_test_names_it_is_a_finding(tmp_path):
    _tree(
        tmp_path,
        """
        def load_parser():
            try:
                import fastjson as parser
            except ImportError:
                import json as parser
            return parser
        """,
    )
    result = _run(tmp_path)
    assert result["status"] == "found"
    assert result["findings"][0]["function"] == "load_parser"
    assert result["findings"][0]["kind"] == "exception"


def test_ordinary_error_handling_is_not_a_fallback(tmp_path):
    """The 685-vs-14 case. A handler that logs and carries on takes no alternative
    path -- it is error handling, not a fallback, and reporting it buries the real
    findings under two orders of magnitude of noise."""
    _tree(
        tmp_path,
        """
        def save(thing):
            try:
                write(thing)
            except ValueError:
                log.warning("bad thing")
                return None
        """,
    )
    assert _run(tmp_path)["status"] == "clean"


def test_an_import_error_that_only_logs_is_not_a_fallback(tmp_path):
    """Catching ImportError is necessary but not sufficient. Without supplying the
    thing another way, there is no second path for a test to enter."""
    _tree(
        tmp_path,
        """
        def probe():
            try:
                import optional_dep
            except ImportError:
                log.info("optional dep absent")
        """,
    )
    assert _run(tmp_path)["status"] == "clean"


def test_platform_conditional_is_a_finding(tmp_path):
    """The lane's own precedent was a Windows-only path. A detector blind to
    platform conditionals cannot see the shape of the case it was written from."""
    _tree(
        tmp_path,
        """
        import sys

        def pid_exists(pid):
            if sys.platform == "win32":
                return _win_probe(pid)
            return _posix_probe(pid)
        """,
    )
    result = _run(tmp_path)
    assert result["status"] == "found"
    assert result["findings"][0]["kind"] == "platform"


def test_a_fallback_some_test_names_is_clean(tmp_path):
    """A textual mention is all the lane asks for -- it proves the name is KNOWN
    to the tests, not that they exercise it. The stronger check needs coverage
    data and the lane defers it explicitly."""
    _tree(
        tmp_path,
        """
        def load_parser():
            try:
                import fastjson as parser
            except ImportError:
                import json as parser
            return parser
        """,
        tests="""
        def test_parser():
            from core.w import load_parser
            assert load_parser() is not None
        """,
    )
    assert _run(tmp_path)["status"] == "clean"


def test_a_declared_site_is_exempt(tmp_path):
    _tree(
        tmp_path,
        """
        def load_parser():
            # untested-fallback: the accelerated parser is never installed in CI
            try:
                import fastjson as parser
            except ImportError:
                import json as parser
            return parser
        """,
    )
    assert _run(tmp_path)["status"] == "clean"


def test_a_module_level_fallback_has_no_symbol_to_check(tmp_path):
    """Outside a function there is no name a test could mention, so the lane's
    own clearing rule cannot be applied. Reporting it would be unanswerable."""
    _tree(
        tmp_path,
        """
        try:
            import fastjson as parser
        except ImportError:
            import json as parser
        """,
    )
    assert _run(tmp_path)["status"] == "clean"


def test_scope_is_reported(tmp_path):
    """Whether a result covered the change set or the whole tree changes what a
    clean result means, so the result says which."""
    _tree(tmp_path, "def f():\n    pass\n")
    assert gate.run(tmp_path, all_files=True)["scope"] == "whole-tree"


def test_finding_exits_nonzero(tmp_path):
    _tree(
        tmp_path,
        """
        def load_parser():
            try:
                import fastjson as parser
            except ImportError:
                import json as parser
            return parser
        """,
    )
    assert gate.main(["--repo-root", str(tmp_path), "--all"]) == 1


def test_accepts_repo_root(tmp_path):
    _tree(tmp_path, "def f():\n    pass\n")
    assert gate.main(["--repo-root", str(tmp_path), "--all"]) == 0


def test_real_tree_backlog_is_small_enough_to_be_actionable():
    """Against the actual repository, whole-tree. The number is the point: the
    first cut of this detector reported 685 here, which is a wall. If this ever
    climbs back into the hundreds the detection has broadened wrongly again, and
    the gate will be ignored rather than obeyed."""
    result = gate.run(all_files=True)
    assert result["files_scanned"] > 500
    assert len(result["findings"]) < 40, [f["file"] for f in result["findings"]][:10]
