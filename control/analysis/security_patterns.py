"""Security pattern scanning library for on-security-scan hook.

Extracts security anti-pattern detection logic from hook to comply with
constitutional requirement that hooks be <50 lines.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from core.gates.credential_patterns import CREDENTIAL_PATTERNS, TOKEN_SHAPED_PATTERN

# Name-based assignment + code-smell heuristics stay local (they are not credential
# FORMATS). The PEM and token-shape checks come from the single source
# (core/gates/credential_patterns.py) so credential detection cannot drift — WO d84efdc4.
PATTERNS = [
    (
        re.compile(
            r'(?i)(password|passwd|api_key|api_secret|secret_key|auth_token)\s*=\s*["\'][^"\']{4,}["\']'
        ),
        "hardcoded credential",
    ),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bos\.system\s*\("), "os.system()"),
    # `shell=True` is NOT here any more. It was `subprocess[^\n]+shell\s*=\s*True`, and
    # that newline-free class is the whole defect: black formats a multi-argument call
    # across lines, so the token and the keyword never share one. Counted over
    # `git ls-files *.py` by walking each call's parenthesis depth, 56 subprocess call
    # sites in this repo are single-line and 189 span lines -- blind to 77% of them, and
    # blind to the one live shell injection it was written to catch (WO 26675b56).
    # Detection is now `shell_true_findings`, which PARSES. The regex remains the fallback
    # for non-Python content and for a file too broken to parse.
    (re.compile(r"shell\s*=\s*True"), "shell=True"),
    (CREDENTIAL_PATTERNS["private_key_block"], "private key in source"),
    (TOKEN_SHAPED_PATTERN, "token-shaped string"),
]

#: The label the parsed check owns. Named once so the regex entry and the parsed path
#: cannot disagree about it -- two spellings of one finding is how a dedupe silently
#: stops deduping.
SHELL_LABEL = "shell=True"

#: Calls whose NAME is the finding, resolved by the parser rather than matched in text.
#: The regex equivalents flagged prose: measured across `git ls-files *.py`,
#: `\beval\s*\(` matched 10 files and a parse confirmed a real `eval()` call in ZERO of
#: them -- "Subcommand-shaped eval (`deno eval <code>`)" is a sentence with a parenthetical,
#: and the pattern read it as a call. A blocking gate on that would fire on 10 clean files.
_CALL_LABELS = {
    "eval": "eval()",
    "builtins.eval": "eval()",
    "exec": "exec()",
    "builtins.exec": "exec()",
    "os.system": "os.system()",
}

#: Callees for which a NON-LITERAL ``shell=`` value is a finding. A truthy literal is
#: reported whatever the callee, because ``shell=True`` is essentially only subprocess and
#: over-reporting is the safe direction. An UNDETERMINED value needs this list, because
#: without it ``shell=_detect_shell()`` in a dataclass whose field is named ``shell``
#: (core/config/platform.py) is reported as a security finding on innocent code. Callee
#: resolution was deliberately rejected for the literal case and is right here: it is the
#: only thing separating a guess from a fact. Names are resolved through the module's own
#: imports first, so ``import subprocess as sp`` and ``from subprocess import run`` both
#: land here.
_SUBPROCESS_CALLEES = frozenset(
    {
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
        "os.popen",
        "os.spawnl",
        "os.spawnv",
        "os.spawnlp",
        "os.spawnvp",
        "os.posix_spawn",
        "os.execv",
        "os.execvp",
    }
)
#: FULLY QUALIFIED ONLY. An earlier cut also held the bare names (`run`, `call`, `Popen`,
#: ...) so that `from subprocess import run` would be recognised. Those matched ANY
#: unqualified call by that name, so a local `def run(cmd, shell=False)` invoked as
#: `run(cmd, shell=flag)` was reported -- the identical false-positive shape this narrowing
#: was built to remove from `core/config/platform.py`. Import resolution already handles the
#: legitimate case: `from subprocess import run` maps `run` to `subprocess.run`, while a
#: locally defined `run` resolves to nothing and is left alone.

#: Where each code shape can actually EXECUTE, which is where it is worth scanning.
#: ``.yaml``/``.yml``/``.env`` are absent on purpose: a code shape there is a value or
#: prose, never a call, and those are the files whose prose about these patterns made an
#: earlier cut of this gate block its own change set on nine findings.
_SHELL_LIKE_EXTS = (".sh", ".bash", ".zsh")
_JS_LIKE_EXTS = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")

#: The native shell injection shape, which the Python-flavoured patterns cannot see. `eval`
#: in shell takes no parentheses -- `eval "$cmd"` -- so `\beval\s*\(` never matched it, and
#: "shell is scanned by regex" oversold what was covered: only Python code EMBEDDED in a
#: shell file was ever caught.
_SHELL_EVAL_RE = re.compile(r"\beval\s+[^\s]")

#: Findings that are PYTHON SYNTAX, and so are found only by parsing Python. Matching them
#: as text in a manifest is a category error: it made this gate block its own change set on
#: nine findings that were all prose describing the fix.
_CODE_SHAPE_LABELS = frozenset({SHELL_LABEL, "eval()", "os.system()"})

#: Reported when a .py file cannot be parsed, so that a check which could not run is never
#: mistaken for a check that passed.
UNPARSEABLE_LABEL = "unparseable Python"

#: EVERY label this module can produce, in report order. `scan_for_patterns` used to order
#: its output by iterating PATTERNS, which silently DROPPED any label without a PATTERNS
#: entry -- `exec()` was added to the parsed label table and vanished from that function and
#: from the hook, while the gate reported it correctly. A list of labels coupled to a list
#: of regexes breaks the first time the two diverge, so the order is stated once here.
_LABEL_ORDER = (
    "hardcoded credential",
    "eval()",
    "exec()",
    "os.system()",
    SHELL_LABEL,
    "private key in source",
    "token-shaped string",
    UNPARSEABLE_LABEL,
)

SCAN_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".sh", ".yaml", ".yml", ".env"}
SKIP_PATH_PARTS = {"tests", "test", "__pycache__", "node_modules", ".venv", "venv"}


def extract_content(payload: dict) -> tuple[str, str]:
    """Extract file path and content from tool payload.

    Returns:
        (file_path, content) tuple. Content is empty string if not Edit/Write.
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            return "", ""

    fp = tool_input.get("file_path", "")

    if tool_name == "Edit":
        return fp, tool_input.get("new_string", "")
    if tool_name == "Write":
        return fp, tool_input.get("content", "")

    return fp, ""


