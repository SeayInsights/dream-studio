"""What a DIRECTORY run of pytest leaves out, as the rule-enforcement gate must see it.

`canonical/rules.yml` names tests as `file::test`. Naming a file and a test that exist is not
enough: CI and developers run pytest on directories, and a directory run does not collect
everything an explicit `pytest file.py::test` does. A test excluded from the directory run
enforces nothing in CI, so a rule that names only that test is a rule nothing holds up --
the failure `core/gates/rule_enforcement.py` exists to catch, one level further out.

The resolver (`core/gates/pytest_node_resolver.py`) reads the exclusions pytest applies from
the repo's own configuration and conftest files without importing anything:

  * `--ignore`, `--ignore-glob`, `--deselect` in `addopts`;
  * `norecursedirs` (the default set when the repo names none), `testpaths`;
  * `collect_ignore` / `collect_ignore_glob` in the root conftest AND sub-directory
    conftests, where the NEAREST conftest that defines the name is the only one pytest reads;
  * pytest's built-in exclusions (`__pycache__`, a virtualenv root).

Every one is judged by pytest itself in `test_pytest_collection_agreement.py`: each scenario
builds a tree, asks `pytest --collect-only` what a bare run collects, and requires the resolver
to agree on every file in both directions. That file starts a pytest process per scenario, so
CI runs it and the pre-push pin list does not; this one is pure source analysis and does run
on every push.

What it cannot evaluate it refuses, naming the cause, rather than accepting on doubt: a
`collect_ignore` that is not a literal list of strings, and any conftest that defines a hook
which changes what is collected (`pytest_collect_file` and its relatives).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.gates.pytest_node_resolver import CollectionConfigError, NodeResolver
from tests.helpers.resolver_cases import _DEFAULT_DIRS, _OK, _SCENARIOS, _defaults
from tests.helpers.resolver_cases import write_tree as _tree

REPO_ROOT = Path(__file__).resolve().parents[2]


def _why(root: Path, reference: str) -> str | None:
    return NodeResolver(root).resolve(reference)


# --------------------------------------------------------------------------
# Each exclusion is refused naming the exclusion that excludes it
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reference,fragments",
    [
        ("build/test_top_0.py::test_ok", ["norecursedirs", "`build`"]),
        ("ok/build/test_ok_then_build.py::test_ok", ["norecursedirs", "`build`"]),
        ("node_modules/test_top_2.py::test_ok", ["norecursedirs", "`node_modules`"]),
        (".hidden/test_top_4.py::test_ok", ["norecursedirs", "`.*`"]),
        ("pkg.egg/test_top_5.py::test_ok", ["norecursedirs", "`*.egg`"]),
        ("{arch}/test_top_8.py::test_ok", ["norecursedirs", "`{arch}`"]),
        ("__pycache__/test_in_pycache.py::test_ok", ["__pycache__"]),
        ("myenv/test_in_a_virtualenv.py::test_ok", ["virtualenv", "pyvenv.cfg"]),
    ],
)
def test_a_default_exclusion_is_named(tmp_path, reference, fragments):
    root = _tree(tmp_path, _defaults())
    why = _why(root, reference) or ""
    assert all(f in why for f in fragments), why


@pytest.mark.parametrize("name", ["_build", "ok", "tmp_x"])
def test_directories_pytest_does_collect_resolve(tmp_path, name):
    """`_build` and `tmp*` are not in pytest's default norecursedirs, whatever folklore says."""
    root = _tree(tmp_path, _defaults())
    index = _DEFAULT_DIRS.index(name)
    assert _why(root, f"{name}/test_top_{index}.py::test_ok") is None
    assert _why(root, f"{name}/inner/test_inner_{index}.py::test_ok") is None


def test_the_default_norecursedirs_are_the_ones_the_installed_pytest_uses():
    """Hardcoded here so the gate does not import pytest; this pins the copy to the real one."""
    from _pytest.config import _prepareconfig

    from core.gates.pytest_collection_rules import DEFAULT_NORECURSEDIRS

    config = _prepareconfig([], None)
    assert sorted(DEFAULT_NORECURSEDIRS) == sorted(config.getini("norecursedirs"))


