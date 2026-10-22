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
to agree on every file in both directions. That file starts a pytest process per scenario; this
one is pure source analysis. Both are in the pre-push pin-tests gate.

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
    "pytest_sessionstart",
    "pytest_addoption",
    "pytest_cmdline_main",
    "pytest_cmdline_parse",
    "pytest_load_initial_conftests",
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


# --------------------------------------------------------------------------
# Follow-ups: an option that is present and EMPTY is not an option that is absent
# --------------------------------------------------------------------------


def test_an_empty_norecursedirs_means_no_exclusions_not_the_defaults(tmp_path):
    """pytest: `norecursedirs =` empties the list. Falling back to the defaults refused eighteen
    references that pytest collects."""
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\nnorecursedirs =\n",
            "build/test_b.py": _OK,
            ".hidden/test_h.py": _OK,
            "node_modules/test_n.py": _OK,
        },
    )
    for name in ("build/test_b.py", ".hidden/test_h.py", "node_modules/test_n.py"):
        assert _why(tmp_path, f"{name}::test_ok") is None, name
    assert NodeResolver(tmp_path).rules.norecursedirs == ()


def test_an_empty_python_files_collects_no_file_from_a_directory_run(tmp_path):
    _tree(tmp_path, {"pytest.ini": "[pytest]\npython_files =\n", "test_a.py": _OK})
    why = _why(tmp_path, "test_a.py::test_ok") or ""
    assert "does not match python_files" in why
    assert NodeResolver(tmp_path).rules.python_files == ()


def test_an_empty_python_files_list_in_toml_is_empty_too(tmp_path):
    _tree(
        tmp_path,
        {"pyproject.toml": "[tool.pytest.ini_options]\npython_files = []\n", "test_a.py": _OK},
    )
    assert "does not match python_files" in (_why(tmp_path, "test_a.py::test_ok") or "")


@pytest.mark.parametrize("option", ["python_classes", "python_functions"])
def test_an_empty_name_pattern_matches_nothing(tmp_path, option):
    _tree(
        tmp_path,
        {
            "pytest.ini": f"[pytest]\n{option} =\n",
            "test_a.py": "def test_x():\n    pass\n\n\nclass TestA:\n    def test_y(self):\n        pass\n",
        },
    )
    assert "does not match" in (_why(tmp_path, "test_a.py::TestA::test_y") or "")


# --------------------------------------------------------------------------
# Follow-ups: which config file wins, and every way a bool is spelled
# --------------------------------------------------------------------------


def _marker(name: str) -> str:
    """The value a config file of this name sets python_functions to, so a read says whose it was."""
    return "from_" + name.replace(".", "_")


def _marker_config(name: str) -> str:
    """A config file of each kind that sets python_functions to the marker of its own name."""
    marker = _marker(name)
    ini = f"[pytest]\npython_functions = {marker}\n"
    return {
        "pytest.toml": f'[pytest]\npython_functions = ["{marker}"]\n',
        ".pytest.toml": f'[pytest]\npython_functions = ["{marker}"]\n',
        "pytest.ini": ini,
        ".pytest.ini": ini,
        "pyproject.toml": f'[tool.pytest.ini_options]\npython_functions = ["{marker}"]\n',
        "tox.ini": ini,
        "setup.cfg": f"[tool:pytest]\npython_functions = {marker}\n",
    }[name]


_PRECEDENCE = [
    "pytest.toml",
    ".pytest.toml",
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
]


@pytest.mark.parametrize("position", range(len(_PRECEDENCE) - 1))
def test_the_config_files_are_read_in_pytests_order_of_precedence(tmp_path, position):
    """Each file beats every file after it, and the later file is read when this one is gone."""
    winner, loser = _PRECEDENCE[position], _PRECEDENCE[position + 1]
    for name in (winner, loser):
        (tmp_path / name).write_text(_marker_config(name), encoding="utf-8")
    assert NodeResolver(tmp_path).rules.python_functions == (_marker(winner),)
    (tmp_path / winner).unlink()
    assert NodeResolver(tmp_path).rules.python_functions == (_marker(loser),)


