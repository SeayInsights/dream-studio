"""WorkflowRunner — bridges workflow state management with skill invocation.

Reads current workflow state, computes ready nodes per dependency wave,
invokes each node's skill via direct imports of
``core.skills.invocation`` (A3 — replaced the legacy
``subprocess.run([sys.executable, '-m', 'interfaces.cli.ds', 'skill',
'invoke', specifier])`` self-shell-out so each node skips an
interpreter respawn).
"""

from __future__ import annotations

import shlex
import sys
import subprocess
import time
from datetime import datetime, UTC
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.config import paths  # noqa: E402
from control.execution.workflow.validate import parse_workflow  # noqa: E402
from control.execution.workflow.engine import (  # noqa: E402
    _compute_ready_nodes,
    _check_context_budget,
    _file_lock,
    resolve_templates,
)
from control.execution.workflow.state import (  # noqa: E402
    _write_checkpoint,
    SCHEMA_VERSION,
)

# ── Skill specifier resolution ────────────────────────────────────────────────

# Maps bare mode names to their owning pack. Fully-qualified names (containing
# ':') bypass this table entirely. Entries reflect packs.yaml modes as of Slice 9.
_BARE_TO_PACK: dict[str, str] = {
    # ds-core
    "think": "ds-core",
    "plan": "ds-core",
    "build": "ds-core",
    "review": "ds-core",
    "verify": "ds-core",
    "ship": "ds-core",
    "handoff": "ds-core",
    "recap": "ds-core",
    "explain": "ds-core",
    # ds-quality
    "debug": "ds-quality",
    "polish": "ds-quality",
    "harden": "ds-quality",
    "pr-security-scan": "ds-quality",
    "structure-audit": "ds-quality",
    "learn": "ds-quality",
    "coach": "ds-quality",
    "audit": "ds-quality",
    # ds-security
    "dast": "ds-security",
    "binary-scan": "ds-security",
    "mitigate": "ds-security",
    "comply": "ds-security",
    "netcompat": "ds-security",
    # ds-analyze
    "multi": "ds-analyze",
    "domain-re": "ds-analyze",
    "repo": "ds-analyze",
    "intelligence": "ds-analyze",
    # ds-domains
    "game-dev": "ds-domains",
    "saas-build": "ds-domains",
    "mcp-build": "ds-domains",
    "dashboard-dev": "ds-domains",
    "client-work": "ds-domains",
    "design": "ds-domains",
    # ds-project
    "scope": "ds-project",
    "resume": "ds-project",
    # ds-setup
    "wizard": "ds-setup",
    "jit": "ds-setup",
    # ds-workflow
    "workflow": "ds-workflow",
}

# ── Command node routing ──────────────────────────────────────────────────────

# Maps node `type:` field values to ds-core skill modes for command: nodes.
# Nodes with no type: field default to _DEFAULT_COMMAND_MODE.
_NODE_TYPE_TO_MODE: dict[str, str] = {
    "research": "think",
    "analysis": "think",
    "synthesis": "think",
    "report": "build",
    "config": "build",
    "plan": "plan",
}
_DEFAULT_COMMAND_MODE = "build"

# A completion check observes an effect that ALREADY happened -- a git ref, a
# status query, a gate's last line. It must be a cheap read, never the work itself.
_COMPLETION_CHECK_TIMEOUT = 60


def resolve_specifier(skill_raw: str) -> str:
    """Resolve a raw skill field value to a fully-qualified ``pack:mode`` specifier.

    If the value already contains ``:``, return it unchanged.
    Otherwise look it up in the bare-mode table; fall back to ``ds-core:<skill_raw>``.
    """
    if ":" in skill_raw:
        return skill_raw
    pack = _BARE_TO_PACK.get(skill_raw, "ds-core")
    return f"{pack}:{skill_raw}"


def _load_full_yaml_nodes(yaml_path: str) -> dict[str, Any]:
    """Load full YAML content including block scalars via yaml.safe_load.

    Returns a node-id → node dict.  Falls back to {} on any parse error so
    the runner degrades gracefully rather than crashing.
    """
    try:
        import yaml as _yaml

        raw = _yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
        return {
            n["id"]: n for n in (raw or {}).get("nodes", []) if isinstance(n, dict) and "id" in n
        }
    except Exception:
        return {}


# ── WorkflowRunner ────────────────────────────────────────────────────────────


#: Characters that mean something only to a SHELL. A completion_check is argv, not shell:
#: it names an executable and its arguments, and every check in canonical/workflows is
#: `py -m <module> [args]`. A raw check containing one of these cannot be honoured in argv
#: mode, and is BLOCKED rather than reinterpreted -- passing a pipe through as a literal
#: argument would let a check that used to pipe exit 0 for the wrong reason, which is a
#: fail-open in the one mechanism that exists to be unbypassable.
_SHELL_METACHARACTERS = ("|", ";", "&", ">", "<", chr(96), "$", chr(10))

#: Refused for a different reason: `shlex.split(posix=True)` DELETES an unquoted backslash,
#: so `C:\Users\Example\f.txt` became `C:UsersExamplef.txt` and the check ran against a path that was
#: never there -- returning a reason of None, so the corruption was silent and the failure
#: looked like the checked thing being absent. A verifier that quietly checks the wrong
#: thing is the fail-open family, so this blocks and says how to fix it.
_ESCAPE_CHARACTER = chr(92)

#: On Windows, Python hands a .bat/.cmd argv[0] to cmd.exe EVEN WITH shell=False. That
#: reopens cmd's own syntax -- `%VAR%`, `^`, `!` -- none of which is in the blocklist
#: above, which encodes POSIX shell constructs. Refusing the shim is cheaper and more
#: honest than trying to enumerate a second shell's metacharacters.
_SHELL_DELEGATING_SUFFIXES = (".bat", ".cmd")

