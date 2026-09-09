"""WO f237b4b5: the security scanner must see the code shapes this repo actually writes.

THE DEFECT. A live shell injection sat in ``control/execution/workflow/runner.py`` for a
month -- a node's own output reached ``subprocess.run(check, shell=True)`` as code, and the
injected command's exit status became the node's verification evidence (WO 26675b56). DS had
carried a ``shell=True`` detector the whole time. Called against that file's content,
``scan_for_patterns`` returned ``[]``.

The pattern was ``subprocess[^\\n]+shell\\s*=\\s*True``: the token and the keyword on ONE
line. Black formats any multi-argument call across lines. Counted over
``git ls-files *.py`` by walking each call's parenthesis depth, 56 subprocess call sites in
this repo are single-line and 189 span lines -- blind to 77% of them.

Widening the window was the obvious fix and the wrong one. A 400-character DOTALL window is
exactly what made ``single-read-path``'s first cut name five lines containing no status
comparison at all, because it bridged unrelated statements. Parsing has no window to get
wrong -- and it removes false positives as well: the ``eval()`` pattern flagged 10 files and
a parse confirmed a real ``eval()`` call in ZERO of them, because a regex over source reads
prose as code and flags its own explanation.

MOST OF THESE TESTS CALL THE CHECKER WITH CONSTRUCTED INPUT rather than editing a real
file. Mutating a real input tests the input; it does not test the checker. Two tests use
the real repository on purpose, and say why in their own docstrings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from control.analysis.security_patterns import (
    UNPARSEABLE_LABEL,
    findings_with_lines,
    parsed_findings,
    scan_for_patterns,
)
from core.gates.security_scan import changed_scannable_files, offenders_in_text

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The shape the old pattern could not see: black's output for any real call.
MULTILINE = "import subprocess\nsubprocess.run(\n    cmd,\n    shell=True,\n)\n"

#: The shape it could see, kept so the fix is shown not to have traded one blindness for
#: another.
SINGLE_LINE = "import subprocess\nsubprocess.run(cmd, shell=True)\n"


# ── the blindness that let a live injection through ──────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        MULTILINE,
        SINGLE_LINE,
        "import subprocess\nsubprocess.run(\n    cmd,\n    shell=True,  # trailing comment\n)\n",
        "import subprocess as sp\nsp.Popen(\n    cmd,\n    shell=True\n)\n",
        "subprocess.check_output(\n    cmd,\n    shell=True,\n    timeout=5,\n)\n",
    ],
)
def test_a_multiline_shell_true_call_is_found(source):
    """Every one of these is a real call. The old pattern saw only the single-line one."""
    assert "shell=True" in scan_for_patterns(source, "x.py")


def test_shell_false_is_not_a_finding():
    """Without this, the two tests above would pass against a checker that flags the word
    `shell` and says nothing about its value -- which is measuring key presence instead of
    value, the mistake this session had to correct once already."""
    assert scan_for_patterns("subprocess.run(cmd, shell=False)\n", "x.py") == []


def test_the_keyword_line_is_reported_not_the_call_line():
    """For a multi-line call these differ, and the keyword line is both what a reader needs
    pointed at and where an author would put an exemption comment."""
    found = findings_with_lines(MULTILINE, "x.py")
    assert found == [(4, "shell=True", "subprocess.run")], found


def test_the_vulnerable_file_that_was_reported_clean_is_now_found():
    """THE REGRESSION THIS EXISTS FOR, against the real historical content.

    Reads the pre-fix ``runner.py`` out of git rather than a fixture, because the claim
    being pinned is about THAT file: the detector returned [] on it while it held a proven,
    exploitable shell injection. A fixture could drift away from the real shape; git cannot.
    """
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "show", "c9e81457~1:control/execution/workflow/runner.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if proc.returncode != 0:
        pytest.skip("the pre-fix commit is not reachable in this checkout")
    assert "shell=True" in scan_for_patterns(proc.stdout, "runner.py")


def test_the_fixed_file_is_clean():
    """The other direction. A checker that flags everything would pass the test above.

    CARRIES ITS OWN POSITIVE CONTROL. An independent audit made the parser return nothing
    and this test still passed -- "the file is clean" is satisfied by a scanner that finds
    nothing anywhere. So it now also plants a finding in the same content and requires it
    to be found. Clean has to mean looked-and-found-nothing, not never-looked.
    """
    current = (REPO_ROOT / "control" / "execution" / "workflow" / "runner.py").read_text(
        encoding="utf-8"
    )
    assert scan_for_patterns(current, "runner.py") == []

    planted = current + "\n\nsubprocess.run(\n    cmd,\n    shell=True,\n)\n"
    assert "shell=True" in scan_for_patterns(planted, "runner.py"), (
        "the scanner found nothing in a file with a planted finding, so the assertion"
        " above proves nothing"
    )


# ── the false positives parsing removes ──────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        '"""Never use shell=True here."""\n',
        "# Subcommand-shaped eval (`deno eval <code>`) was invisible by construction\n",
        "# os.system() is refused; use subprocess with an argv list\n",
        'HELP = "pass shell=True only with a literal argv"\n',
    ],
)
def test_prose_about_a_pattern_is_not_a_use_of_it(source):
    """A regex over source flags its own explanation.

    Measured: `\\beval\\s*\\(` matched 10 files in this repo and a parse confirmed a real
    `eval()` call in none of them -- "eval (`deno eval <code>`)" is a sentence with a
    parenthetical. A blocking gate on that would fire on 10 clean files and be switched off
    within a day.
    """
    assert scan_for_patterns(source, "x.py") == []


def test_a_real_eval_call_is_still_found():
    """The exemption above is for PROSE, not for eval itself."""
    assert "eval()" in scan_for_patterns("value = eval(user_input)\n", "x.py")


def test_a_real_os_system_call_is_still_found():
    assert "os.system()" in scan_for_patterns("import os\nos.system(cmd)\n", "x.py")


def test_the_whole_tracked_tree_is_clean():
    """The compatibility claim, pinned rather than asserted: registering this as a BLOCKING
    gate is only defensible if it passes on the tree as it stands. Before parsing, the
    eval() pattern alone flagged 10 files."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    flagged = {}
    scanned = 0
    for rel in proc.stdout.split():
        path = REPO_ROOT / rel
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        scanned += 1
        offenders = offenders_in_text(content, rel)
        if offenders:
            flagged[rel] = [o["label"] for o in offenders]
    assert not flagged, f"the gate would block the current tree: {flagged}"

    # POSITIVE CONTROL, for the same reason as test_the_fixed_file_is_clean: this passed
    # under a mutation that made the parser return nothing.
    assert scanned > 1000, f"only {scanned} files were read; the sweep is not running"
    assert offenders_in_text(
        "subprocess.run(\n  c,\n  shell=True,\n)\n", "probe.py"
    ), "the gate found nothing in constructed hostile input, so a clean tree proves nothing"