def test_a_pyproject_with_no_pytest_table_and_a_tox_without_a_pytest_section_fall_through(
    tmp_path,
):
    (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "tox.ini").write_text("[tox]\nenvlist = py\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(_marker_config("setup.cfg"), encoding="utf-8")
    assert NodeResolver(tmp_path).rules.python_functions == (_marker("setup.cfg"),)


@pytest.mark.parametrize("name", ["pytest.ini", ".pytest.ini"])
def test_a_pytest_ini_with_no_pytest_section_still_wins_over_every_later_file(tmp_path, name):
    (tmp_path / name).write_text("# nothing here\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_marker_config("pyproject.toml"), encoding="utf-8")
    (tmp_path / "tox.ini").write_text(_marker_config("tox.ini"), encoding="utf-8")
    rules = NodeResolver(tmp_path).rules
    assert rules.python_functions == ("test",)
    assert rules.config_file == name


def test_a_pytest_toml_with_no_pytest_table_still_wins_over_every_later_file(tmp_path):
    (tmp_path / "pytest.toml").write_text("# nothing here\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(_marker_config("pytest.ini"), encoding="utf-8")
    assert NodeResolver(tmp_path).rules.python_functions == ("test",)


def test_both_native_and_legacy_pytest_tables_in_one_pyproject_is_an_error(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest]\ntestpaths = ["a"]\n\n[tool.pytest.ini_options]\naddopts = "-v"\n',
        encoding="utf-8",
    )
    with pytest.raises(CollectionConfigError, match="both"):
        NodeResolver(tmp_path)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("on", True),
        ("On", True),
        ("t", True),
        ("y", True),
        ("TRUE", True),
        ("off", False),
        ("n", False),
        ("no", False),
        ("f", False),
        ("False", False),
    ],
)
def test_every_bool_spelling_pytest_accepts_is_read(tmp_path, text, expected):
    (tmp_path / "pytest.ini").write_text(f"[pytest]\ncollect_imported_tests = {text}\n")
    assert NodeResolver(tmp_path).rules.collect_imported_tests is expected


def test_a_native_toml_bool_is_read(tmp_path):
    (tmp_path / "pytest.toml").write_text("[pytest]\ncollect_imported_tests = false\n")
    assert NodeResolver(tmp_path).rules.collect_imported_tests is False


# --------------------------------------------------------------------------
# Follow-ups: addopts spellings that cannot be evaluated
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tokens,named",
    [
        ("-mslow", "-m"),
        ("-kfoo", "-k"),
        ("--lf", "--lf"),
        ("--last-failed", "--last-failed"),
        ("--sw", "--sw"),
        ("--stepwise", "--stepwise"),
        ("--rootdir=sub", "--rootdir"),
        ("--rootdir sub", "--rootdir"),
        ("-pplugin_x", "-p"),
        ("-p plugin_x", "-p"),
        ("--import-mode=importlib", "--import-mode"),
        ("--confcutdir=sub", "--confcutdir"),
    ],
)
def test_attached_and_separate_spellings_of_the_unevaluable_options_are_refused(
    tmp_path, tokens, named
):
    (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = {tokens}\n", encoding="utf-8")
    with pytest.raises(CollectionConfigError) as caught:
        NodeResolver(tmp_path)
    assert "addopts" in str(caught.value) and named in str(caught.value)


@pytest.mark.parametrize("tokens", ["-q", "-ra", "-vv", "-x", "--tb=short", "-pno:cacheprovider"])
def test_options_that_do_not_change_collection_are_not_refused(tmp_path, tokens):
    (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = {tokens}\n", encoding="utf-8")
    assert NodeResolver(tmp_path).rules.ignore == ()


def test_ignore_glob_is_case_sensitive_on_every_platform(tmp_path):
    """pytest matches with `fnmatch.fnmatch`, which folds case on Windows and not on Linux. CI is
    Linux, so a Windows push must not pass what Linux would fail: the case rule is Linux's."""
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\naddopts = --ignore-glob=*/SKIP_*_test.py\n",
            "sub/skip_a_test.py": _OK,
            "sub/SKIP_b_test.py": _OK,
        },
    )
    assert _why(tmp_path, "sub/skip_a_test.py::test_ok") is None
    assert "--ignore-glob" in (_why(tmp_path, "sub/SKIP_b_test.py::test_ok") or "")