def test_a_collect_ignore_in_the_root_conftest_names_the_conftest_and_the_entry(tmp_path):
    root = _tree(tmp_path, _SCENARIOS["conftest"][0])
    why = _why(root, "test_root_ignored.py::test_ok") or ""
    assert "collect_ignore" in why and "conftest.py" in why and "test_root_ignored.py" in why
    why = _why(root, "ignored_dir/test_in_ignored_dir.py::test_ok") or ""
    assert "collect_ignore" in why and "ignored_dir" in why
    why = _why(root, "glob_test.py::test_ok") or ""
    assert "collect_ignore_glob" in why and "glob_*" in why
    why = _why(root, "sub/test_sub_ignored.py::test_ok") or ""
    assert "collect_ignore" in why and "sub" in why and "conftest.py" in why


def test_only_the_nearest_conftest_that_defines_collect_ignore_is_read(tmp_path):
    root = _tree(tmp_path, _SCENARIOS["conftest"][0])
    assert _why(root, "sub/test_masked.py::test_ok") is None
    assert _why(root, "sub/deep/test_deep_kept.py::test_ok") is None
    assert _why(root, "plain/test_plain_kept.py::test_ok") is None


def test_addopts_exclusions_are_named(tmp_path):
    root = _tree(tmp_path, _SCENARIOS["addopts"][0])
    cases = {
        "ign_file/test_ign.py::test_ok": "--ignore",
        "ign_dir/test_in_ign_dir.py::test_ok": "--ignore",
        "x/globbed_one_test.py::test_ok": "--ignore-glob",
        "x/y/globbed_two_test.py::test_ok": "--ignore-glob",
        "desel_dir/test_desel.py::test_ok": "--deselect",
        "desel_dir/test_desel.py::test_ok_two": "--deselect",
        "desel_other/test_a.py::test_ok": "--deselect",
        "desel_other/sub/test_b.py::test_ok": "--deselect",
    }
    for reference, fragment in cases.items():
        why = _why(root, reference) or ""
        assert fragment in why and "addopts" in why, (reference, why)
    for reference in (
        "ign_file/test_ign_sibling.py::test_ok",
        "globbed_three_test.py::test_ok",
        "desel_dir/test_desel_kept.py::test_ok",
        "kept/test_kept.py::test_ok",
    ):
        assert _why(root, reference) is None, reference


def test_a_file_outside_testpaths_is_named(tmp_path):
    root = _tree(tmp_path, _SCENARIOS["testpaths"][0])
    for reference in ("other/test_other.py::test_ok", "test_root.py::test_ok"):
        why = _why(root, reference) or ""
        assert "testpaths" in why and "in_a" in why, (reference, why)
    for reference in (
        "in_a/test_a.py::test_ok",
        "in_b/sub/test_b_sub.py::test_ok",
        "globdir_1/test_g1.py::test_ok",
        "globdir_2/test_g2.py::test_ok",
        "build/test_in_build.py::test_ok",
    ):
        assert _why(root, reference) is None, reference
    # a file listed in testpaths is an explicit argument: python_files does not apply to it
    assert _why(root, "checks.py::test_ok") is None
    assert "norecursedirs" in (_why(root, "in_a/build/test_in_a_build.py::test_ok") or "")
    assert "norecursedirs" in (_why(root, "build/dist/test_nested_dist.py::test_ok") or "")


def test_testpaths_that_match_nothing_fall_back_to_the_whole_tree_as_pytest_does(tmp_path):
    root = _tree(
        tmp_path,
        {"pytest.ini": "[pytest]\ntestpaths = nowhere\n", "test_a.py": _OK},
    )
    assert _why(root, "test_a.py::test_ok") is None


def test_norecursedirs_named_by_the_repo_replaces_the_defaults(tmp_path):
    root = _tree(tmp_path, _SCENARIOS["norecursedirs"][0])
    assert _why(root, "build/test_b.py::test_ok") is None
    assert "`skipme`" in (_why(root, "skipme/test_s.py::test_ok") or "")
    assert "`custom_*`" in (_why(root, "custom_x/test_c.py::test_ok") or "")
    assert "`skipme`" in (_why(root, "ok/skipme/test_deep.py::test_ok") or "")
    assert "norecursedirs" in (_why(root, "a/b/test_path_pattern.py::test_ok") or "")
    assert "norecursedirs" in (_why(root, "c/a/b/test_path_pattern_two.py::test_ok") or "")
    assert _why(root, "a/test_a_only.py::test_ok") is None


