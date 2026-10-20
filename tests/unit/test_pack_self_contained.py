"""An enrolled skill pack reaches nothing outside its own directory, and says so truthfully.

WHY THIS FILE EXISTS. docs/contracts/pack-capability-contract.md sets the direction: a
pack is self-contained content that reaches governance only through declared capabilities.
The audit behind it found the opposite in practice -- seven skill files hardcoded
`builds/dream-studio-clean/templates/...`, twenty-six read the repo-level `templates/`,
and 35 of 51 `metadata.yml` files declared `core_modules: []` while their text called into
the platform. The first pack to be extracted, `analyze`, showed the same disease in
smaller form:

  * `repo-analyzer.py` climbed four `.parent` hops to a repository root and imported
    `canonical.skills.analyze.domains`. In an installed copy there is no repository
    root, the import raised, a bare `except ImportError` turned domain analysis off
    silently, and `--auto-detect` died with "No module named 'canonical'".
  * its vendored package was named `core`, the same as the platform's own top-level
    `core`; whichever imported first won the whole process.
  * `modes/multi` called `insert_lesson()` and wrote `~/.dream-studio/...` while its
    metadata declared `core_modules: []` and `files_required: []`.
  * three modes named `skills/analyze/...` or `skills/domain-re/...` paths that exist in
    neither the checkout nor the installed layout.

THE RULE, rather than a list of spellings. The first version of this guard was a deny-list
of spellings, and an outside verifier walked around it 66 times in about 85 tries (#892): `\\` for `/`,
`./templates`, `Templates`, `$HOME/.dream-studio`, `os.path.dirname` chains, a `.sh` file.
A deny-list loses to the next spelling. So the guard states one rule and derives
everything else from the repository:

    A reference in a pack, once its separators, case and `.`/`..` segments are normalised,
    must land inside the pack directory; what lands outside is either forbidden outright
    (a checkout layout, a user's machine, a host install) or a REACH, which the mode's
    metadata.yml must declare.

What counts as a layout name, as a platform module, as a stdlib module and as a pack is
read from the repository (`git ls-files` top level, `sys.stdlib_module_names`,
packs.yaml), never from a list written here, so a new top-level package is covered the day
it lands.

WHAT IT CHECKS, for every pack in ENROLLED_PACKS:

  1. The pack exists (packs.yaml entry, directory, every declared mode directory with a
     SKILL.md and a metadata.yml). An enrolled pack that is missing FAILS; it is not skipped.
  2. Every file is scanned by CONTENT, not by suffix: any file without a NUL byte is text
     (`.sh`, `.ps1`, `.js`, `.html`, `.j2`, `.csv`, extensionless, upper-case `.MD`).
     Real binaries are skipped. A symlink or junction that resolves outside the pack, or to
     nothing, is a violation.
  3. No text names a path outside the pack: a checkout layout (`canonical/`, `templates/`,
     `docs/`, `config/`, `scripts/`, `tools/`, `schemas/`, `packs.yaml`, `dist/plugin`, ...),
     a user-specific absolute path (any drive letter, `/home/`, `/Users/`), a host install
     path (`.claude/`), a `..` reference that does not land on something inside the pack,
     or `${CLAUDE_PLUGIN_ROOT}` climbed above. Separators and case are normalised first.
  4. Python is parsed with `ast`; a file that does not parse is a violation (a syntax error
     must not hide the imports under it). Imports of a platform package are reaches, found
     through `import`, `from ... import`, `importlib.import_module`, `__import__` and
     `runpy.run_module`; a dynamic import whose name cannot be resolved is a violation. A
     path expression that climbs above the pack is found by evaluating it: `.parent` and
     `.parents[n]` chains, `os.path.dirname`/`join`/`abspath`, `/` and `joinpath` with `..`,
     `sys.argv[0]`, names assigned earlier, chains split over lines.
  5. No top-level name in the pack, or in a directory of scripts, shadows a platform package
     or a standard-library module (the `core` shadow, a `json.py`, a namespace `core/`).
  6. What a mode DOES reach -- platform modules, third-party Python packages,
     `~/.dream-studio/` and `.planning/` state, environment variables, the `ds` CLI and other
     external tools, other packs' skills, subagent types -- is declared in that mode's
     metadata.yml `dependencies`; a reach without the declaration is a contradiction. A
     pack-level file is judged against the modes that claim it in `files_required`, and one
     no mode claims may reach nothing. Code is read for reaches too: `Path.home() /
     '.dream-studio'`, `os.environ[...]`, `os.system`, `subprocess.run(..., shell=True)`, a
     command held in a variable. Tools run by shell scripts and fenced shell blocks are read
     deny-by-default (anything not a shell builtin or a PowerShell cmdlet is a tool); in prose,
     only a backtick span of two words or more that starts with a tool from a short list
     (`_KNOWN_TOOLS`, the one hand-written list left, for the one place a rule cannot be derived).
  7. The declaration itself is true where it can be checked: every key present as a list
     (`core_modules`, `tools_required`, `python_packages`, `env_vars_required`,
     `files_required`, `calls_skills`), every pack-relative `files_required` entry exists
     inside the pack, and a third-party import is covered by a `python_packages` entry that
     names the distribution providing it (`yaml` is satisfied by `PyYAML`, asked of the
     installed environment, with a small fallback map for a host where it is not installed).

WHAT A STATIC CHECK CANNOT CATCH, and this guard does not pretend to (each is documented,
none is covered): a path or command assembled from runtime data (`sys.argv[1]`, a config
file's contents, `input()`); `exec`/`eval`/`compile` of text built at run time (a literal
program IS read, and a non-literal one IS a violation); a reach spelled in an encoding the
guard does not undo (it undoes entities, `%2e`, `\\u002e` and compatibility forms; not base64,
homoglyphs such as a Cyrillic `е`, or 8.3 short names); a path wrapped across two lines of
prose; `getattr(importlib, name)`-style indirection; a value rebound in a loop, by tuple
unpacking or through a helper function's parameter (assignments are tracked flat, last one
wins); `parents[len(x)]`; `inspect`-based file lookups; a path assembled by shell variables; a
path anchored on an arbitrary variable (`$REPO/templates/x`, a user's own name for it); a
command passed through a helper function (only the final `subprocess` call is judged, and an
unresolvable command there IS a violation); a symlink created at install time rather than
shipped; prose that tells an agent to look "in the parent repository" without naming a path.
It reads text and structure, not behavior. KNOWN_GAPS below pins each of these as an expected
failure, so the day the guard learns one the test says the list above is out of date.

WHAT IT DELIBERATELY DOES NOT CHECK. A declared `core_modules` entry no text names is
allowed (the intelligence mode declares the engine stages it runs but never spells out
in prose). Third-party names and a user's own paths (`~/repos/x`, `~/builds/my-app`) are
not this repository's to forbid; neither are `tests/` and `examples/`, which are ordinary
names in the repositories an analysis pack reads.

The synthetic-pack tests below pin each rule: a detector that stopped matching (the
failure mode of a regex written in a shell heredoc, where `\\b` turns into a backspace
byte) would otherwise report clean on the real pack. Each one builds a pack that breaks
exactly one rule and asserts the rule names it.
"""

from __future__ import annotations

import ast
import html
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Packs held to the contract. Explicit on purpose: enrolling a pack is a decision that
#: comes with fixing it, and a glob would enrol the 12 packs that still read the
#: checkout. Extend as each pack is extracted.
ENROLLED_PACKS = ("analyze",)

DEPENDENCY_KEYS = (
    "core_modules",
    "tools_required",
    "python_packages",
    "env_vars_required",
    "files_required",
    "calls_skills",
)

#: Top-level directories of the repository that are ordinary names in the repositories a
#: pack analyses (`tests/`, `examples/`), so a mention is not a reach into this checkout.
GENERIC_DIRS = frozenset({"tests", "examples"})

#: The installed layouts, which are not top-level directories of the repository.
LAYOUT_EXTRA = frozenset({"skills"})

#: Absolute roots that mean one person's machine.
_ABS_ROOT = re.compile(r"^/(?:home|users|root|mnt|volumes|private|opt|srv|workspace)(?:/|$)", re.I)
_ANCHOR_DRIVE = re.compile(r"^/?[A-Za-z]:/")
_ANCHOR_UNC = re.compile(r"^//[^/]+/")
_HOMEISH = r"(?:HOME|USERPROFILE|HOMEPATH|HOMEDRIVE|APPDATA|LOCALAPPDATA|XDG_[A-Z_]+)"
_ANCHOR_HOME = re.compile(
    r"^(?:~[\w.-]*|\$\{?" + _HOMEISH + r"\}?|%" + _HOMEISH + r"%)(?=/|$)", re.I
)
_ANCHOR_ENV = re.compile(r"^(?:\$\{?([A-Za-z_]\w*)\}?|%([A-Za-z_]\w*)%)(?=/|$)")

#: An environment variable that names Dream Studio or its host: reading a path through it
#: reaches outside the pack, and the mode must say it needs the variable.
_SENSITIVE_ENV = re.compile(r"^(?:CLAUDE_|DREAM_STUDIO|.*PLUGIN)", re.I)

_URL = re.compile(r"\b(?:https?|ftp|ssh|git|wss?)://[^\s<>\"'`)\]]+|[\w.-]+@[\w.-]+:[\w./-]+", re.I)
_DELIM = re.compile(r"[\s`'\"()<>\[\]|;,=*?!#^&]+")

_FROM_IMPORT = re.compile(r"\bfrom\s+([A-Za-z_]\w*(?:\.\w+)*)\s+import\b")
_PLAIN_IMPORT = re.compile(r"(?:^|[`;])\s*import\s+([A-Za-z_]\w*(?:\.\w+)*)")
_DOTTED = re.compile(r"(?<![\w./~-])([A-Za-z_]\w*)((?:\.[a-z_][a-z0-9_]*)+)")

#: Platform functions skills are known to tell an agent to call, by the module they live
#: in. Found in the audit; extend when a skill is found calling another.
_PLATFORM_CALLS = (
    (re.compile(r"\binsert_lesson\("), "core.event_store"),
    (re.compile(r"\bpaths\.state_dir\("), "core.config.paths"),
)

#: The `ds` CLI: a standalone `ds` word (so `fields`/`ds_documents`/`ds-analyze` do not
#: match), bare, as `./ds`, with a subcommand or a flag.
_DS_CLI = re.compile(r"(?<![\w/.\-])(?:\.[/\\])?ds(?=\s+(?:-{1,2}[a-z]|[a-z][a-z-]*))")

#: Another pack's skill id (`ds-code-health`), as in `Skill(skill="DS-code-health", ...)`.
_OTHER_SKILL = re.compile(r"(?<![\w-])ds-([a-z][a-z-]*)", re.I)
_PLUGIN_SKILL = re.compile(r"(?<![\w-])dream-studio:(?:ds-)?([a-z][a-z-]*)", re.I)

#: A subagent type an instruction dispatches: `Agent(subagent_type="x")`.
_AGENT = re.compile(r"subagent_type\s*[=:]\s*[\"']?([\w.:-]+)")

_PYTHON_SUFFIXES = {".py", ".pyi", ".pyw"}

_SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".ksh", ".ps1", ".psm1", ".bat", ".cmd"}
_SHELL_FENCE_LANGS = {
    "sh",
    "bash",
    "shell",
    "zsh",
    "console",
    "terminal",
    "powershell",
    "ps1",
    "pwsh",
    "cmd",
    "bat",
    "batch",
    "shell-session",
}

#: What a shell snippet may run with no declaration: the shell's own words and the POSIX /
#: cmd / PowerShell userland every host has. Anything else a snippet runs is an external tool
#: and the mode names it. (`bash`, `cmd`, `powershell` are NOT here: needing one is a need.)
_BUILTIN_COMMANDS = frozenset(
    "cd echo cat ls dir mkdir rm cp mv pwd export set unset source . : test [ [[ if then else "
    "elif fi for while do done case esac in exit return read printf true false sleep head tail "
    "grep sed awk sort uniq wc tr cut find touch which basename dirname chmod ln diff tee date "
    "type command alias local function copy del move ren rd md cls rem call start setlocal "
    "endlocal pushd popd env time xargs sudo nohup nice".split()
)

#: External command-line tools, for the one place a deny-by-default rule cannot work: a
#: backtick span in prose (`sqlite3 db "select 1"`), where most first words are not commands.
#: A shell snippet and a script file do not use this list; they flag anything not builtin.
_KNOWN_TOOLS = frozenset(
    "git gh hg svn docker docker-compose podman kubectl helm terraform aws az gcloud sqlite3 "
    "psql mysql mongosh redis-cli curl wget ssh scp rsync npm npx node yarn pnpm bun deno pip "
    "pip3 pipx uv poetry cargo rustc go java javac mvn gradle dotnet make cmake ruby gem bundle "
    "php composer jq yq rg ag fd tar zip unzip 7z brew apt apt-get choco winget ffmpeg magick "
    "pandoc playwright pytest black flake8 ruff mypy bash sh zsh cmd powershell pwsh".split()
)