# ── a check that could not run must not report clean ────────────────────────


def test_unparseable_python_is_reported_not_passed():
    """A CHECK THAT COULD NOT RUN MUST NOT READ AS A PASS.

    Silence from a parser that never ran is indistinguishable from a clean result, which is
    the fail-open shape `core/gates/fail_open_probe.py` guards. An earlier cut answered this
    with a regex fallback; the fallback is what flagged nine lines of prose in YAML, so an
    unparseable .py now yields an explicit finding instead. All 1598 tracked .py files
    parse, so this is a report, not a wall.
    """
    assert parsed_findings("    shell=True,") is None
    labels = scan_for_patterns("    shell=True,", "x.py")
    assert UNPARSEABLE_LABEL in labels, labels


def test_a_shell_script_is_scanned_by_regex():
    """WHERE THE SYNTAX CAN EXECUTE. Making code shapes Python-only deleted a capability the
    single-regex design had and broke
    `tests/integration/test_hook_on_security_scan.py::test_warns_on_shell_true`, which
    writes a shell=True call into a .sh file and expects a warning. Shell and JS-family
    files are matched by regex -- weaker than parsing, and the only option without a parser
    for those languages."""
    found = findings_with_lines("subprocess.run(cmd, shell=True)\n", "deploy.sh")
    assert found, "a .sh file was not scanned for code shapes"
    assert "no parser" in found[0][2]


