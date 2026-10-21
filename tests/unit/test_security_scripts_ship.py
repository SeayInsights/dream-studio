"""The security skill ships the scripts its modes run, and they run from an installed copy.

WHY (issue #895 item 7). The security modes tell the agent to run
`py -3.12 templates/security/etl/parse_binary.py` (and parse_dast, parse_sarif, score_findings,
map_compliance, ...) and to render `templates/security/**/*.j2`. `templates/` is not under
canonical/, so `dist/plugin` shipped the instructions and not the thing they run: an installed
plugin had a binary-scan ingest step naming a script that did not exist on the machine, and
the coverage work (scan_coverage.py) was unreachable from every install. Seven mode docs also
named a path into one contributor's checkout.

The choice and its limits (see SKILL_SUPPORT_TREES in plugin_dist.py): the whole
`templates/security/` tree is copied into `skills/ds-security/templates/security/` by
plugin_dist, with its layout intact (the scripts find `compliance/` and `mitigations/` by
relative path), and the docs say `<skill-dir>/templates/security/...`. The source stays where
it is: moving it is the pack extraction the pack-capability contract describes. The security
pack is NOT enrolled in the pack-self-contained guard and these tests do not enrol it.

The installed-style tests copy the built skill directory to a temp directory with no
repository around it, block the platform's `core` package, and run a parser from there.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from integrations.marketplace import plugin_dist
from integrations.marketplace.plugin_dist import build_plugin_dist

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "templates" / "security"
DOCS = REPO_ROOT / "canonical" / "skills" / "security"
ETL_SCRIPTS = sorted(p.name for p in (SOURCE / "etl").glob("*.py"))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("plugin") / "plugin"
    build_plugin_dist(out, repo_root=REPO_ROOT)
    return out / "skills" / "ds-security"


def _files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")
    }


# -- the build ----------------------------------------------------------------------------------------


def test_the_registry_names_the_security_tree():
    assert plugin_dist.SKILL_SUPPORT_TREES["ds-security"] == (
        ("templates/security", "templates/security"),
    )


def test_every_source_file_is_shipped_under_the_skill_directory(built: Path):
    shipped = _files(built / "templates" / "security")
    assert shipped == _files(SOURCE)
    for script in ETL_SCRIPTS:
        assert f"etl/{script}" in shipped
    for needed in (
        "etl/scan_coverage.py",
        "etl/etl_home.py",
        "etl/header_analysis.py",
        "compliance/soc2-mapping.yaml",
        "mitigations/auth-fixes.yaml",
        "binary/yara-rules.yar.j2",
        "powerbi/dashboard-spec.md",
        "README.md",
    ):
        assert needed in shipped, needed


def test_shipped_text_is_the_source_text_with_lf_line_endings(built: Path):
    for rel in ("etl/parse_binary.py", "binary/analyze.sh.j2", "README.md"):
        shipped = (built / "templates" / "security" / rel).read_bytes()
        assert b"\r" not in shipped, rel
        source = (SOURCE / rel).read_text(encoding="utf-8")
        assert shipped.decode("utf-8") == source


def _source_with_bytecode(root: Path) -> Path:
    """A copy-sized stand-in for the support tree with every kind of build output planted in
    it, so the assertions below can fail on a clean checkout (which has none)."""
    tree = root / "templates" / "security"
    (tree / "etl" / "__pycache__").mkdir(parents=True)
    (tree / "etl" / ".pytest_cache").mkdir()
    (tree / "etl" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tree / "etl" / "real.pyc").write_bytes(b"\x00pyc")
    (tree / "etl" / "real.pyo").write_bytes(b"\x00pyo")
    (tree / "etl" / "native.pyd").write_bytes(b"MZ")
    (tree / "etl" / "__pycache__" / "real.cpython-312.pyc").write_bytes(b"\x00pyc")
    (tree / "etl" / ".pytest_cache" / "v").write_text("cache", encoding="utf-8")
    (tree / "README.md").write_text("# readme\n", encoding="utf-8")
    return root


def test_no_bytecode_or_cache_is_shipped_by_the_installer_listing(tmp_path: Path):
    from integrations.installer.claude_code_fileops import _collect_skill_dir_ops

    repo = _source_with_bytecode(tmp_path / "repo")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# security\n", encoding="utf-8")
    ops = _collect_skill_dir_ops(skill, tmp_path / "out", "ds-security", tmp_path / "bk", repo)
    shipped = sorted(Path(op.target).relative_to(tmp_path / "out").as_posix() for op in ops)
    assert shipped == [
        "SKILL.md",
        "templates/security/README.md",
        "templates/security/etl/real.py",
    ]


def test_no_bytecode_or_cache_is_shipped_by_the_plugin_build(tmp_path: Path, monkeypatch):
    repo = _source_with_bytecode(tmp_path / "planted")
    try:
        relative = os.path.relpath(repo / "templates" / "security", REPO_ROOT).replace("\\", "/")
    except ValueError:
        pytest.skip("the temp directory is on another drive than the checkout")
    monkeypatch.setitem(
        plugin_dist.SKILL_SUPPORT_TREES, "ds-security", ((relative, "templates/security"),)
    )
    out = tmp_path / "plugin"
    build_plugin_dist(out, repo_root=REPO_ROOT)
    tree = out / "skills" / "ds-security" / "templates" / "security"
    assert (tree / "etl" / "real.py").is_file()  # the planted tree really was shipped...
    leaked = [
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if "__pycache__" in p.parts
        or ".pytest_cache" in p.parts
        or p.suffix in (".pyc", ".pyo", ".pyd")
    ]
    assert leaked == []  # ...without the bytecode and caches planted beside it


def test_the_built_plugin_has_no_bytecode_anywhere(built: Path):
    assert not [p for p in built.rglob("*") if "__pycache__" in p.parts or p.suffix == ".pyc"]


def test_other_skills_do_not_gain_a_templates_tree(built: Path):
    siblings = built.parent
    for skill in siblings.iterdir():
        if skill.name != "ds-security":
            assert not (skill / "templates" / "security").exists(), skill.name


def test_a_missing_source_tree_fails_the_build_loudly(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(
        plugin_dist.SKILL_SUPPORT_TREES, "ds-security", (("templates/nope", "templates/nope"),)
    )
    with pytest.raises(FileNotFoundError, match="templates/nope"):
        build_plugin_dist(tmp_path / "plugin", repo_root=REPO_ROOT)


def test_the_committed_plugin_carries_the_scripts():
    committed = REPO_ROOT / "dist" / "plugin" / "skills" / "ds-security" / "templates" / "security"
    assert (committed / "etl" / "parse_binary.py").is_file()
    assert (committed / "etl" / "scan_coverage.py").is_file()


# -- the docs name what ships --------------------------------------------------------------------------


def _security_docs() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.md") if p.name != "changelog.md")


def test_no_security_doc_names_a_path_into_a_checkout():
    for doc in _security_docs():
        text = doc.read_text(encoding="utf-8")
        assert "builds/dream-studio-clean" not in text, doc.relative_to(DOCS)
        # a bare repo-relative path is only right in a checkout; installed, it is skill-relative
        bare = re.findall(r"(?<!<skill-dir>/)templates/security/", text)
        if doc == DOCS / "SKILL.md":
            # the pack SKILL.md is where the checkout fallback is explained, so it says the
            # bare form twice: the repository-root location and the equivalence
            assert len(bare) == 2
            continue
        assert not bare, f"{doc.relative_to(DOCS)} names templates/security/ without <skill-dir>/"


def test_every_script_and_template_a_doc_names_exists_in_the_shipped_tree(built: Path):
    shipped = _files(built / "templates" / "security")
    named: set[str] = set()
    for doc in _security_docs():
        text = doc.read_text(encoding="utf-8")
        for ref in re.findall(r"<skill-dir>/templates/security/([A-Za-z0-9_./-]+)", text):
            ref = ref.rstrip(".,;:)`")
            if ref.endswith("/") or not Path(ref).suffix:  # a directory (`etl`, `mitigations/`)
                prefix = ref.rstrip("/") + "/"
                assert any(f.startswith(prefix) for f in shipped), f"{doc.name}: {ref}"
            else:
                named.add(ref)
                assert ref in shipped, f"{doc.name} names {ref}, which does not ship"
    # the scripts the modes execute are among what the docs name
    for script in (
        "etl/parse_binary.py",
        "etl/parse_dast.py",
        "etl/parse_sarif.py",
        "etl/header_analysis.py",
        "etl/export_dataset.py",
    ):
        assert script in named, script


def test_the_pack_skill_md_defines_skill_dir_and_the_checkout_fallback():
    text = " ".join((DOCS / "SKILL.md").read_text(encoding="utf-8").split())
    assert "`<skill-dir>` in the mode docs is this skill's own directory" in text
    assert "<skill-dir>/templates/security/" in text
    assert "In a source checkout" in text and "templates/security/` in the repository root" in text


def test_the_instruction_commands_gate_still_sees_no_dangling_security_command():
    from core.gates import instruction_commands

    findings = [
        f
        for f in instruction_commands.unresolved_commands()
        if str(f["file"]).startswith("canonical/skills/security/")
    ]
    assert findings == []


# -- an installed copy, with no repository around it --------------------------------------------------


@pytest.fixture()
def installed(built: Path, tmp_path: Path) -> Path:
    """The built skill directory copied to a temp directory outside the repository."""
    target = tmp_path / "installed" / "ds-security"
    shutil.copytree(built, target)
    assert REPO_ROOT not in target.resolve().parents
    return target


_RUN_WITHOUT_CORE = (
    "import runpy, sys\n"
    "sys.modules['core'] = None  # the platform package is not part of an installed plugin\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def _run(script: Path, *args: str, cwd: Path, home: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "DREAM_STUDIO_HOME")}
    env["DREAM_STUDIO_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-c", _RUN_WITHOUT_CORE, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        timeout=120,
    )


def _scan_dir(root: Path) -> Path:
    d = root / "scans" / "app" / "2026-10-21"
    d.mkdir(parents=True)
    (d / "checksec.json").write_text(
        json.dumps({"app.exe": {"nx": "no", "pie": "yes"}}), encoding="utf-8"
    )
    steps = [
        {"step": "checksec", "status": "ran", "tool": "checksec"},
        {"step": "yara", "status": "skipped", "tool": "yara", "reason": "yara is not installed"},
        {"step": "strings", "status": "skipped", "tool": "strings", "reason": "no strings"},
        {"step": "header_analysis", "status": "skipped", "tool": "pefile", "reason": "no pefile"},
    ]
    (d / "scan-meta.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
    return d


def test_a_parser_runs_from_an_installed_copy_and_reports_coverage(installed: Path, tmp_path: Path):
    scan = _scan_dir(tmp_path)
    work = tmp_path / "elsewhere"
    work.mkdir()
    out, cov = work / "findings.json", work / "coverage.json"
    script = installed / "templates" / "security" / "etl" / "parse_binary.py"

    proc = _run(
        script,
        "--client",
        "acme",
        "--scans-dir",
        str(scan),
        "--output",
        str(out),
        "--coverage-output",
        str(cov),
        cwd=work,
        home=tmp_path / "home",
    )

    assert proc.returncode == 0, proc.stderr
    findings = json.loads(out.read_text(encoding="utf-8"))
    assert [f["hardening_check"] for f in findings] == ["nx"]
    assert {f["coverage"] for f in findings} == {"partial"}
    report = json.loads(cov.read_text(encoding="utf-8"))
    assert report["scans"][0]["skipped_steps"] == ["yara", "strings", "header_analysis"]


def test_the_home_of_an_installed_copy_follows_dream_studio_home(installed: Path, tmp_path: Path):
    """No `core` to ask: the default scans directory is under DREAM_STUDIO_HOME."""
    home = tmp_path / "home"
    scan = home / "security" / "scans" / "acme" / "app" / "2026-10-21"
    scan.mkdir(parents=True)
    (scan / "checksec.json").write_text(json.dumps({"app.exe": {"nx": "no"}}), encoding="utf-8")
    (scan / "scan-meta.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
    script = installed / "templates" / "security" / "etl" / "parse_binary.py"

    # the client tree itself: the scan directory is found only through the resolved home
    proc = _run(script, "--client", "acme", cwd=tmp_path, home=home)

    assert "scans directory not found" not in proc.stderr, proc.stderr
    # the default scans directory was resolved under DREAM_STUDIO_HOME (it holds the client
    # tree, whose scan directories are one level down, so there is nothing at its top level)
    assert str((home / "security" / "scans" / "acme").resolve()) in proc.stderr


@pytest.mark.parametrize("script", ETL_SCRIPTS)
def test_every_shipped_script_starts_from_an_installed_copy(
    installed: Path, tmp_path: Path, script: str
):
    if script in ("scan_coverage.py", "etl_home.py"):
        pytest.skip("a library the scripts import, not a command")
    proc = _run(
        installed / "templates" / "security" / "etl" / script,
        "--help",
        cwd=tmp_path,
        home=tmp_path / "home",
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout.lower()


def test_the_data_directories_the_scripts_read_ship_beside_them(installed: Path):
    etl = installed / "templates" / "security" / "etl"
    assert (etl.parent / "compliance" / "soc2-mapping.yaml").is_file()
    assert (etl.parent / "mitigations" / "auth-fixes.yaml").is_file()


def test_generate_mitigations_finds_its_templates_from_an_installed_copy(
    installed: Path, tmp_path: Path
):
    pytest.importorskip("yaml")
    script = installed / "templates" / "security" / "etl" / "generate_mitigations.py"
    finding = {
        "id": "f1",
        "repo": "r",
        "severity": "high",
        "rule_id": "x",
        "cwe": "CWE-89",
        "message": "sql",
    }
    env_home = tmp_path / "home"
    out = tmp_path / "out.json"
    src = tmp_path / "in.json"
    src.write_text(json.dumps([finding]), encoding="utf-8")
    proc = _run(
        script,
        "--client",
        "acme",
        "--input",
        str(src),
        "--output",
        str(out),
        cwd=tmp_path,
        home=env_home,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Total templates loaded:" in proc.stderr
    assert "Total templates loaded: 0" not in proc.stderr


# -- etl_home -------------------------------------------------------------------------------------------


def test_in_a_checkout_etl_home_asks_the_platform(monkeypatch, tmp_path: Path):
    sys.path.insert(0, str(SOURCE / "etl"))
    import etl_home
    from core.config import paths

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "h"))
    assert etl_home.home_dir() == paths.home_dir() == tmp_path / "h"


def test_without_a_checkout_etl_home_uses_the_env_then_the_default(monkeypatch, tmp_path: Path):
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copy(SOURCE / "etl" / "etl_home.py", alone / "etl_home.py")
    code = "import sys; sys.path.insert(0, %r); import etl_home; print(etl_home.home_dir())" % str(
        alone
    )
    base = {k: v for k, v in os.environ.items() if k != "DREAM_STUDIO_HOME"}
    custom = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env={**base, "DREAM_STUDIO_HOME": str(tmp_path / "custom")},
    )
    default = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=base,
    )
    assert custom.stdout.strip() == str(tmp_path / "custom"), custom.stderr
    assert default.stdout.strip() == str(Path.home() / ".dream-studio"), default.stderr