#: Import names whose distribution has a different name, for a host where the package is
#: not installed to ask (`importlib.metadata.packages_distributions` answers when it is).
_PACKAGE_MAP = {
    "yaml": "pyyaml",
    "PIL": "pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "attr": "attrs",
    "jwt": "pyjwt",
    "git": "gitpython",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "markdown": "markdown",
    "magic": "python-magic",
    "serial": "pyserial",
}

#: Containers whose members the guard does not open (zip family, gzip, 7z, rar, bzip2, xz).
_ARCHIVE_MAGIC = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"\x1f\x8b",
    b"7z\xbc\xaf",
    b"Rar!",
    b"BZh",
    b"\xfd7zXZ",
)
_SPAWN = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.check_output",
    "subprocess.check_call",
    "subprocess.call",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "os.system",
    "os.popen",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
}
_SPAWN_FILE_FIRST = {"os.execv", "os.execve", "os.execvp", "os.execvpe", "os.execl", "os.execlp"}
_SPAWN_FILE_SECOND = {"os.spawnv", "os.spawnve", "os.spawnvp", "os.spawnl", "os.spawnlp"}
_DYNAMIC_IMPORT = {
    "importlib.import_module",
    "importlib.__import__",
    "importlib.util.find_spec",
    "__import__",
    "runpy.run_module",
}
_EXEC = {"exec", "eval", "compile"}

#: A command that runs another command: its own name is a reach, and so is what it runs.
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_WRAPPERS = {"env", "sudo", "nohup", "time", "xargs", "nice", "command"}
_PATH_CTORS = {"Path", "PurePath", "PosixPath", "WindowsPath", "PurePosixPath", "PureWindowsPath"}
_PATH_PASSTHROUGH = {
    "resolve",
    "absolute",
    "expanduser",
    "with_name",
    "with_suffix",
    "with_stem",
    "as_posix",
}
_OS_PASSTHROUGH = {"os.path.abspath", "os.path.realpath", "os.path.normpath", "os.path.expanduser"}


# --------------------------------------------------------------------------- helpers


def _pack_dir_for(name: str, spec: dict, root: Path) -> Path:
    """Resolve a pack's directory the way the projector does (`skill_path`, else name)."""
    skill_path = (spec or {}).get("skill_path")
    return root / skill_path if skill_path else root / "canonical" / "skills" / name


@lru_cache(maxsize=None)
def _tracked_top(base: str) -> tuple[frozenset, frozenset, frozenset, frozenset]:
    """What `base` owns at its top level: (importable names, packages, layout roots, files).

    Read from `git ls-files` when `base` is a checkout (so an untracked `build/` or `.venv/`
    on one machine does not change what the guard accepts on another), from the directory
    listing otherwise. Never from a list written in this file.
    """
    root = Path(base)
    paths: list[str] = []
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=60,
        )
        paths = [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        if root.is_dir():
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for f in filenames:
                    paths.append(Path(dirpath, f).relative_to(root).as_posix())
    tracked = set(paths)
    owned, packages, layout, files = set(), set(), set(), set()
    for rel in paths:
        parts = rel.split("/")
        top = parts[0]
        if top.startswith((".", "_")):
            continue
        if len(parts) == 1:
            if top.endswith(".py") and top[:-3].isidentifier():
                owned.add(top[:-3])
            elif top.endswith((".yaml", ".yml")) and top.lower() != "config.yml":
                files.add(top.lower())
            continue
        if top not in GENERIC_DIRS:
            layout.add(top.lower())
        if rel.endswith(".py") and top.isidentifier():
            owned.add(top)
        if f"{top}/__init__.py" in tracked:
            packages.add(top)
    return frozenset(owned), frozenset(packages), frozenset(layout), frozenset(files)


def _platform_names(root: Path) -> tuple[frozenset, frozenset, frozenset, frozenset]:
    """The repository's own top-level names, unioned with `root`'s when that differs."""
    base = _tracked_top(str(REPO_ROOT))
    if Path(root).resolve() == REPO_ROOT:
        return base
    extra = _tracked_top(str(Path(root).resolve()))
    return tuple(a | b for a, b in zip(base, extra))  # type: ignore[return-value]


def _stdlib() -> frozenset:
    return frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


@lru_cache(maxsize=None)
def _pack_names() -> frozenset:
    try:
        packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return frozenset()
    return frozenset(str(n).lower() for n in packs)


@dataclass(frozen=True)
class _Ctx:
    pack_dir: Path
    pack_name: str
    owned: frozenset
    packages: frozenset
    layout: frozenset
    layout_files: frozenset
    packs: frozenset
    local: frozenset
    stdlib: frozenset
    rel_dir: tuple  # the file's directory, as segments below the pack root
    test_file: bool = False


def _listing(directory: Path) -> dict[str, Path]:
    try:
        return {c.name.lower(): c for c in directory.iterdir()}
    except OSError:
        return {}


def _inside_exists(pack_dir: Path, parts: list[str]) -> bool:
    """`parts` (no `..`) names something that exists inside the pack, ignoring case."""
    current = pack_dir
    for part in parts:
        found = _listing(current).get(part.lower())
        if found is None:
            return False
        current = found
    return True


def _normalise(parts: list[str]):
    """Resolve `.`/`..`; None when the path climbs above where it started."""
    out: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(part)
    return out


def _resolves_in_pack(ctx: _Ctx, parts: list[str]) -> bool:
    """A relative reference lands on something inside the pack, read from the pack root or
    from the directory the file sits in (a link in `modes/x/SKILL.md` is written either way)."""
    for base in ([], list(ctx.rel_dir)):
        norm = _normalise(base + parts)
        if norm is not None and _inside_exists(ctx.pack_dir, norm):
            return True
    return False


def _resolve_platform_module(ctx: _Ctx, segs: list[str]):
    """`control/analysis/stacks` -> `control.analysis.stacks` when it exists in the checkout."""
    current = REPO_ROOT
    resolved: list[str] = []
    for index, seg in enumerate(segs):
        name = seg[:-3] if index == len(segs) - 1 and seg.endswith(".py") else seg
        if (current / name).is_dir():
            resolved.append(name)
            current = current / name
        elif (current / f"{name}.py").is_file():
            resolved.append(name)
            break
        else:
            break
    return ".".join(resolved) if len(resolved) >= 2 else None


def _covered(token: str, declared: list[str]) -> bool:
    """A reference is declared when it and a declared entry nest one inside the other, on
    a segment boundary (`/` or `.`) -- `core.event` is not covered by `core.event_store`."""
    token = token.rstrip(".:;/")
    for entry in declared:
        entry = str(entry).rstrip("/")
        for outer, inner in ((token, entry), (entry, token)):
            if outer == inner or outer.startswith(inner + "/") or outer.startswith(inner + "."):
                return True
    return False


# ------------------------------------------------------------------- walking and reading


def _is_link(path: Path) -> bool:
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda p: False)(path)


def _walk(pack_dir: Path):
    """Every entry under the pack, links reported and never followed."""
    for dirpath, dirnames, filenames in os.walk(pack_dir, followlinks=False):
        here = Path(dirpath)
        links = [d for d in dirnames if _is_link(here / d)]
        dirnames[:] = sorted(d for d in dirnames if d not in links)
        for name in sorted(links):
            yield here / name, True
        for name in sorted(filenames):
            yield here / name, _is_link(here / name)


def _decode(data: bytes):
    """Text of a file, or None for a real binary. Content decides, never the suffix."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if b"\x00" in data[:8192]:
        return _utf16_without_bom(data)
    text = data.decode("utf-8", errors="replace")
    if text and text.count("�") > max(8, len(text) // 10):
        return None
    return text


def _utf16_without_bom(data: bytes):
    """Text of a UTF-16 file that carries no byte-order mark, or None for a binary. ASCII text
    in UTF-16 has a NUL in every other byte; a binary does not, and does not decode cleanly."""
    sample = data[:400]
    for encoding, zeros in (("utf-16-le", sample[1::2]), ("utf-16-be", sample[0::2])):
        if zeros and zeros.count(0) >= 0.9 * len(zeros):
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                return None
            printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
            return text if text and printable >= 0.95 * len(text) else None
    return None


def _is_python(path: Path, text: str) -> bool:
    if path.suffix.lower() in _PYTHON_SUFFIXES:
        return True
    first = text.split("\n", 1)[0]
    return not path.suffix and first.startswith("#!") and "python" in first


def _link_verdict(exists: bool, target: Path, real_pack: Path):
    """The rule for a link, apart from reading the filesystem so a host that cannot make a
    link can still test it: it must resolve to something, and to something inside the pack."""
    if not exists:
        return "symlink points at nothing"
    if target != real_pack and real_pack not in target.parents:
        return f"symlink resolves outside the pack ({target})"
    return None


def _symlink_finding(path: Path, pack_dir: Path):
    return _link_verdict(path.exists(), path.resolve(), pack_dir.resolve())


# ------------------------------------------------------------------------ text reaches


def _pieces(line: str):
    """Path-shaped pieces of a line, separators normalised to `/`."""
    norm = line.replace("\\", "/")
    norm = re.sub(r"\$env:(\w+)", r"${\1}", norm, flags=re.I)
    norm = re.sub(r"\bfile:/{2,3}", "", norm, flags=re.I)
    norm = _URL.sub(" ", norm)
    for raw in _DELIM.split(norm):
        if not raw:
            continue
        parts = [raw] if _ANCHOR_DRIVE.match(raw) else raw.split(":")
        for part in parts:
            part = part.strip()
            if part.endswith(".") and not part.endswith(("/..", "/.")):
                part = part.rstrip(".")
            if part:
                yield part


def _path_reaches(piece: str, ctx: _Ctx):
    """(kind, token) for what one path-shaped piece reaches. Kinds: violation, state, module,
    env. The rule is the same for every spelling: normalise, then ask where it lands."""
    anchor, rest = "rel", piece
    match = _ANCHOR_HOME.match(piece)
    if match:
        after = match.end()
        anchor, rest = "home", piece[after:]
    elif _ANCHOR_DRIVE.match(piece) or _ANCHOR_UNC.match(piece) or _ABS_ROOT.match(piece):
        anchor, rest = "abs", piece
        yield "violation", f"user-specific path: {piece}"
    else:
        match = _ANCHOR_ENV.match(piece)
        if match:
            name = match.group(1) or match.group(2)
            after = match.end()
            rest = piece[after:]
            if _SENSITIVE_ENV.match(name):
                anchor = "env"
                yield "env", name
            else:
                anchor = "env-other"
    # Windows drops trailing dots and spaces from a name: `templates./x` is `templates/x`.
    segs_raw = [s if s in (".", "..") else s.rstrip(". ") for s in rest.split("/")]
    segs = [s for s in segs_raw if s not in ("", ".")]
    low = [s.lower() for s in segs]
    trailing = piece.endswith("/")

    # State and host paths are named by a segment, wherever they hang from.
    for state_dir, prefix in ((".dream-studio", "~/.dream-studio/"), (".planning", ".planning/")):
        if state_dir in low:
            after_it = low.index(state_dir) + 1
            yield "state", prefix + "/".join(segs[after_it:])
    if ".claude" in low and (len(segs) >= 2 or trailing or anchor != "rel"):
        yield "violation", f"host install path: {piece}"
    for index in range(len(low) - 1):
        if low[index] == "builds" and low[index + 1].startswith("dream-studio"):
            yield "violation", f"user-specific path: {piece}"
            break
        if (low[index], low[index + 1]) in {("canonical", "skills"), ("dist", "plugin")}:
            yield "violation", f"checkout path: {piece}"
            return

    if anchor in ("home", "abs", "env-other"):
        return
    if ".." in segs_raw and (len(segs_raw) > 1):
        if anchor == "env":
            yield "violation", f"relative reference leaves the pack: {piece}"
        elif not _resolves_in_pack(ctx, segs_raw):
            yield "violation", f"relative reference leaves the pack: {piece}"
        return
    if not low:
        return
    pathlike = len(segs) >= 2 or trailing
    top = low[0]
    if (pathlike and top in ctx.layout) or (len(segs) == 1 and top in ctx.layout_files):
        if anchor == "rel" and _resolves_in_pack(ctx, segs):
            return
        if top in ctx.packages:
            module = _resolve_platform_module(ctx, segs)
            if module:
                yield "module", module
                return
        yield "violation", f"checkout path: {piece}"


@lru_cache(maxsize=None)
def _slash_command(packs: frozenset):
    """`/quality:harden`: a slash command that names a pack packs.yaml really declares."""
    names = "|".join(sorted(re.escape(p) for p in packs))
    return re.compile(r"(?<![\w/.:~-])/(" + names + r"):[a-z][a-z-]*")


def _clean(line: str) -> str:
    """The line as a reader sees it: entities, `%2e`/`%2f`/`%5c` and compatibility forms
    (full-width `／`, `∕`) decoded, invisible format characters (zero-width space) dropped."""
    for _ in range(3):  # `%252e` is `%2e` once decoded; stop when nothing changes
        before = line
        if "&" in line:
            line = html.unescape(line)
        if "%" in line:
            line = re.sub(r"%(25|2[eEfF]|5[cC])", lambda m: chr(int(m.group(1), 16)), line)
        if "\\u" in line:  # a JSON or JavaScript string: "../x"
            line = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), line)
        if line == before:
            break
    line = unicodedata.normalize("NFKC", line)
    for slash in ("∕", "⁄", "⧸"):
        line = line.replace(slash, "/")
    return "".join(ch for ch in line if unicodedata.category(ch) != "Cf")


def _line_reaches(line: str, ctx: _Ctx, is_python: bool):
    """(kind, token) for every reach into the platform that one line of text makes."""
    line = _clean(line)
    for piece in _pieces(line):
        yield from _path_reaches(piece, ctx)
    if not is_python:
        for pattern in (_FROM_IMPORT, _PLAIN_IMPORT):
            for match in pattern.finditer(line):
                name = match.group(1)
                if name.split(".")[0] in ctx.owned and name.split(".")[0] not in ctx.local:
                    yield "module", name
        for match in _DOTTED.finditer(line):
            if match.group(1) in ctx.packages:
                module = _resolve_platform_module(
                    ctx, [match.group(1)] + match.group(2).lstrip(".").split(".")
                )
                if module:
                    yield "module", module
    for pattern, module in _PLATFORM_CALLS:
        if pattern.search(line):
            yield "module", module
    for _ in _DS_CLI.finditer(line):
        yield "tool", "ds"
    seen = set()
    for pattern in (_OTHER_SKILL, _PLUGIN_SKILL):
        for match in pattern.finditer(line):
            skill = "ds-" + match.group(1).lower()
            if skill != f"ds-{ctx.pack_name}" and skill not in seen:
                seen.add(skill)
                yield "skill", skill
    if ctx.packs:
        for match in _slash_command(ctx.packs).finditer(line):
            if match.group(1) != ctx.pack_name:
                yield "skill", "ds-" + match.group(1)
    for match in _AGENT.finditer(line):
        yield "agent", match.group(1)


# ------------------------------------------------------------------------ shell reaches


def _shell_flags(path: Path, lines: list[str]) -> list[bool]:
    """Which lines are shell: every line of a shell script, and the lines of a fenced block
    labelled as shell. (A bare fence holds trees, output and prose; it is not read as shell.)"""
    first = lines[0] if lines else ""
    if path.suffix.lower() in _SHELL_SUFFIXES or (
        first.startswith("#!") and re.search(r"\b(?:ba|z|k|da)?sh\b|pwsh", first)
    ):
        return [True] * len(lines)
    flags: list[bool] = []
    inside, lang = False, ""
    for line in lines:
        fence = re.match(r"\s*(?:```|~~~)\s*([\w+-]*)", line)
        if fence:
            inside, lang = not inside, fence.group(1).lower()
            flags.append(False)
        else:
            flags.append(inside and lang in _SHELL_FENCE_LANGS)
    return flags


_PROMPT = re.compile(r"^\s*(?:\$|PS[^>\n]*>|>)\s+")
_PLAIN_COMMAND = re.compile(r"[a-z][a-z0-9._+-]*")
_NOT_A_COMMAND = re.compile(r".*\.(?:py|sh|ps1|md|ya?ml|json|txt|js|ts|html?)$")


def _external(tools) -> list[str]:
    return [
        t
        for t in tools
        if t
        and t != "python"
        and t not in _BUILTIN_COMMANDS
        and _PLAIN_COMMAND.fullmatch(t)
        and not _NOT_A_COMMAND.match(t)
    ]


def _shell_line_tools(line: str) -> list[str]:
    """External tools one line of a shell snippet runs."""
    text = _PROMPT.sub("", line.strip())
    if not text or text.startswith(("#", "//", "::")) or text.upper().startswith("REM "):
        return []
    text = re.sub(r"^(?:\w+=\S*\s+)+", "", text)  # FOO=bar cmd
    return _external(_shell_tools(text))


def _inline_tools(line: str) -> list[str]:
    """Known tools a prose backtick span runs: `sqlite3 db "select 1"`. Two words or more, so
    a mention (`git` history) is not read as a command; the guard's own list, see _KNOWN_TOOLS."""
    found: list[str] = []
    for span in re.findall(r"`([^`\n]+)`", line):
        if len(span.split()) >= 2:
            found += [
                t for t in _external(_shell_tools(_PROMPT.sub("", span))) if t in _KNOWN_TOOLS
            ]
    return found