#: A shell named DIRECTLY, which the suffix test above cannot catch because none of these
#: ends in .bat or .cmd. `cmd /c thing <arg>` re-parses its own arguments into a command
#: string, so an interpolated ARGUMENT -- which this guard otherwise allows, because
#: shell=False makes it inert -- becomes code again. That is the proven injection restored
#: through the front door, so these are refused for the same reason the shims are.
_SHELL_INTERPRETERS = frozenset(
    {
        "cmd",
        "cmd.exe",
        "command.com",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "bash",
        "dash",
        "zsh",
        "ksh",
        "csh",
        "tcsh",
        "fish",
        "wscript",
        "wscript.exe",
        "cscript",
        "cscript.exe",
    }
)


#: Markers whose ARGUMENT is source code on essentially any program that accepts them. A
#: template may not land there: `py -m mod {{x}}` passes an interpolated value as data into
#: sys.argv, but `py -c {{x}}` makes it THE PROGRAM -- and the argv[0] rules cannot see
#: that, because argv[0] is the innocent interpreter. Refusing python/node/perl outright
#: would be overbroad and would reject all nine shipped checks, which are `py -m <module>`.
#: So the rule follows the CODE, not the program.
_UNIVERSAL_CODE_MARKERS = frozenset({"-c", "-e", "--eval", "--exec", "--command"})

#: Markers that mean eval ON THESE PROGRAMS ONLY, keyed by bare program name. Conditioning
#: on the program is the point: `-p` is eval on node and "paginate" on git, `-r` is eval on
#: php and "recursive" on grep. A blanket refusal would reject ordinary checks, which is the
#: failure `test_a_template_in_a_data_position_is_still_allowed` exists to catch.
#:
#: `eval` carries no dash on purpose. Subcommand-shaped eval (`deno eval <code>`) was
#: invisible to the first cut BY CONSTRUCTION, not by a missing name -- the scan only
#: matched dash-prefixed tokens -- so one more flag would not have fixed the shape.
#:
#: Comparison is lowercased, which is why `-R` (php) and `-E` (perl) need no separate entry.
_PROGRAM_CODE_MARKERS: dict[str, frozenset[str]] = {
    "node": frozenset({"-p", "--print"}),
    "bun": frozenset({"-p", "--print"}),
    "deno": frozenset({"eval"}),
    "php": frozenset({"-r"}),
}


#: Names for the same interpreter. Debian's node package installs `nodejs`.
_PROGRAM_ALIASES = {"nodejs": "node"}

#: Commands whose job is to run ANOTHER command. Refused as argv[0], because the marker set
#: is chosen from argv[0]: with `env node -p {{x}}` the set consulted is `env`'s and node's
#: `-p` is never considered. Refusing the redirector is the principle already used for the
#: .bat shim and the shell, and it is preferred over re-anchoring the scan on a later token
#: -- that would keep the complexity, still leak for every unlisted wrapper, and reopen the
#: false positives that per-program markers exist to avoid (a token that merely SAYS
#: `node`). A completion_check is a cheap read that names its program; it has no reason to
#: run one program in order to run another. Missing an entry here costs only the
#: per-program markers, since the universal set is checked regardless of program identity.
_INDIRECTION_COMMANDS = frozenset(
    {
        "env",
        "nice",
        "ionice",
        "timeout",
        "nohup",
        "setsid",
        "stdbuf",
        "unshare",
        "chroot",
        "xargs",
        "sudo",
        "doas",
        "su",
        "runuser",
        "start",
        "time",
        # Probed after the first cut of this list and found leaking. All LIST-class: the
        # mechanism is right and the failure is bounded (only the per-program markers are
        # lost), so these were added in the same pass rather than by opening another
        # review round. `/usr/bin/env` and `timeout.exe` already resolved -- the name is
        # compared after path and `.exe` are stripped.
        "command",
        "exec",
        "busybox",
        "winpty",
        "docker",
        "podman",
        "ssh",
        "wsl",
        "watch",
        "flock",
        "parallel",
        "strace",
        "ltrace",
        "valgrind",
        "script",
    }
)


def _program_key(program: str) -> str:
    """The marker-set key for an executable name, with version and packaging noise removed.

    WITHOUT THIS THE PER-PROGRAM CONDITIONING IS TRIVIALLY BYPASSED by the names people
    actually type: `node20 -p`, `nodejs -p`, `php8 -r` and `php8.2 -r` were all accepted,
    because none of those strings is a key. Only the UNIVERSAL markers held, which is why
    `python3 -c` looked fine and hid the problem.

    Trailing digits and dots are stripped, and OVER-stripping is the safe direction: it can
    only select a marker set for something that is not that program, which refuses MORE.
    Under-stripping leaks. `bzip2` reduces to `bzip`, matches no key, and nothing changes.

    Only the NAME is normalised, never the path -- an install whose version lives in the
    directory (`.../v20.11.0/bin/node`) always resolved correctly, since the bare filename
    is what is compared.
    """
    key = program.removesuffix(".exe").rstrip("0123456789.")
    return _PROGRAM_ALIASES.get(key, key)


def _code_markers_for(program: str) -> frozenset[str]:
    """Every marker that means "the next argument is code" for this program."""
    return _UNIVERSAL_CODE_MARKERS | _PROGRAM_CODE_MARKERS.get(_program_key(program), frozenset())