@pytest.mark.parametrize(
    ("source", "path"),
    [
        ("# never use shell=True here\n", "deploy.sh"),
        ("// eval(x) is banned in this codebase\n", "app.js"),
    ],
)
def test_a_comment_in_a_non_python_file_is_not_a_use(source, path):
    """The regex path skips comment lines. A heuristic rather than a parser, and named as
    one -- but without it the same prose-flagging defect returns for shell and JS."""
    assert findings_with_lines(source, path) == []


@pytest.mark.parametrize("path", ["canonical/rules.yml", "pre-push.yaml", "sample.env"])
def test_a_data_file_gets_no_code_shape_scan(path):
    """YAML and .env are DATA. A `shell=True` there is a value or prose, never a call --
    and these are the files whose prose about these patterns made an earlier cut of the gate
    block its own change set on nine findings, every one of them documentation."""
    source = "description: reached subprocess.run(check, shell=True) and eval() matched\n"
    assert findings_with_lines(source, path) == []


# ── the gate's exemption, which must cost something to use ──────────────────


def test_an_exemption_with_a_real_reason_is_honoured():
    source = MULTILINE.replace(
        "    shell=True,",
        "    shell=True,  # security-scan: argv is a fixed literal, nothing interpolated",
    )
    assert offenders_in_text(source, "x.py") == []


@pytest.mark.parametrize("reason", ["fine", "ok", "needed", "wontfix"])
def test_an_exemption_needs_a_usable_reason(reason):
    """An escape hatch without a mandatory reason becomes the norm, which is how a rule
    turns back into prose. Follows `fixture-schema-parity`'s precedent."""
    source = MULTILINE.replace("    shell=True,", f"    shell=True,  # security-scan: {reason}")
    offenders = offenders_in_text(source, "x.py")
    assert offenders, f"a reason of {reason!r} was accepted"
    assert "no usable reason" in offenders[0]["message"]


def test_an_exemption_on_the_line_above_is_honoured():
    """Black moves a long trailing comment onto its own line, so requiring the comment on
    the finding's exact line would make the rule depend on the formatter."""
    source = MULTILINE.replace(
        "    shell=True,",
        "    # security-scan: argv is a fixed literal, nothing interpolated\n    shell=True,",
    )
    assert offenders_in_text(source, "x.py") == []


def test_an_unrelated_comment_is_not_an_exemption():
    """The fixture is LONG on purpose.

    A first cut used `# noqa: S602`, which the gate rejects for being under the reason
    length -- not for failing to be an exemption at all. An audit broadened the exemption
    regex to match any comment and this test stayed green, because the short fixture was
    still refused for the wrong reason. A comment well past the length bar can only be
    refused for the right one.
    """
    long_unrelated = "  # this comment is comfortably longer than the minimum reason length"
    source = MULTILINE.replace("    shell=True,", f"    shell=True,{long_unrelated}")
    offenders = offenders_in_text(source, "x.py")
    assert offenders, "an unrelated comment was accepted as an exemption"
    assert "no usable reason" not in offenders[0]["message"], (
        "refused for being too short rather than for not being an exemption -- the fixture"
        " cannot tell the two apart"
    )


# ── the gate sees new files, which is where a security gate is most needed ──


