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

WHAT IT CHECKS, for every pack in ENROLLED_PACKS:

  1. The pack exists (packs.yaml entry, directory, every declared mode directory with a
     SKILL.md and a metadata.yml). An enrolled pack that is missing FAILS; it is not skipped.
  2. No file in the pack names a path outside it: a checkout layout (`canonical/`,
     `templates/`, `shared/`, `skills/<x>/`, `dist/plugin`), a user-specific absolute path,
     a host install path (`~/.claude/`), or a `.parent` chain that climbs above the pack.
  3. No python file in the pack imports a Dream Studio package, and no top-level name in
     the pack collides with one (the `core` shadow).
  4. What a mode DOES reach -- platform modules, `~/.dream-studio/` and `.planning/` state,
     the `ds` CLI, other packs' skills, external tools -- is declared in that mode's
     metadata.yml `dependencies`; text that reaches without the declaration is a
     contradiction, and the pack-level files shared by every mode may reach nothing.
  5. The declaration itself is true where it can be checked: all five keys present as
     lists, and every pack-relative `files_required` entry exists inside the pack.

WHAT IT DELIBERATELY DOES NOT CHECK. A declared `core_modules` entry no text names is
allowed (the intelligence mode declares the engine stages it runs but never spells out
in prose). Third-party names and a user's own paths (`~/repos/x`, `~/builds/my-app`) are
not this repository's to forbid. Dynamic imports and prose that merely discusses a
platform concept are invisible to it -- it reads text, not behavior.

The synthetic-pack tests below pin each rule: a detector that stopped matching (the
failure mode of a regex written in a shell heredoc, where `\\b` turns into a backspace
byte) would otherwise report clean on the real pack. Each one builds a pack that breaks
exactly one rule and asserts the rule names it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Packs held to the contract. Explicit on purpose: enrolling a pack is a decision that
#: comes with fixing it, and a glob would enrol the 12 packs that still read the
#: checkout. Extend as each pack is extracted.
ENROLLED_PACKS = ("analyze",)

#: Dream Studio's own top-level packages. A pack imports none of them and defines no
#: top-level name that equals one.
PLATFORM_PACKAGES = (
    "core",
    "control",
    "integrations",
    "interfaces",
    "projections",
    "runtime",
    "spool",
    "hooks",
    "canonical",
)

DEPENDENCY_KEYS = (
    "core_modules",
    "tools_required",
    "env_vars_required",
    "files_required",
    "calls_skills",
)

TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".py", ".json", ".txt", ".toml", ".cfg"}

_PKG = "|".join(PLATFORM_PACKAGES)

#: A path that only means something inside a source checkout or on one person's machine.
#: The lookbehind keeps `scripts/templates` (a prose list) and `~/repos/x` out of it.
_LAYOUT = (
    (
        "checkout path",
        re.compile(r"(?<![\w.~/-])(?:canonical|dist/plugin|templates|shared|skills)/[\w.{<-]"),
    ),
    (
        "checkout path",
        re.compile(
            r"(?<![\w.~/-])(?:runtime|integrations|interfaces|projections|spool)/[a-z_]\w*/"
        ),
    ),
    (
        "user-specific path",
        re.compile(r"[A-Za-z]:\\Users\\|/Users/[A-Za-z]|builds[/\\]dream-studio"),
    ),
    ("host install path", re.compile(r"~/\.claude/")),
)

#: State a mode reads or writes outside the pack. Needs a files_required entry.
_STATE = re.compile(r"(?:~/\.dream-studio/|(?<![\w])\.planning/)[^\s`'\")\],]*")

#: A Dream Studio module named in text: `from X import`, `import X`, or dotted/slash form.
_MODULE_TEXT = (
    re.compile(r"\b(?:from|import)\s+((?:" + _PKG + r")(?:\.\w+)*)"),
    re.compile(r"(?<![\w./~-])((?:" + _PKG + r")(?:\.[a-z_][a-z0-9_]*)+)"),
    re.compile(r"(?<![\w./~-])((?:" + _PKG + r")(?:/[a-z_][a-z0-9_]*)+)"),
)

#: Platform functions skills are known to tell an agent to call, by the module they live
#: in. Found in the audit; extend when a skill is found calling another.
_PLATFORM_CALLS = (
    (re.compile(r"\binsert_lesson\("), "core.event_store"),
    (re.compile(r"\bpaths\.state_dir\("), "core.config.paths"),
)

#: The `ds` CLI. A standalone `ds` word, so `fields`/`ds_documents`/`ds-analyze` do not match.
_DS_CLI = re.compile(r"(?<![\w/.-])ds [a-z][a-z-]*")

#: Another pack's skill id (`ds-code-health`), as in `Skill(skill="ds-code-health", ...)`.
_OTHER_SKILL = re.compile(r"\bds-([a-z][a-z-]*)")

_PARENT_CHAIN = re.compile(r"__file__\)(?:\.resolve\(\))?((?:\.parent)+)")
_PARENTS_INDEX = re.compile(r"__file__\)(?:\.resolve\(\))?\.parents\[(\d+)\]")

_SUBPROCESS = {"run", "Popen", "check_output", "check_call", "call"}


# --------------------------------------------------------------------------- helpers


def _pack_dir_for(name: str, spec: dict, root: Path) -> Path:
    """Resolve a pack's directory the way the projector does (`skill_path`, else name)."""
    skill_path = (spec or {}).get("skill_path")
    return root / skill_path if skill_path else root / "canonical" / "skills" / name