def should_scan(file_path: str, *, include_tests: bool = False) -> bool:
    """Whether to scan this path, by extension and by location.

    ``include_tests`` EXISTS BECAUSE TWO CALLERS WANT DIFFERENT ANSWERS, and the blocking
    gate inherited the advisory hook's answer by accident. ``SKIP_PATH_PARTS`` holds
    ``tests``/``test`` to keep per-edit noise down while someone works on fixtures --
    reasonable for a hook that only prints. The gate then reused it unchanged, so a real
    ``shell=True``, ``eval()`` or ``os.system()`` added anywhere under ``tests/`` could
    never trip the blocking tier. A live one already sits in
    ``tests/unit/test_hook_runtime_reliability.py``. The gate passes ``include_tests=True``;
    the hook keeps the quiet default.

    ``__pycache__``, ``node_modules`` and the virtualenvs are skipped for both, always:
    those are not authored source and nobody can act on a finding in them.
    """
    if not file_path:
        return False

    path = Path(file_path)

    if path.suffix.lower() not in SCAN_EXTS:
        return False

    skip = set(SKIP_PATH_PARTS)
    if include_tests:
        skip -= {"tests", "test"}
    if skip & set(path.parts):
        return False

    return True


def parsed_findings(content: str) -> list[tuple[int, str, str]] | None:
    """``(line, label, call)`` for every CODE-SHAPE finding in Python source.

    Returns None when the content is not parseable Python, which tells the caller to say so
    rather than report a clean result -- silence from a parser that never ran is the
    "compared nothing, reported clean" shape.

    WHY PARSING RATHER THAN A WIDER REGEX. The pattern this replaces required
    ``subprocess`` and ``shell=True`` on ONE line. Black puts them on different lines for
    any call with more than a couple of arguments, so the detector missed 189 of the 245
    subprocess call sites in this repo -- including the live shell injection of WO
    26675b56. Widening the window to span lines was the obvious fix and the wrong one: a
    400-character DOTALL window is exactly what made ``single-read-path``'s first cut name
    five lines containing no status comparison at all. Parsing has no window to get wrong.

    IT ALSO REMOVES FALSE POSITIVES. ``ast`` does not see inside strings or comments, so
    prose DISCUSSING these patterns is not read as a use of them. Measured: the
    ``eval`` regex matched 10 files in this repo and a parse confirms a real
    ``eval()`` call in ZERO of them, because "eval (`deno eval <code>`)" is a sentence with
    a parenthetical. A regex over source flags its own explanation.

    ``shell=`` IS CHECKED BY VALUE, AND AN UNDETERMINED VALUE COUNTS. Only a literal false
    value clears a call. ``shell=1``, ``shell=bool(1)``, ``shell=True if x else False`` and
    ``shell=SHELL`` were all invisible when this matched a literal ``True`` alone -- and
    ``shell=(platform.system() == "Windows")`` is idiomatic Python, not an evasion. What
    cannot be resolved statically is reported as undetermined, because for a security check
    "I could not tell" belongs with "yes", not with "no".

    ANY call is reported for ``shell=``, not only a recognised subprocess name. Resolving
    the callee is brittleness worth avoiding: it may be ``run``, ``Popen``,
    ``check_output``, an aliased import, or ``sp.run``. ``shell=`` is essentially only the
    subprocess family, and over-reporting is the safe direction -- the gate owns the escape
    hatch. A local function that happens to take a ``shell`` keyword is a known, accepted
    false positive.

    ``eval`` and ``os.system`` are matched by NAME, with import ALIASES resolved from the
    module's own imports -- ``import os as o`` then ``o.system(cmd)``, and
    ``from os import system as run_it``, both of which evaded a literal-name match.

    KNOWN LIMIT, stated rather than implied: an alias created by ASSIGNMENT (``ev = eval``)
    or a call name built at runtime (``getattr(os, "sys" + "tem")``) needs dataflow, which
    this does not do. ``**kwargs`` unpacking is resolved only for a literal dict --
    ``**{"shell": True}`` is caught, ``**opts`` is not.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    module_alias, direct_alias = _import_aliases(tree)
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        raw = _call_name(node)
        name = _canonical_name(raw, module_alias, direct_alias)
        for keyword in node.keywords:
            found.extend(_shell_keyword_findings(keyword, raw, name))
        if name in _CALL_LABELS:
            found.append((node.lineno, _CALL_LABELS[name], raw))
    return sorted(set(found))


def _shell_keyword_findings(
    keyword: ast.keyword, call: str, resolved: str
) -> list[tuple[int, str, str]]:
    """Findings for one keyword argument of a call.

    Handles the plain ``shell=<value>`` form and the literal-dict ``**{"shell": True}``
    form. A non-literal value is reported as undetermined rather than cleared.
    """
    value = keyword.value
    if keyword.arg == "shell":
        verdict = _truthiness(value)
        if verdict is False:
            return []
        if verdict is True:
            return [(value.lineno, SHELL_LABEL, call)]
        # UNDETERMINED. Reported only for a subprocess callee -- see _SUBPROCESS_CALLEES for
        # why this one case needs the callee and the literal case does not.
        if resolved in _SUBPROCESS_CALLEES:
            return [(value.lineno, SHELL_LABEL, f"{call} (shell=<undetermined>)")]
        return []
    if keyword.arg is None and isinstance(value, ast.Dict):
        # `**{"shell": True}` -- the same argument, spelled through a literal mapping.
        for key, item in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == "shell":
                verdict = _truthiness(item)
                if verdict is True or (verdict is None and resolved in _SUBPROCESS_CALLEES):
                    return [(item.lineno, SHELL_LABEL, f"{call} (**{{'shell': ...}})")]
    return []


def _truthiness(node: ast.AST) -> bool | None:
    """``True``/``False`` for a literal, None when it cannot be resolved statically.

    None is deliberately NOT treated as false by the caller. A value this cannot resolve
    may well be true at runtime, and a security check that reads "unknown" as "safe" is a
    fail-open.
    """
    if isinstance(node, ast.Constant):
        return bool(node.value)
    return None


def _import_aliases(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    """``(module_alias, direct_alias)`` built from the module's own import statements.

    Without this, ``import os as o`` then ``o.system(cmd)`` is invisible to a literal-name
    match -- and this repo writes ``import subprocess as sp`` in its own test fixtures, so
    the alias shape is native here rather than exotic.
    """
    module_alias: dict[str, str] = {}
    direct_alias: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for entry in node.names:
                module_alias[entry.asname or entry.name] = entry.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for entry in node.names:
                direct_alias[entry.asname or entry.name] = f"{node.module}.{entry.name}"
    return module_alias, direct_alias


def _canonical_name(name: str, module_alias: dict[str, str], direct_alias: dict[str, str]) -> str:
    """Resolve a called name through the module's imports to its real dotted path."""
    if name in direct_alias:
        return direct_alias[name]
    head, _, rest = name.partition(".")
    if head in module_alias:
        real = module_alias[head]
        return f"{real}.{rest}" if rest else real
    return name