def test_the_gate_looks_at_untracked_files_too():
    """`git diff` never reports an untracked file, and a brand-new file is exactly the case
    a security gate most needs to see -- the `gitignore-phantom` gate was written after that
    same blind spot.

    THIS DRIVES THE SURFACE. A first cut read the AST of the gate's own source looking for
    an `ls-files --others` argv, and an independent audit showed it was ceremony: keep the
    literal, discard its output, and the test still passed while untracked detection was
    verifiably broken at runtime. Reading source text where you could drive the real thing
    is the exact substitution `core/gates/deterministic_evidence.py` exists to report.

    The file is written inside the repo because that is the only place the function looks,
    and removed in a finally so a failure cannot leave the tree dirty.
    """
    probe = REPO_ROOT / "_security_scan_untracked_probe.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    try:
        returned = changed_scannable_files()
        assert probe.name in {Path(rel).name for rel in returned}, (
            f"an untracked file was not returned; the gate cannot see a new file. got"
            f" {returned}"
        )
    finally:
        probe.unlink(missing_ok=True)


def test_changed_scannable_files_returns_only_scannable_paths():
    """Driven against the real repository: whatever the current diff is, every path this
    returns must be one the scanner accepts, or the gate would try to parse a PNG."""
    for rel in changed_scannable_files():
        assert Path(rel).suffix.lower() in {
            ".py",
            ".ts",
            ".js",
            ".tsx",
            ".jsx",
            ".sh",
            ".yaml",
            ".yml",
            ".env",
        }, rel


# ── the hook, which is the fast tier and cannot block ───────────────────────


def test_the_hook_scans_the_file_not_the_fragment(tmp_path):
    """The hook used to scan an Edit's `new_string`. For a realistic payload that is
    `'    shell=True,'`: unparseable, and missing the `subprocess` token the old regex also
    required. Being PostToolUse the complete file is already on disk, so it reads that.

    Asserts BOTH directions -- the finding is reported from the file, and would not be
    reported from the fragment alone -- so the test distinguishes the fix from the bug.
    """
    victim = tmp_path / "victim.py"
    victim.write_text(MULTILINE, encoding="utf-8")
    fragment = "    shell=True,"

    assert parsed_findings(fragment) is None
    assert "shell=True" in scan_for_patterns(victim.read_text(encoding="utf-8"), str(victim))

    hook = REPO_ROOT / "runtime" / "hooks" / "quality" / "on-security-scan.py"
    payload = (
        '{"tool_name": "Edit", "tool_input": {"file_path": '
        + repr(str(victim)).replace("'", '"')
        + ', "new_string": "    shell=True,"}}'
    )
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(hook)],
        input=payload,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        # INHERIT the environment. A first cut passed a bare dict with SYSTEMROOT="" and
        # Windows then could not load `_overlapped`, which the import chain reaches through
        # asyncio -- WinError 10106, on windows-latest only. It passed ubuntu and macos and
        # would have redded the one platform the merge rule requires.
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "shell=True" in (proc.stdout or ""), proc.stdout


def test_the_hook_has_no_deny_path_and_that_is_deliberate():
    """PostToolUse runs AFTER the edit is applied, so there is nothing left to block. A
    deny path here would be theatre; the blocking tier is the gate. Pinned so nobody adds
    one believing it protects something."""
    source = (REPO_ROOT / "runtime" / "hooks" / "quality" / "on-security-scan.py").read_text(
        encoding="utf-8"
    )
    assert "sys.exit(2)" not in source
    assert "permissionDecision" not in source


# ── what the second audit round found ───────────────────────────────────────


def test_a_credential_in_valid_python_is_found():
    """THE FAIL-OPEN I INTRODUCED, and it was worse than the defect being fixed.

    `findings_with_lines` returned as soon as `parsed_findings` succeeded, and
    `parsed_findings` knows only the three code shapes. Every one of the 1598 tracked .py
    files parses, so the blocking gate never checked ANY of them for a hardcoded
    credential, a PEM block or a token. Proven end to end by an independent audit with a
    probe file carrying all three: it appeared in `files_checked` and contributed zero
    offenders.
    """
    # security-scan: fabricated credential used as INPUT to the detector under test; it reaches an assertion, never a service.
    source = 'import os\npassword = "hunter2hunter2"\n'
    labels = scan_for_patterns(source, "probe.py")
    assert "hardcoded credential" in labels, labels
    assert offenders_in_text(source, "probe.py")