# --------------------------------------------------------------------------
# What cannot be evaluated is refused, naming the cause
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "import os\ncollect_ignore = [os.path.join('a', 'b')]\n",
        "collect_ignore = ['a'] + ['b']\n",
        "collect_ignore = [name for name in ('a', 'b')]\n",
        "collect_ignore = ['a', 3]\n",
        "import sys\nif sys.platform == 'plan9':\n    collect_ignore = ['a']\n",
        "collect_ignore = []\nif True:\n    collect_ignore.append('a')\n",
        "collect_ignore = []\ncollect_ignore.append(compute())\n",
        "collect_ignore = []\ncollect_ignore.extend(compute())\n",
        "from elsewhere import collect_ignore\n",
        "def hide():\n    return collect_ignore\n",
        "collect_ignore += ['a']\n",
    ],
)
def test_a_collect_ignore_that_cannot_be_evaluated_is_refused_not_accepted(tmp_path, body):
    root = _tree(tmp_path, {"conftest.py": body, "test_a.py": _OK})
    why = _why(root, "test_a.py::test_ok") or ""
    assert "cannot evaluate" in why and "collect_ignore" in why and "conftest.py" in why, why


def test_a_non_literal_collect_ignore_glob_is_refused_too(tmp_path):
    root = _tree(tmp_path, {"conftest.py": "collect_ignore_glob = make()\n", "test_a.py": _OK})
    assert "cannot evaluate" in (_why(root, "test_a.py::test_ok") or "")


@pytest.mark.parametrize(
    "body,ignored",
    [
        ("collect_ignore = ['test_a.py']\n", True),
        ("collect_ignore = ('test_a.py',)\n", True),
        ("collect_ignore: list = ['test_a.py']\n", True),
        ("collect_ignore = []\ncollect_ignore.append('test_a.py')\n", True),
        ("collect_ignore = []\ncollect_ignore.extend(['test_a.py'])\n", True),
        ("collect_ignore = []\ncollect_ignore += ['test_a.py']\n", True),
        ("collect_ignore = ['other.py']\ncollect_ignore = []\n", False),
        ("collect_ignore = ['test_a.py']\ncollect_ignore = []\n", False),
    ],
)
def test_the_literal_forms_of_collect_ignore_are_evaluated(tmp_path, body, ignored):
    root = _tree(tmp_path, {"conftest.py": body, "test_a.py": _OK})
    why = _why(root, "test_a.py::test_ok")
    if ignored:
        assert why is not None and "collect_ignore" in why and "cannot evaluate" not in why, why
    else:
        assert why is None, why


@pytest.mark.parametrize(
    "body",
    [
        "collect_ignore = ['test_x.py']\ncollect_ignore += ['test_a.py']\n",
        "collect_ignore = ['test_x.py']\ncollect_ignore.append('test_a.py')\n",
        "collect_ignore = ['test_x.py']\ncollect_ignore.extend(['test_a.py'])\n",
    ],
)
def test_an_extension_keeps_what_the_list_already_held(tmp_path, body):
    root = _tree(tmp_path, {"conftest.py": body, "test_a.py": _OK, "test_x.py": _OK})
    for name in ("test_a.py", "test_x.py"):
        assert "collect_ignore" in (_why(root, f"{name}::test_ok") or ""), name


def test_a_conda_environment_without_pyvenv_cfg_is_a_virtualenv_too(tmp_path):
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\n",
            "condaenv/conda-meta/history": "x\n",
            "condaenv/test_in_conda.py": _OK,
        },
    )
    assert "virtualenv" in (_why(tmp_path, "condaenv/test_in_conda.py::test_ok") or "")