def _call_name(node: ast.Call) -> str:
    """A readable name for the called thing, best effort -- it is for a message and for an
    alias lookup, so an unrecognised shape degrades to a placeholder rather than raising."""
    target = node.func
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts)) if parts else "<call>"


def is_python_path(file_path: str) -> bool:
    """Whether to treat this content as Python. An empty path means "assume Python", which
    keeps a caller that passes content alone on the stronger check."""
    return not file_path or file_path.lower().endswith((".py", ".pyi"))


def findings_with_lines(content: str, file_path: str = "") -> list[tuple[int, str, str]]:
    """``(line, label, detail)`` for one file's content. The single line-level entry point.

    TWO KINDS OF PATTERN, and conflating them was a defect in both directions.

    FORMAT patterns -- a hardcoded credential, a PEM block, a token-shaped string -- are
    about the shape of a STRING, which is what a regex is for. They run over every line of
    every scannable file.

    CODE-SHAPE patterns -- ``shell=True``, ``eval()``, ``os.system()`` -- are Python syntax,
    and are found only by PARSING Python. Matching them as text in a YAML manifest is a
    category error: it made the gate block its own change set on nine findings that were all
    prose describing this fix. There is no allowlist of self-referential files any more,
    because with the category fixed none is needed.

    THE EARLY RETURN THAT USED TO BE HERE WAS A FAIL-OPEN. It returned the parsed findings
    as soon as a Python file parsed, so the format patterns never ran on any valid Python --
    and every tracked .py file in this repo parses. A probe carrying a password, an RSA
    private key and a PAT-shaped token was reported clean by the blocking gate. Both kinds
    now always run.

    An unparseable .py yields an explicit finding rather than silence: a check that could
    not run must not read as a pass. All 1598 tracked .py files parse today, so this is not
    a wall.

    RESIDUAL RISK, two of them:

    * a code shape is scanned only where that syntax can EXECUTE: Python is parsed, shell
      and JS-family files are matched by regex with comment lines skipped, and YAML/.env
      get no code-shape scan at all. The YAML exclusion is deliberate -- a ``shell=True``
      in a manifest is prose or a value -- but it leaves a real gap this note previously
      undersold: a ``.github/workflows/*.yml`` ``run:`` block IS shell script, so an
      ``eval`` of untrusted input there is not detected. The regex path for shell and JS is
      weaker than the parsed path and its comment skipping is a heuristic, not a parser.
    * the FORMAT patterns are still regexes, so their own limits remain. Measured:
      an assignment whose value is wrapped in PARENTHESES across lines is not
      matched, because the pattern expects a quote after the equals sign and finds a
      parenthesis. Searching the whole content rather than each line closes the
      NEWLINE case -- an unparenthesised value on the following line is caught -- but
      it does not make a regex understand syntax. A credential is a string SHAPE, so
      a regex is the right tool for it; it is still a regex.
    """
    out: list[tuple[int, str, str]] = []
    for pattern, label in PATTERNS:
        if label in _CODE_SHAPE_LABELS:
            continue
        # OVER THE WHOLE CONTENT, with the line derived from the match offset -- NOT
        # per-line. A first cut scanned line by line and reintroduced, in this lane, the
        # exact blindness this work order exists to remove: an assignment whose value sits
        # on the next line has whitespace spanning that newline, so a whole-content search
        # matches it and a per-line search cannot. Found by testing the fix rather than
        # reading it, two hours after writing "parsing has no window to get wrong".
        for match in pattern.finditer(content):
            out.append((content.count(chr(10), 0, match.start()) + 1, label, "format match"))
    out.extend(_code_shape_findings(content, file_path))
    return sorted(set(out))


