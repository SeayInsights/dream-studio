"""H30 — the fail-open census, and the ratchet that keeps it from being a wall.

Every case that expects clean is paired with one that expects a catch, same convention as
``test_fail_open_probe_gate.py``: a gate no test can make FAIL is indistinguishable from a
gate that checks nothing.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import fail_open_census
from core.gates.fail_open_census import FailOpenSite, compare_to_baseline, scan

_BARE_EXCEPT_PASS = """
def read_maybe(path):
    try:
        return path.read_text()
    except OSError:
        pass
"""

_FALSY_RETURN_NONE = """
def find_config():
    try:
        return load_it()
    except FileNotFoundError:
        return None
"""

_FALSY_RETURN_BARE = """
def maybe_run():
    try:
        do_it()
    except RuntimeError:
        return
"""

_FALSY_RETURN_FALSE = """
def is_ready():
    try:
        return check()
    except ValueError:
        return False
"""

_NOT_FLAGGED_LOGS_AND_RERAISES = """
import logging

def careful():
    try:
        risky()
    except ValueError:
        logging.error("risky failed")
        raise
"""

_NOT_FLAGGED_RETURNS_TRUTHY = """
def fallback():
    try:
        return primary()
    except ValueError:
        return "default"
"""

_NOT_FLAGGED_DOCSTRING_THEN_RAISE = """
def strict():
    try:
        risky()
    except ValueError:
        \"\"\"never swallow\"\"\"
        raise
"""


def _tree(tmp_path: Path, source: str, *, rel: str = "core/site.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def test_catches_bare_except_pass(tmp_path):
    sites = scan(_tree(tmp_path, _BARE_EXCEPT_PASS))
    assert len(sites) == 1
    assert sites[0].shape == "bare-except-pass"


def test_catches_falsy_return_none(tmp_path):
    sites = scan(_tree(tmp_path, _FALSY_RETURN_NONE))
    assert len(sites) == 1
    assert sites[0].shape == "falsy-return"


def test_catches_bare_return_as_falsy(tmp_path):
    sites = scan(_tree(tmp_path, _FALSY_RETURN_BARE))
    assert len(sites) == 1
    assert sites[0].shape == "falsy-return"


def test_catches_explicit_false_return(tmp_path):
    sites = scan(_tree(tmp_path, _FALSY_RETURN_FALSE))
    assert len(sites) == 1
    assert sites[0].shape == "falsy-return"


def test_a_handler_that_logs_and_reraises_is_not_flagged(tmp_path):
    assert scan(_tree(tmp_path, _NOT_FLAGGED_LOGS_AND_RERAISES)) == []


def test_a_handler_returning_a_truthy_default_is_not_flagged(tmp_path):
    assert scan(_tree(tmp_path, _NOT_FLAGGED_RETURNS_TRUTHY)) == []


def test_a_docstring_before_raise_does_not_count_as_bare_pass(tmp_path):
    assert scan(_tree(tmp_path, _NOT_FLAGGED_DOCSTRING_THEN_RAISE)) == []


def test_a_docstring_before_pass_still_counts(tmp_path):
    """The docstring EXPLAINS the silence; it does not undo it."""
    source = '''
def read_maybe(path):
    try:
        return path.read_text()
    except OSError:
        """deliberately silent: caller treats missing as absent"""
        pass
'''
    sites = scan(_tree(tmp_path, source))
    assert len(sites) == 1
    assert sites[0].shape == "bare-except-pass"


def test_test_files_are_not_scanned(tmp_path):
    tree = _tree(tmp_path, _BARE_EXCEPT_PASS, rel="core/test_site.py")
    assert scan(tree) == []


# ── the ratchet ───────────────────────────────────────────────────────────────


def test_a_site_already_in_the_baseline_does_not_fail():
    current = [FailOpenSite("core/x.py", 10, "bare-except-pass")]
    baseline = ["core/x.py|10|bare-except-pass"]
    result = compare_to_baseline(current, baseline)
    assert result["status"] == "pass"
    assert result["new_count"] == 0


def test_a_site_not_in_the_baseline_fails():
    current = [FailOpenSite("core/x.py", 10, "bare-except-pass")]
    baseline: list[str] = []
    result = compare_to_baseline(current, baseline)
    assert result["status"] == "fail"
    assert result["new_count"] == 1
    assert "core/x.py:10" in result["new_sites"][0]


def test_a_resolved_site_is_reported_but_does_not_fail():
    """Shrinking the baseline (fixing an existing site) is free — the gate does not
    demand the baseline be regenerated just because something got fixed."""
    current: list[FailOpenSite] = []
    baseline = ["core/x.py|10|bare-except-pass"]
    result = compare_to_baseline(current, baseline)
    assert result["status"] == "pass"
    assert result["resolved_count"] == 1


def test_a_line_shifting_within_the_same_file_reads_as_new_not_moved():
    """Identity is path|line|shape, same as the flake8 baseline's path|code|message —
    a genuinely moved site needs a baseline regen, exactly like a flake8 finding does."""
    current = [FailOpenSite("core/x.py", 11, "bare-except-pass")]
    baseline = ["core/x.py|10|bare-except-pass"]
    result = compare_to_baseline(current, baseline)
    assert result["status"] == "fail"


def test_main_fails_on_a_repo_root_with_no_baseline(tmp_path):
    tree = _tree(tmp_path, _BARE_EXCEPT_PASS)
    empty_baseline = tmp_path / "empty-baseline.txt"
    exit_code = fail_open_census.main(["--repo-root", str(tree), "--baseline", str(empty_baseline)])
    assert exit_code == 1


def test_main_passes_once_the_site_is_baselined(tmp_path):
    tree = _tree(tmp_path, _BARE_EXCEPT_PASS)
    baseline_path = tmp_path / "baseline.txt"
    write_exit = fail_open_census.main(
        ["--repo-root", str(tree), "--baseline", str(baseline_path), "--write-baseline"]
    )
    assert write_exit == 0
    check_exit = fail_open_census.main(["--repo-root", str(tree), "--baseline", str(baseline_path)])
    assert check_exit == 0


def test_the_real_repository_has_no_new_sites_beyond_its_own_baseline():
    """Pinned regression: this repo's own baseline must stay current. A new fail-open
    site added anywhere in product code without updating the baseline fails this test
    locally before it ever reaches the gate in CI."""
    sites = scan()
    baseline = fail_open_census.load_baseline(fail_open_census.DEFAULT_BASELINE)
    result = compare_to_baseline(sites, baseline)
    assert result["status"] == "pass", result["new_sites"]