def test_a_credential_whose_value_is_on_the_next_line_is_found():
    """MY OWN REGRESSION, found by testing the fix rather than reading it, about two hours
    after writing "parsing has no window to get wrong".

    The format patterns were scanned line by line, which reintroduced the newline blindness
    this work order exists to remove: the credential pattern's whitespace spans a newline,
    so a whole-content search matches and a per-line search cannot.
    """
    source = 'password =\n    "hunter2hunter2"\n'
    assert "hardcoded credential" in scan_for_patterns(source, "probe.py")


def test_a_format_finding_reports_the_right_line():
    """The line comes from the match offset, so it survives the whole-content search."""
    # security-scan: fabricated credential used as INPUT to the detector under test; it reaches an assertion, never a service.
    source = "\n" * 7 + 'password = "hunter2hunter2"\n'
    found = [f for f in findings_with_lines(source, "x.py") if f[1] == "hardcoded credential"]
    assert found == [(8, "hardcoded credential", "format match")], found


@pytest.mark.parametrize(
    "source",
    [
        "subprocess.run(cmd, shell=1)\n",
        "subprocess.run(cmd, shell=bool(1))\n",
        "subprocess.run(cmd, shell=True if flag else False)\n",
        "SHELL = True\nsubprocess.run(cmd, shell=SHELL)\n",
        'subprocess.run(cmd, **{"shell": True})\n',
    ],
)
def test_a_shell_value_that_is_not_a_literal_false_is_a_finding(source):
    """`shell=(platform.system() == "Windows")` is idiomatic Python, not an evasion, and a
    check that reads "I could not tell" as "safe" is a fail-open. Only a literal false value
    clears a subprocess call."""
    assert "shell=True" in scan_for_patterns(source, "x.py")


def test_an_undetermined_shell_value_on_an_unrelated_callee_is_not_a_finding():
    """THE FALSE POSITIVE ON INNOCENT CODE. `core/config/platform.py` has
    `shell=_detect_shell()` -- a dataclass field named `shell`, nothing to do with
    subprocess. Treating undetermined as a finding is right for `subprocess.run`; here it
    reported a security finding on safe code, and diff-scoping only hid it until someone
    touched that file for an unrelated reason.

    A truthy LITERAL is still reported on any callee, because `shell=True` is essentially
    only subprocess and over-reporting is the safe direction there.
    """
    assert scan_for_patterns("Settings(shell=_detect_shell())\n", "x.py") == []
    assert "shell=True" in scan_for_patterns("Settings(shell=True)\n", "x.py")


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(cmd, shell=flag)\n",
        "import subprocess as sp\nsp.run(cmd, shell=flag)\n",
        "from subprocess import run\nrun(cmd, shell=flag)\n",
    ],
)
def test_an_undetermined_shell_value_on_a_subprocess_callee_is_a_finding(source):
    """The coverage that matters, and it has to survive an import alias -- this repo writes
    `import subprocess as sp` in its own fixtures."""
    assert "shell=True" in scan_for_patterns(source, "x.py")


@pytest.mark.parametrize(
    "source",
    [
        "import os as o\no.system(cmd)\n",
        "from os import system\nsystem(cmd)\n",
        "from os import system as run_it\nrun_it(cmd)\n",
        "import builtins\nbuiltins.eval(x)\n",
    ],
)
def test_an_import_alias_does_not_hide_a_dangerous_call(source):
    """Matched by literal name, any alias evaded it. The docstring had admitted only the
    `from os import` case while `import os as o` is the more common shape."""
    assert scan_for_patterns(source, "x.py")


def test_exec_is_detected():
    """eval's more powerful sibling, and it was absent from the label table entirely."""
    assert "exec()" in scan_for_patterns("exec(user_input)\n", "x.py")