@pytest.mark.parametrize(
    "text,expected",
    [("true", True), ("yes", True), ("1", True), ("false", False), ("off", False), ("0", False)],
)
def test_the_bool_spellings_pytest_accepts_are_read(tmp_path, text, expected):
    _tree(
        tmp_path,
        {
            "pytest.ini": f"[pytest]\ncollect_imported_tests = {text}\n",
            "helper.py": "def test_shared():\n    pass\n",
            "test_a.py": "from helper import test_shared\n",
        },
    )
    assert (_why(tmp_path, "test_a.py::test_shared") is None) is expected


def test_a_non_literal_collect_ignore_in_a_sub_conftest_does_not_affect_other_directories(
    tmp_path,
):
    root = _tree(
        tmp_path,
        {
            "sub/conftest.py": "collect_ignore = compute()\n",
            "sub/test_in_sub.py": _OK,
            "test_at_root.py": _OK,
        },
    )
    assert "cannot evaluate" in (_why(root, "sub/test_in_sub.py::test_ok") or "")
    assert _why(root, "test_at_root.py::test_ok") is None


def test_a_conftest_that_does_not_parse_is_refused(tmp_path):
    root = _tree(tmp_path, {"conftest.py": "def broken(:\n", "test_a.py": _OK})
    why = _why(root, "test_a.py::test_ok") or ""
    assert "conftest.py" in why and "does not parse" in why


@pytest.mark.parametrize(
    "option",
    ["-m", "-k", "--noconftest", "--confcutdir", "--pyargs", "--import-mode", "-p"],
)
def test_an_addopts_option_that_changes_what_is_collected_in_a_way_that_cannot_be_read_is_an_error(
    tmp_path, option
):
    argument = "plugin_x" if option == "-p" else "value"
    needs_argument = option in ("-m", "-k", "--confcutdir", "--import-mode", "-p")
    tail = f" {argument}" if needs_argument else ""
    (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = {option}{tail}\n", encoding="utf-8")
    with pytest.raises(CollectionConfigError) as caught:
        NodeResolver(tmp_path)
    assert "addopts" in str(caught.value) and option in str(caught.value)


def test_disabling_a_plugin_in_addopts_is_not_a_collection_change(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = -p no:cacheprovider -v --color=no -q\n", encoding="utf-8"
    )
    _tree(tmp_path, {"test_a.py": _OK})
    assert _why(tmp_path, "test_a.py::test_ok") is None


def test_an_addopts_option_missing_its_value_is_an_error(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --ignore\n", encoding="utf-8")
    with pytest.raises(CollectionConfigError, match="--ignore"):
        NodeResolver(tmp_path)


def test_collect_in_virtualenv_is_honoured(tmp_path):
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\naddopts = --collect-in-virtualenv\n",
            "myenv/pyvenv.cfg": "home = x\n",
            "myenv/test_in_a_virtualenv.py": _OK,
        },
    )
    assert _why(tmp_path, "myenv/test_in_a_virtualenv.py::test_ok") is None


# --------------------------------------------------------------------------
# A conftest hook that changes collection cannot be evaluated: fail loudly
# --------------------------------------------------------------------------

_HOOKS = [
    "pytest_collect_file",
    "pytest_pycollect_makeitem",
    "pytest_ignore_collect",
    "pytest_collection_modifyitems",
    "pytest_collect_directory",
    "pytest_collection",
    "pytest_make_collect_report",
]


@pytest.mark.parametrize("hook", _HOOKS)
def test_a_conftest_hook_that_changes_collection_makes_the_files_under_it_untrusted(tmp_path, hook):
    root = _tree(
        tmp_path,
        {
            "tests/conftest.py": f"def {hook}(*args, **kwargs):\n    return None\n",
            "tests/test_a.py": _OK,
            "other/test_b.py": _OK,
        },
    )
    why = _why(root, "tests/test_a.py::test_ok") or ""
    assert f"`{hook}`" in why and "conftest.py" in why and "cannot evaluate" in why, why
    # a conftest only governs what sits under it
    assert _why(root, "other/test_b.py::test_ok") is None


def test_a_hook_in_the_root_conftest_governs_every_file(tmp_path):
    root = _tree(
        tmp_path,
        {
            "conftest.py": "async def pytest_collect_file(file_path, parent):\n    return None\n",
            "deep/er/test_a.py": _OK,
        },
    )
    assert "pytest_collect_file" in (_why(root, "deep/er/test_a.py::test_ok") or "")


