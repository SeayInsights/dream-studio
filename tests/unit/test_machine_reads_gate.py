"""The test-isolation gate must fail when a test reads the machine it runs on.

Defect of record, 2026-10-21 (issue #911): tests read ``~/.claude`` (the operator's installed
hooks, skills, CLAUDE.md), ``~/builds/dreamysuite``, a sibling ``dream-studio-enterprise``,
``origin/main`` of the clone, and inherited ``CLAUDE_CONFIG_DIR``. Each passed where it was
written, skipped on CI, and failed on a machine whose install was behind -- for a reason no
commit caused. ``core/gates/machine_reads.py`` is the detector.

Both directions are asserted, and the second matters as much as the first: a gate that bans
``Path.home`` outright would delete the temp-home redirection that keeps ~100 tests off live
state, so every redirect shape pinned below must stay allowed. The last tests prove the gate is
bound to the real suite -- putting a fixed pattern back into a real file must fail it -- because
a clean run proves nothing about a detector that quietly stopped recognising its shapes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates import machine_reads, test_isolation


def _tree(tmp_path: Path, source: str, *, rel: str = "tests/unit/test_subject.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def _run(tmp_path: Path, source: str, **kw) -> dict:
    return test_isolation.run(repo_root=_tree(tmp_path, source, **kw))


def _kinds(result: dict) -> list[str]:
    return [o["kind"] for o in result["offenders"]]


# --- what must FAIL ----------------------------------------------------------------------

_READS = {
    "Path.home in a test": (
        "from pathlib import Path\n"
        "def test_x():\n"
        "    assert (Path.home() / '.claude').exists()\n",
        "home-read",
    ),
    "pathlib.Path.home": (
        "import pathlib\ndef test_x():\n    pathlib.Path.home()\n",
        "home-read",
    ),
    "os.path.expanduser": (
        "import os\ndef test_x():\n    os.path.expanduser('~/.dream-studio')\n",
        "home-read",
    ),
    "expanduser of a computed path": (
        "import os\ndef test_x(where):\n    os.path.expanduser(where)\n",
        "home-read",
    ),
    "Path.expanduser of a computed path": (
        "from pathlib import Path\ndef test_x(where):\n    Path(where).expanduser()\n",
        "home-read",
    ),
    "Path.expanduser": (
        "from pathlib import Path\ndef test_x():\n    Path('~/x').expanduser()\n",
        "home-read",
    ),
    "os.environ get HOME": (
        "import os\ndef test_x():\n    os.environ.get('HOME')\n",
        "home-read",
    ),
    "os.environ index USERPROFILE": (
        "import os\ndef test_x():\n    os.environ['USERPROFILE']\n",
        "home-read",
    ),
    "os.getenv APPDATA": (
        "import os\ndef test_x():\n    os.getenv('APPDATA')\n",
        "home-read",
    ),
    "tilde literal given to Path": (
        "from pathlib import Path\ndef test_x():\n    Path('~/.claude/skills')\n",
        "home-read",
    ),
    "module-level read": (
        "from pathlib import Path\nLIVE = Path.home() / '.dream-studio'\ndef test_x():\n    pass\n",
        "home-read",
    ),
    "claude_config_root": (
        "from core.config.paths import claude_config_root\n"
        "def test_x():\n    claude_config_root()\n",
        "config-root-read",
    ),
    "sibling checkout": (
        "from pathlib import Path\n"
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    (REPO_ROOT.parent / 'dream-studio-enterprise').exists()\n",
        "sibling-read",
    ),
    "parents past the repository": (
        "from pathlib import Path\n" "def test_x():\n    Path(__file__).resolve().parents[3]\n",
        "sibling-read",
    ),
    "git against the checkout, no cwd": (
        "import subprocess\n"
        "def test_x():\n    subprocess.run(['git', 'tag'], capture_output=True)\n",
        "git-checkout",
    ),
    "git against the checkout, cwd REPO_ROOT": (
        "import subprocess\nfrom pathlib import Path\n"
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    subprocess.run(['git', 'rev-parse', 'origin/main'], cwd=REPO_ROOT)\n",
        "git-checkout",
    ),
    "git -C the checkout": (
        "import subprocess\nfrom pathlib import Path\n"
        "REPO = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'])\n",
        "git-checkout",
    ),
    "a redirect in another test does not excuse this one": (
        "from pathlib import Path\n"
        "def test_redirected(monkeypatch, tmp_path):\n"
        "    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))\n"
        "    Path.home()\n"
        "def test_not_redirected():\n"
        "    Path.home()\n",
        "home-read",
    ),
    "a home redirect does not excuse a sibling read": (
        "from pathlib import Path\nREPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x(isolated_home):\n    (REPO_ROOT.parent / 'beside').exists()\n",
        "sibling-read",
    ),
}


@pytest.mark.parametrize("case", sorted(_READS))
def test_a_machine_read_with_nothing_redirecting_it_fails(tmp_path, case):
    source, kind = _READS[case]
    result = _run(tmp_path, source)
    assert result["status"] == "fail", case
    assert _kinds(result) == [kind], (case, result["offenders"])


def test_the_message_says_what_to_do_instead(tmp_path):
    result = _run(tmp_path, _READS["Path.home in a test"][0])
    message = result["offenders"][0]["message"]
    assert "install_check" in message and "isolated_home" in message
    assert "test_subject.py:3 in test_x()" in message


# --- what must stay ALLOWED --------------------------------------------------------------

_REDIRECTED = {
    "isolated_home fixture": (
        "from pathlib import Path\n" "def test_x(isolated_home):\n    Path.home()\n"
    ),
    "monkeypatch.setattr(Path, 'home')": (
        "from pathlib import Path\n"
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))\n"
        "    Path.home()\n"
    ),
    "patch('pathlib.Path.home')": (
        "from pathlib import Path\nfrom unittest.mock import patch\n"
        "def test_x(tmp_path):\n"
        "    with patch('pathlib.Path.home', return_value=tmp_path):\n"
        "        Path.home()\n"
    ),
    "setenv HOME": (
        "import os\n"
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setenv('HOME', str(tmp_path))\n"
        "    os.environ.get('HOME')\n"
    ),
    "env mapping for a subprocess": (
        "import os\nfrom pathlib import Path\n"
        "def test_x(tmp_path):\n"
        "    env = dict(os.environ)\n"
        "    env['USERPROFILE'] = str(tmp_path)\n"
        "    Path.home()\n"
    ),
    "CLAUDE_CONFIG_DIR for a config-root read": (
        "from core.config.paths import claude_config_root\n"
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))\n"
        "    claude_config_root()\n"
    ),
    "a class-level usefixtures mark": (
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.mark.usefixtures('isolated_home')\n"
        "class TestX:\n"
        "    def test_x(self):\n        Path.home()\n"
    ),
    "a module-level autouse fixture": (
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.fixture(autouse=True)\n"
        "def _home(monkeypatch, tmp_path):\n"
        "    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))\n"
        "def test_x():\n    Path.home()\n"
    ),
    "a class-level autouse fixture": (
        "import pytest\nfrom pathlib import Path\n"
        "class TestX:\n"
        "    @pytest.fixture(autouse=True)\n"
        "    def _home(self, monkeypatch, tmp_path):\n"
        "        monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))\n"
        "    def test_x(self):\n        Path.home()\n"
    ),
    "a helper in a module that redirects": (
        "from pathlib import Path\n"
        "def _helper():\n    return Path.home()\n"
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))\n"
        "    _helper()\n"
    ),
    "git in a repository the test built": (
        "import subprocess\n"
        "def test_x(tmp_path):\n    subprocess.run(['git', 'tag'], cwd=tmp_path)\n"
    ),
    "git -C a repository the test built": (
        "import subprocess\n"
        "def test_x(repo):\n    subprocess.run(['git', '-C', str(repo), 'tag'])\n"
    ),
    "git init is self-contained": (
        "import subprocess\n"
        "def test_x(tmp_path):\n    subprocess.run(['git', 'init'], capture_output=True)\n"
    ),
    "git ls-files lists tracked content": (
        "import subprocess\nfrom pathlib import Path\n"
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    subprocess.run(['git', 'ls-files'], cwd=REPO_ROOT)\n"
    ),
    "git with kwargs spread may carry a cwd": (
        "import subprocess\n" "def test_x(run):\n    subprocess.run(['git', 'tag'], **run)\n"
    ),
    "parents inside the repository": (
        "from pathlib import Path\n"
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    pass\n"
    ),
    "module.__file__ is the module under test, not this file": (
        "from pathlib import Path\nimport project_list\n"
        "def test_x():\n    Path(project_list.__file__).resolve().parents[3]\n"
    ),
    "REPO_ROOT / name stays inside the repository": (
        "from pathlib import Path\nREPO_ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n    (REPO_ROOT / 'core').exists()\n"
    ),
    "a tilde literal that is only data": (
        "def test_x():\n    assert '~/.dream-studio' in 'source text'\n"
    ),
}


@pytest.mark.parametrize("case", sorted(_REDIRECTED))
def test_a_redirected_or_self_contained_read_stays_allowed(tmp_path, case):
    # If one of these starts failing the gate has begun deleting the isolation that keeps the
    # suite off the operator's live home, which is worse than the defect it exists for.
    result = _run(tmp_path, _REDIRECTED[case])
    assert result["status"] == "pass", (case, result["offenders"])


def test_an_install_check_may_read_the_machine(tmp_path):
    for source in (
        "import pytest\nfrom pathlib import Path\npytestmark = pytest.mark.install_check\n"
        "def test_x():\n    Path.home()\n",
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.mark.install_check\ndef test_x():\n    Path.home()\n",
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.mark.install_check\nclass TestX:\n    def test_x(self):\n        Path.home()\n",
    ):
        assert _run(tmp_path, source)["status"] == "pass", source


def test_the_install_checks_directory_is_exempt_as_a_whole(tmp_path):
    result = _run(
        tmp_path,
        "from pathlib import Path\ndef test_x():\n    Path.home()\n",
        rel="tests/install_checks/test_anything.py",
    )
    assert result["status"] == "pass"


def test_a_test_file_the_gate_cannot_parse_is_a_finding_not_a_pass(tmp_path):
    """Unparseable must not read as clean: the file was not examined."""
    result = _run(tmp_path, "def test_x(:\n    pass\n", rel="tests/unit/test_broken.py")
    assert result["status"] == "fail"
    assert _kinds(result) == ["unreadable-test-file"]
    assert "NOT checked" in result["offenders"][0]["message"]


def test_a_conftest_the_gate_cannot_parse_is_a_finding_too(tmp_path):
    result = _run(tmp_path, "def (:\n", rel="tests/conftest.py")
    assert _kinds(result) == ["unreadable-test-file"]


def test_a_file_pytest_does_not_collect_may_be_unparseable(tmp_path):
    """A fixture that is deliberately not valid Python is not a test module."""
    result = _run(tmp_path, "def (:\n", rel="tests/fixtures/guard/not_python.py")
    assert result["status"] == "pass", result["offenders"]


# --- the allow-list may only shrink ------------------------------------------------------


def test_an_allowlist_entry_that_matches_nothing_fails(tmp_path):
    tree = _tree(tmp_path, "def test_x():\n    pass\n")
    allow = {("tests/unit/test_subject.py", "test_gone"): "the use was fixed"}
    result = test_isolation.run(repo_root=tree, allowlist=allow)
    assert result["status"] == "fail"
    assert _kinds(result) == ["stale-allowlist-entry"]
    assert "delete the entry" in result["offenders"][0]["message"]


def test_an_allowlisted_read_passes_and_is_counted(tmp_path):
    source = "from pathlib import Path\ndef test_x():\n    Path.home()\n"
    tree = _tree(tmp_path, source)
    allow = {("tests/unit/test_subject.py", "test_x"): "a reason"}
    result = test_isolation.run(repo_root=tree, allowlist=allow)
    assert result["status"] == "pass"
    assert result["allowlisted"] == 1


def test_every_real_allowlist_entry_has_a_reason():
    for key, reason in machine_reads.ALLOWLIST.items():
        assert len(reason.split()) >= 12, f"{key} needs a real reason, got {reason!r}"


def test_the_real_allowlist_has_not_grown():
    """A ceiling, so the list can only go down. Lowering it is the whole point of a fix; raising
    it needs a review that agrees the read cannot be redirected, rebuilt, or marked."""
    assert len(machine_reads.ALLOWLIST) <= 3, sorted(machine_reads.ALLOWLIST)


# --- bound to the real suite -------------------------------------------------------------


def _real(rel: str) -> str:
    return (Path(test_isolation.REPO_ROOT) / rel).read_text(encoding="utf-8")


def _gate_on_one_real_file(tmp_path: Path, rel: str, source: str) -> dict:
    """The real gate over a tree holding only ``rel`` with the given (mutated) source."""
    return test_isolation.run(repo_root=_tree(tmp_path, source, rel=rel))


def test_the_real_suite_is_clean():
    result = test_isolation.run()
    assert result["status"] == "pass", result["offenders"]
    assert result["files_scanned"] > 300, "the scan found almost nothing -- the tests root is wrong"


def test_reverting_the_detector_fixture_fails_the_gate(tmp_path):
    """tests/unit/integrations/test_detector.py compared against the machine's ~/.claude."""
    rel = "tests/unit/integrations/test_detector.py"
    source = _real(rel)
    assert 'monkeypatch.setattr(Path, "home"' in source, "the fixture is gone"
    reverted = source.replace(
        'monkeypatch.setattr(Path, "home"', 'monkeypatch.setattr(Path, "xhome"'
    )
    reverted = reverted.replace('monkeypatch.setenv("HOME"', 'monkeypatch.setenv("XHOME"')
    reverted = reverted.replace('monkeypatch.setenv("USERPROFILE"', 'monkeypatch.setenv("XPROFILE"')
    reverted = reverted.replace(
        'monkeypatch.delenv("CLAUDE_CONFIG_DIR"', 'monkeypatch.delenv("X_CFG"'
    )
    reverted += "\n\ndef test_reintroduced():\n    assert Path.home() / '.claude'\n"
    result = _gate_on_one_real_file(tmp_path, rel, reverted)
    assert result["status"] == "fail"
    assert "home-read" in _kinds(result)