def test_python_files_and_collect_ignore_are_case_sensitive_everywhere(tmp_path):
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\n",
            "tests/Test_c.py": _OK,
            "tests/test_c2.py": _OK,
            "tests/TEST_f_test.py": _OK,
            "conftest.py": "collect_ignore = ['tests/test_c2.PY']\n",
        },
    )
    assert "python_files" in (_why(tmp_path, "tests/Test_c.py::test_ok") or "")
    assert "python_files" not in (_why(tmp_path, "tests/TEST_f_test.py::test_ok") or "")
    assert _why(tmp_path, "tests/test_c2.py::test_ok") is None  # `.PY` is not the name on disk


def test_norecursedirs_is_case_sensitive_everywhere(tmp_path):
    ini = "[pytest]\nnorecursedirs = Build\n"
    lower = _tree(tmp_path / "lower", {"pytest.ini": ini, "build/test_d.py": _OK})
    upper = _tree(tmp_path / "upper", {"pytest.ini": ini, "Build/test_e.py": _OK})
    assert _why(lower, "build/test_d.py::test_ok") is None  # a directory `build` is not `Build`
    assert "norecursedirs" in (_why(upper, "Build/test_e.py::test_ok") or "")


def test_a_pattern_with_a_backslash_is_read_with_a_slash(tmp_path):
    """Only a TOML string can carry a backslash through (an ini value is split like a shell
    line, which eats it); `a\\b` there is the pattern `a/b`."""
    _tree(
        tmp_path,
        {
            "pytest.toml": '[pytest]\nnorecursedirs = ["a\\\\b"]\n',
            "a/b/test_x.py": _OK,
            "a/test_y.py": _OK,
        },
    )
    assert "norecursedirs" in (_why(tmp_path, "a/b/test_x.py::test_ok") or "")
    assert _why(tmp_path, "a/test_y.py::test_ok") is None


# --------------------------------------------------------------------------
# Follow-ups: paths in addopts, a [pytest] section in setup.cfg, and what a conftest can do
# --------------------------------------------------------------------------


def test_a_path_in_addopts_narrows_the_run_and_replaces_testpaths(tmp_path):
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\ntestpaths = other\naddopts = -q --tb short tests/unit\n",
            "tests/unit/test_a.py": _OK,
            "tests/integration/test_b.py": _OK,
            "other/test_c.py": _OK,
        },
    )
    assert _why(tmp_path, "tests/unit/test_a.py::test_ok") is None
    for ref in ("tests/integration/test_b.py", "other/test_c.py"):
        why = _why(tmp_path, f"{ref}::test_ok") or ""
        assert "outside the paths addopts gives pytest (tests/unit)" in why, why


def test_the_value_of_an_option_in_addopts_is_not_a_path(tmp_path):
    _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\naddopts = --tb short -W error --maxfail 2 -o foo=bar\n",
            "short": "",
            "test_a.py": _OK,
        },
    )
    rules = NodeResolver(tmp_path).rules
    assert rules.positional == ()
    assert _why(tmp_path, "test_a.py::test_ok") is None


def test_a_bare_word_that_names_nothing_in_the_repository_is_not_a_path(tmp_path):
    _tree(tmp_path, {"pytest.ini": "[pytest]\naddopts = --weird nowhere\n", "test_a.py": _OK})
    assert NodeResolver(tmp_path).rules.positional == ()
    assert _why(tmp_path, "test_a.py::test_ok") is None