# test_a_credential_testing_fixture_is_excluded was DELETED, not fixed. It asserted the
# path-allowlist behaviour that three audit rounds showed to be the wrong tool -- it went
# red the moment the allowlist was removed, which is a test correctly reporting that its
# subject is gone. Its replacement is
# test_an_ordinary_file_cannot_lose_coverage_by_its_name, which pins the opposite
# property: no filename can silence a finding.
def test_a_credential_fixture_is_still_scanned_for_code_shapes():
    """The exclusion is for credential FORMATS, not a blanket pass. A real `shell=True` in
    one of those files is still a finding."""
    source = "subprocess.run(\n    cmd,\n    shell=True,\n)\n"
    assert offenders_in_text(source, "tests/unit/test_credential_patterns_x.py")


def test_an_exemption_can_sit_above_the_containing_statement():
    """A FINDING INSIDE A MULTI-LINE LITERAL HAS NO LINE A COMMENT CAN ATTACH TO.

    Found by using the mechanism: I declared a triple-quoted credential fixture and the
    gate ignored the declaration, because the walk upward stops at the assignment line,
    which is not a comment -- and a `#` inside the string would change the fixture. The
    easy way out was to exempt the whole file on the path list, which would have papered
    over a gap in this mechanism with a blanket exclusion.
    """
    # security-scan: fabricated credential used as INPUT to the detector under test; it reaches an assertion, never a service.
    source = (
        "# security-scan: sample source fed to the auditor; the key is fabricated\n"
        'SAMPLE = """\n'
        'API_KEY = "sk-abc123def456"\n'
        '"""\n'
    )
    assert offenders_in_text(source, "x.py") == []


def test_a_distant_comment_still_cannot_silence_a_finding():
    """The statement anchor must not become a way for any comment anywhere to reach a
    finding. Both anchor points stay contiguous.

    THE FINDING IS INSIDE A MULTI-LINE LITERAL on purpose, so the statement fallback is
    actually entered. An earlier fixture put the finding on the statement's own first
    line, which means `start == number` and the fallback branch never ran -- an
    independent audit mutated the statement anchor's contiguity and the test stayed
    green. It was testing the direct-line anchor twice.

    The declaration below is about the FIXTURE, not the case: the scanner reads this
    file too, and the fixture string is credential-shaped by design.
    """
    # security-scan: the credential below is fabricated and is the input to the assertion.
    source = (
        "# security-scan: a reason placed nowhere near the finding it would excuse\n"
        "x = 1\n\n\n"
        'SAMPLE = """\n'
        'password = "hunter2hunter2"\n'
        '"""\n'
    )
    assert offenders_in_text(
        source, "x.py"
    ), "a non-contiguous comment reached a finding inside a multi-line literal"


# -- round 3: the path allowlist is gone, and four narrower fixes -----------


@pytest.mark.parametrize(
    "path",
    [
        "core/utils/test_credential_patterns_helper.py",
        "src/templates/security_report_generator.py",
        "app/test_secret_scanner_but_not_really.py",
        "my_test_security_baseline_wrapper.py",
    ],
)
def test_an_ordinary_file_cannot_lose_coverage_by_its_name(path):
    """WHY THE PATH ALLOWLIST WAS DELETED RATHER THAN EXTENDED.

    Three audit rounds produced the same root cause three times: a file that
    legitimately holds credential-shaped strings was not on a hand-maintained list, so
    the gate blocked on it -- the third time, on this work order's own test file. And
    the list failed in the OTHER direction too: the check was a bare substring test, so
    every path here is an ordinary file that matched one entry and silently lost ALL
    THREE format patterns, because one match short-circuited the whole format lane.

    The replacement is the declared exemption at the finding site: local, visible in
    the diff, carrying a reason, and impossible to forget for a new file -- a new file
    with a credential fixture simply fails until someone declares it.
    """
    # security-scan: a fabricated credential; the assertion is that it IS reported.
    probe = 'password = "hunter2hunter2"\n'
    assert offenders_in_text(probe, path)


