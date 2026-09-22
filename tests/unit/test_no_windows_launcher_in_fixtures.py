"""No test fixture runs the Windows Python launcher.

THE DEFECT. Three tests written in one session declared `py` as the interpreter inside a
Dream Studio command — a gate manifest's `command:`, a standards profile's `with_target:`,
and a `TEST-CHECK: cmd:` string. `py` is the **Windows launcher**. Ubuntu and macOS do
not have it, so those three tests ran nowhere but the machine that wrote them.

WHY NOTHING CAUGHT IT FOR A DAY. `pr-smoke` runs four gate files, so every one of those
pull requests went green on all three platforms. `full-ci` on `main` runs the suite and
went red — after the merges. The subset gap, exactly as the repository's own notes
describe it, and the failure surfaces on the branch nobody is watching.

WHAT THIS DELIBERATELY DOES NOT FLAG. `py` appearing in an assertion about manifest TEXT
(`assert entry["command"] == ["py", "-m", ...]`) is correct: this repository's own
manifests invoke `py`, and Windows is where they run. The pattern therefore matches only
`py` in the interpreter slot of a Dream Studio command DECLARATION — `command:`,
`with_target:`, `cmd:` — which is the shape that executes. Measured when written: it
catches all three real cases and none of the fifteen assertion-shaped mentions.
"""

from __future__ import annotations

import pathlib
import re

TESTS_DIR = pathlib.Path(__file__).resolve().parents[1]

#: `py` as the interpreter of a command a test actually runs.
LAUNCHER_IN_COMMAND = re.compile(
    r"""(?:^|["'\s])(?:command|with_target|cmd):\s*\[?\s*["']?py[\s"',]"""
)


def _offenders() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if LAUNCHER_IN_COMMAND.search(line):
                found.append((path.relative_to(TESTS_DIR).as_posix(), number, line.strip()))
    return found


def test_no_fixture_declares_the_windows_launcher_as_its_interpreter():
    offenders = _offenders()
    assert not offenders, "\n".join(
        f"  {p}:{n}  {line[:100]}\n"
        "    `py` is the Windows launcher; ubuntu and macos do not have it."
        " Use sys.executable."
        for p, n, line in offenders
    )


def test_the_pattern_catches_the_three_that_broke_main():
    """Guard the guard. A pattern that matched nothing would pass this file forever while
    the next fixture reintroduced the defect."""
    for sample in (
        '    command: [py, -c, "print(1)"]',
        '  with_target: py -c "x" {target}',
        '_run_one_test_check("cmd: py -c pass", root)',
    ):
        assert LAUNCHER_IN_COMMAND.search(sample), sample


def test_the_pattern_does_not_flag_assertions_about_manifest_text():
    """This repository's own manifests invoke `py`, and Windows is where they run. A
    pattern that flagged those would be a wall people route around."""
    for sample in (
        'assert entry["command"] == ["py", "-m", "core.gates.agent_coverage"]',
        'record = run_check("test", ["py", "-m", "pytest"])',
        '@pytest.mark.parametrize("program", ["py", "git", "gh"])',
        'assert argv == ["py", "-m", "core.gates.migration_risk"]',
    ):
        assert not LAUNCHER_IN_COMMAND.search(sample), sample