def _templated_code_argument(tokens: list[str], program: str) -> str | None:
    """The code-executing marker whose argument is templated, if any.

    NOT an equality test for flags, because the value may be ATTACHED: `py -cprint(42)`
    runs, so `-c{{x}}` is ONE token and matching a token equal to `-c` misses it entirely.
    That was the hole in both the first cut of this rule and an independent audit's
    recommendation for it, found by calling the function rather than reading it.

    Prefix matching is safe for the short flags: `"--check".startswith("-c")` is False,
    its second character being another dash, so `--check {{x}}` and `--config {{x}}` stay
    allowed. It is NOT applied to word markers like `eval`, which must match exactly --
    `evaluate-thing {{x}}` is not deno's eval subcommand.
    """
    markers = _code_markers_for(program)
    short = tuple(m for m in markers if len(m) == 2 and m.startswith("-"))
    assigned = tuple(m + "=" for m in markers if m.startswith("--"))
    for index, token in enumerate(tokens):
        low = token.lower()
        if "{{" in token and (low.startswith(short) or low.startswith(assigned)):
            return low.split("{{", 1)[0] or token
        if low in markers:
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            if "{{" in following:
                return token
    return None


def _executable_name(token: str) -> str:
    """The bare program name of an argv[0], normalised for comparison.

    TRAILING DOTS AND SPACES ARE STRIPPED because Windows' path layer strips them from a
    path component, so `tool.bat.` and `tool.bat ` both resolve to `tool.bat` -- and both
    slipped past a plain suffix test.
    """
    # PureWINDOWSPath, not PurePosix. `C:cmd.exe` is drive-relative Windows syntax with no
    # separator at all, so the POSIX flavour returned the whole string as the name and it
    # matched nothing -- an outright bypass of the shell refusal below. The Windows flavour
    # models the drive and returns `cmd.exe`, and still handles `C:/x/cmd.exe`,
    # `//host/share/cmd.exe` and a bare name identically.
    name = PureWindowsPath(token).name.lower()
    return name.rstrip(". ")