@pytest.mark.parametrize(
    "source",
    [
        "def run(cmd, shell=False):\n    pass\nrun(cmd, shell=flag)\n",
        "def call(x, shell=None):\n    return x\ncall(y, shell=cfg.shell)\n",
        "def check_output(a, shell=None):\n    return a\ncheck_output(b, shell=z)\n",
    ],
)
def test_a_local_function_named_like_subprocess_is_not_treated_as_subprocess(source):
    """The subprocess list held BARE names so that `from subprocess import run` would
    resolve. Those matched any unqualified call by that name, so a locally defined `run`
    with an unrelated `shell=` keyword was reported -- the identical false-positive
    shape the narrowing was built to remove from `core/config/platform.py`.

    Import resolution already covers the legitimate case, so the bare names are gone.
    """
    assert scan_for_patterns(source, "x.py") == []


def test_os_posix_spawn_is_a_subprocess_callee():
    source = "import os\nos.posix_spawn(path, argv, env, shell=flag)\n"
    assert "shell=True" in scan_for_patterns(source, "x.py")


def test_a_js_block_comment_body_is_not_code():
    """The comment heuristic was wrong in BOTH directions. A `/* */` body line without a
    leading `*` was read as code -- prose flagged as a call, this work order's own
    defect returning for JS."""
    source = "/*\na comment\neval(userInput)\nstill comment\n*/\n"
    assert findings_with_lines(source, "app.js") == []


def test_a_js_generator_shorthand_is_code():
    """The other direction: `*gen()` starts with `*` and was skipped as a comment
    continuation, hiding a real executable eval behind ordinary syntax."""
    assert findings_with_lines("*gen() { eval(x) }\n", "app.js")


def test_a_closed_block_comment_does_not_swallow_the_rest_of_the_file():
    """A one-line `/* ... */` must not open a block, and a closed block must not leave
    the scanner blind for everything after it."""
    source = "/* short */\neval(userInput)\n"
    assert findings_with_lines(source, "app.js")


def test_native_shell_eval_is_detected():
    """SCOPE CORRECTION. The Python-flavoured patterns need parentheses and shell's eval
    takes none, so `eval` of an untrusted variable -- the actual shell injection shape --
    was never matched. Only Python code EMBEDDED in a shell file was ever caught."""
    found = findings_with_lines('eval "$cmd"\n', "deploy.sh")
    assert found, "native shell eval was not detected"
    assert found[0][1] == "eval()"


def test_a_commented_shell_eval_is_not_a_finding():
    probe = '# eval "$cmd" is banned here\n'
    assert findings_with_lines(probe, "deploy.sh") == []


def test_every_label_the_module_can_produce_survives_scan_for_patterns():
    """THE COUPLING THAT BROKE THE FIRST TIME IT WAS USED.

    `scan_for_patterns` ordered its output by iterating PATTERNS, so a label with no
    PATTERNS entry was silently dropped -- `exec()` was added to the parsed label table
    and vanished from this function and from the advisory hook, while the blocking gate
    reported it correctly. Two lists that had to agree, coupled by nothing.

    This asserts the round trip for every label, so the next one added cannot go
    missing quietly.
    """
    # security-scan: every probe below is fabricated input to the detector under test.
    probes = {
        "hardcoded credential": ('password = "hunter2hunter2"\n', "x.py"),
        "eval()": ("eval(user_input)\n", "x.py"),
        "exec()": ("exec(user_input)\n", "x.py"),
        "os.system()": ("import os\nos.system(cmd)\n", "x.py"),
        "shell=True": ("subprocess.run(cmd, shell=True)\n", "x.py"),
        "private key in source": ('K = "-----BEGIN RSA PRIVATE KEY-----"\n', "x.py"),
        UNPARSEABLE_LABEL: ("    shell=True,", "x.py"),
    }
    for label, (source, path) in probes.items():
        line_level = {found[1] for found in findings_with_lines(source, path)}
        assert label in line_level, f"{label} is not produced at line level"
        assert label in scan_for_patterns(source, path), (
            f"{label} is produced at line level but dropped by scan_for_patterns, so"
            " the advisory hook would never report it"
        )


