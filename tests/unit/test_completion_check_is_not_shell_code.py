"""WO 26675b56: a node's output must not be executed as shell code.

THE DEFECT, proven by driving the real ``_verify_completion`` with a crafted state.
``completion_check`` was resolved through ``resolve_templates`` and then run with
``subprocess.run(check, shell=True)``. ``engine._resolve_ref`` returns
``str(node.get(field, ""))`` for any ``{{node_id.output}}`` reference, so text a command
node captured -- or an LLM's stdout -- became shell CODE.

The RCE is the lesser half. The injected command's exit status BECAME THE NODE'S EVIDENCE:
a check for a module that does not exist reported ``completed`` because the node's output
ended in a shell separator. The checked party could author its own PASS, in the one
mechanism whose whole purpose is to be unforgeable.

MOST OF THESE TESTS IMPORT THE GUARD AND CALL IT with constructed input -- absent, empty,
malformed, hostile -- rather than editing a real manifest. Mutating a real input tests the
input; it does not test the checker. The two end-to-end tests exist because the guard being
correct in isolation would prove nothing about whether the runner uses it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from control.execution.workflow.runner import _SHELL_METACHARACTERS, WorkflowRunner, check_argv

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The interpreter, as a check would have to spell it. NOT `py`: that is the Windows
#: Python launcher and does not exist on ubuntu or macos, so a `py` fixture would fail on
#: two of the three platforms that gate a merge -- invisible to a Windows-only test run.
#: As a POSIX path because `shlex` deletes backslashes, and quoted because the interpreter
#: path contains a space on a default Windows install.
PYTHON = chr(34) + Path(sys.executable).as_posix() + chr(34)


# ── the guard, called directly with constructed input ─────────────────────────


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_an_absent_check_is_not_runnable(raw):
    """No check at all must not become an empty argv that some shell then interprets."""
    argv, reason = check_argv(raw)
    assert argv is None
    assert reason


def test_a_plain_command_becomes_argv():
    argv, reason = check_argv("py -m core.gates.migration_risk")
    assert reason is None
    assert argv == ["py", "-m", "core.gates.migration_risk"]


@pytest.mark.parametrize("char", [c for c in _SHELL_METACHARACTERS if c != chr(10)])
def test_a_shell_metacharacter_in_the_raw_check_blocks(char):
    """Blocked, never reinterpreted.

    Silently passing the character through as a literal argument would let a check that
    used to pipe exit 0 for the wrong reason -- a fail-open in a verifier, which is worse
    than refusing to run.
    """
    argv, reason = check_argv(f"py -m thing {char} other")
    assert argv is None, f"{char!r} produced argv instead of blocking"
    assert reason is not None
    assert repr(char) in reason, f"the reason must name {char!r} so an author can fix it"


def test_a_newline_in_the_raw_check_blocks_and_is_named_readably():
    argv, reason = check_argv("py -m one" + chr(10) + "py -m two")
    assert argv is None
    assert reason is not None
    assert "newline" in reason


def test_an_unbalanced_quote_blocks_rather_than_raising():
    """shlex.split raises on this. A verifier that crashes is a verifier that stops the
    run for a reason the operator cannot read."""
    argv, reason = check_argv('py -m thing "unclosed')
    assert argv is None
    assert reason is not None


# ── the load-bearing property: split first, resolve per token ────────────────


def test_a_resolved_value_containing_spaces_stays_one_argument():
    """THE reason resolution happens per token.

    Resolving the whole string and splitting afterwards would let one interpolated value
    expand into several argv elements. A work-order id is a single argument even when the
    value substituted for it is a sentence.
    """
    argv, reason = check_argv(
        "py -m ds work-order tasks {{workflow.work_order_id}}",
        lambda t: "a b c" if "{{" in t else t,
    )
    assert reason is None
    assert argv == ["py", "-m", "ds", "work-order", "tasks", "a b c"]


def test_a_resolved_value_containing_shell_syntax_stays_one_argument():
    """After resolution a metacharacter is DATA. It arrived in a node's output and must
    become exactly one literal argv element -- never a second command, never a second
    argument."""
    hostile = "harmless & exit 0"
    argv, reason = check_argv("py -m thing {{agent.output}}", lambda t: hostile if "{{" in t else t)
    assert reason is None
    assert argv == ["py", "-m", "thing", hostile]


def test_a_resolved_value_cannot_smuggle_a_second_flag():
    """Argument injection, not just shell injection. `--force` in an interpolated value
    must reach the command as part of one argument, not as a flag of its own."""
    argv, reason = check_argv(
        "py -m ds work-order close {{agent.output}}",
        lambda t: "some-id --force" if "{{" in t else t,
    )
    assert reason is None
    assert "--force" not in argv
    assert argv[-1] == "some-id --force"


def test_no_resolver_leaves_tokens_alone():
    argv, reason = check_argv("py -m thing {{agent.output}}")
    assert reason is None
    assert argv == ["py", "-m", "thing", "{{agent.output}}"]


# ── end to end, through the runner that must actually use the guard ──────────


def _runner_with(node_output: str) -> WorkflowRunner:
    state = {
        "active_workflows": {
            "probe": {
                "nodes": {"agent": {"status": "completed", "output": node_output}},
                "params": {},
            }
        }
    }
    runner = WorkflowRunner("probe")
    runner._load_state = lambda: state  # type: ignore[method-assign]
    return runner


def test_a_nodes_output_does_not_execute(tmp_path):
    """The marker file is the evidence. It was written, once, by the unfixed code."""
    marker = tmp_path / "INJECTED.txt"
    runner = _runner_with(f'x && echo pwned > "{marker}"')

    runner._verify_completion(
        "victim", {"completion_check": f"{PYTHON} -c pass {{{{agent.output}}}}"}
    )

    assert not marker.exists(), "node output reached a shell and executed"


def test_a_failing_check_cannot_be_rescued_by_the_nodes_output():
    """THE FORGERY, and the reason this outranks the RCE reading.

    The check names a module that does not exist, so it must fail on its own merits. With
    `& exit 0` appended from the node's output, the shell path made the whole line exit 0
    and the node reported `completed` -- verified against the unfixed code, where this
    test returns 'completed'. The separator is chosen to work in both cmd.exe (an
    unconditional sequence) and sh (background, then exit), so this fails on every CI
    platform if the guard is removed.
    """
    runner = _runner_with("harmless & exit 0")

    status, reason = runner._verify_completion(
        "victim",
        {"completion_check": f"{PYTHON} -m nonexistent_module_xyz {{{{agent.output}}}}"},
    )

    assert status == "blocked", (
        "a check whose command fails reported " + status + " -- the checked party forged"
        " its own evidence"
    )
    assert reason


def test_a_legitimate_check_still_completes():
    """The guard must not turn every check into a blockage. Without this the two tests
    above would pass against a `_verify_completion` that simply always blocks."""
    runner = _runner_with("irrelevant")
    status, reason = runner._verify_completion("victim", {"completion_check": f"{PYTHON} -c pass"})
    assert status == "completed", reason


def test_completion_contains_still_matches_a_substring_with_spaces():
    """completion_contains is deliberately NOT tokenised: it is compared with `in` and
    never executed, and a substring may legitimately hold spaces. The task for this fix
    asked for symmetry with the check; reading the use showed symmetry would be the bug,
    so this pins the asymmetry.

    The fixture is `--version` rather than a `-c` one-liner on purpose. The first attempt
    used `py -c print('hello there world')` and failed against its own guard -- twice
    over: the parentheses were refused, and `shlex` eats the inner quotes so the code was
    a SyntaxError anyway. `--version` prints a multi-word string with no quoting and no
    metacharacters at all.
    """
    runner = _runner_with("irrelevant")
    status, reason = runner._verify_completion(
        "victim",
        {
            "completion_check": f"{PYTHON} --version",
            "completion_contains": "Python 3",
        },
    )
    assert status == "completed", reason


# ── the guard must not break the checks that already ship ────────────────────


def test_every_shipped_completion_check_is_runnable_as_argv():
    """A guard that rejected the live checks would be reverted within a day.

    Reads the manifests as text on purpose: this asserts the checks AS AUTHORED survive
    the guard, which is the compatibility claim, and a YAML parser is not needed to find
    them.
    """
    pattern = re.compile(r"^\s*completion_check:\s*(?P<check>\S.*)$", re.MULTILINE)
    found = 0
    for manifest in sorted((REPO_ROOT / "canonical" / "workflows").glob("*.y*ml")):
        text = manifest.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            raw = match.group("check").strip()
            found += 1
            argv, reason = check_argv(raw)
            assert argv is not None, f"{manifest.name}: shipped check rejected -- {reason}"
    assert found >= 9, (
        f"expected the orchestrator's shipped checks to be found, saw {found}."
        " If this drops, either the checks were removed or the pattern stopped matching"
        " them, and this test would then be asserting nothing."
    )


# ── the four refusals an independent adversarial pass surfaced ────────────────


def test_parentheses_are_allowed_because_they_are_not_shell_control():
    """The first cut refused these, and so refused every Python `-c` one-liner and every
    regex argument -- for no safety, since parentheses are neither a separator nor a
    substitution and nothing parses the argv as shell. Command substitution is still
    refused, by `$`."""
    argv, reason = check_argv("py -m thing --pattern ^foo_bar$")
    assert argv is None and reason is not None, "a $ substitution must still be refused"

    argv, reason = check_argv("py -m thing --pattern (a|b)")
    assert argv is None, "a pipe must still be refused"

    argv, reason = check_argv("py -m thing --shape abc(def)")
    assert reason is None, reason
    assert argv == ["py", "-m", "thing", "--shape", "abc(def)"]


def test_a_backslash_blocks_rather_than_being_silently_deleted():
    """shlex(posix=True) DELETES an unquoted backslash. Before this guard,
    `C:\\Users\\Example\\f.txt` became `C:Usersxf.txt` and check_argv returned reason=None --
    so the check ran against a path that never existed and reported the effect absent for
    the wrong reason. Silent corruption in a verifier is a fail-open."""
    raw = "py -m thing C:" + chr(92) + "Users" + chr(92) + "Example" + chr(92) + "f.txt"
    argv, reason = check_argv(raw)
    assert argv is None, f"backslash silently produced {argv}"
    assert reason is not None
    assert "backslash" in reason
    assert "forward slashes" in reason, "the reason must say how to fix it"


def test_a_templated_executable_blocks():
    """shell=False stops an interpolated value becoming code. It does nothing about a
    value that IS the program, so the author must name the executable."""
    argv, reason = check_argv("{{agent.output}} --version", lambda t: "evil.exe")
    assert argv is None
    assert reason is not None
    assert "executable" in reason


def test_a_batch_shim_executable_blocks():
    """Windows hands a .bat/.cmd to cmd.exe even with shell=False, which would reinterpret
    cmd's own syntax (%VAR%, ^, !) inside an interpolated value -- and that syntax is not
    in the POSIX metacharacter set this guard screens."""
    for shim in ("tool.bat", "TOOL.CMD"):
        argv, reason = check_argv(f"{shim} --check {{{{agent.output}}}}")
        assert argv is None, f"{shim} was accepted"
        assert reason is not None
        assert "cmd.exe" in reason


@pytest.mark.parametrize("shim", ["tool.bat.", '"tool.bat "', "TOOL.CMD.", "C:/t/RUNME~1.BAT"])
def test_a_batch_shim_cannot_hide_behind_a_trailing_dot_or_space(shim):
    """Windows strips trailing dots and spaces from a path component, so `tool.bat.` and
    `tool.bat ` both resolve to the batch file -- and both slipped past a plain
    `endswith` test. argv[0] is compared by bare program name, normalised."""
    argv, reason = check_argv(f"{shim} --check {{{{agent.output}}}}")
    assert argv is None, f"{shim} was accepted as {argv}"
    assert reason is not None


@pytest.mark.parametrize(
    "shell",
    [
        "cmd",
        "cmd.exe",
        "CMD.EXE",
        "powershell.exe",
        "pwsh",
        "sh",
        "bash",
        "/usr/bin/bash",
        "C:/Windows/System32/cmd.exe",
        "wscript.exe",
    ],
)
def test_a_shell_as_the_executable_blocks(shell):
    """The gap that reopens the original injection through the front door.

    None of these ends in .bat or .cmd, so the suffix rule never saw them. `cmd /c thing
    <arg>` re-parses its own arguments into a command string, so an interpolated ARGUMENT
    -- which this guard otherwise allows precisely because shell=False makes it inert --
    becomes code again. An author writing a plausible-looking check would have restored
    the proven RCE.
    """
    argv, reason = check_argv(f"{shell} -c thing {{{{agent.output}}}}")
    assert argv is None, f"{shell} was accepted as {argv}"
    assert reason is not None
    assert "shell" in reason.lower()


@pytest.mark.parametrize("program", ["py", "git", "gh", "node", "C:/tools/mytool.exe"])
def test_an_ordinary_program_is_still_allowed(program):
    """The refusals must be a short list, not a mood. Without this, tightening argv[0]
    could drift into refusing everything and the two tests above would still pass."""
    argv, reason = check_argv(f"{program} --check {{{{agent.output}}}}")
    assert reason is None, reason
    assert argv is not None and argv[0] == program


@pytest.mark.parametrize(
    "raw",
    [
        "py -c {{agent.output}}",
        "py -c{{agent.output}}",
        "python3 -c {{agent.output}}",
        "perl -e {{agent.output}}",
        "ruby -e {{agent.output}}",
        "node --eval={{agent.output}}",
        "node --eval {{agent.output}}",
        "tool --exec={{agent.output}}",
        "tool --command {{agent.output}}",
    ],
)
def test_a_template_in_a_code_executing_flags_argument_blocks(raw):
    """The gap that reopens the proven RCE without any shell at all.

    `py -m mod {{x}}` passes an interpolated value as DATA -- it lands in sys.argv, which
    is the property the whole design rests on. `py -c {{x}}` makes it THE PROGRAM, and the
    argv[0] rules cannot see it because argv[0] is the innocent interpreter. Refusing
    python/node/perl outright would be overbroad and would reject all nine shipped checks,
    so the rule follows the code rather than the program.

    THE ATTACHED FORM is in here deliberately: `py -cprint(42)` runs and prints 42, so
    `-c{{x}}` is a single token, and a rule matching a token EQUAL to `-c` misses it. Both
    the first cut of this fix and an independent audit's recommendation had that hole.
    """
    argv, reason = check_argv(raw, lambda t: "import os; os.system('id')" if "{{" in t else t)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None


@pytest.mark.parametrize(
    "raw",
    [
        "py -c pass {{agent.output}}",
        "py --check {{agent.output}}",
        "py --config {{agent.output}}",
        "py -m interfaces.cli.ds work-order tasks {{workflow.work_order_id}}",
        "node script.js {{agent.output}}",
    ],
)
def test_a_template_in_a_data_position_is_still_allowed(raw):
    """The other half of the line, and the reason the rule is not "refuse -c anywhere".

    In each of these the interpolated value reaches sys.argv (or process.argv) as data,
    which shell=False keeps inert. `--check` and `--config` are here because a prefix test
    for the short flags must not catch them -- it does not, since their second character
    is another dash -- and the shipped shape is here because refusing it would make the
    guard useless.
    """
    argv, reason = check_argv(raw, lambda t: "import os; os.system('id')" if "{{" in t else t)
    assert reason is None, reason
    assert argv is not None


@pytest.mark.parametrize("raw", ["C:cmd.exe --check", "c:powershell.exe -x", "C:tool.bat -y"])
def test_a_drive_relative_executable_cannot_hide_from_the_shell_rules(raw):
    """`C:cmd.exe` is drive-relative Windows syntax with NO separator, so PurePosixPath
    returned the whole string as the program name and it matched nothing -- an outright
    bypass of the shell refusal. PureWindowsPath models the drive."""
    argv, reason = check_argv(raw)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None


@pytest.mark.parametrize("raw", ["... --check", '"   " --check', ".. -x"])
def test_an_executable_that_normalises_to_nothing_blocks(raw):
    """This failed safe already -- subprocess raises OSError and the node blocks -- but on
    a missing-file error rather than on the check naming no program."""
    argv, reason = check_argv(raw)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None
    assert "no program" in reason


@pytest.mark.parametrize(
    "raw",
    [
        "node -p {{agent.output}}",
        "node --print {{agent.output}}",
        "node -p{{agent.output}}",
        "node.exe -p {{agent.output}}",
        "bun -p {{agent.output}}",
        "php -r {{agent.output}}",
        "php -R {{agent.output}}",
        "php -r{{agent.output}}",
        "deno eval {{agent.output}}",
    ],
)
def test_an_interpreters_own_eval_marker_blocks(raw):
    """Each of these is the named interpreter's own one-liner idiom, and each was found
    unblocked by a LATER audit round than the one that closed `-c`/`-e`.

    `-R` and `.exe` need no separate entries: markers are compared lowercased and the
    program name has its `.exe` stripped.
    """
    argv, reason = check_argv(raw, lambda t: "os.system('id')" if "{{" in t else t)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None


@pytest.mark.parametrize(
    "raw",
    [
        "grep -r {{agent.output}}",
        "git -p {{agent.output}}",
        "rsync -r {{agent.output}}",
        "tool evaluate-thing {{agent.output}}",
        "tool eval-report {{agent.output}}",
    ],
)
def test_a_marker_that_is_not_eval_on_this_program_is_allowed(raw):
    """WHY THE MARKERS ARE PER-PROGRAM, and the test that stops the list going blanket.

    `-r` is eval on php and "recursive" on grep and rsync; `-p` is eval on node and
    "paginate" on git. Refusing them everywhere would reject ordinary checks. And `eval`
    is matched as a WHOLE WORD, so `evaluate-thing` and `eval-report` are not deno's
    subcommand -- prefix matching is applied to dash-flags only.
    """
    argv, reason = check_argv(raw, lambda t: "os.system('id')" if "{{" in t else t)
    assert reason is None, reason
    assert argv is not None


@pytest.mark.parametrize("raw", ["cmd.exe:payload --check", "tool.exe:evil -x"])
def test_an_alternate_data_stream_executable_blocks(raw):
    """`cmd.exe:payload` runs what is in the NTFS stream, not the file it hangs off, so
    the program name says nothing about what executes -- and the bare-name comparison
    never matched because the name is not `cmd.exe`. The least reachable of these rules
    (it needs prior filesystem write access AND a literal argv[0]); it is here because it
    is the same shape as the trailing-dot bypass."""
    argv, reason = check_argv(raw)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None
    assert "stream" in reason


def test_the_drive_colon_is_not_mistaken_for_a_stream():
    """The ADS rule looks at the NAME, after _executable_name has resolved the drive. If
    it looked at the raw token instead, every `C:/...` path would read as a stream."""
    argv, reason = check_argv("C:/tools/mytool.exe --check {{agent.output}}")
    assert reason is None, reason
    assert argv is not None and argv[0] == "C:/tools/mytool.exe"


@pytest.mark.parametrize(
    "raw",
    [
        "env node -p {{agent.output}}",
        "env php -r {{agent.output}}",
        "env deno eval {{agent.output}}",
        "env.exe node -p {{agent.output}}",
        "nice node -p {{agent.output}}",
        "timeout 5 node -p {{agent.output}}",
        "xargs node -p {{agent.output}}",
        "sudo node -p {{agent.output}}",
    ],
)
def test_an_indirection_command_blocks(raw):
    """THE STRUCTURAL GAP, and the only finding across five audit rounds that was not
    "another marker we had not listed".

    The marker set is chosen ONCE from argv[0]. With `env node -p {{x}}` the set consulted
    is `env`'s -- universal only -- and node's `-p` never enters the comparison. No number
    of added marker names fixes that: the function was looking at the wrong token to
    decide which set to use.

    The audit recommended re-anchoring the scan on tokens[1] for `env` specifically. This
    refuses the redirector instead, which is the principle already used three times here
    (refuse the .bat shim, refuse the shell, refuse a templated argv[0]) rather than
    chasing what the redirection leads to. Re-anchoring would keep the complexity, still
    leak for every unlisted wrapper, and reopen the false positives that per-program
    markers exist to avoid.
    """
    argv, reason = check_argv(raw, lambda t: "os.system('id')" if "{{" in t else t)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None
    assert "another program" in reason


@pytest.mark.parametrize(
    "raw",
    [
        "node20 -p {{agent.output}}",
        "nodejs -p {{agent.output}}",
        "php8 -r {{agent.output}}",
        "php8.2 -r {{agent.output}}",
        "deno1 eval {{agent.output}}",
    ],
)
def test_a_version_or_packaging_name_still_selects_the_right_markers(raw):
    """Conditioning markers on the program is defeated by the names people actually type.

    Every one of these was accepted before the program key was normalised. Debian's node
    package installs `nodejs`; CI images ship `php8.2`; version managers leave `node20`.
    `python3 -c` was refused throughout and hid the problem, because `-c` is universal --
    it was only the PER-PROGRAM markers that leaked.
    """
    argv, reason = check_argv(raw, lambda t: "os.system('id')" if "{{" in t else t)
    assert argv is None, f"{raw!r} was accepted as {argv}"
    assert reason is not None


def test_a_version_in_the_PATH_was_never_the_problem():
    """Only the NAME is normalised, never the path. An install whose version lives in the
    directory always resolved, because the bare filename is what is compared -- confirmed
    by the audit, and pinned here so a future 'fix' to path handling cannot regress it."""
    argv, reason = check_argv(
        "C:/nvm/v20.11.0/bin/node -p {{agent.output}}", lambda t: "code" if "{{" in t else t
    )
    assert argv is None, f"accepted as {argv}"
    assert reason is not None


def test_over_stripping_a_program_name_cannot_let_something_through():
    """Stripping trailing digits is the SAFE direction: it can only select a marker set for
    a program that is not that program, which refuses MORE. `bzip2` reduces to `bzip`,
    matches no key, and nothing changes -- so an ordinary tool whose name ends in a digit
    is unaffected."""
    argv, reason = check_argv("bzip2 -r {{agent.output}}", lambda t: "data" if "{{" in t else t)
    assert reason is None, reason
    assert argv is not None and argv[0] == "bzip2"


def test_a_resolver_that_raises_returns_a_reason_instead_of_propagating():
    """The docstring promises (None, reason). That was only true because the single
    caller wrapped its resolver in a broad try/except -- the guard itself enforced no such
    contract, so any other use of this public function would crash a verifier."""

    def raiser(_token: str) -> str:
        raise RuntimeError("resolution exploded")

    argv, reason = check_argv("py -m thing {{agent.output}}", raiser)
    assert argv is None
    assert reason is not None
    assert "RuntimeError" in reason


def test_a_resolver_returning_a_non_string_is_coerced():
    """subprocess.run raises TypeError on a None in argv, which would surface as a crash
    rather than a blocked node with a reason."""
    argv, reason = check_argv("py -m thing {{agent.output}}", lambda t: None)
    assert reason is None, reason
    assert argv is not None
    assert all(isinstance(token, str) for token in argv)