def test_a_node_id_in_addopts_is_refused(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = tests/test_a.py::test_x\n", encoding="utf-8"
    )
    with pytest.raises(CollectionConfigError, match="test_a.py::test_x"):
        NodeResolver(tmp_path)


def test_a_setup_cfg_with_a_pytest_section_is_an_error_as_it_is_in_pytest(tmp_path):
    (tmp_path / "setup.cfg").write_text("[pytest]\npython_files = x_*.py\n", encoding="utf-8")
    with pytest.raises(CollectionConfigError, match=r"\[pytest\] section"):
        NodeResolver(tmp_path)


def test_a_setup_cfg_with_both_sections_reads_the_tool_one(tmp_path):
    (tmp_path / "setup.cfg").write_text(
        "[pytest]\npython_files = ignored_*.py\n\n[tool:pytest]\npython_files = tool_*.py\n",
        encoding="utf-8",
    )
    assert NodeResolver(tmp_path).rules.python_files == ("tool_*.py",)


@pytest.mark.parametrize(
    "body",
    [
        "raise RuntimeError('x')\n",
        "import sys\nsys.exit(0)\n",
        "exit()\n",
        "import pytest\npytest.exit('x')\n",
        "assert False\n",
        "assert 0, 'no'\n",
    ],
)
def test_a_conftest_that_always_raises_poisons_everything_under_it(tmp_path, body):
    root = _tree(
        tmp_path,
        {"tests/conftest.py": body, "tests/test_a.py": _OK, "elsewhere/test_b.py": _OK},
    )
    why = _why(root, "tests/test_a.py::test_ok") or ""
    assert "conftest.py" in why and "so pytest collects nothing from anything under tests/" in why
    assert _why(root, "elsewhere/test_b.py::test_ok") is None


@pytest.mark.parametrize(
    "body",
    [
        "def f():\n    raise RuntimeError\n",
        "import sys\nif sys.platform == 'x':\n    sys.exit(0)\n",
        "assert True\n",
        "def pytest_configure(config):\n    config.option.verbose = 1\n    config.getoption('x')\n",
    ][:3],
)
def test_a_conftest_that_may_not_raise_is_not_poison(tmp_path, body):
    root = _tree(tmp_path, {"tests/conftest.py": body, "tests/test_a.py": _OK})
    assert _why(root, "tests/test_a.py::test_ok") is None


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("def pytest_configure(config):\n    config.option.ignore = ['x']\n", "config.option"),
        ("def pytest_configure(config):\n    config.option.deselect += ['x']\n", "config.option"),
        (
            "def pytest_configure(config):\n    config.addinivalue_line('norecursedirs', 'x')\n",
            "norecursedirs",
        ),
        (
            "def pytest_configure(config):\n    config.addinivalue_line('python_files', 'x_*.py')\n",
            "python_files",
        ),
        ("def pytest_sessionstart(session):\n    pass\n", "pytest_sessionstart"),
        ("def pytest_addoption(parser):\n    pass\n", "pytest_addoption"),
        ("def pytest_load_initial_conftests(early_config):\n    pass\n", "pytest_load"),
    ],
)
def test_a_conftest_that_changes_the_collection_settings_while_configuring_is_untrusted(
    tmp_path, body, fragment
):
    root = _tree(tmp_path, {"conftest.py": body, "test_a.py": _OK})
    why = _why(root, "test_a.py::test_ok") or ""
    assert fragment in why and "cannot evaluate" in why, why


def test_registering_a_marker_in_configure_is_not_a_collection_change(tmp_path):
    root = _tree(
        tmp_path,
        {
            "conftest.py": (
                "def pytest_configure(config):\n"
                "    config.addinivalue_line('markers', 'slow: x')\n"
                "    config.option.verbose\n"
            ),
            "test_a.py": _OK,
        },
    )
    assert _why(root, "test_a.py::test_ok") is None