# -- the container anchor, for formats a parser cannot reach -----------------


def test_a_declaration_reaches_a_finding_inside_a_yaml_block_scalar():
    """A finding inside a `>` or `|` scalar cannot carry a `#`: that would become part of
    the STRING, changing the data and exempting nothing. Two real template files are
    shaped exactly this way, and solving it only for Python (via ast) left them
    unexemptable.

    An audit found the mechanism load-bearing -- removing it makes the gate fail on its
    own diff -- but also found every test still passing without it, because no fixture
    exercised an indented block. A load-bearing mechanism with no test is the shape this
    work order is about.
    """
    # security-scan: a fabricated credential inside a fixture for the detector under test.
    source = (
        "parent:"
        + "\n"
        + "  # security-scan: a bracketed placeholder in a remediation example"
        + "\n"
        + "  code_before: |"
        + "\n"
        + '    DB_PASSWORD = "hunter2hunter2"'
        + "\n"
    )
    assert offenders_in_text(source, "fixes.yaml") == []


def test_a_declaration_does_not_reach_a_sibling_block():
    """The walk stops at the nearest preceding line indented LESS than the finding, so it
    lands on the finding's own immediate key and never a sibling's."""
    # security-scan: a fabricated credential inside a fixture for the detector under test.
    source = (
        "parent:"
        + "\n"
        + "  # security-scan: this declaration is about the first block only"
        + "\n"
        + "  first: |"
        + "\n"
        + '    password = "hunter2hunter2"'
        + "\n"
        + "  second: |"
        + "\n"
        + '    password = "hunter2hunter2"'
        + "\n"
    )
    offenders = offenders_in_text(source, "fixes.yaml")
    assert len(offenders) == 1, offenders


def test_a_declaration_above_an_ancestor_does_not_reach_a_nested_finding():
    """Tighter than expected, and worth pinning: the declaration has to be adjacent to the
    IMMEDIATE owning key, not to any ancestor further up the tree."""
    # security-scan: a fabricated credential inside a fixture for the detector under test.
    source = (
        "# security-scan: a declaration parked above the grandparent key"
        + "\n"
        + "a:"
        + "\n"
        + "  b:"
        + "\n"
        + "    inner: |"
        + "\n"
        + '      password = "hunter2hunter2"'
        + "\n"
    )
    assert offenders_in_text(source, "fixes.yaml")


def test_one_declaration_covers_its_whole_block():
    """THE ACCEPTED OVER-REACH, pinned so it is never mistaken for an unaccepted one.

    A declaration above a container covers findings anywhere inside it -- the same trade
    already made for a large Python statement. It is explicit, in the diff, and carries a
    reason, which is what makes it acceptable."""
    # security-scan: a fabricated credential inside a fixture for the detector under test.
    source = (
        "# security-scan: both placeholders below are bracketed hints, not credentials"
        + "\n"
        + "code_before: |"
        + "\n"
        + '  DB_PASSWORD = "hunter2hunter2"'
        + "\n"
        + '  API_KEY = "hunter2hunter2"'
        + "\n"
    )
    assert offenders_in_text(source, "fixes.yaml") == []


def test_the_two_real_template_files_stay_exempted():
    """Driven against the REAL files, because they are the reason the anchor exists and a
    constructed fixture can drift away from their shape. Each must produce raw findings
    and zero offenders -- a genuine zero, not an unscanned one.
    """
    for rel in (
        "templates/security/compliance/cwe-top25-mapping.yaml",
        "templates/security/mitigations/secrets-fixes.yaml",
    ):
        path = REPO_ROOT / rel
        if not path.is_file():
            pytest.skip(f"{rel} is absent from this checkout")
        content = path.read_text(encoding="utf-8")
        raw = findings_with_lines(content, rel)
        assert raw, f"{rel} produced no findings at all; the scanner is not looking"
        assert offenders_in_text(content, rel) == [], rel