def _repo_root_packages(root: Path) -> set[str]:
    """Top-level packages of the repository the pack is installed alongside."""
    found = set(PLATFORM_PACKAGES)
    if root.is_dir():
        found |= {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").is_file()}
    return found


def _files(pack_dir: Path):
    for path in sorted(pack_dir.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts:
            yield path


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


def _as_dotted(token: str) -> str:
    return token.replace("/", ".")


def _hops_allowed(path: Path, pack_dir: Path) -> int:
    """`Path(__file__).parent` reaches the file's directory; one more hop per level below
    the pack root reaches the pack root itself. Anything past that leaves the pack."""
    return len(path.relative_to(pack_dir).parts)


def _python_findings(path: Path, text: str):
    """(line, kind, token) for imports, subprocess tools and which() lookups in a .py file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in PLATFORM_PACKAGES:
                    yield node.lineno, "module", alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.split(".")[0] in PLATFORM_PACKAGES:
                yield node.lineno, "module", node.module
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if (
                name in _SUBPROCESS
                and node.args
                and isinstance(node.args[0], (ast.List, ast.Tuple))
            ):
                first = node.args[0].elts[0] if node.args[0].elts else None
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    yield node.lineno, "tool", first.value
            elif name == "which" and node.args and isinstance(node.args[0], ast.Constant):
                yield node.lineno, "tool", str(node.args[0].value)


def _text_reaches(text: str, is_python: bool):
    """(line, kind, token) for every reach into the platform that text makes."""
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _STATE.finditer(line):
            yield number, "state", match.group(0)
        if not is_python:
            for pattern in _MODULE_TEXT:
                for match in pattern.finditer(line):
                    yield number, "module", _as_dotted(match.group(1))
        for pattern, module in _PLATFORM_CALLS:
            if pattern.search(line):
                yield number, "module", module
        for match in _DS_CLI.finditer(line):
            yield number, "tool", "ds"
        for match in _OTHER_SKILL.finditer(line):
            if match.group(1) != "analyze":
                yield number, "skill", "ds-" + match.group(1)


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


def pack_violations(pack_dir: Path, modes: list[str], root: Path) -> list[str]:
    """Every way `pack_dir` reaches outside itself or declares a dependency falsely."""
    out: list[str] = []
    if not pack_dir.is_dir():
        return [f"{pack_dir}: pack directory does not exist"]
    if not (pack_dir / "SKILL.md").is_file():
        out.append(f"{pack_dir.name}: no SKILL.md at the pack root")

    # 3b. A top-level name in the pack that equals a package the platform owns.
    owned = _repo_root_packages(root)
    for child in sorted(pack_dir.iterdir()):
        stem = child.stem if child.is_file() and child.suffix == ".py" else child.name
        if stem in owned and (
            child.is_dir() and (child / "__init__.py").is_file() or child.suffix == ".py"
        ):
            out.append(f"{child.name}: top-level name shadows the platform package `{stem}`")

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
            entry = str(entry)
            if entry.startswith("~/"):
                if not entry.startswith("~/.dream-studio/"):
                    out.append(
                        f"modes/{mode}/metadata.yml: files_required `{entry}` is outside ~/.dream-studio/"
                    )
            elif entry.startswith(".planning/"):
                continue
            elif not (pack_dir / entry).exists():
                out.append(
                    f"modes/{mode}/metadata.yml: files_required `{entry}` does not exist in the pack"
                )

    for path in _files(pack_dir):
        rel = path.relative_to(pack_dir)
        text = path.read_text(encoding="utf-8", errors="replace")
        is_python = path.suffix == ".py"
        parts = rel.parts
        mode = (
            parts[1]
            if len(parts) > 2 and parts[0] == "modes" and parts[1] in deps_by_mode
            else None
        )
        if rel.name == "metadata.yml" and mode:
            continue  # the declaration itself names what it declares

        where = rel.as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in _LAYOUT:
                if pattern.search(line):
                    out.append(f"{where}:{number}: {label}: {line.strip()[:100]}")
        if is_python:
            allowed = _hops_allowed(path, pack_dir)
            for number, line in enumerate(text.splitlines(), start=1):
                for match in _PARENT_CHAIN.finditer(line):
                    if match.group(1).count(".parent") > allowed:
                        out.append(
                            f"{where}:{number}: climbs above the pack directory ({line.strip()[:80]})"
                        )
                for match in _PARENTS_INDEX.finditer(line):
                    if int(match.group(1)) + 1 > allowed:
                        out.append(
                            f"{where}:{number}: climbs above the pack directory ({line.strip()[:80]})"
                        )

        reaches = list(_text_reaches(text, is_python))
        if is_python:
            reaches += list(_python_findings(path, text))
        deps = deps_by_mode.get(mode, {}) if mode else {}
        declared = {
            "state": [str(e) for e in deps.get("files_required") or []],
            "module": [str(e) for e in deps.get("core_modules") or []],
            "tool": [
                str(e)
                for e in (deps.get("tools_required") or []) + (deps.get("tools_optional") or [])
            ],
            "skill": [str(e).split(":")[0] for e in deps.get("calls_skills") or []],
        }
        for number, kind, token in reaches:
            if kind == "tool" and token in ("python", "py") and mode:
                continue
            if mode is None:
                ok = False
            elif kind == "tool":
                ok = token in declared["tool"]
            elif kind == "skill":
                ok = token in declared["skill"]
            else:
                ok = _covered(token, declared[kind])
            if not ok:
                owner = (
                    f"modes/{mode}/metadata.yml"
                    if mode
                    else "no declaration is possible in a pack-level file"
                )
                out.append(f"{where}:{number}: undeclared {kind} reach `{token}` ({owner})")
    return out


def _enrolled_pack(name: str):
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    return packs.get(name)


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
    "user absolute path": ({"mode_text": "Open C:\\Users\\Example\\x.md.\n"}, "user-specific path"),
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