# --------------------------------------------------------------------------
# Follow-ups: a collect_ignore that is extended in a form that is not an addition
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "collect_ignore = ['x']\ncollect_ignore -= ['x']\n",
        "collect_ignore = ['x']\ncollect_ignore *= ['x']\n",
        "collect_ignore = ['x']\ncollect_ignore |= ['x']\n",
    ],
)
def test_an_augmented_assignment_that_is_not_an_addition_cannot_be_evaluated(tmp_path, body):
    root = _tree(tmp_path, {"conftest.py": body, "test_a.py": _OK})
    why = _why(root, "test_a.py::test_ok") or ""
    assert "cannot evaluate" in why and "collect_ignore" in why, why


# --------------------------------------------------------------------------
# Follow-ups: a hook imported under another name is only a hook if it lands on a hook name
# --------------------------------------------------------------------------


def test_an_import_bound_to_a_hook_name_is_a_hook_whatever_it_was_called_there(tmp_path):
    root = _tree(
        tmp_path,
        {
            "a/conftest.py": "from plugin import impl as pytest_collect_file\n",
            "a/test_a.py": _OK,
            "b/conftest.py": "from plugin import pytest_collect_file as unused\n",
            "b/test_b.py": _OK,
            "c/conftest.py": "import plugin as pytest_ignore_collect\n",
            "c/test_c.py": _OK,
        },
    )
    assert "pytest_collect_file" in (_why(root, "a/test_a.py::test_ok") or "")
    assert _why(root, "b/test_b.py::test_ok") is None  # bound to `unused`: not registered
    assert "pytest_ignore_collect" in (_why(root, "c/test_c.py::test_ok") or "")


# --------------------------------------------------------------------------
# Follow-ups: a path spelled through a link is judged by how it is spelled, and by its case
# --------------------------------------------------------------------------


def _link(link: Path, target: Path) -> bool:
    """A directory link, as a junction on Windows (no privilege needed) or a symlink."""
    import subprocess

    try:
        if os.name == "nt":
            done = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
            )
            return done.returncode == 0
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


def test_a_reference_spelled_through_a_link_is_judged_by_its_spelled_path(tmp_path):
    """pytest walks the directories as they are spelled. A reference through `skipme/` is under
    `skipme/` whatever the link points at; judging the resolved path called it `real/`."""
    _tree(
        tmp_path,
        {"pytest.ini": "[pytest]\nnorecursedirs = skipme\n", "real/test_a.py": _OK},
    )
    if not _link(tmp_path / "skipme", tmp_path / "real"):
        pytest.skip("this platform will not make a directory link here")
    assert "skipme" in (_why(tmp_path, "skipme/test_a.py::test_ok") or "")
    assert _why(tmp_path, "real/test_a.py::test_ok") is None


def test_a_link_to_a_directory_outside_the_repository_is_still_refused(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    _tree(outside, {"test_a.py": _OK})
    repo.mkdir()
    if not _link(repo / "linked", outside):
        pytest.skip("this platform will not make a directory link here")
    assert _why(repo, "linked/test_a.py::test_ok") == "path escapes the repository"


def test_a_path_whose_case_differs_from_the_file_on_disk_is_refused(tmp_path):
    """Windows would find `TESTS/Test_A.PY`; a Linux checkout, which CI is, would not."""
    _tree(tmp_path, {"tests/test_a.py": _OK})
    insensitive = (tmp_path / "TESTS" / "TEST_A.PY").is_file()
    why = _why(tmp_path, "TESTS/TEST_A.PY::test_ok") or ""
    if insensitive:
        assert "differs in case" in why, why
    else:
        assert why == "no such test file"
    assert _why(tmp_path, "tests/test_a.py::test_ok") is None
    assert _why(tmp_path, "tests/../tests/test_a.py::test_ok") is None