def _code_shape_findings(content: str, file_path: str) -> list[tuple[int, str, str]]:
    """Code-shape findings, scanned WHERE THAT SYNTAX CAN EXECUTE.

    Python is parsed. Shell and JS-family files are matched by regex with comment lines
    skipped, which is weaker but is the only option without a parser for those languages --
    and dropping it entirely deleted a capability the single-regex design had and broke
    `test_hook_on_security_scan.py::test_warns_on_shell_true`.

    YAML and ``.env`` get NO code-shape scan. A ``shell=True`` in a manifest is a value or
    prose, never a call, and those files are where this repo's own prose about these
    patterns lives -- matching it there made an earlier cut of the gate block its own
    change set on nine findings. RESIDUAL RISK, and it is a real one: a
    ``.github/workflows/*.yml`` ``run:`` block IS shell script, so an ``eval`` of untrusted
    input there is not detected. Closing that needs the run-block extracted and scanned as
    shell, which is a YAML-aware job this does not do.
    """
    lowered = (file_path or "").lower()
    if is_python_path(file_path):
        parsed = parsed_findings(content)
        if parsed is None:
            return [(1, UNPARSEABLE_LABEL, "code shapes could not be checked")]
        return parsed
    is_shell = lowered.endswith(_SHELL_LIKE_EXTS)
    if not is_shell and not lowered.endswith(_JS_LIKE_EXTS):
        return []
    out: list[tuple[int, str, str]] = []
    in_block = False
    for number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        was_in_block = in_block
        if not is_shell:
            if "/*" in stripped and "*/" not in stripped:
                in_block = True
            elif was_in_block and "*/" in stripped:
                in_block = False
                continue
        if was_in_block:
            # Inside an open /* */ block. A first cut instead treated a LEADING `*` as a
            # comment, which was wrong twice: a block body line without one read as code
            # (prose flagged as a call, this work order's own defect returning for JS), and
            # a generator shorthand `*gen() { eval(x) }` was skipped as if it were a comment.
            continue
        if _is_line_comment(stripped, is_shell):
            continue
        for pattern, label in PATTERNS:
            if label in _CODE_SHAPE_LABELS and pattern.search(line):
                out.append((number, label, "text match (no parser for this language)"))
        if is_shell and _SHELL_EVAL_RE.search(line):
            out.append((number, "eval()", "shell eval (text match, no parser)"))
    return out