def check_argv(
    raw_check: str,
    resolver: Callable[[str], str] | None = None,
) -> tuple[list[str] | None, str | None]:
    """Turn a raw ``completion_check`` into argv, or say why it cannot be run.

    Returns ``(argv, None)`` when runnable, ``(None, reason)`` when not.

    THE DEFECT THIS EXISTS FOR, proven 2026-09-08 by driving the real
    ``_verify_completion`` with a crafted state. ``completion_check`` was resolved through
    ``resolve_templates`` and then run with ``subprocess.run(check, shell=True)``.
    ``engine._resolve_ref`` returns ``str(node.get(field, ""))`` for any
    ``{{node_id.output}}`` reference -- arbitrary text a command node captured, or an LLM's
    stdout -- so a node's OUTPUT became shell CODE. A node output of
    ``x <and> echo pwned > <path>`` wrote the file.

    Worse than the RCE reading: the injected command's exit status BECAME THE NODE'S
    EVIDENCE, and the node reported ``completed``. The checked party could author its own
    PASS by ending its output with a command that always succeeds. That is the
    assert-instead-of-verify defect, forgeable by the very thing being verified.

    SPLIT FIRST, RESOLVE PER TOKEN. That ordering is the load-bearing half. Resolving the
    whole string and splitting afterwards would let one interpolated value expand into
    several argv elements -- so ``--force`` could be smuggled into an authority command
    even with the shell gone. Resolving inside each token means an interpolated value is
    structurally incapable of becoming more than one argument, whatever it contains.

    The metacharacter test reads the RAW check, deliberately. After resolution a
    metacharacter is DATA: it arrived in an interpolated value and becomes one literal
    argv element, which is exactly the containment this function provides. Only the author
    of the YAML can be asking for a shell.

    WHAT IS REFUSED, and why each one rather than a blanket "looks dangerous":

    * a separator or substitution in the RAW check (``| ; & > <`` backtick ``$`` newline)
      -- honouring it would need a shell, and passing it through as a literal argument
      would let a check that used to pipe exit 0 for the wrong reason. Parentheses are NOT
      refused: they are neither, so refusing them bought nothing and rejected every Python
      ``-c`` one-liner and every regex argument. ``$(...)`` is still refused, by ``$``.
    * a backslash -- ``shlex`` deletes it, so the check would run against a corrupted path
      and report the effect absent for the wrong reason.
    * a TEMPLATED argv[0] -- shell=False stops an interpolated value becoming code, and
      does nothing about a value that IS the program.
    * a ``.bat``/``.cmd`` argv[0] -- Windows hands those to cmd.exe even with shell=False.
    * a TEMPLATE IN A CODE-EXECUTING MARKER'S ARGUMENT, attached or separate --
      ``py -m mod {{x}}`` passes an interpolated value as data, but ``py -c {{x}}`` makes it
      the program, and the argv[0] rules cannot see that because argv[0] is the innocent
      interpreter. The rule follows the code rather than the program, so the nine shipped
      ``py -m <module>`` checks are untouched while an interpreter cannot be turned into an
      eval. Markers are PER-PROGRAM on top of a universal set, because ``-p`` is eval on
      node and "paginate" on git, and ``-r`` is eval on php and "recursive" on grep -- a
      blanket refusal would reject ordinary checks.
    * an NTFS ALTERNATE DATA STREAM as argv[0] (``cmd.exe:payload``) -- what runs is the
      stream, so the program name says nothing about it.
    * an argv[0] that normalises to NOTHING (``...``) -- it named no program.
    * a SHELL as argv[0] (``cmd``, ``powershell``, ``sh``, ``bash``, ``wscript``, ...) --
      it re-parses its own arguments as a command string, so an interpolated ARGUMENT,
      which this guard otherwise allows because shell=False makes it inert, would become
      code again. argv[0] is compared by bare program name with trailing dots and spaces
      stripped, because Windows strips those from a path component and `tool.bat.` and
      `tool.bat ` both resolve to the batch file.

    RESIDUAL RISK, stated rather than implied, because two of these enumerations cannot be
    complete:

    * the metacharacter set encodes POSIX shell constructs. cmd.exe's own (``%VAR%``,
      ``^``, ``!``) are not in it, and are inert only because no shell parses the argv --
      which the argv[0] rules are what keep true.
    * the code-eval markers are a LIST, and a list of this kind is never finished. Four
      independent audit rounds each added to it (``-c``/``-e`` first, then node's
      ``-p``/``--print``, php's ``-r``, deno's subcommand ``eval``). An interpreter whose
      eval spelling is not listed will not be caught.
    * a WRAPPER still defeats the per-program markers. Known indirection commands (``env``,
      ``nice``, ``timeout``, ``xargs``, ``sudo``, ...) are refused outright as argv[0], and
      `_program_key` normalises version and packaging noise (``node20``, ``nodejs``,
      ``php8.2`` all resolve), but an executable that execs an interpreter INTERNALLY -- a
      shim, a symlink, a ``check.exe`` that runs node -- selects its own marker set. No
      inspection of argv[0] can see through that: a limit of naming, not an oversight. The
      failure is BOUNDED, because the universal markers are checked regardless of which
      program is named. Known-unlisted at the close of review: ``flatpak run``, macOS
      ``open -a``, and hyphenated packaging variants (``env-v2`` reduces to ``env-v``,
      since only trailing digits and dots are stripped). None corresponds to a binary
      found in the wild, unlike ``nodejs``/``php8.2``/``node20``, which did and are fixed.
    * NORMALISING BEFORE THE INDIRECTION LOOKUP has a side effect worth knowing: several
      entries are short ordinary words (``su``, ``time``, ``start``, ``exec``, ``watch``),
      so a real tool named ``su2`` or ``time2`` would be refused outright. A search for a
      live collision found none -- and ``environ`` does NOT collide with ``env``, since
      the comparison is exact-match-after-stripping rather than prefix -- but the
      direction of this failure is what makes it acceptable: it wrongly BLOCKS a check,
      never wrongly executes one.

    WHAT THIS GUARD IS, which is why an incomplete list is still the right shape: the check
    string is authored by a trusted operator in canonical YAML, and the TEMPLATE VALUE is
    not trusted -- it is a node's output or an LLM's stdout. This is a footgun guard
    against an author accidentally making an untrusted value executable, not a sandbox
    against a hostile author. A hostile author has the whole check.
    """
    raw = (raw_check or "").strip()
    if not raw:
        return None, "empty check"
    for char in _SHELL_METACHARACTERS:
        if char in raw:
            shown = "a newline" if char == chr(10) else repr(char)
            return None, (
                f"completion_check contains the shell metacharacter {shown}, and a check"
                " is argv rather than shell -- it names an executable and its arguments,"
                " and is run with shell=False so that a node's output can never become"
                " code. Rewrite it as a single command, or move the logic into a module"
                " the check can invoke."
            )
    if _ESCAPE_CHARACTER in raw:
        return None, (
            "completion_check contains a backslash, which is consumed as an escape when"
            " the check is split into arguments -- an unquoted Windows path would silently"
            " lose its separators and the check would run against a path that does not"
            " exist, reporting the effect as absent for the wrong reason. Use forward"
            " slashes, which work on every platform, or quote the argument."
        )
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError as exc:
        return None, f"completion_check could not be split into arguments ({exc}): {raw}"
    if not tokens:
        return None, "empty check"
    if "{{" in tokens[0]:
        return None, (
            "completion_check names its executable with a template. The author of the"
            " check must name the program: running with shell=False stops an interpolated"
            " value from becoming code or an extra argument, but it does nothing about a"
            " value that IS the program. Put the template in an argument instead."
        )
    executable = _executable_name(tokens[0])
    if ":" in executable:
        # An NTFS ALTERNATE DATA STREAM. `cmd.exe:payload` executes what is stored in the
        # named stream, and the bare-name comparison below never matches because the name
        # is not `cmd.exe`. Position 1 is the drive colon (`C:tool`), which
        # _executable_name has already resolved; a colon anywhere in the resulting NAME is
        # a stream. Exploiting it needs prior filesystem write access AND a literal
        # argv[0], so this is the least reachable of these rules -- it is here because it
        # is the same shape as the trailing-dot bypass, and consistency is cheaper than
        # remembering the exception.
        return None, (
            f"completion_check names an NTFS alternate data stream ({tokens[0]!r}), which"
            " executes what is stored in the stream rather than the file it is attached"
            " to -- so the program name says nothing about what runs. Name the executable"
            " directly."
        )
    if not executable:
        return None, (
            f"completion_check names no program: {tokens[0]!r} normalises to nothing once"
            " its path and trailing dots and spaces are removed. This already failed, but"
            " on a missing-file error rather than on the check being malformed."
        )
    if executable.endswith(_SHELL_DELEGATING_SUFFIXES):
        return None, (
            f"completion_check runs {tokens[0]!r}, and Windows hands a .bat/.cmd to"
            " cmd.exe even with shell=False -- which would let cmd's own syntax (%VAR%,"
            " ^, !) be reinterpreted in an interpolated value. Invoke the underlying"
            " program directly."
        )
    if _program_key(executable) in _INDIRECTION_COMMANDS:
        return None, (
            f"completion_check runs {tokens[0]!r}, whose job is to run another program --"
            " so the program this check names is not the program that executes, and the"
            " code-eval markers for the real one are never consulted (`env node -p"
            " <template>` was accepted for exactly this reason). Name the program"
            " directly; a check is a cheap read and has no reason to run one program in"
            " order to run another."
        )
    if executable in _SHELL_INTERPRETERS:
        return None, (
            f"completion_check runs {tokens[0]!r}, which is a shell: it re-parses its own"
            " arguments as a command string, so an interpolated value would become code"
            " again -- the exact injection running with shell=False closes. Invoke the"
            " program directly, or move the logic into a module the check can call."
        )
    code_flag = _templated_code_argument(tokens, executable)
    if code_flag is not None:
        return None, (
            f"completion_check interpolates a template into the argument of {code_flag!r},"
            f" which is source code to {executable!r} -- so a node's output would be the"
            " program rather than data. Running with shell=False makes an interpolated"
            " ARGUMENT inert; it does nothing when that argument is what gets executed."
            " Pass the value as a plain positional argument to something that reads it as"
            " data, which is the shape every shipped check already uses."
        )
    if resolver is not None:
        resolved: list[str] = []
        for token in tokens:
            try:
                resolved.append(str(resolver(token)))
            except Exception as exc:  # noqa: BLE001 - a verifier reports, never crashes
                return None, (
                    f"completion_check could not resolve {token!r}"
                    f" ({type(exc).__name__}: {exc}). A verifier reports a reason rather"
                    " than raising, so the node blocks and names this."
                )
        tokens = resolved
    return tokens, None