def test_reintroducing_the_installed_hook_read_fails_the_gate(tmp_path):
    """The line #911 names in test_hook_write_accounting, put back as it was."""
    rel = "tests/unit/test_hook_write_accounting.py"
    source = _real(rel) + (
        "\n\ndef test_the_projected_hook_copies_carry_this_fix_reintroduced():\n"
        "    for tree in (_REPO / '.claude' / 'hooks', Path.home() / '.claude' / 'hooks'):\n"
        "        assert tree\n"
    )
    result = _gate_on_one_real_file(tmp_path, rel, source)
    assert result["status"] == "fail"
    assert [o["function"] for o in result["offenders"]] == [
        "test_the_projected_hook_copies_carry_this_fix_reintroduced"
    ]


def test_reintroducing_the_sibling_repository_read_fails_the_gate(tmp_path):
    rel = "tests/unit/test_product_readiness_baseline.py"
    source = _real(rel).replace(
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n",
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        'ENTERPRISE_ROOT = REPO_ROOT.parent / "dream-studio-enterprise"\n',
        1,
    )
    assert "ENTERPRISE_ROOT" in source
    result = _gate_on_one_real_file(tmp_path, rel, source)
    assert _kinds(result) == ["sibling-read"], result["offenders"]


def test_reintroducing_the_dreamysuite_read_fails_the_gate(tmp_path):
    rel = "tests/unit/test_audit_dispatcher.py"
    source = _real(rel).replace(
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n",
        "REPO_ROOT = Path(__file__).resolve().parents[2]\n"
        'DREAMYSUITE_PATH = Path.home() / "builds" / "dreamysuite"\n',
        1,
    )
    assert "DREAMYSUITE_PATH" in source
    result = _gate_on_one_real_file(tmp_path, rel, source)
    assert result["status"] == "fail"
    assert _kinds(result) == ["home-read"]
    assert result["offenders"][0]["function"] == "<module>"