def _is_line_comment(stripped: str, is_shell: bool) -> bool:
    """Whether a stripped line begins a comment in this language.

    A HEURISTIC, and named as one -- but without it "# never use shell=True" reads as a
    use, which is the defect this whole work order is about. `*` is deliberately NOT
    treated as a comment marker here: outside an open block it begins a JS generator
    method, and inside one the caller has already skipped the line.
    """
    if is_shell:
        return stripped.startswith("#")
    return stripped.startswith(("//", "/*"))


def scan_for_patterns(content: str, file_path: str = "") -> list[str]:
    """Labels for the anti-patterns in this content.

    Derived from ``findings_with_lines`` rather than implemented again, so the label-level
    and line-level answers cannot disagree -- two implementations of one rule is how the
    two drift and the weaker one quietly becomes the policy.
    """
    labels = {label for _line, label, _detail in findings_with_lines(content, file_path)}
    return [label for label in _LABEL_ORDER if label in labels]


def print_warning(file_path: str, findings: list[str]) -> None:
    """Print security warning for findings.

    Args:
        file_path: Path to file with findings
        findings: List of pattern labels that matched
    """
    name = Path(file_path).name if file_path else "file"
    labels = ", ".join(findings)
    print(f"\n[dream-studio] Security: {name} — {labels}. Review before committing.\n", flush=True)