def test_a_plugin_named_in_a_conftest_is_as_untrusted_as_a_hook(tmp_path):
    root = _tree(
        tmp_path,
        {"conftest.py": "pytest_plugins = ['plugin_x']\n", "test_a.py": _OK},
    )
    why = _why(root, "test_a.py::test_ok") or ""
    assert "pytest_plugins" in why and "cannot evaluate" in why


def test_a_conftest_registering_a_plugin_dynamically_is_untrusted(tmp_path):
    root = _tree(
        tmp_path,
        {
            "conftest.py": (
                "def pytest_configure(config):\n    config.pluginmanager.register(object())\n"
            ),
            "test_a.py": _OK,
        },
    )
    why = _why(root, "test_a.py::test_ok") or ""
    assert "pluginmanager" in why and "cannot evaluate" in why


def test_an_ordinary_conftest_with_fixtures_and_configure_is_trusted(tmp_path):
    root = _tree(
        tmp_path,
        {
            "conftest.py": (
                "import pytest\n\n\n@pytest.fixture\ndef thing(request):\n"
                "    request.config.pluginmanager.get_plugin('terminalreporter')\n    return 1\n\n\n"
                "def pytest_configure(config):\n    config.addinivalue_line('markers', 'x: y')\n"
            ),
            "test_a.py": _OK,
        },
    )
    assert _why(root, "test_a.py::test_ok") is None


def _conftests_in_repo() -> list[Path]:
    skipped = {"node_modules", "dist", "build", "venv", "__pycache__"}
    found = []
    for directory, subdirs, names in os.walk(REPO_ROOT):
        subdirs[:] = [d for d in subdirs if d not in skipped and not d.startswith(".")]
        if "conftest.py" in names:
            found.append(Path(directory) / "conftest.py")
    return found


def test_no_conftest_in_this_repository_defines_a_hook_that_changes_collection():
    """The resolver models pytest's collection with the stock hooks. A conftest that replaces
    one makes it answer for a pytest it is not modelling, and a rule would then name a test
    nothing runs while the gate says OK. None exists today; the day one is added, either the
    resolver learns what it does or this fails. The assumption is enforced, not hoped."""
    from core.gates.pytest_collection_rules import conftest_collection_problem

    conftests = _conftests_in_repo()
    assert conftests, "found no conftest.py at all; the walk is broken"
    problems = {
        path.relative_to(REPO_ROOT).as_posix(): conftest_collection_problem(path)
        for path in conftests
        if conftest_collection_problem(path)
    }
    assert problems == {}, (
        "a conftest changes what pytest collects and core/gates/pytest_node_resolver.py does "
        f"not model it: {problems}"
    )


def test_the_hook_check_would_see_a_hook(tmp_path):
    """A check that cannot fail is the thing this guard is for, so show that it does."""
    from core.gates.pytest_collection_rules import conftest_collection_problem

    bad = tmp_path / "conftest.py"
    bad.write_text("def pytest_pycollect_makeitem(collector, name, obj):\n    pass\n")
    assert "pytest_pycollect_makeitem" in (conftest_collection_problem(bad) or "")
    good = tmp_path / "ok" / "conftest.py"
    good.parent.mkdir()
    good.write_text("def pytest_configure(config):\n    pass\n")
    assert conftest_collection_problem(good) is None


# --------------------------------------------------------------------------
# The real repository
# --------------------------------------------------------------------------


def test_the_real_repository_collection_config_is_what_this_gate_was_measured_against():
    """The repo configures only `testpaths` and a harmless addopts; if that grows (an
    `--ignore`, a `norecursedirs`, a `collect_ignore`) the resolver already reads it, and
    this test names what it saw so the change is a deliberate one."""
    from core.gates.pytest_collection_rules import DEFAULT_NORECURSEDIRS

    rules = NodeResolver(REPO_ROOT).rules
    assert rules.testpaths == ("tests", "analytics/tests")
    assert rules.ignore == () and rules.ignore_glob == () and rules.deselect == ()
    assert rules.norecursedirs == DEFAULT_NORECURSEDIRS