class WorkflowRunner:
    """Execute a workflow by iterating dependency waves until completion or failure.

    Args:
        wf_key: Workflow key (from ``workflow_state start`` output).
        dry_run: If True, log what would be invoked but never call any skill.
    """

    def __init__(self, wf_key: str, dry_run: bool = False) -> None:
        self.wf_key = wf_key
        self.dry_run = dry_run
        # Why the last run() stopped, when it stopped at "blocked". Always present, so a
        # caller never has to guess whether the attribute exists before reading it.
        self.blocked_on: str = ""

    # ── Public API ────────────────────────────────────────────────────────

    def run(self) -> str:
        """Execute the workflow to completion (or until blocked/aborted).

        Returns the final workflow status string.
        """
        while True:
            state = self._load_state()
            wf = state.get("active_workflows", {}).get(self.wf_key)
            if wf is None:
                raise KeyError(f"Workflow '{self.wf_key}' not found in state")

            wf_status = wf.get("status", "running")
            if wf_status in ("completed", "completed_with_failures", "aborted", "paused"):
                return wf_status

            yaml_path = wf.get("yaml_path", "")
            if not yaml_path or not Path(yaml_path).is_file():
                print(f"[runner] ERROR: YAML not found at {yaml_path!r}", file=sys.stderr)
                return "aborted"

            yaml_data = parse_workflow(yaml_path)
            yaml_nodes: dict[str, Any] = {
                n["id"]: n for n in yaml_data.get("nodes", []) if "id" in n
            }
            full_yaml_nodes: dict[str, Any] = _load_full_yaml_nodes(yaml_path)
            state_nodes: dict[str, Any] = wf.get("nodes", {})

            ready, skipped = _compute_ready_nodes(yaml_nodes, state_nodes, wf)

            if skipped:
                self._mark_skipped(skipped, reason="condition false")
                state = self._load_state()
                wf = state.get("active_workflows", {}).get(self.wf_key, {})
                state_nodes = wf.get("nodes", {})

            if not ready:
                running = [nid for nid, n in state_nodes.items() if n.get("status") == "running"]
                if running:
                    # Agents still in flight; caller should poll or wait
                    return "running"
                # Nothing ready and nothing running — blocked or done
                all_statuses = {n.get("status") for n in state_nodes.values()}
                if all_statuses <= {"completed", "skipped"}:
                    return "completed"
                # A run that reached the end without observing some of its nodes did not
                # complete -- it finished. Reporting "completed" here would restore the
                # exact claim this work order exists to stop, one level up from the node.
                if all_statuses <= {"completed", "skipped", "unverified"}:
                    self.blocked_on = self._describe_unverified(state_nodes)
                    return "completed_with_unverified"
                if all_statuses <= {"completed", "skipped", "failed", "unverified"}:
                    return "completed_with_failures"
                self.blocked_on = self._describe_blockage(state_nodes)
                return "blocked"

            # Context budget guard for parallel waves
            if len(ready) > 1 and not self.dry_run:
                budget = _check_context_budget(len(ready))
                if budget == "block":
                    self._mark_skipped(
                        ready, reason="context budget too high for parallel dispatch"
                    )
                    continue

            wave_failed = self._execute_wave(ready, yaml_nodes, yaml_data, full_yaml_nodes)
            if wave_failed:
                # Propagate — state already updated; loop will detect blocked state
                continue

        # unreachable; loop exits via return statements above

    def advance(self) -> list[str]:
        """Execute one wave of ready nodes and return their node IDs.

        Unlike ``run()``, does not loop — useful for step-by-step execution.
        Returns empty list if blocked or finished.
        """
        state = self._load_state()
        wf = state.get("active_workflows", {}).get(self.wf_key)
        if wf is None:
            return []

        if wf.get("status") in ("completed", "completed_with_failures", "aborted", "paused"):
            return []

        yaml_path = wf.get("yaml_path", "")
        if not yaml_path or not Path(yaml_path).is_file():
            return []

        yaml_data = parse_workflow(yaml_path)
        yaml_nodes: dict[str, Any] = {n["id"]: n for n in yaml_data.get("nodes", []) if "id" in n}
        full_yaml_nodes: dict[str, Any] = _load_full_yaml_nodes(yaml_path)
        state_nodes: dict[str, Any] = wf.get("nodes", {})

        ready, skipped = _compute_ready_nodes(yaml_nodes, state_nodes, wf)
        if skipped:
            self._mark_skipped(skipped, reason="condition false")
        if not ready:
            return []

        self._execute_wave(ready, yaml_nodes, yaml_data, full_yaml_nodes)
        return ready

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_state(self) -> dict:
        p = paths.state_dir() / "workflows.json"
        if not p.is_file():
            return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
        try:
            import json

            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}

    def _execute_wave(
        self,
        node_ids: list[str],
        yaml_nodes: dict[str, Any],
        yaml_data: dict,
        full_yaml_nodes: dict[str, Any] | None = None,
    ) -> bool:
        """Execute all nodes in ``node_ids`` sequentially (parallel in a future wave).

        Returns True if any node failed.
        """

        wf_state = self._load_state()
        wf = wf_state.get("active_workflows", {}).get(self.wf_key, {})
        session_dir = wf.get("session_dir")

        any_failed = False
        for node_id in node_ids:
            ynode = yaml_nodes[node_id]
            skill_raw = ynode.get("skill", "")

            # Template resolution (e.g. {{params.audit}})
            skill_raw = resolve_templates(skill_raw, wf, session_dir)

            is_command_node = False
            if not skill_raw:
                # No skill: field — check for command: field (LLM instruction prompt)
                has_command = bool(ynode.get("command"))
                if not has_command:
                    print(
                        f"[runner] Node {node_id}: no skill or command defined — skipping",
                        flush=True,
                    )
                    self._update_node(node_id, "skipped", "no skill or command defined")
                    self._emit_node_event(node_id, "skipped")
                    continue

                # Route command: node through the appropriate core skill mode
                node_type = str(ynode.get("type", "") or "")
                mode = _NODE_TYPE_TO_MODE.get(node_type, _DEFAULT_COMMAND_MODE)
                specifier = resolve_specifier(mode)
                is_command_node = True

                # Resolve actual command content from full YAML (block scalar)
                full_ynode = (full_yaml_nodes or {}).get(node_id, {})
                raw_command = full_ynode.get("command", "") or ""
                if raw_command and not isinstance(raw_command, bool):
                    resolved_command = resolve_templates(raw_command, wf, session_dir)
                else:
                    resolved_command = (
                        f"# Workflow node: {node_id}\n# (command content unavailable)\n"
                    )
                context_path = self._write_command_context(
                    node_id, resolved_command, node_type, yaml_data
                )
                print(
                    f"[runner] Node {node_id}: executing command via {specifier}"
                    f" — prompt at {context_path}",
                    flush=True,
                )
            else:
                specifier = resolve_specifier(skill_raw)
                print(f"[runner] Node {node_id}: invoking {specifier}", flush=True)

            self._update_node(node_id, "running", None)

            t0 = time.monotonic()
            success, output = self._invoke_skill(specifier, node_id)
            duration = round(time.monotonic() - t0, 2)

            # THE COMPLETION DECISION DOES NOT LOOK AT THIS TEXT AT ALL, which is why
            # the synthetic summary is harmless here. A previous cut threaded the real
            # output into _verify_completion to stop it checking this receipt; a later
            # review pointed out the method had by then stopped reading the parameter
            # entirely, so the thread was ceremony. The only evidence available to this
            # runner is a completion_check subprocess observing state from outside.
            if is_command_node and success:
                output = f"{node_id} executed via {specifier}"

            if not success:
                status, reason = "failed", None
            else:
                # Read the FULL yaml node, not the parsed summary: completion_check
                # is a block scalar and lives only in the full node. Resolved here
                # rather than reusing `full_ynode`, which is assigned only inside the
                # command-node branch -- referencing it for a skill node raised
                # UnboundLocalError and broke four existing tests.
                _node_yaml = (full_yaml_nodes or {}).get(node_id) or ynode
                status, reason = self._verify_completion(node_id, _node_yaml)
            if reason:
                output = f"{output}\n\n[completion] {status.upper()}: {reason}"
            self._update_node(node_id, status, output, duration=duration)
            self._emit_node_event(node_id, status)
            self._emit_progress_event(wf_state)

            if not success:
                any_failed = True
                print(f"[runner] Node {node_id} FAILED (duration={duration}s)", flush=True)

        return any_failed

    def _invoke_skill(self, specifier: str, node_id: str) -> tuple[bool, str]:
        """Invoke a skill via direct imports of ``core.skills.invocation``.

        Returns ``(success, output)`` where ``output`` is the same
        operator-style text the legacy subprocess CLI handler produced
        (SKILL.md content + footer with specifier/mode/target). Truncated
        to 2000 chars to match the pre-A3 contract.

        dry_run always returns (True, "[dry_run]") without loading the
        skill or emitting any spool event.
        """

        if self.dry_run:
            print(
                f"[runner] [dry_run] would invoke: {specifier} (node={node_id})",
                flush=True,
            )
            return True, "[dry_run]"

        try:
            from core.skills.invocation import load_skill_content, record_skill_invocation

            source_root = Path(__file__).resolve().parents[3]

            load_result = load_skill_content(specifier=specifier, source_root=source_root)
            if not load_result.get("ok"):
                return False, str(load_result.get("error", "skill load failed"))[:2000]

            # Best-effort spool emission of ``skill.invoked``. Failure
            # inside record_skill_invocation is already swallowed there,
            # but wrap defensively so any import-time exception (e.g.
            # spool root unreachable) doesn't break the node.
            try:
                record_skill_invocation(
                    specifier=specifier,
                    target=None,
                    work_order_id=None,
                    project_id=None,
                    source_root=source_root,
                )
            except Exception:
                pass

            # Reproduce the legacy CLI handler's stdout block so workflow
            # state captures the same operator-facing text.
            footer_lines = [
                "---",
                f"Skill: {specifier}",
                "Mode: direct",
                "Target: not specified",
                "Work order: none",
                "Invocation recorded.",
                "",
                (
                    "The AI reading this output has the skill instructions above "
                    "and should now execute them."
                ),
            ]
            output = (
                load_result["skill_content"].rstrip() + "\n" + "\n".join(footer_lines)
            ).strip()
            return True, output[:2000]
        except Exception as exc:
            return False, str(exc)[:500]

    # WO-NODE-COMPLETION-EVIDENCE: a node is complete when its effect is OBSERVABLE.
    #
    # Operator: "I'm tired of having to update you to move on ... register everything that
    # is needed and an orchestrator continues on making sure everything moves along
    # correctly."
    #
    # The orchestrator already exists -- execute-work-orders.yaml has 14 nodes covering the
    # whole loop, and this runner computes ready nodes from real dependency logic. What was
    # missing is not a driver. It is that completion was UNVERIFIED: _invoke_skill loads a
    # node's text, returns it with the footer "The AI reading this output has the skill
    # instructions above and should now execute them", and the wave then marked the node
    # "completed" on a successful LOAD. All 14 nodes are prose-for-an-agent; none is
    # executable as written.
    #
    # So a driver over this would march through fourteen nodes printing prompts and
    # declaring success with no work done -- the assert-instead-of-verify defect at the
    # orchestration layer, where it is hardest to notice. That is why the driver is
    # sequenced AFTER this.
    #
    # A node may declare `completion_check`: a shell command whose exit status is the
    # evidence. Optionally `completion_contains` requires text in its output, for the case
    # where a command succeeds but says the wrong thing (a gate that prints
    # "Overall: FAIL" and exits 0).

    def _describe_unverified(self, state_nodes: dict) -> str:
        """Which nodes finished without anyone observing their effect."""
        lines = [
            f"  {nid}: no completion_check, so nothing confirmed this node's effect"
            for nid, node in state_nodes.items()
            if node.get("status") == "unverified"
        ]
        return chr(10).join(lines)

    def _describe_blockage(self, state_nodes: dict) -> str:
        """Why the run stopped, in terms an operator can act on.

        `run()` returned the bare string "blocked" and `ds workflow run` printed
        "[workflow] final status: blocked". That is a status, not direction -- it names
        no node, no reason, and nothing to do, so the loop hands back exactly the
        question the operator started with. A driver that stops without saying what it
        is waiting on has not removed the human from the loop; it has moved them to a
        worse position, because now they must reconstruct the state themselves.
        """
        lines: list[str] = []
        for nid, node in state_nodes.items():
            status = node.get("status")
            if status in ("completed", "skipped", "pending"):
                continue
            reason = (node.get("blocked_reason") or "").strip()
            if not reason:
                out = (node.get("output") or "").strip()
                marker = "[completion] "
                if marker in out:
                    reason = out.split(marker, 1)[1].splitlines()[0]
            lines.append(f"  {nid}: {status}" + (f" — {reason}" if reason else ""))
        if not lines:
            return "no node reports a blocking status; check for a dependency cycle"
        return chr(10).join(lines)

    def _verify_completion(self, node_id: str, ynode: dict) -> tuple[str, str | None]:
        """Return ``(status, reason)`` for a node whose prompt was delivered.

        Two kinds of evidence, because the nodes come in two kinds.

        ``completion_contains`` ALONE checks the node's OWN output. Every node in
        execute-work-orders ends by telling the agent to print a specific token --
        "Print: GATES: PASS", "Print: BRANCH: <name>", "Print: REVIEW_PASS" -- so the
        token is already the declared observable, and the agent either produced it or did
        not. Requiring a subprocess to confirm that would mean inventing an external
        effect for a node whose effect is a report.

        ``completion_check`` runs a shell command whose exit status is the evidence, for
        nodes with an effect worth confirming independently of what the agent claims --
        a branch that exists, a work order the authority says is closed.
        ``completion_contains`` then applies to THAT command's output.

        * neither declared -> ``("unverified", why)``. NOT "completed": a node whose
          effect nobody looked at has not been shown to have happened, and reporting it as
          done is the exact claim this work order exists to stop.
        * evidence holds -> ``("completed", None)``
        * evidence absent -> ``("blocked", what was expected and what was seen)``

        BLOCKED IS NOT FAILED. Failed means the work was attempted and went wrong; blocked
        means the effect is not there yet, which for a prose node usually means the agent
        has not done it. A driver must stop at blocked without recording a failure.
        """
        # DRY RUN SIMULATES; it does not execute. Nothing ran, so no completion condition
        # can hold, and verifying one would make every dry run report blocked -- turning a
        # planning tool into a wall. The simulation keeps its old meaning: this node WOULD
        # complete.
        if self.dry_run:
            return "completed", None

        check = (ynode.get("completion_check") or "").strip()
        expected_raw = (ynode.get("completion_contains") or "").strip()

        # A check that cannot name the thing it is checking can only assert generalities.
        # `{{node.output}}` and `{{node.field}}` resolve here exactly as they do in a
        # node's prompt -- without this, "does the PR exist" could not reference the PR
        # number the previous node printed, and every check would have to be repo-global.
        #
        # A RESOLVER, NOT A RESOLVED STRING. `check_argv` splits the raw check into tokens
        # and calls this on each one, so an interpolated value can never become more than
        # a single argv element. Resolving the whole string here (what this did until WO
        # 26675b56) put agent-authored text into a `shell=True` command line.
        def _resolve(text: str) -> str:
            if "{{" not in text:
                return text
            try:
                from control.execution.workflow.engine import resolve_templates

                wf = (self._load_state().get("active_workflows", {}) or {}).get(self.wf_key, {})
                return resolve_templates(text, wf)
            except Exception:
                # An unresolvable template leaves the literal in place; the check then
                # fails and the node blocks with the reason, which is the right outcome.
                return text

        # completion_contains is NOT given the per-token treatment, and that asymmetry is
        # deliberate. It is compared with `in` against the check's output and never
        # executed, so there is no injection to contain -- and it is a SUBSTRING, which
        # may legitimately hold spaces that tokenising would destroy. The task for this
        # fix asked for symmetry; reading the use showed symmetry would be the bug.
        expected_raw = _resolve(expected_raw).strip()
        if not check:
            # WHY completion_contains ALONE IS NOT ENOUGH, corrected after an independent
            # review. I had it check "the node's own output", reasoning that each node
            # ends by telling the agent to print a token. The runner has no such output:
            # _invoke_skill LOADS a skill and returns its SKILL.md text plus a footer, and
            # the agent that would produce a report reads that text out of band. There is
            # no execution result here to inspect. Checking the loaded prompt instead would
            # be worse than useless -- every token appears in its own prompt by
            # construction, so every node would "complete" by reading its own instructions.
            hint = (
                " (completion_contains alone cannot be checked here: this runner delivers a"
                " prompt and never sees what the agent then does. Pair it with a"
                " completion_check that observes the effect -- a git ref, an authority"
                " query -- or leave the node honestly unverified.)"
                if expected_raw
                else ""
            )
            return (
                "unverified",
                "no completion_check declared, so the effect of this node was never "
                "observed -- its prompt was delivered and nothing confirms the work" + hint,
            )

        argv, argv_reason = check_argv(check, _resolve)
        if argv is None:
            return "blocked", str(argv_reason)

        try:
            proc = subprocess.run(  # noqa: S603 - argv, shell=False; see check_argv
                argv,
                cwd=str(Path(__file__).resolve().parents[3]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_COMPLETION_CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                "blocked",
                f"completion_check timed out after {_COMPLETION_CHECK_TIMEOUT}s: {check}",
            )
        except OSError as exc:
            return "blocked", f"completion_check could not run ({type(exc).__name__}): {check}"

        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            tail = out.splitlines()[-1][:160] if out else "(no output)"
            return (
                "blocked",
                f"completion_check exited {proc.returncode}: {check}" f" (ran: {argv}) -> {tail}",
            )

        expected = expected_raw
        if expected and expected not in out:
            return (
                "blocked",
                f"completion_check succeeded but its output does not contain "
                f"{expected!r}: {check}",
            )
        return "completed", None

    def _update_node(
        self,
        node_id: str,
        status: str,
        output: str | None,
        duration: float | None = None,
    ) -> None:
        """Atomically update a node's status in workflows.json."""
        import json

        now = datetime.now(UTC).isoformat()
        lock_path = paths.state_dir() / "workflows.json.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with _file_lock(lock_path):
            p = paths.state_dir() / "workflows.json"
            if not p.is_file():
                return
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return

            wf = data.get("active_workflows", {}).get(self.wf_key)
            if wf is None:
                return

            node = wf.setdefault("nodes", {}).setdefault(node_id, {})
            node["status"] = status

            if status == "running" and "started" not in node:
                node["started"] = now
            if status in ("completed", "failed", "skipped"):
                node["finished"] = now
            if status == "completed":
                completed = wf.setdefault("completed_nodes", [])
                if node_id not in completed:
                    completed.append(node_id)
            if output is not None:
                node["output"] = output
            if duration is not None:
                node["duration_s"] = duration

            wf["current_node"] = node_id

            # Update workflow-level status
            statuses = [n.get("status") for n in wf.get("nodes", {}).values()]
            if all(s in ("completed", "skipped") for s in statuses):
                wf["status"] = "completed"
            elif all(s in ("completed", "skipped", "failed") for s in statuses):
                wf["status"] = "completed_with_failures"

            p.write_text(json.dumps(data, indent=2), encoding="utf-8")

        _write_checkpoint(self.wf_key, node_id, status)

    def _mark_skipped(self, node_ids: list[str], reason: str) -> None:
        for nid in node_ids:
            self._update_node(nid, "skipped", f"SKIPPED: {reason}")

    def _emit_node_event(self, node_id: str, status: str) -> None:
        """Emit a workflow.node.completed event to the spool."""
        try:
            from spool.writer import write_event
            from canonical.events.types import EventType

            write_event(
                {
                    "event_type": EventType.WORKFLOW_NODE_COMPLETED.value,
                    "workflow_key": self.wf_key,
                    "node_id": node_id,
                    "status": status,
                    "dry_run": self.dry_run,
                }
            )
        except Exception:
            pass

    def _write_command_context(
        self,
        node_id: str,
        command: str,
        node_type: str,
        yaml_data: dict,
    ) -> Path:
        """Write command: node prompt to .planning/workflow/<wf_key>/<node_id>-prompt.md.

        The file gives Claude the node-specific instructions.  The skill
        invocation (ds-core:build / think / plan) provides the execution
        framework; this file provides the task payload.
        """
        try:
            base = paths.plugin_root()
        except (RuntimeError, Exception):
            base = Path(__file__).resolve().parents[3]
        context_dir = base / ".planning" / "workflow" / self.wf_key
        context_dir.mkdir(parents=True, exist_ok=True)
        wf_name = str(yaml_data.get("name", "") or "unknown")
        context_file = context_dir / f"{node_id}-prompt.md"
        content = (
            f"# Workflow Node: {node_id}\n"
            f"# Workflow: {wf_name}\n"
            f"# Node type: {node_type or 'unspecified'}\n\n"
            f"{command}"
        )
        context_file.write_text(content, encoding="utf-8")
        return context_file

    def _emit_progress_event(self, state: dict) -> None:
        """Emit a workflow.progress.updated event after each node completes."""
        try:
            from spool.writer import write_event
            from canonical.events.types import EventType

            wf = state.get("active_workflows", {}).get(self.wf_key, {})
            nodes = wf.get("nodes", {})
            done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
            total = len(nodes)

            write_event(
                {
                    "event_type": EventType.WORKFLOW_PROGRESS_UPDATED.value,
                    "workflow_key": self.wf_key,
                    "workflow_name": wf.get("workflow", ""),
                    "done": done,
                    "total": total,
                    "dry_run": self.dry_run,
                }
            )
        except Exception:
            pass