# ---------------------------------------------------------------------- python reaches


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


class _Module:
    """One parsed python file: what its names are bound to, and what an expression means."""

    def __init__(self, tree: ast.AST, depth: int):
        self.depth = depth
        self.aliases: dict[str, str] = {}
        self.env: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.aliases[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                if isinstance(node.targets[0], ast.Name):
                    self.env[node.targets[0].id] = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if isinstance(node.target, ast.Name):
                    self.env[node.target.id] = node.value

    def canon(self, func) -> str:
        """The name a call really has: `sp.run` -> `subprocess.run`, an alias followed."""
        name = _dotted(func)
        if not name:
            return ""
        head, _, tail = name.partition(".")
        if head in self.aliases:
            name = self.aliases[head] + ("." + tail if tail else "")
        elif head in self.env and isinstance(self.env[head], (ast.Name, ast.Attribute)):
            inner = _dotted(self.env[head])
            if inner and inner != head:
                name = inner + ("." + tail if tail else "")
                head2 = inner.split(".")[0]
                if head2 in self.aliases:
                    cut = len(head2)
                    name = self.aliases[head2] + name[cut:]
        return name

    # -- where a path expression lands, as a depth below the pack root (negative = above)

    def level(self, node, seen=frozenset()):
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return self.depth
            if node.id in self.env and node.id not in seen:
                return self.level(self.env[node.id], seen | {node.id})
            return None
        if isinstance(node, ast.Attribute):
            if node.attr == "parent":
                inner = self.level(node.value, seen)
                return None if inner is None else inner - 1
            if node.attr == "__file__" and isinstance(node.value, ast.Subscript):
                if self.canon(node.value.value) == "sys.modules":
                    return self.depth  # sys.modules[__name__].__file__ is this file
            return None
        if isinstance(node, ast.Subscript):
            target = node.value
            index = node.slice
            if not (isinstance(index, ast.Constant) and isinstance(index.value, int)):
                return None
            if isinstance(target, ast.Attribute) and target.attr == "parents" and index.value >= 0:
                inner = self.level(target.value, seen)
                return None if inner is None else inner - (index.value + 1)
            if self.canon(target) == "sys.argv" and index.value == 0:
                return self.depth
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self._apply(self.level(node.left, seen), self._text(node.right, seen))
        if isinstance(node, ast.Call):
            return self._call_level(node, seen)
        return None

    def _call_level(self, node: ast.Call, seen):
        func = node.func
        name = self.canon(func)
        if isinstance(func, ast.Attribute):
            if func.attr in _PATH_PASSTHROUGH:
                return self.level(func.value, seen)
            if func.attr == "joinpath":
                return self._join([func.value, *node.args], seen)
        last = name.rsplit(".", 1)[-1]
        if last in _PATH_CTORS and name in (last, f"pathlib.{last}"):
            return self._join(node.args, seen)
        if name == "os.path.dirname" and node.args:
            inner = self.level(node.args[0], seen)
            return None if inner is None else inner - 1
        if name in _OS_PASSTHROUGH and node.args:
            return self.level(node.args[0], seen)
        if name == "os.path.join":
            return self._join(node.args, seen)
        if name in ("str", "os.fspath") and node.args:
            return self.level(node.args[0], seen)
        return None

    def _join(self, args, seen):
        if not args:
            return None
        current = self.level(args[0], seen)
        rest = []
        for arg in args[1:]:  # os.path.join(base, *['..', '..']) is two more arguments
            if isinstance(arg, ast.Starred) and isinstance(arg.value, (ast.List, ast.Tuple)):
                rest += arg.value.elts
            else:
                rest.append(arg)
        for arg in rest:
            text = self._text(arg, seen)
            current = self._apply(current, text) if text is not None else self._bump(current)
        return current

    @staticmethod
    def _bump(level):
        return None if level is None else level + 1

    @staticmethod
    def _apply(level, text):
        if level is None:
            return None
        if text is None:
            return level + 1
        text = text.replace("\\", "/")
        if text.startswith(("/", "~")) or re.match(r"[A-Za-z]:/", text):
            return None
        for seg in text.split("/"):
            if seg in ("", "."):
                continue
            level += -1 if seg == ".." else 1
        return level

    def _text(self, node, seen=frozenset()):
        return self.fold(node, seen)

    # -- constant folding: the string an expression builds, when it builds one statically

    def fold(self, node, seen=frozenset()):
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.Name):
            if node.id in self.env and node.id not in seen:
                return self.fold(self.env[node.id], seen | {node.id})
            return None
        if isinstance(node, ast.JoinedStr):
            out = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    out.append(str(part.value))
                elif isinstance(part, ast.FormattedValue):
                    out.append(self.fold(part.value, seen) or "{}")
            return "".join(out)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
            left, right = self.fold(node.left, seen), self.fold(node.right, seen)
            if left is None or right is None:
                return None
            return left + ("/" if isinstance(node.op, ast.Div) else "") + right
        if isinstance(node, ast.Attribute):
            named = self.canon(node)
            if named in ("os.pardir", "os.path.pardir"):
                return ".."
            if named in ("os.curdir", "os.path.curdir"):
                return "."
            return None
        if isinstance(node, ast.Call):
            name = self.canon(node.func)
            joinable = name == "os.path.join" or name.rsplit(".", 1)[-1] in _PATH_CTORS
            if joinable or (isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath"):
                args = list(node.args)
                if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
                    args = [node.func.value, *args]
                folded = [self.fold(a, seen) for a in args]
                return "/".join(folded) if folded and None not in folded else None
        return None


def _tool_name(token: str) -> str:
    if re.fullmatch(r"[A-Z][A-Za-z]+-[A-Z][A-Za-z]+", token):
        return "<cmdlet>"  # a PowerShell cmdlet: the host's own, like a shell builtin
    name = posixpath.basename(token.replace("\\", "/")).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if re.fullmatch(r"python[\d.]*|py(?:thon)?3?", name):
        return "python"
    return name


def _words_tools(words: list) -> list:
    """Tools one command line runs, looking through the commands that run commands:
    `bash -c 'git x'`, `cmd /c docker ps`, `env A=1 docker ps`. None marks a word that is
    not statically known."""
    if not words or words[0] is None:
        return [None]
    tool = _tool_name(words[0].strip("'\""))
    out: list = [tool]
    rest = words[1:]
    if tool in _SHELLS or tool in ("cmd", "powershell", "pwsh"):
        flags = {"-c"} if tool in _SHELLS else {"/c", "/k", "-c", "-command"}
        for index, word in enumerate(rest):
            if word is not None and word.lower() in flags and index + 1 < len(rest):
                first = index + 1
                tail = rest[first:]
                if None in tail:
                    out.append(None)
                else:
                    out += list(_shell_tools(" ".join(w.strip("'\"") for w in tail)))
                break
    elif tool in _WRAPPERS:
        for index, word in enumerate(rest):
            if word is None:
                out.append(None)
                break
            if word.startswith("-") or re.match(r"\w+=", word):
                continue
            out += _words_tools(rest[index:])
            break
    return out


def _shell_tools(text: str):
    """Every command in a shell string (`a && b | c`), through wrappers."""
    for segment in re.split(r"&&|\|\||[;|\n]", text):
        try:
            words = shlex.split(segment, posix=False)
        except ValueError:
            words = segment.split()
        if words:
            yield from _words_tools(words)


def _command_tools(mod: _Module, node):
    """Tool names a spawn call runs; [None] when the command cannot be resolved statically."""
    seen = 0
    while isinstance(node, ast.Name) and node.id in mod.env and seen < 8:
        node, seen = mod.env[node.id], seen + 1
    if isinstance(node, (ast.List, ast.Tuple)):
        if not node.elts:
            return [None]
        first = node.elts[0]
        if isinstance(first, ast.Attribute) and _dotted(first) == "sys.executable":
            return ["python"]
        return _words_tools([mod.fold(e) for e in node.elts])
    text = mod.fold(node)
    if text is None:
        return [None]
    return list(_shell_tools(text)) or [None]


def _python_findings(path: Path, text: str, ctx: _Ctx, depth: int):
    """(line, kind, token) for what a python file reaches. `violation` tokens are messages."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        yield getattr(exc, "lineno", 1) or 1, "violation", f"python does not parse ({exc})"
        return
    mod = _Module(tree, depth)
    reported: set = set()

    def module_reach(line: int, name: str):
        top = name.split(".")[0]
        if top in ctx.local:
            return None
        if top in ctx.owned:
            return (line, "module", name)
        if top == "pytest" and ctx.test_file:
            return None  # the runner a shipped test file needs is not a dependency of the mode
        if top not in ctx.stdlib:
            return (line, "package", top)  # third party: a pip install the mode must name
        return None

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                found = module_reach(line, alias.name)
                if found:
                    yield found
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found = module_reach(line, node.module)
                if found:
                    yield found
            elif node.level > depth:
                yield line, "violation", "relative import climbs above the pack directory"
        elif isinstance(node, ast.Subscript) and mod.canon(node.value) == "os.environ":
            key = mod.fold(node.slice)
            yield line, "env", key if key else "<dynamic>"
        elif isinstance(node, ast.Call):
            name = mod.canon(node.func)
            if name in ("os.getenv", "os.environ.get", "os.environ.setdefault", "os.environ.pop"):
                key = mod.fold(node.args[0]) if node.args else None
                yield line, "env", key if key else "<dynamic>"
            elif name in _DYNAMIC_IMPORT:
                target = mod.fold(node.args[0]) if node.args else None
                if target is None:
                    yield line, "violation", f"dynamic import that cannot be resolved ({name})"
                elif not target.startswith("."):
                    found = module_reach(line, target)
                    if found:
                        yield found
            elif name in _SPAWN or name in _SPAWN_FILE_FIRST or name in _SPAWN_FILE_SECOND:
                index = 1 if name in _SPAWN_FILE_SECOND else 0
                argument = node.args[index] if len(node.args) > index else None
                if argument is None:
                    argument = next((k.value for k in node.keywords if k.arg == "args"), None)
                tools = _command_tools(mod, argument) if argument is not None else [None]
                for tool in tools:
                    if tool is None:
                        yield line, "violation", f"command cannot be resolved statically ({name})"
                    else:
                        yield line, "tool", tool
            elif name.endswith("shutil.which") or name == "which":
                target = mod.fold(node.args[0]) if node.args else None
                if target:
                    yield line, "tool", _tool_name(target)
            elif name in _EXEC:
                source = mod.fold(node.args[0]) if node.args else None
                if source is None:
                    yield line, "violation", f"dynamic code that cannot be analysed ({name})"
                else:  # a literal program is read as the program it is
                    for _, kind, token in _python_findings(path, source, ctx, depth):
                        yield line, kind, token
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            segment = ast.get_source_segment(text, node)
            if segment is None or node.value not in segment:  # escapes or implicit concatenation
                for kind, token in _line_reaches(node.value, ctx, True):
                    yield line, kind, token
        if isinstance(node, (ast.Attribute, ast.Call, ast.BinOp, ast.Subscript)):
            level = mod.level(node)
            if level is not None and level < 0 and line not in reported:
                reported.add(line)
                yield line, "violation", "climbs above the pack directory"
        # A string built from parts: the parts may each be harmless and the whole not.
        if isinstance(node, (ast.BinOp, ast.JoinedStr, ast.Call)):
            folded = mod.fold(node)
            if folded and not isinstance(node, ast.Constant):
                for kind, token in _line_reaches(folded, ctx, True):
                    yield line, kind, token


def _notebook_source(text: str):
    """Code of an .ipynb as one python source; None when it is not a notebook."""
    try:
        cells = json.loads(text)["cells"]
    except (ValueError, KeyError, TypeError):
        return None
    lines: list[str] = []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        body = "".join(source) if isinstance(source, list) else str(source)
        for raw in body.splitlines():
            lines.append("pass" if raw.lstrip().startswith(("%", "!")) else raw)
    return "\n".join(lines)


# ------------------------------------------------------------------------------ the guard


def _load_metadata(mode_dir: Path):
    path = mode_dir / "metadata.yml"
    if not path.is_file():
        return None, f"{mode_dir.name}: no metadata.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return None, f"{mode_dir.name}: metadata.yml does not parse ({exc})"
    deps = data.get("dependencies")
    if not isinstance(deps, dict):
        return None, f"{mode_dir.name}: metadata.yml has no `dependencies` mapping"
    return deps, None


def _top_level_python(directory: Path) -> dict[str, Path]:
    """Names a directory contributes to the import path when it is on `sys.path`."""
    found: dict[str, Path] = {}
    if not directory.is_dir():
        return found
    for child in sorted(directory.iterdir()):
        name = child.name
        if name.startswith((".", "__")):
            continue
        if child.is_file() and child.suffix.lower() in _PYTHON_SUFFIXES:
            if child.stem.isidentifier():
                found[child.stem] = child
        elif child.is_dir() and not _is_link(child):
            # An importable name: a package, or a directory holding modules (a namespace
            # package). A directory of subdirectories (`modes/`) is a folder, not a name.
            if (child / "__init__.py").is_file() or any(child.glob("*.py")):
                found[name] = child
    return found


def _script_directories(pack_dir: Path):
    """The pack root and every directory that holds scripts without being a package: the
    places a running script finds its siblings by name."""
    yield pack_dir
    for dirpath, dirnames, filenames in os.walk(pack_dir, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if here != pack_dir and "__init__.py" not in filenames:
            if any(f.lower().endswith(".py") for f in filenames):
                yield here


def _shadow_findings(pack_dir: Path, ctx_owned: frozenset):
    stdlib = _stdlib()
    for directory in _script_directories(pack_dir):
        for stem, child in _top_level_python(directory).items():
            where = child.relative_to(pack_dir).as_posix()
            if stem in ctx_owned:
                yield f"{where}: top-level name shadows the platform package `{stem}`"
            elif stem in stdlib:
                yield f"{where}: top-level name shadows the standard-library module `{stem}`"


def top_level_python_names(pack_dir: Path) -> set[str]:
    """Importable top-level names of a pack: what it puts on the import path."""
    return set(_top_level_python(pack_dir))


def cross_pack_collisions(packs: dict[str, Path]) -> list[str]:
    """Top-level python names two packs both own. Extracted side by side, they collide."""
    owners: dict[str, list[str]] = {}
    for name, directory in packs.items():
        for stem in top_level_python_names(directory):
            owners.setdefault(stem, []).append(name)
    return [
        f"top-level python name `{stem}` is defined by packs {sorted(names)}"
        for stem, names in sorted(owners.items())
        if len(names) > 1
    ]


def pack_violations(pack_dir: Path, modes: list[str], root: Path) -> list[str]:
    """Every way `pack_dir` reaches outside itself or declares a dependency falsely."""
    out: list[str] = []
    if not pack_dir.is_dir():
        return [f"{pack_dir}: pack directory does not exist"]
    if not (pack_dir / "SKILL.md").is_file():
        out.append(f"{pack_dir.name}: no SKILL.md at the pack root")

    owned, packages, layout, layout_files = _platform_names(root)
    out.extend(_shadow_findings(pack_dir, owned))

    deps_by_mode: dict[str, dict] = {}
    for mode in modes:
        mode_dir = pack_dir / "modes" / mode
        if not (mode_dir / "SKILL.md").is_file():
            out.append(f"modes/{mode}: declared mode has no SKILL.md")
            continue
        deps, problem = _load_metadata(mode_dir)
        if problem:
            out.append(f"modes/{mode}: {problem}")
            continue
        for key in DEPENDENCY_KEYS:
            if not isinstance(deps.get(key), list):
                out.append(f"modes/{mode}/metadata.yml: dependencies.{key} must be a list")
        deps_by_mode[mode] = deps
        for entry in deps.get("files_required") or []:
            entry = str(entry).replace("\\", "/")
            if entry.startswith("~/"):
                if not entry.startswith("~/.dream-studio/"):
                    out.append(
                        f"modes/{mode}/metadata.yml: files_required `{entry}` is outside ~/.dream-studio/"
                    )
            elif entry.startswith(".planning/"):
                continue
            else:
                norm = _normalise(entry.split("/"))
                if norm is None or not _inside_exists(pack_dir, norm):
                    out.append(
                        f"modes/{mode}/metadata.yml: files_required `{entry}` does not exist in the pack"
                    )

    pack_names = _top_level_python(pack_dir)
    for path, is_link in _walk(pack_dir):
        rel = path.relative_to(pack_dir)
        where = rel.as_posix()
        if is_link:
            problem = _symlink_finding(path, pack_dir)
            if problem:
                out.append(f"{where}: {problem}")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            out.append(f"{where}: unreadable ({exc.__class__.__name__})")
            continue
        if data.startswith(_ARCHIVE_MAGIC) or data[257:262] == b"ustar":
            out.append(f"{where}: archive file: its contents are not scanned, ship the files")
            continue
        text = _decode(data)
        if text is None:
            continue  # a real binary: no text to read
        parts = rel.parts
        mode = (
            parts[1]
            if len(parts) > 2 and parts[0] == "modes" and parts[1] in deps_by_mode
            else None
        )
        if rel.name == "metadata.yml" and mode:
            continue  # the declaration itself names what it declares

        local = frozenset(pack_names) | frozenset(_top_level_python(path.parent))
        ctx = _Ctx(
            pack_dir=pack_dir,
            pack_name=pack_dir.name,
            owned=owned,
            packages=packages,
            layout=layout | LAYOUT_EXTRA,
            layout_files=layout_files,
            packs=_pack_names(),
            local=local,
            stdlib=_stdlib(),
            rel_dir=tuple(parts[:-1]),
            test_file=bool(re.fullmatch(r"(?:test_.*|.*_test|conftest)\.py", rel.name)),
        )
        python = _is_python(path, text)
        notebook = path.suffix.lower() == ".ipynb"

        reaches: list[tuple[int, str, str]] = []
        lines = text.splitlines()
        shell = [] if (python or notebook) else _shell_flags(path, lines)
        continued = False  # the previous shell line ended in a line continuation
        for number, line in enumerate(lines, start=1):
            for kind, token in _line_reaches(line, ctx, python or notebook):
                reaches.append((number, kind, token))
            if not (python or notebook):
                tools = _inline_tools(line)
                if shell[number - 1]:
                    if not continued:
                        tools += _shell_line_tools(line)
                    continued = line.rstrip().endswith(("\\", "`", "^"))
                else:
                    continued = False
                reaches += [(number, "tool", tool) for tool in tools]
        if python:
            reaches += list(_python_findings(path, text, ctx, len(parts)))
        elif notebook:
            source = _notebook_source(text)
            if source is not None:
                reaches += list(_python_findings(path, source, ctx, 0))

        owners = [mode] if mode else _owning_modes(where, deps_by_mode)
        declared = _declared([deps_by_mode[m] for m in owners])
        for number, kind, token in reaches:
            if kind == "violation":
                out.append(f"{where}:{number}: {token}")
                continue
            if kind == "tool" and token == "python":
                continue  # the interpreter that is already running the pack
            if not owners:
                ok = False
            elif kind == "package":
                ok = _package_declared(token, declared["package"])
            elif kind in ("tool", "skill", "agent", "env"):
                ok = token in declared[kind]
            else:
                ok = _covered(token, declared[kind])
            if not ok:
                owner = (
                    ", ".join(f"modes/{m}/metadata.yml" for m in owners)
                    if owners
                    else "no declaration is possible in a pack-level file"
                )
                label = {"env": "env var", "agent": "agent", "package": "python package"}.get(
                    kind, kind
                )
                out.append(f"{where}:{number}: undeclared {label} reach `{token}` ({owner})")
    return list(dict.fromkeys(out))


def _owning_modes(where: str, deps_by_mode: dict) -> list[str]:
    """The modes that declare a pack-level file in `files_required`: the file is theirs, so
    what it reaches is judged against what they declare. A file no mode claims may reach
    nothing, as before."""
    owners = []
    for mode, deps in deps_by_mode.items():
        for entry in deps.get("files_required") or []:
            entry = str(entry).replace("\\", "/").strip("/")
            if entry and not entry.startswith(("~", ".planning")):
                if where == entry or where.startswith(entry + "/"):
                    owners.append(mode)
                    break
    return owners


def _declared(deps_list: list[dict]) -> dict[str, list[str]]:
    """What the owning modes' metadata declares, by the kind of reach it covers."""

    def listed(key: str) -> list:
        return [e for deps in deps_list for e in deps.get(key) or []]

    return {
        "state": [str(e) for e in listed("files_required")],
        "module": [str(e) for e in listed("core_modules")],
        "tool": [_tool_name(str(e)) for e in listed("tools_required") + listed("tools_optional")],
        "package": [str(e) for e in listed("python_packages")],
        "skill": [
            ("" if str(e).startswith("ds-") else "ds-") + str(e).split(":")[0].lower()
            for e in listed("calls_skills")
            if not str(e).startswith("agent:")
        ],
        "agent": [
            str(e).split(":", 1)[1] for e in listed("calls_skills") if str(e).startswith("agent:")
        ],
        "env": [str(e) for e in listed("env_vars_required")],
    }


def _dist_name(name: str) -> str:
    """A distribution name, normalised the way pip compares them, version specifier dropped."""
    return re.sub(r"[-_.]+", "-", re.split(r"[<>=!~;\[\s(]", str(name).strip(), 1)[0]).lower()


def _package_declared(top: str, declared: list[str]) -> bool:
    """An import of `top` is declared when `python_packages` names the distribution that
    provides it (asked of the installed environment) or the import name itself."""
    try:
        from importlib.metadata import packages_distributions

        providers = packages_distributions().get(top, [])
    except Exception:  # noqa: BLE001 - metadata trouble must not hide a finding
        providers = []
    wanted = {_dist_name(top), _dist_name(_PACKAGE_MAP.get(top, top))}
    wanted |= {_dist_name(p) for p in providers}
    return any(_dist_name(d) in wanted for d in declared)


def _enrolled_pack(name: str):
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    return packs.get(name)


def _files(pack_dir: Path):
    """Every regular, non-linked file the guard reads (for the "reads a real pack" check)."""
    for path, is_link in _walk(pack_dir):
        if not is_link:
            yield path


# ------------------------------------------------------------------------ the real packs


@pytest.mark.parametrize("name", ENROLLED_PACKS)
def test_enrolled_pack_exists(name):
    """Enrolled and missing is a failure, never a skip: a typo here must not read as a pass."""
    spec = _enrolled_pack(name)
    assert spec is not None, f"`{name}` is enrolled but packs.yaml has no such pack"
    pack_dir = _pack_dir_for(name, spec, REPO_ROOT)
    assert pack_dir.is_dir(), f"`{name}` is enrolled but {pack_dir} does not exist"
    assert spec.get("modes"), f"`{name}` is enrolled but declares no modes"


@pytest.mark.parametrize("name", ENROLLED_PACKS)
def test_enrolled_pack_is_self_contained(name):
    spec = _enrolled_pack(name)
    assert spec is not None, f"`{name}` is enrolled but packs.yaml has no such pack"
    found = pack_violations(
        _pack_dir_for(name, spec, REPO_ROOT), list(spec.get("modes") or []), REPO_ROOT
    )
    assert found == [], (
        f"pack `{name}` reaches outside its own directory or declares its dependencies falsely "
        "(docs/contracts/pack-capability-contract.md):\n  " + "\n  ".join(found)
    )


def test_the_guard_reads_a_real_pack():
    """A guard that walked an empty tree would pass on nothing."""
    spec = _enrolled_pack("analyze")
    pack_dir = _pack_dir_for("analyze", spec, REPO_ROOT)
    assert len(list(_files(pack_dir))) > 50
    assert {"multi", "repo", "intelligence"} <= set(spec["modes"])


# ------------------------------------------------------- the detector, on synthetic packs


def _pack(tmp_path: Path, *, mode_text="Plain prose.\n", deps=None, extra=None) -> Path:
    """A pack with one mode that breaks nothing; `extra` maps relative path -> content."""
    pack = tmp_path / "canonical" / "skills" / "demo"
    mode = pack / "modes" / "m"
    mode.mkdir(parents=True)
    (pack / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (mode / "SKILL.md").write_text(mode_text, encoding="utf-8")
    deps = {k: [] for k in DEPENDENCY_KEYS} | (deps or {})
    (mode / "metadata.yml").write_text(
        yaml.safe_dump({"name": "m", "dependencies": deps}), encoding="utf-8"
    )
    for rel, content in (extra or {}).items():
        target = pack / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return pack


def _run(pack: Path, tmp_path: Path) -> list[str]:
    return pack_violations(pack, ["m"], tmp_path)


def test_a_clean_pack_has_no_violations(tmp_path):
    pack = _pack(
        tmp_path,
        mode_text="Read `modes.yml`. Write ~/.dream-studio/demo/state.json. Run `ds status`.\n"
        'from control.analysis.engine import run\nSkill(skill="ds-quality")\n',
        deps={
            "files_required": ["modes.yml", "~/.dream-studio/demo/"],
            "tools_optional": ["ds"],
            "core_modules": ["control.analysis.engine"],
            "calls_skills": ["ds-quality:harden"],
        },
        extra={"modes.yml": "a: 1\n"},
    )
    assert _run(pack, tmp_path) == []


BAD_CASES = {
    "checkout templates dir": (
        {"mode_text": "Load builds/dream-studio-clean/templates/x.md for the format.\n"},
        "builds/dream-studio",
    ),
    "repo level templates": ({"mode_text": "Read templates/report.md first.\n"}, "checkout path"),
    "canonical path": ({"mode_text": "See canonical/skills/demo/x.md.\n"}, "checkout path"),
    "skills layout path": ({"mode_text": "Read skills/demo/modes.yml.\n"}, "checkout path"),
    "user absolute path": ({"mode_text": "Open C:\\Users\\someone\\x.md.\n"}, "user-specific path"),
    "host install path": ({"mode_text": "Dispatch ~/.claude/agents/a.md.\n"}, "host install path"),
    "undeclared state": ({"mode_text": "Write ~/.dream-studio/demo/a.json.\n"}, "undeclared state"),
    "undeclared planning dir": ({"mode_text": "Write .planning/specs/x.md.\n"}, "undeclared state"),
    "undeclared module (dotted)": (
        {"mode_text": "Call control.analysis.engine now.\n"},
        "undeclared module",
    ),
    "undeclared module (slash)": (
        {"mode_text": "Extend control/analysis/stacks/ here.\n"},
        "undeclared module",
    ),
    "undeclared import line": (
        {"mode_text": "from core.config.paths import x\n"},
        "undeclared module",
    ),
    "undeclared platform call": (
        {"mode_text": "Record it via insert_lesson(a, b).\n"},
        "undeclared module",
    ),
    "undeclared ds cli": ({"mode_text": "Run `ds lesson-queue list`.\n"}, "undeclared tool"),
    "undeclared other skill": ({"mode_text": 'Skill(skill="ds-quality")\n'}, "undeclared skill"),
    "python imports the platform": (
        {"extra": {"x.py": "from core.thing import y\n"}},
        "undeclared module",
    ),
    "python climbs out of the pack": (
        {"extra": {"x.py": "from pathlib import Path\nROOT = Path(__file__).parent.parent\n"}},
        "climbs above",
    ),
    "python parents index": (
        {"extra": {"x.py": "from pathlib import Path\nROOT = Path(__file__).parents[3]\n"}},
        "climbs above",
    ),
    "python shells out undeclared": (
        {"extra": {"modes/m/run.py": "import subprocess\nsubprocess.run(['git', 'clone'])\n"}},
        "undeclared tool",
    ),
    "pack-level file reaches state": (
        {"extra": {"shared.md": "Write ~/.dream-studio/x/y.json\n"}},
        "no declaration is possible",
    ),
    "shadowing package": ({"extra": {"core/__init__.py": ""}}, "shadows the platform package"),
    "metadata key missing": ({"deps": {"calls_skills": None}}, "must be a list"),
    "declared file absent": (
        {"deps": {"files_required": ["nope/gone.md"]}},
        "does not exist in the pack",
    ),
    "declared state outside home": (
        {"deps": {"files_required": ["~/elsewhere/x"]}},
        "outside ~/.dream-studio/",
    ),
}


@pytest.mark.parametrize("case", sorted(BAD_CASES))
def test_each_rule_catches_its_violation(case, tmp_path):
    kwargs, expected = BAD_CASES[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(
        expected in line for line in found
    ), f"{case}: expected a violation containing `{expected}`, got {found}"


def test_a_declaration_silences_exactly_what_it_names(tmp_path):
    """Declaring one state path must not excuse a different one."""
    pack = _pack(
        tmp_path,
        mode_text="Write ~/.dream-studio/demo/a.json and ~/.dream-studio/other/b.json.\n",
        deps={"files_required": ["~/.dream-studio/demo/"]},
    )
    found = _run(pack, tmp_path)
    assert len(found) == 1 and "other/b.json" in found[0], found


def test_a_missing_pack_is_a_violation_not_a_pass(tmp_path):
    assert any("does not exist" in v for v in pack_violations(tmp_path / "nope", ["m"], tmp_path))


# --------------------------------------------- evasions found by an outside verifier (#892)
#
# One synthetic pack per case, each breaking exactly one rule in a spelling the first
# version of this guard accepted. The expected substring is the contract: a case names
# the finding it must produce, so it cannot pass on an unrelated violation.

_NB_IMPORT_CORE = (
    '{"cells": [{"cell_type": "code", "metadata": {}, "outputs": [], "source": '
    '["from core.thing import y\\n"]}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'
)

EVASIONS = {
    # -- separators and case
    "windows separators: templates": (
        {"mode_text": "Read templates\\report.md first.\n"},
        "checkout path",
    ),
    "windows separators: canonical": (
        {"mode_text": "See canonical\\skills\\x for it.\n"},
        "checkout path",
    ),
    "case: Templates": ({"mode_text": "Read Templates/x.md first.\n"}, "checkout path"),
    "case: CANONICAL": ({"mode_text": "See CANONICAL/skills/x.md.\n"}, "checkout path"),
    # -- relative spellings
    "dot-slash templates": ({"mode_text": "Read ./templates/x.md first.\n"}, "checkout path"),
    "dotdot to templates": ({"mode_text": "Read ../../templates/x.md first.\n"}, "leaves the pack"),
    "dotdot to another pack": (
        {"mode_text": "See ../../other-pack/SKILL.md.\n"},
        "leaves the pack",
    ),
    "plugin root climb": (
        {"mode_text": "Read ${CLAUDE_PLUGIN_ROOT}/../../shared/x.md.\n"},
        "leaves the pack",
    ),
    "absolute /home path": ({"mode_text": "Open /home/dan/x.md.\n"}, "user-specific path"),
    # -- home and drive paths
    "drive path": ({"mode_text": "Open D:\\work\\x.md.\n"}, "user-specific path"),
    "$HOME/.claude": ({"mode_text": "Read $HOME/.claude/agents/a.md.\n"}, "host install path"),
    "$HOME/.dream-studio": (
        {"mode_text": "Write $HOME/.dream-studio/demo/a.json.\n"},
        "undeclared state",
    ),
    ".dream-studio without ~/": (
        {"mode_text": "Write .dream-studio/demo/a.json.\n"},
        "undeclared state",
    ),
    "~\\.dream-studio": (
        {"mode_text": "Write ~\\.dream-studio\\demo\\a.json.\n"},
        "undeclared state",
    ),
    ".planning with backslash": (
        {"mode_text": "Write .planning\\specs\\x.md.\n"},
        "undeclared state",
    ),
    # -- python path climbs
    "py: dirname chain": (
        {
            "extra": {
                "x.py": "import os\nROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))\n"
            }
        },
        "climbs above",
    ),
    "py: os.path.join with ..": (
        {"extra": {"x.py": "import os\nP = os.path.join(os.path.dirname(__file__), '..', '..')\n"}},
        "climbs above",
    ),
    "py: absolute().parent chain": (
        {
            "extra": {
                "x.py": "from pathlib import Path\nROOT = Path(__file__).absolute().parent.parent\n"
            }
        },
        "climbs above",
    ),
    "py: parent / '..'": (
        {"extra": {"x.py": "from pathlib import Path\nROOT = Path(__file__).parent / '..'\n"}},
        "climbs above",
    ),
    "py: sys.argv[0]": (
        {
            "extra": {
                "x.py": "import os, sys\nROOT = os.path.dirname(os.path.dirname(sys.argv[0]))\n"
            }
        },
        "climbs above",
    ),
    "py: chain split across lines": (
        {
            "extra": {
                "x.py": "from pathlib import Path\nROOT = (\n    Path(__file__)\n    .resolve()\n"
                "    .parent\n    .parent\n)\n"
            }
        },
        "climbs above",
    ),
    # -- python imports
    "py: importlib.import_module": (
        {"extra": {"x.py": "import importlib\nm = importlib.import_module('core.config.paths')\n"}},
        "undeclared module",
    ),
    "py: __import__": ({"extra": {"x.py": "m = __import__('core')\n"}}, "undeclared module"),
    "py: syntax error hides imports": (
        {"extra": {"x.py": "from core.thing import y\ndef broken(:\n"}},
        "does not parse",
    ),
    # -- reaches made by code
    "py: Path.home()/.dream-studio": (
        {"extra": {"x.py": "from pathlib import Path\nP = Path.home() / '.dream-studio' / 'x'\n"}},
        "undeclared state",
    ),
    "py: os.environ[...]": (
        {"extra": {"x.py": "import os\nH = os.environ['DREAM_STUDIO_HOME']\n"}},
        "undeclared env var",
    ),
    "py: os.system": (
        {"extra": {"x.py": "import os\nos.system('git status')\n"}},
        "undeclared tool",
    ),
    "py: subprocess shell=True": (
        {"extra": {"x.py": "import subprocess\nsubprocess.run('git status', shell=True)\n"}},
        "undeclared tool",
    ),
    "py: command in a variable": (
        {"extra": {"x.py": "import subprocess\ncmd = ['git', 'status']\nsubprocess.run(cmd)\n"}},
        "undeclared tool",
    ),
    # -- files the suffix list skipped
    "unscanned .sh": ({"extra": {"run.sh": "cat templates/report.md\n"}}, "checkout path"),
    "unscanned .ps1": (
        {"extra": {"run.ps1": "Get-Content templates\\report.md\n"}},
        "checkout path",
    ),
    "unscanned .js": ({"extra": {"x.js": "const t = 'templates/report.md';\n"}}, "checkout path"),
    "unscanned .html": (
        {"extra": {"x.html": "<a href='canonical/skills/x'>x</a>\n"}},
        "checkout path",
    ),
    "unscanned .j2": ({"extra": {"x.md.j2": "Read templates/report.md\n"}}, "checkout path"),
    "unscanned .csv": ({"extra": {"x.csv": "path\ntemplates/report.md\n"}}, "checkout path"),
    "unscanned .pyi": ({"extra": {"x.pyi": "from core.thing import y\n"}}, "undeclared module"),
    "unscanned .ipynb": ({"extra": {"x.ipynb": _NB_IMPORT_CORE}}, "undeclared module"),
    "unscanned extensionless": (
        {"extra": {"NOTES": "Read templates/report.md\n"}},
        "checkout path",
    ),
    "unscanned .PY": ({"extra": {"x.PY": "from core.thing import y\n"}}, "undeclared module"),
    "unscanned .MD": ({"extra": {"X.MD": "Read templates/report.md\n"}}, "checkout path"),
    # -- prose
    "prose: ds --help": ({"mode_text": "Run `ds --help` to list commands.\n"}, "undeclared tool"),
    "prose: ./ds status": ({"mode_text": "Run `./ds status` first.\n"}, "undeclared tool"),
    "prose: Skill(skill='DS-quality')": (
        {"mode_text": "Skill(skill='DS-quality')\n"},
        "undeclared skill",
    ),
    "prose: /quality:harden": ({"mode_text": "Then run /quality:harden.\n"}, "undeclared skill"),
    "prose: dream-studio:quality": (
        {"mode_text": "Invoke dream-studio:quality next.\n"},
        "undeclared skill",
    ),
    "prose: Agent(subagent_type=)": (
        {"mode_text": "Agent(subagent_type='code-reviewer', prompt='x')\n"},
        "undeclared agent",
    ),
    "prose: docs/": ({"mode_text": "Read docs/ARCHITECTURE.md first.\n"}, "checkout path"),
    "prose: config/": ({"mode_text": "Edit config/settings.yml.\n"}, "checkout path"),
    "prose: scripts/": ({"mode_text": "Run scripts/build.sh.\n"}, "checkout path"),
    "prose: tools/": ({"mode_text": "Open tools/canonical_join.py.\n"}, "checkout path"),
    "prose: schemas/": ({"mode_text": "Validate against schemas/x.json.\n"}, "checkout path"),
    "prose: packs.yaml": ({"mode_text": "Check packs.yaml for the mode list.\n"}, "checkout path"),
    # -- shadowing
    "shadow: top-level json.py": ({"extra": {"json.py": "x = 1\n"}}, "shadows"),
    "shadow: namespace package core/": ({"extra": {"core/helper.py": "x = 1\n"}}, "shadows"),
}

#: Platform top-level names the first version's hand list omitted.
for _name in ("shared", "tools", "scripts", "emitters", "guardrails", "compat"):
    EVASIONS[f"py: from {_name} import"] = (
        {"extra": {"x.py": f"from {_name} import thing\n"}},
        "undeclared module",
    )


@pytest.mark.parametrize("case", sorted(EVASIONS))
def test_each_evasion_is_caught(case, tmp_path):
    kwargs, expected = EVASIONS[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(
        expected in line for line in found
    ), f"{case}: expected a violation containing `{expected}`, got {found}"


# ------------------------------- variants written for this hardening, none of them in the issue
#
# Written after reading the rule, not the issue's list: each is a spelling of "a reference
# that lands outside the pack" a reviewer could reach for next. Scored on first run before any
# fix: 45 of 45 for the first group, 10 of 29 for the second (full-width slashes, entities,
# implicit concatenation, `bash -c`, `exec`, archives ...), the rest fixed in the same commit.

OWN_VARIANTS_PATHS = {
    "mixed case and backslash: TEMPLATES\\Report.md": (
        {"mode_text": "Read  TEMPLATES\\Report.md now.\n"},
        "checkout path",
    ),
    "markdown link climbing three levels": (
        {"mode_text": "See [x](../../../docs/x.md).\n"},
        "leaves the pack",
    ),
    "file:/// URL to a user dir": (
        {"mode_text": "Open file:///C:/Users/dan/x.md.\n"},
        "user-specific path",
    ),
    "%USERPROFILE%\\.dream-studio": (
        {"mode_text": "Write %USERPROFILE%\\.dream-studio\\x.json.\n"},
        "undeclared state",
    ),
    "$env:USERPROFILE\\.claude": (
        {"mode_text": "Read $env:USERPROFILE\\.claude\\agents\\a.md.\n"},
        "host install path",
    ),
    "UNC path": ({"mode_text": "Open \\\\server\\share\\x.md.\n"}, "user-specific path"),
    "upper-case .DREAM-STUDIO": (
        {"mode_text": "Write ~/.DREAM-STUDIO/x.json.\n"},
        "undeclared state",
    ),
    "upper-case .Claude": ({"mode_text": "Read ~/.Claude/agents/a.md.\n"}, "host install path"),
    "Docs/ upper": ({"mode_text": "Read Docs/ARCHITECTURE.md.\n"}, "checkout path"),
    ".\\templates\\x": ({"mode_text": "Read .\\templates\\x.md.\n"}, "checkout path"),
    "inner .. that escapes: a/../../x": (
        {"mode_text": "Read a/../../../x/y.md.\n"},
        "leaves the pack",
    ),
    "PYTHONPATH=../../..": (
        {"extra": {"run.sh": "PYTHONPATH=../../.. python x.py\n"}},
        "leaves the pack",
    ),
    "JS require('../../../shared/x')": (
        {"extra": {"x.js": "const s = require('../../../shared/x');\n"}},
        "leaves the pack",
    ),
    "yaml value ../../../templates/x": (
        {"extra": {"conf.yml": "path: ../../../templates/x.md\n"}},
        "leaves the pack",
    ),
    "json escaped C:\\\\Users": (
        {"extra": {"c.json": '{"p": "C:\\\\Users\\\\dan\\\\x"}\n'}},
        "user-specific path",
    ),
    "BOM utf-8 file": ({"extra": {"b.md": b"\xef\xbb\xbfRead templates/x.md\n"}}, "checkout path"),
    "UTF-16 file with BOM": (
        {"extra": {"u.md": "Read templates/x.md\n".encode("utf-16")}},
        "checkout path",
    ),
    "CRLF python": ({"extra": {"c.py": b"from core.x import y\r\n"}}, "undeclared module"),
    "py: import core.thing as c": (
        {"extra": {"x.py": "import core.thing as c\n"}},
        "undeclared module",
    ),
    "py: parenthesised from-import": (
        {"extra": {"x.py": "from core import (\n    a,\n    b,\n)\n"}},
        "undeclared module",
    ),
    "py: relative import climbs": (
        {"extra": {"modes/m/r.py": "from .... import x\n"}},
        "climbs above",
    ),
    "py: import_module(non-const)": (
        {"extra": {"x.py": "import importlib, sys\nimportlib.import_module(sys.argv[1])\n"}},
        "dynamic import",
    ),
    "py: alias of import_module": (
        {"extra": {"x.py": "import importlib\nimp = importlib.import_module\nimp('core.x')\n"}},
        "undeclared module",
    ),
    "py: import importlib as il": (
        {"extra": {"x.py": "import importlib as il\nil.import_module('core.x')\n"}},
        "undeclared module",
    ),
    "py: runpy.run_module": (
        {"extra": {"x.py": "import runpy\nrunpy.run_module('core.x')\n"}},
        "undeclared module",
    ),
    "py: concat building ~/.dream-studio": (
        {"extra": {"x.py": "P = '~/.dream-' + 'studio/x'\n"}},
        "undeclared state",
    ),
    "py: f-string home": (
        {"extra": {"x.py": "home = 'h'\nP = f'{home}/.dream-studio/x'\n"}},
        "undeclared state",
    ),
    "py: expanduser join": (
        {
            "extra": {
                "x.py": "import os\nP = os.path.join(os.path.expanduser('~'), '.dream-studio')\n"
            }
        },
        "undeclared state",
    ),
    "py: parents[5] in a deep file": (
        {"extra": {"modes/m/d.py": "from pathlib import Path\nR = Path(__file__).parents[5]\n"}},
        "climbs above",
    ),
    "py: variable chain": (
        {
            "extra": {
                "x.py": "from pathlib import Path\nHERE = Path(__file__).resolve().parent\nROOT = HERE.parent\n"
            }
        },
        "climbs above",
    ),
    "py: os.getenv": (
        {"extra": {"x.py": "import os\nv = os.getenv('HOME_DIR')\n"}},
        "undeclared env var",
    ),
    "py: os.environ.get": (
        {"extra": {"x.py": "import os\nv = os.environ.get('X', '')\n"}},
        "undeclared env var",
    ),
    "py: shutil.which": (
        {"extra": {"x.py": "import shutil\nshutil.which('docker')\n"}},
        "undeclared tool",
    ),
    "py: from subprocess import run": (
        {"extra": {"x.py": "from subprocess import run\nrun(['docker', 'ps'])\n"}},
        "undeclared tool",
    ),
    "py: subprocess aliased": (
        {"extra": {"x.py": "import subprocess as sp\nsp.Popen(['curl', 'x'])\n"}},
        "undeclared tool",
    ),
    "py: subprocess of argv": (
        {"extra": {"x.py": "import subprocess, sys\nsubprocess.run(sys.argv[1:])\n"}},
        "cannot be resolved",
    ),
    "py: spec_from_file_location above": (
        {
            "extra": {
                "x.py": "import importlib.util as u\nfrom pathlib import Path\ns = u.spec_from_file_location('x', Path(__file__).parent.parent / 'x.py')\n"
            }
        },
        "climbs above",
    ),
    "py: sys.path.insert above": (
        {
            "extra": {
                "x.py": "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            }
        },
        "climbs above",
    ),
    "shadow: stdlib module in a script dir": (
        {"extra": {"modes/m/random.py": "x = 1\n"}},
        "shadows",
    ),
    "shadow: code.py at the root": ({"extra": {"code.py": "x = 1\n"}}, "shadows"),
    "shadow: package named like platform with init": (
        {"extra": {"runtime/__init__.py": ""}},
        "shadows",
    ),
    "notebook with os.system": (
        {
            "extra": {
                "n.ipynb": '{"cells":[{"cell_type":"code","source":["import os\\n","os.system(\'git x\')"]}]}'
            }
        },
        "undeclared tool",
    ),
    "html script src": (
        {"extra": {"p.html": '<script src="../../../shared/x.js"></script>\n'}},
        "leaves the pack",
    ),
    "toml path": ({"extra": {"c.toml": 'p = "docs/x.md"\n'}}, "checkout path"),
    "dockerfile COPY": ({"extra": {"Dockerfile": "COPY templates/x.md /x\n"}}, "checkout path"),
}

OWN_VARIANTS_CODE = {
    "zero-width space inside .dream-studio": (
        {"mode_text": "Write ~/.dream\u200b-studio/x.json.\n"},
        "undeclared state",
    ),
    "fullwidth slash in templates": ({"mode_text": "Read templates\uff0fx.md.\n"}, "checkout path"),
    "division slash in templates": ({"mode_text": "Read templates\u2215x.md.\n"}, "checkout path"),
    "percent-encoded dotdot": (
        {"mode_text": "Read %2e%2e/%2e%2e/%2e%2e/templates/x.md.\n"},
        "leaves the pack",
    ),
    "html entity dots": (
        {"extra": {"p.html": '<a href="&#46;&#46;/&#46;&#46;/&#46;&#46;/x.md">x</a>\n'}},
        "leaves the pack",
    ),
    "py: string with \\x escapes": (
        {"extra": {"x.py": "P = '\\x7e/.dream-studio/x'\n"}},
        "undeclared state",
    ),
    "py: implicit concatenation": (
        {"extra": {"x.py": "P = ('~/.dream-'\n     'studio/x')\n"}},
        "undeclared state",
    ),
    "py: os.pardir": (
        {"extra": {"x.py": "import os\nP = os.path.join(os.path.dirname(__file__), os.pardir)\n"}},
        "climbs above",
    ),
    "py: env var built by concatenation": (
        {"extra": {"x.py": "import os\nv = os.environ['DREAM' + '_STUDIO_HOME']\n"}},
        "undeclared env var",
    ),
    "py: bash -c git": (
        {"extra": {"x.py": "import subprocess\nsubprocess.run(['bash', '-c', 'git status'])\n"}},
        "reach `git`",
    ),
    "py: env wrapper": (
        {
            "extra": {
                "x.py": "import subprocess\nsubprocess.run(['env', 'FOO=1', 'docker', 'ps'])\n"
            }
        },
        "reach `docker`",
    ),
    "py: cmd /c": (
        {"extra": {"x.py": "import os\nos.system('cmd /c docker ps')\n"}},
        "reach `docker`",
    ),
    "py: os.popen": ({"extra": {"x.py": "import os\nos.popen('git log')\n"}}, "undeclared tool"),
    "py: asyncio subprocess": (
        {"extra": {"x.py": "import asyncio\nasyncio.create_subprocess_exec('git', 'log')\n"}},
        "undeclared tool",
    ),
    "py: os.chdir above": (
        {"extra": {"x.py": "import os\nos.chdir('../..')\n"}},
        "leaves the pack",
    ),
    "py: __file__ via module attribute": (
        {
            "extra": {
                "x.py": "import sys, os\nP = os.path.dirname(os.path.dirname(sys.modules[__name__].__file__))\n"
            }
        },
        "climbs above",
    ),
    "py: pathlib.Path with .. string": (
        {"extra": {"x.py": "from pathlib import Path\nP = Path('../x')\n"}},
        "leaves the pack",
    ),
    "py: glob above": (
        {"extra": {"x.py": "import glob\nglob.glob('../../**/*.md')\n"}},
        "leaves the pack",
    ),
    "py: open absolute home": (
        {"extra": {"x.py": "open('/home/dan/x.txt')\n"}},
        "user-specific path",
    ),
    "py: __import__ with concatenation": (
        {"extra": {"x.py": "m = __import__('co' + 're')\n"}},
        "undeclared module",
    ),
    "py: importlib.util.find_spec": (
        {"extra": {"x.py": "import importlib.util\nimportlib.util.find_spec('core.x')\n"}},
        "undeclared module",
    ),
    "py: exec of import": (
        {"extra": {"x.py": "exec('from core.x import y')\n"}},
        "undeclared module",
    ),
    "py: eval of dynamic": ({"extra": {"x.py": "import sys\nexec(sys.argv[1])\n"}}, "dynamic"),
    "py: pth file import": ({"extra": {"site.pth": "import core.x\n"}}, "undeclared module"),
    "py: json-encoded path in .json": (
        {"extra": {"a.json": '{"cmd": "python ../../../scripts/x.py"}\n'}},
        "leaves the pack",
    ),
    "zip archive holding a layout": (
        {"extra": {"a.zip": b"PK\x03\x04\x00\x00templates/x.md"}},
        "archive",
    ),
}


@pytest.mark.parametrize("case", sorted(OWN_VARIANTS_PATHS))
def test_own_variant_paths_are_caught(case, tmp_path):
    kwargs, expected = OWN_VARIANTS_PATHS[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(expected in line for line in found), f"{case}: wanted `{expected}`, got {found}"


@pytest.mark.parametrize("case", sorted(OWN_VARIANTS_CODE))
def test_own_variant_code_is_caught(case, tmp_path):
    kwargs, expected = OWN_VARIANTS_CODE[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(expected in line for line in found), f"{case}: wanted `{expected}`, got {found}"


# ------------------------------------------------ what the guard must NOT flag (false positives)
#
# A guard that flags everything is one people learn to silence. Each of these is ordinary
# pack content that touches the same spellings the rules look for.

LEGIT = {
    "link to a sibling mode inside the pack": {
        "mode_text": "See [other](../n/SKILL.md) and [self](./SKILL.md).\n",
        "extra": {"modes/n/SKILL.md": "# n\n"},
    },
    "pack-relative path that exists": {
        "mode_text": "Read modes.yml and `domains/x.md`.\n",
        "extra": {"modes.yml": "a: 1\n", "domains/x.md": "# x\n"},
    },
    "the pack has its own templates/ directory": {
        "mode_text": "Fill `templates/report.md`, or Templates\\report.md.\n",
        "extra": {"templates/report.md": "# r\n"},
    },
    "urls carry platform names": {
        "mode_text": "See https://github.com/org/repo/blob/main/docs/x.md and git@github.com:o/r.git.\n"
        "Also http://localhost:8000/config/settings and https://example.com/templates/x.\n",
    },
    "a user's own paths": {
        "mode_text": "Clone to ~/repos/x or ~/builds/my-app, or /path/to/repo, or ./my-repo.\n",
    },
    "tests and examples are the analysed repo's directories": {
        "mode_text": "Look under tests/unit and examples/basic.\n",
    },
    "ordinary words with a slash": {
        "mode_text": "Pass/fail, and/or input/output, client/server, 24/7, either/or.\n",
    },
    "a dot-dot that stays inside the pack": {
        "mode_text": "Back up one level: ../n/SKILL.md.\n",
        "extra": {"modes/n/SKILL.md": "# n\n"},
    },
    "python in the pack, inside the pack": {
        "extra": {
            "modes/m/run.py": (
                "import json\nimport sys\nfrom pathlib import Path\n"
                "ROOT = Path(__file__).parent.parent.parent\n"
                "sys.path.insert(0, str(ROOT))\nHERE = Path(__file__).resolve().parent\n"
                "DATA = ROOT / 'data.json'\nprint(json.dumps({}), HERE, DATA)\n"
            ),
            "data.json": "{}\n",
        }
    },
    "python imports a sibling module": {
        "extra": {"helper.py": "X = 1\n", "x.py": "import helper\nfrom helper import X\n"},
    },
    "a command that is python": {
        "extra": {
            "x.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n"
        },
    },
    "the pack's own skill id": {"mode_text": 'Skill(skill="ds-demo") and /demo:m.\n'},
    "an environment variable that is declared": {
        "extra": {"modes/m/x.py": "import os\nv = os.environ['DEMO_KEY']\n"},
        "deps": {"env_vars_required": ["DEMO_KEY"]},
    },
    "a real binary mentioning a layout path": {
        "extra": {
            "img.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00templates/x.md\x00\x00from core import x\n"
        },
    },
}


@pytest.mark.parametrize("case", sorted(LEGIT))
def test_ordinary_pack_content_is_not_flagged(case, tmp_path):
    found = _run(_pack(tmp_path, **LEGIT[case]), tmp_path)
    assert found == [], f"{case}: {found}"


def test_a_binary_is_skipped_by_content_not_by_name(tmp_path):
    """A text file named `.png` is read; a binary named `.md` is not."""
    pack = _pack(
        tmp_path,
        extra={
            "fake.png": "Read templates/x.md\n",
            "blob.md": b"\x00\x01\x02templates/x.md\x00",
        },
    )
    found = _run(pack, tmp_path)
    assert any("fake.png" in line and "checkout path" in line for line in found), found
    assert not any("blob.md" in line for line in found), found


def test_an_archive_is_refused_not_trusted(tmp_path):
    found = _run(_pack(tmp_path, extra={"a.zip": b"PK\x03\x04\x00\x00data"}), tmp_path)
    assert any("a.zip" in line and "archive" in line for line in found), found


# ------------------------------------------------------------- links that leave the pack


def _link(link: Path, target: Path) -> bool:
    """Make a directory link. A junction needs no privilege on Windows; a symlink does
    (WinError 1314). Returns False when neither can be made, so the caller says UNVERIFIED."""
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt" and target.is_dir():
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
        )
        return done.returncode == 0
    return False


def test_a_link_out_of_the_pack_is_a_violation(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("templates/x.md\n", encoding="utf-8")
    pack = _pack(tmp_path)
    if not _link(pack / "escape", outside):
        pytest.skip("UNVERIFIED: this host cannot create a symlink or a junction")
    found = _run(pack, tmp_path)
    assert any("escape" in line and "outside the pack" in line for line in found), found


def test_a_link_to_nothing_is_a_violation(tmp_path):
    pack = _pack(tmp_path)
    gone = pack / "inner_target"  # inside the pack, so only "points at nothing" can name it
    gone.mkdir()
    if not _link(pack / "dangling", gone):
        pytest.skip("UNVERIFIED: this host cannot create a symlink or a junction")
    gone.rmdir()
    found = _run(pack, tmp_path)
    assert any("dangling" in line and "points at nothing" in line for line in found), found


def test_a_link_inside_the_pack_is_allowed(tmp_path):
    pack = _pack(tmp_path, extra={"real/x.md": "# x\n"})
    if not _link(pack / "alias", pack / "real"):
        pytest.skip("UNVERIFIED: this host cannot create a symlink or a junction")
    assert _run(pack, tmp_path) == []


def test_the_link_rule_itself_without_a_link(tmp_path):
    """When a host cannot make a link (WinError 1314) the rule must still be exercised: the
    verdict is a pure function of where a link points, so give it each case directly."""
    pack = _pack(tmp_path).resolve()
    outside = tmp_path.resolve() / "outside.md"
    assert "outside the pack" in (_link_verdict(True, outside, pack) or "")
    assert "outside the pack" in (_link_verdict(True, pack.parent, pack) or "")
    assert "points at nothing" in (_link_verdict(False, pack / "x", pack) or "")
    assert _link_verdict(True, pack / "modes" / "m", pack) is None
    assert _link_verdict(True, pack, pack) is None
    # and a path that is not a link at all passes through the real resolution unchanged
    assert _symlink_finding(pack / "SKILL.md", pack) is None


# ------------------------------------------- what the guard knows comes from the repository


def test_platform_names_are_read_from_the_repository_not_listed():
    owned, packages, layout, layout_files = _platform_names(REPO_ROOT)
    # the names the first version's hand list omitted
    assert {"shared", "tools", "scripts", "emitters", "guardrails", "compat"} <= owned
    assert {"core", "control", "interfaces", "integrations", "runtime"} <= packages
    assert {"docs", "config", "scripts", "tools", "schemas", "templates", "canonical"} <= layout
    assert "packs.yaml" in layout_files
    assert not {"tests", "examples"} & layout, "ordinary names in an analysed repo"


def test_a_new_top_level_package_is_covered_the_day_it_lands(tmp_path):
    """No list to update: a package that appears beside the pack is a platform name."""
    (tmp_path / "brand_new_pkg").mkdir()
    (tmp_path / "brand_new_pkg" / "__init__.py").write_text("", encoding="utf-8")
    pack = _pack(tmp_path, extra={"x.py": "from brand_new_pkg import thing\n"})
    found = _run(pack, tmp_path)
    assert any("undeclared module" in line and "brand_new_pkg" in line for line in found), found


def test_stdlib_names_come_from_the_interpreter():
    assert {"json", "os", "random", "code", "types"} <= set(_stdlib())


def test_pack_names_come_from_packs_yaml():
    assert {"quality", "analyze", "core"} <= set(_pack_names())


# ---------------------------------------------- packs that sit side by side must not collide


def test_cross_pack_collision_is_found(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for pack in (a, b):
        (pack / "domains").mkdir(parents=True)
        (pack / "domains" / "x.py").write_text("X = 1\n", encoding="utf-8")
    (a / "only_a.py").write_text("X = 1\n", encoding="utf-8")
    found = cross_pack_collisions({"a": a, "b": b})
    assert len(found) == 1 and "`domains`" in found[0], found


def test_a_folder_of_folders_is_not_an_importable_name(tmp_path):
    (tmp_path / "modes" / "m").mkdir(parents=True)
    (tmp_path / "modes" / "m" / "run.py").write_text("X = 1\n", encoding="utf-8")
    assert top_level_python_names(tmp_path) == set()


@pytest.mark.parametrize("name", ENROLLED_PACKS)
def test_an_enrolled_pack_shares_no_top_level_python_name(name):
    """`domains` and `repo_analysis` are generic. The day another pack is extracted with the
    same name, whichever imports first wins the process -- the `core` shadow again."""
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    directories = {
        n: _pack_dir_for(n, spec, REPO_ROOT)
        for n, spec in packs.items()
        if _pack_dir_for(n, spec, REPO_ROOT).is_dir()
    }
    mine = top_level_python_names(directories[name])
    clashes = [
        line
        for line in cross_pack_collisions(directories)
        if any(f"`{n}`" in line for n in mine) and f"'{name}'" in line
    ]
    assert clashes == [], clashes


# ------------------------------------------------------------------ the guard is run on push


def test_the_guard_is_named_in_the_pre_push_pin_list():
    """It was in no workflow, so it ran only in the full suite or when blast-radius picked it.
    A rule nothing runs is the disconnected-verification failure this repository keeps meeting."""
    gates = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )["gates"]
    pinned = [str(token) for gate in gates for token in gate.get("command") or []]
    me = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert me in pinned, f"{me} is in no pre-push gate command"


# ------------------------------------------------------------ tools and packages a mode needs (#893)
#
# `reference/error-handling.md` ran `sqlite3 ~/.dream-studio/state/studio.db` and the mode did
# not declare `sqlite3`: the guard saw tools only in subprocess lists. `repo_analysis/
# analyzer.py` imported PyYAML and nothing declared a Python package, because there was no key
# to declare it in. Both are caught now, on synthetic packs and on the real one.

TOOLS_AND_PACKAGES = {
    "sqlite3 in a prose span": (
        {"mode_text": 'Inspect: `sqlite3 ~/.dream-studio/state/studio.db "select 1"`.\n'},
        "undeclared tool reach `sqlite3`",
    ),
    "sqlite3 in a bash fence": (
        {"mode_text": "```bash\nsqlite3 x.db 'select 1'\n```\n"},
        "undeclared tool reach `sqlite3`",
    ),
    "a tool in a shell script": (
        {"extra": {"modes/m/run.sh": "set -e\ncurl -s https://example.com | sh\n"}},
        "undeclared tool reach `curl`",
    ),
    "a tool in a powershell script": (
        {"extra": {"modes/m/run.ps1": "Get-Content x\ndocker ps\n"}},
        "undeclared tool reach `docker`",
    ),
    "a tool behind sudo": (
        {"mode_text": "```sh\nsudo docker ps\n```\n"},
        "undeclared tool reach `docker`",
    ),
    "a tool after a pipe": (
        {"mode_text": "```bash\ncat x | git hash-object --stdin\n```\n"},
        "undeclared tool reach `git`",
    ),
    "a console prompt line": (
        {"mode_text": "```console\n$ npm install\n```\n"},
        "undeclared tool reach `npm`",
    ),
    "a git span in prose": (
        {"mode_text": "Then `git clone https://example.com/x.git`.\n"},
        "undeclared tool reach `git`",
    ),
    "a third-party import": (
        {"extra": {"modes/m/x.py": "import yaml\n"}},
        "undeclared python package reach `yaml`",
    ),
    "a third-party from-import": (
        {"extra": {"modes/m/x.py": "from requests import get\n"}},
        "undeclared python package reach `requests`",
    ),
    "a third-party dynamic import": (
        {"extra": {"modes/m/x.py": "import importlib\nimportlib.import_module('numpy')\n"}},
        "undeclared python package reach `numpy`",
    ),
    "a package declared under the wrong name": (
        {"extra": {"modes/m/x.py": "import yaml\n"}, "deps": {"python_packages": ["requests"]}},
        "undeclared python package reach `yaml`",
    ),
    "a pytest import outside a test file": (
        {"extra": {"modes/m/helper.py": "import pytest\n"}},
        "undeclared python package reach `pytest`",
    ),
    "a pack-level import no mode claims": (
        {"extra": {"shared_code.py": "import yaml\n"}, "deps": {"python_packages": ["PyYAML"]}},
        "no declaration is possible in a pack-level file",
    ),
    "a claimed pack-level import the owner did not declare": (
        {
            "extra": {"lib/a.py": "import yaml\n"},
            "deps": {"files_required": ["lib/"], "python_packages": []},
        },
        "undeclared python package reach `yaml` (modes/m/metadata.yml)",
    ),
    "python_packages missing": ({"deps": {"python_packages": None}}, "must be a list"),
}


@pytest.mark.parametrize("case", sorted(TOOLS_AND_PACKAGES))
def test_a_tool_or_package_a_mode_needs_must_be_declared(case, tmp_path):
    kwargs, expected = TOOLS_AND_PACKAGES[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(expected in line for line in found), f"{case}: wanted `{expected}`, got {found}"


DECLARED_AND_FINE = {
    "sqlite3 declared": {
        "mode_text": "Inspect: `sqlite3 x.db 'select 1'`.\n```bash\nsqlite3 x.db .tables\n```\n",
        "deps": {"tools_required": ["python", "sqlite3"]},
    },
    "a tool declared optional": {
        "mode_text": "```bash\ngit status\n```\n",
        "deps": {"tools_optional": ["git"]},
    },
    "PyYAML declared for import yaml": {
        "extra": {"modes/m/x.py": "import yaml\n"},
        "deps": {"python_packages": ["PyYAML"]},
    },
    "a version specifier and an extra on the declaration": {
        "extra": {"modes/m/x.py": "import yaml\nimport requests\n"},
        "deps": {"python_packages": ["pyyaml>=6,<7", "requests[socks]"]},
    },
    "the standard library": {
        "extra": {"modes/m/x.py": "import json, re, subprocess, sys\nfrom pathlib import Path\n"},
    },
    "a sibling module of the pack": {
        "extra": {
            "modes/m/x.py": "import helper\nfrom helper import Y\n",
            "modes/m/helper.py": "Y = 1\n",
        },
    },
    "pytest in a test file": {"extra": {"test_thing.py": "import pytest\n"}},
    "a claimed pack-level import the owner declared": {
        "extra": {"lib/a.py": "import yaml\n"},
        "deps": {"files_required": ["lib/"], "python_packages": ["PyYAML"]},
    },
    "line continuations are one command": {
        "mode_text": "```bash\npy run.py \\\n    ~/repos/one \\\n    ~/repos/two\n```\n",
    },
    "a bare fence is prose, not shell": {
        "mode_text": "```\nanalyze_repositories() returns a dict\nTenant: x\n```\n",
    },
    "builtins and cmdlets are not external tools": {
        "mode_text": "```powershell\nGet-ChildItem . | Sort-Object Name\ncd x; ls; echo hi\n```\n",
    },
    "a mention of a tool is not a command": {"mode_text": "It needs `git` history to exist.\n"},
}


@pytest.mark.parametrize("case", sorted(DECLARED_AND_FINE))
def test_a_declared_need_is_not_flagged(case, tmp_path):
    found = _run(_pack(tmp_path, **DECLARED_AND_FINE[case]), tmp_path)
    assert found == [], f"{case}: {found}"


def test_python_packages_is_an_enforced_dependency_key():
    assert "python_packages" in DEPENDENCY_KEYS


def test_package_names_are_matched_the_way_pip_matches_them():
    assert _dist_name("PyYAML") == "pyyaml"
    assert _dist_name("python_dateutil>=2.8") == "python-dateutil"
    assert _dist_name("Requests[socks] ; python_version>'3'") == "requests"
    assert _package_declared("yaml", ["PyYAML"])
    assert _package_declared("PIL", ["pillow"])
    assert not _package_declared("yaml", ["requests"])
    assert not _package_declared("yaml", [])


# -------------------------------- the real analyze pack: reintroduce each defect, the guard says so


def _real_pack_copy(tmp_path):
    spec = _enrolled_pack("analyze")
    destination = tmp_path / "canonical" / "skills" / "analyze"
    shutil.copytree(
        _pack_dir_for("analyze", spec, REPO_ROOT),
        destination,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return destination, list(spec["modes"])


def _edit(pack: Path, rel: str, old: str, new: str) -> None:
    target = pack / rel
    text = target.read_text(encoding="utf-8")
    assert old in text, f"{rel} no longer contains {old!r}: the reintroduction would be a no-op"
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


REINTRODUCTIONS = {
    "sqlite3 dropped from intelligence tools_required": (
        ("modes/intelligence/metadata.yml", "[python, git, ds, sqlite3]", "[python, git, ds]"),
        "undeclared tool reach `sqlite3` (modes/intelligence/metadata.yml)",
    ),
    "PyYAML dropped from repo python_packages": (
        ("modes/repo/metadata.yml", "python_packages: [PyYAML]", "python_packages: []"),
        "undeclared python package reach `yaml` (modes/repo/metadata.yml)",
    ),
    "the repo_analysis files lose their owner": (
        ("modes/repo/metadata.yml", "    - repo_analysis/\n", ""),
        "repo_analysis/analyzer.py:8: undeclared python package reach `yaml` (no declaration",
    ),
    "git dropped from domain-re": (
        ("modes/domain-re/metadata.yml", "tools_optional: [git]", "tools_optional: []"),
        "undeclared tool reach `git` (modes/domain-re/metadata.yml)",
    ),
    "the nonexistent ds lesson-queue command comes back": (
        (
            "modes/multi/examples.md",
            "`py -m interfaces.cli.lesson_queue list`",
            "`ds lesson-queue list`",
        ),
        "undeclared tool reach `ds` (modes/multi/metadata.yml)",
    ),
    "the PRD is again said to be written into .planning": (
        (
            "modes/intelligence/SKILL.md",
            "`~/.dream-studio/projects/<project-name>/planning/specs/prd.md`",
            "`.planning/specs/<project-name>/prd.md`",
        ),
        "undeclared state reach `.planning/specs`",
    ),
    "the made-up error log is declared nowhere but named again": (
        (
            "modes/intelligence/reference/error-handling.md",
            "(a failed run is recorded there; no error log file is written)",
            "then `cat ~/.dream-studio/logs/analysis-errors.log`",
        ),
        "undeclared state reach `~/.dream-studio/logs/analysis-errors.log`",
    ),
    "the metadata drops the python_packages key": (
        ("modes/repo/metadata.yml", "  python_packages: [PyYAML]\n", ""),
        "modes/repo/metadata.yml: dependencies.python_packages must be a list",
    ),
}


def test_the_real_pack_copy_is_clean(tmp_path):
    pack, modes = _real_pack_copy(tmp_path)
    assert pack_violations(pack, modes, tmp_path) == []


@pytest.mark.parametrize("case", sorted(REINTRODUCTIONS))
def test_a_reintroduced_defect_in_the_real_pack_is_caught(case, tmp_path):
    pack, modes = _real_pack_copy(tmp_path)
    (rel, old, new), expected = REINTRODUCTIONS[case]
    _edit(pack, rel, old, new)
    found = pack_violations(pack, modes, tmp_path)
    assert any(expected in line for line in found), f"{case}: wanted `{expected}`, got {found}"


# ------------------------------------------- forms found cheap to catch after a second look

CHEAP_FIXES = {
    "windows trailing dot on a directory name": (
        {"mode_text": "Read templates./x.md.\n"},
        "checkout path",
    ),
    "json unicode-escaped dots": (
        {"extra": {"c.json": '{"p": "\\u002e\\u002e/\\u002e\\u002e/\\u002e\\u002e/x.md"}\n'}},
        "leaves the pack",
    ),
    "double percent-encoded dots": (
        {"mode_text": "Read %252e%252e/%252e%252e/%252e%252e/x.md.\n"},
        "leaves the pack",
    ),
    "star-args join with ..": (
        {
            "extra": {
                "x.py": "import os\nP = os.path.join(os.path.dirname(__file__), *['..', '..'])\n"
            }
        },
        "climbs above",
    ),
    "utf-16 file without a byte-order mark": (
        {"extra": {"u.md": "Read templates/x.md\n".encode("utf-16-le")}},
        "checkout path",
    ),
    "utf-16 big-endian file without a byte-order mark": (
        {"extra": {"u.md": "Read templates/x.md\n".encode("utf-16-be")}},
        "checkout path",
    ),
}


@pytest.mark.parametrize("case", sorted(CHEAP_FIXES))
def test_a_cheap_to_catch_spelling_is_caught(case, tmp_path):
    kwargs, expected = CHEAP_FIXES[case]
    found = _run(_pack(tmp_path, **kwargs), tmp_path)
    assert any(expected in line for line in found), f"{case}: wanted `{expected}`, got {found}"


def test_a_utf16_binary_is_still_skipped(tmp_path):
    noise = bytes(range(256)) * 4
    assert _run(_pack(tmp_path, extra={"blob.bin": noise}), tmp_path) == []


# --------------------------------------------------------------- what a static check cannot see
#
# Each of these reaches outside the pack and the guard does not say so. They are written down
# as expected failures (strict: if the guard ever catches one, the test fails and the list in
# the module docstring is out of date). A gap that is documented is a decision; a gap nobody
# listed is a hole.

KNOWN_GAPS = {
    "a path from runtime data": {
        "extra": {
            "x.py": "import sys\nfrom pathlib import Path\nP = Path(sys.argv[1]).parent.parent\n"
        }
    },
    "getattr indirection": {
        "extra": {"x.py": "import importlib\nm = getattr(importlib, 'import_module')('core.x')\n"}
    },
    "a helper that climbs": {
        "extra": {
            "x.py": "from pathlib import Path\ndef up(p, n):\n    for _ in range(n):\n"
            "        p = p.parent\n    return p\nR = up(Path(__file__), 3)\n"
        }
    },
    "tuple-unpacked rebinding": {
        "extra": {
            "x.py": "from pathlib import Path\nhere, n = Path(__file__).parent, 1\nR = here.parent.parent\n"
        }
    },
    "parents[len(x)]": {
        "extra": {"x.py": "from pathlib import Path\nR = Path(__file__).parents[len('abcdef')]\n"}
    },
    "inspect.getfile": {
        "extra": {
            "x.py": "import inspect, os\n"
            "R = os.path.dirname(os.path.dirname(inspect.getfile(inspect.currentframe())))\n"
        }
    },
    "an arbitrary variable as the anchor": {"mode_text": "Read $REPO/templates/x.md.\n"},
    "a homoglyph in the layout name": {"mode_text": "Read tеmplates/x.md.\n"},
    "an 8.3 short name": {"mode_text": "Read TEMPLA~1/x.md.\n"},
    "a path assembled by shell variables": {"extra": {"r.sh": "d=..\ncd $d/$d/$d\n"}},
    "a path wrapped across two lines of prose": {
        "mode_text": "Read templ\nates/report.md afterwards.\n"
    },
    "prose that names no path": {
        "mode_text": "Look in the sibling repository for the shared templates.\n"
    },
}


@pytest.mark.parametrize("case", sorted(KNOWN_GAPS))
@pytest.mark.xfail(
    strict=True, reason="a documented limit of reading text, see the module docstring"
)
def test_a_documented_gap_is_still_a_gap(case, tmp_path):
    assert _run(_pack(tmp_path, **KNOWN_GAPS[case]), tmp_path), f"the guard now catches: {case}"
