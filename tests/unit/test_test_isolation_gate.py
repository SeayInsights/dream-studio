"""The test-isolation gate must fail on the patch that aborted the suite.

Defect of record, 2026-09-06: ``monkeypatch.setattr(type(f), "stat", lambda self_, **_:
mock_stat)`` in ``test_game_validate.py`` made every path in the process report 20 MB,
the autouse spool guard concluded the run had written into the operator's real
``~/.dream-studio/events``, and the session aborted FATAL. The test passed throughout.
The full local suite could not complete -- which is why 45 failures reached ``main`` on a
green subset.

Both directions are asserted. The exemptions matter as much as the catches: banning
``Path.home`` would delete the temp-home redirection that keeps ~100 tests off live state,
so a test here pins that it stays allowed.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import test_isolation

# The exact line that aborted the suite.
_DEFECT = """
def test_skips_oversized_file(tmp_path, monkeypatch):
    f = tmp_path / "big.gd"
    mock_stat = object()
    monkeypatch.setattr(type(f), "stat", lambda self_, **_: mock_stat)
    assert True
"""

# The fix: a named function that delegates for anything but the object under test.
_SCOPED = """
def test_skips_oversized_file(tmp_path, monkeypatch):
    f = tmp_path / "big.gd"
    real_stat = type(f).stat
    target = str(f)

    def _stat_only_for_target(self_, **kw):
        if str(self_) == target:
            return object()
        return real_stat(self_, **kw)

    monkeypatch.setattr(type(f), "stat", _stat_only_for_target)
    assert True
"""

# The temp-home redirection. Class-level, no per-object state, and the mechanism that
# keeps the suite off the operator's real Dream Studio home.
_TEMP_HOME = """
from pathlib import Path


def test_uses_temp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert True
"""

# A bounded context manager. Unwound before teardown, so autouse guards never see it.
_CONTEXT_MANAGER = """
from pathlib import Path
from unittest.mock import patch


def test_read_failure_is_reported(tmp_path):
    with patch.object(Path, "read_text", side_effect=OSError("denied")):
        assert True
"""

# Patching the module under test, not a stdlib type. Always fine.
_MODULE_ATTR = """
def test_patches_its_own_module(handler, monkeypatch):
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    assert True
"""


def _tree(tmp_path: Path, source: str, *, rel: str = "tests/unit/test_subject.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def test_catches_the_patch_that_aborted_the_suite(tmp_path):
    result = test_isolation.run(repo_root=_tree(tmp_path, _DEFECT))
    assert result["status"] == "fail"
    assert len(result["offenders"]) == 1
    assert result["offenders"][0]["target"] == "type(...).stat"


def test_message_explains_the_teardown_blast_radius(tmp_path):
    result = test_isolation.run(repo_root=_tree(tmp_path, _DEFECT))
    message = result["offenders"][0]["message"]
    assert "teardown" in message
    assert "named function that delegates" in message


def test_named_delegating_function_is_allowed(tmp_path):
    result = test_isolation.run(repo_root=_tree(tmp_path, _SCOPED))
    assert result["status"] == "pass", result["offenders"]


def test_temp_home_redirection_stays_allowed(tmp_path):
    # If this ever starts failing, the gate has begun deleting the isolation that keeps
    # the suite off the operator's live Dream Studio home. That is worse than the defect.
    result = test_isolation.run(repo_root=_tree(tmp_path, _TEMP_HOME))
    assert result["status"] == "pass", result["offenders"]


def test_bounded_context_manager_stays_allowed(tmp_path):
    result = test_isolation.run(repo_root=_tree(tmp_path, _CONTEXT_MANAGER))
    assert result["status"] == "pass", result["offenders"]


def test_patching_the_module_under_test_is_not_a_finding(tmp_path):
    result = test_isolation.run(repo_root=_tree(tmp_path, _MODULE_ATTR))
    assert result["status"] == "pass", result["offenders"]


def test_mock_replacement_is_treated_as_an_inline_fake(tmp_path):
    source = (
        "from pathlib import Path\n"
        "from unittest.mock import MagicMock\n"
        "\n"
        "\n"
        "def test_x(monkeypatch):\n"
        '    monkeypatch.setattr(Path, "stat", MagicMock())\n'
    )
    result = test_isolation.run(repo_root=_tree(tmp_path, source))
    assert result["status"] == "fail"
    assert result["offenders"][0]["target"] == "Path.stat"


def test_real_test_suite_is_clean():
    result = test_isolation.run()
    assert result["status"] == "pass", result["offenders"]
    assert result["files_scanned"] > 300, "scan found almost nothing -- tests root is wrong"


def test_gate_is_bound_to_the_real_suite(tmp_path):
    """Reverting the real fix must make the gate fail.

    `test_real_test_suite_is_clean` passes just as readily if the gate quietly stopped
    recognising the shape; only putting the original line back into the real file proves
    otherwise.
    """
    real = Path(test_isolation.REPO_ROOT) / "tests" / "unit" / "test_game_validate.py"
    source = real.read_text(encoding="utf-8")
    fixed = 'monkeypatch.setattr(type(f), "stat", _stat_only_for_target)'
    assert fixed in source, "the scoped fix is gone -- this lock no longer means anything"
    reverted = source.replace(
        fixed, 'monkeypatch.setattr(type(f), "stat", lambda self_, **_: oversized)', 1
    )
    target = tmp_path / "tests" / "unit" / "test_game_validate.py"
    target.parent.mkdir(parents=True)
    target.write_text(reverted, encoding="utf-8")

    result = test_isolation.run(repo_root=tmp_path)
    assert result["status"] == "fail"
    assert result["offenders"][0]["target"] == "type(...).stat"
