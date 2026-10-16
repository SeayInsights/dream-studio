"""An installed wheel runs `ds` with no checkout anywhere on its import path.

Measured 2026-10-15 on main 0a1f7673: a wheel built from a clean export carried none
of the runtime's data files (migrations, event schemas, packs.yaml, VERSION, the
canonical tree), left out the top-level `compat` module and the `config` package,
and an installed `ds --help` died with ModuleNotFoundError: compat. Every surface
therefore ran straight from the git checkout.

This builds the wheel from the TRACKED files only (what `git archive` of a commit
holds), installs it into a fresh venv outside the checkout, and drives it:

- every tracked runtime data file is in the wheel;
- `ds --help` and `ds validate` succeed through the installed console script;
- a brand-new database migrates to the latest schema from the installed migrations;
- no Dream Studio module is imported from the checkout and the checkout root is not on
  sys.path.

Third-party dependencies come from the running interpreter's site-packages through a
.pth line, which keeps the test offline and fast; the Dream Studio packages come ONLY
from the wheel.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DS_TOP_LEVEL = (
    "core",
    "runtime",
    "interfaces",
    "spool",
    "projections",
    "emitters",
    "canonical",
    "control",
    "shared",
    "guardrails",
    "integrations",
    "config",
)
#: Tracked files inside package directories that the wheel deliberately leaves out.
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".rs")
EXCLUDED_NAMES = ("Cargo.toml", "Cargo.lock")

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git to list the tracked files"
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def _scripts_dir(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _venv_python(venv: Path) -> Path:
    return _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")


def _isolated_env(tmp: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "DREAM_STUDIO"))}
    env.pop("DS_DREAM_STUDIO_HOME", None)
    env["DREAM_STUDIO_HOME"] = str(tmp / "home")
    env["DREAM_STUDIO_DB_PATH"] = str(tmp / "home" / "state" / "studio.db")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.fixture(scope="module")
def installed(tmp_path_factory) -> dict:
    try:
        import setuptools  # noqa: F401
        import wheel  # noqa: F401
    except ImportError:  # pragma: no cover - requirements-dev.txt carries both
        pytest.skip("setuptools and wheel are needed to build offline")
    try:
        from importlib.metadata import distribution

        distribution("dream-studio")
        pytest.skip("dream-studio is installed in this interpreter; deps .pth would leak it")
    except Exception:
        pass

    tmp = tmp_path_factory.mktemp("wheel")
    src = tmp / "src"
    tracked = _tracked_files()
    for rel in tracked:
        source = REPO / rel
        if not source.is_file():
            continue
        dest = src / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    dist = tmp / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--quiet",
            "--disable-pip-version-check",
            "-w",
            str(dist),
            str(src),
        ],
        check=True,
        cwd=tmp,
    )
    wheel_path = next(dist.glob("dream_studio-*.whl"))

    venv = tmp / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    py = _venv_python(venv)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(py),
            "install",
            "--no-deps",
            "--quiet",
            "--disable-pip-version-check",
            str(wheel_path),
        ],
        check=True,
        cwd=tmp,
    )
    site = Path(
        subprocess.run(
            [str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
    )
    # Third-party deps only: the running interpreter's site-packages.
    (site / "_ds_test_deps.pth").write_text(
        sysconfig.get_paths()["purelib"] + "\n", encoding="utf-8"
    )
    return {"tmp": tmp, "wheel": wheel_path, "venv": venv, "py": py, "tracked": tracked}


def test_wheel_carries_every_runtime_data_file(installed):
    sys.path.insert(0, str(REPO))
    try:
        from setup import shipped_root_data
    finally:
        sys.path.remove(str(REPO))

    names = set(zipfile.ZipFile(installed["wheel"]).namelist())
    expected = [
        rel
        for rel in installed["tracked"]
        if rel.split("/", 1)[0] in DS_TOP_LEVEL
        and "/" in rel
        and not rel.endswith(EXCLUDED_SUFFIXES)
        and rel.rsplit("/", 1)[-1] not in EXCLUDED_NAMES
        and "/tests/" not in f"/{rel}"  # test packages stay out of the wheel
    ]
    expected += shipped_root_data(str(REPO))
    expected.append("compat.py")
    missing = sorted(rel for rel in expected if rel not in names)
    shipped_tests = sorted(n for n in names if "/tests/" in f"/{n}")
    assert not shipped_tests, f"test packages shipped in the wheel: {shipped_tests[:5]}"
    assert not missing, f"{len(missing)} runtime files missing from the wheel: {missing[:20]}"
    for must in (
        "core/event_store/migrations/.released_version",
        "docs/canonical/event_taxonomy_v1.json",
        "docs/canonical/canonical_event_v1_schema.json",
        "packs.yaml",
        "VERSION",
        "config/__init__.py",
    ):
        assert must in names


def test_installed_ds_help_runs(installed):
    ds = _scripts_dir(installed["venv"]) / ("ds.exe" if os.name == "nt" else "ds")
    proc = subprocess.run(
        [str(ds), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=installed["tmp"],
        env=_isolated_env(installed["tmp"]),
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "Dream Studio global command" in proc.stdout


PROBE = r"""
import io, json, sys, contextlib
from pathlib import Path
from interfaces.cli.ds import main
from core.config.paths import code_root
from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version

out = io.StringIO()
with contextlib.redirect_stdout(out):
    validate_rc = main(["validate"])
fresh = Path(sys.argv[1])
version = bootstrap_database(fresh)
ds_files = sorted(
    getattr(m, "__file__", None) or ""
    for name, m in list(sys.modules.items())
    if name.split(".")[0] in json.loads(sys.argv[2])
)
print(json.dumps({
    "validate_rc": validate_rc,
    "validate": json.loads(out.getvalue()),
    "version": version,
    "latest": latest_migration_version(),
    "sys_path": sys.path,
    "ds_files": ds_files,
    "code_root": str(code_root()),
}))
"""


def test_installed_validate_and_fresh_migration_never_touch_the_checkout(installed):
    tmp = installed["tmp"]
    fresh = tmp / "fresh" / "studio.db"
    proc = subprocess.run(
        [str(installed["py"]), "-c", PROBE, str(fresh), json.dumps(DS_TOP_LEVEL)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp,
        env=_isolated_env(tmp),
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    report = json.loads(proc.stdout.strip().splitlines()[-1])

    assert report["validate_rc"] == 0
    assert report["validate"]["module_profile_errors"] == []
    assert report["latest"] > 0
    assert report["version"] == report["latest"]

    repo = str(REPO.resolve()).lower()
    venv = str(installed["venv"].resolve()).lower()
    assert Path(report["code_root"]).resolve().is_relative_to(installed["venv"].resolve())
    assert repo not in {str(Path(p).resolve()).lower() for p in report["sys_path"] if p}
    assert report["ds_files"], "probe imported no Dream Studio module"
    leaked = [f for f in report["ds_files"] if f and not f.lower().startswith(venv)]
    assert not leaked, f"modules loaded from outside the installed app: {leaked[:10]}"


HOOK_PROBE = r"""
import io, json, runpy, sys
module, event, payload, top = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
sys.argv = [module] + ([event] if event else [])
sys.stdin = io.StringIO(payload)
captured, real = io.StringIO(), sys.stdout
sys.stdout = captured
code = 0
try:
    runpy.run_module(module, run_name="__main__", alter_sys=True)
except SystemExit as exc:
    code = exc.code or 0
finally:
    sys.stdout = real
files = sorted(
    getattr(m, "__file__", None) or ""
    for name, m in list(sys.modules.items())
    if name.split(".")[0] in top
)
print(json.dumps({"code": code, "files": files, "sys_path": sys.path}))
"""


@pytest.mark.parametrize(
    "module,event,payload",
    [
        ("runtime.dispatch.hooks", "UserPromptSubmit", {"session_id": "t", "prompt": "hi"}),
        ("emitters.claude_code.run", "UserPromptSubmit", {"session_id": "t", "prompt": "hi"}),
        (
            "runtime.hooks.meta.on-edit-enforce",
            "",
            {"session_id": "t", "tool_name": "Edit", "tool_input": {"file_path": "x.py"}},
        ),
    ],
)
def test_installed_hook_modules_run_from_the_app_even_inside_a_checkout(
    installed, module, event, payload
):
    """The hook command is `<app python> -I -X utf8 -m <module>`, and Claude Code runs it with the
    PROJECT as the working directory -- here, the Dream Studio checkout itself. Plain `-m`
    would put that directory first on sys.path and import the checkout's packages."""
    tmp = installed["tmp"]
    proc = subprocess.run(
        [
            str(installed["py"]),
            "-I",
            "-c",
            HOOK_PROBE,
            module,
            event,
            json.dumps(payload),
            json.dumps(DS_TOP_LEVEL),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
        env=_isolated_env(tmp),
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["code"] == 0
    repo = str(REPO.resolve()).lower()
    assert repo not in {str(Path(p).resolve()).lower() for p in report["sys_path"] if p}
    venv = str(installed["venv"].resolve()).lower()
    leaked = [f for f in report["files"] if f and not f.lower().startswith(venv)]
    assert not leaked, f"hook imported Dream Studio code from outside the app: {leaked[:10]}"
    if module == "runtime.dispatch.hooks":
        # A HANDLER ran, not just the entry point. The assertions above hold for a
        # dispatcher that exits 0 having run nothing; dispatch_tracking writes a timing
        # line only for a handler it actually executed (round-table S14).
        timing = tmp / "home" / "state" / "hook-timing.jsonl"
        handlers = [json.loads(line)["handler"] for line in timing.read_text("utf-8").splitlines()]
        assert "on-prompt-dispatch" in handlers, handlers


INSTALL_PROBE = r"""
import json, sys
from pathlib import Path
from unittest.mock import patch
from integrations.installer.claude_code import ClaudeCodeInstaller
root, home, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
with patch(
    "integrations.installer.claude_code_launcher._write_path_to_profile",
    return_value={"profile": "x", "action": "skipped"},
):
    r = ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode=mode).install("execute")
print(json.dumps({"ok": r.get("ok"), "hook_mode": r.get("hook_mode")}))
"""


def test_a_retired_enforcement_hook_still_enforces_in_a_running_session(installed):
    """A session that started under a files-mode install keeps calling the copied
    on-edit-enforce.py after the move to module mode. Its stub must give the installed
    module's answer, byte for byte, not exit 0 and switch enforcement off."""
    tmp = installed["tmp"]
    root, home = tmp / "retire-root", tmp / "retire-home"
    root.mkdir(exist_ok=True)
    env = {**_isolated_env(tmp), "DREAM_STUDIO_HOME": str(home)}
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    project = tmp / "retire-project"
    (project / ".planning").mkdir(parents=True, exist_ok=True)
    # A registered project in a fresh authority: enforcement decides only inside one.
    boot = subprocess.run(
        [
            str(installed["py"]),
            "-I",
            "-c",
            "import sys; from core.config.sqlite_bootstrap import bootstrap_database; "
            "bootstrap_database(sys.argv[1])",
            str(home / "state" / "studio.db"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp,
        env=env,
        timeout=600,
    )
    assert boot.returncode == 0, boot.stderr[-1500:]
    reg = subprocess.run(
        [
            str(installed["py"]),
            "-I",
            "-m",
            "interfaces.cli.ds",
            "--home",
            str(home),
            "project",
            "register",
            "--name",
            "Retire",
            "--path",
            str(project),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp,
        env=env,
        timeout=600,
    )
    assert reg.returncode == 0, reg.stdout[-1500:] + reg.stderr[-1500:]
    for py, mode, cwd in ((sys.executable, "files", REPO), (str(installed["py"]), "module", tmp)):
        proc = subprocess.run(
            [
                py,
                *(["-I"] if mode == "module" else []),
                "-c",
                INSTALL_PROBE,
                str(root),
                str(home),
                mode,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
            timeout=600,
        )
        assert proc.returncode == 0, proc.stderr[-3000:]
        assert json.loads(proc.stdout.strip().splitlines()[-1])["hook_mode"] == mode

    stub = root / "hooks" / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"
    assert stub.read_text(encoding="utf-8").startswith("# dream-studio retired hook stub")
    payload = json.dumps(
        {
            "session_id": "t",
            "tool_name": "Write",
            "tool_input": {"file_path": str(project / ".planning" / "x.md"), "content": "x"},
            "cwd": str(project),
        }
    )

    # Enforcement ignores paths under the temp directory, which is where pytest's tmp
    # lives: give the hook processes a temp directory of their own.
    hook_temp = tmp / "retire-temp"
    hook_temp.mkdir(exist_ok=True)
    hook_env = {**env, "TEMP": str(hook_temp), "TMP": str(hook_temp), "TMPDIR": str(hook_temp)}

    def run(cmd):
        return subprocess.run(
            cmd,
            input=payload.encode("utf-8"),
            capture_output=True,
            cwd=project,
            env=hook_env,
            timeout=300,
        )

    via_stub = run([sys.executable, str(stub)])
    direct = run(
        [str(installed["py"]), "-I", "-X", "utf8", "-m", "runtime.hooks.meta.on-edit-enforce"]
    )
    assert (via_stub.returncode, via_stub.stdout) == (
        direct.returncode,
        direct.stdout,
    ), via_stub.stderr.decode("utf-8", "replace")[-2000:]
    assert b"Restart this Claude Code session" not in via_stub.stdout + via_stub.stderr
    assert b"deny" in direct.stdout, "the probe must exercise a real enforcement decision"


ROUTES_PROBE = r"""
import json, sys
from fastapi.testclient import TestClient
import projections.api.main as m
from core.config.paths import code_root, plugin_root
from integrations.compiler.claude_code import compile_pack

def _plugin_root_is_code_root():
    try:
        return plugin_root() == code_root()
    except RuntimeError:
        return False


client = TestClient(m.app, raise_server_exceptions=False)
routes = {}
for r in m.app.routes:
    methods = getattr(r, "methods", None) or set()
    path = getattr(r, "path", "")
    if "GET" not in methods or "{" in path or path.startswith(("/docs", "/redoc", "/openapi")):
        continue
    routes[path] = client.get(path).status_code
print(json.dumps({
    "routes": routes,
    "claude_md": compile_pack(None)["files"]["CLAUDE.md"],
    "plugin_root_is_code_root": _plugin_root_is_code_root(),
}))
"""


def _surface(tmp: Path, name: str, cmd: list[str], cwd: Path, extra_env: dict) -> dict:
    import shutil as _shutil

    home = tmp / f"surface-{name}"
    (home / "state").mkdir(parents=True, exist_ok=True)
    _shutil.copy2(tmp / "surface-seed.db", home / "state" / "studio.db")
    env = _isolated_env(tmp)
    env["DREAM_STUDIO_HOME"] = str(home)
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    env.update(extra_env)
    proc = subprocess.run(
        cmd + ["-c", ROUTES_PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_installed_app_serves_what_the_checkout_serves(installed):
    """Round-table S5: runtime data the wheel did not ship (the security source list,
    adapter-projections/) made six dashboard routes and `ds contract-atlas` fail in the
    app, the installed CLAUDE.md lost its Authority/Resume projection, and plugin_root()
    raised, which locked every progressive skill mode."""
    from core.config.sqlite_bootstrap import bootstrap_database, shipped_released_version

    tmp = installed["tmp"]
    seed = tmp / "surface-seed.db"
    if not seed.exists():
        bootstrap_database(seed, target_version=shipped_released_version())
    checkout = _surface(tmp, "checkout", [sys.executable], REPO, {"PYTHONPATH": str(REPO)})
    app = _surface(tmp, "app", [str(installed["py"]), "-I"], tmp, {})

    differs = {
        path: (checkout["routes"][path], app["routes"].get(path))
        for path in checkout["routes"]
        if checkout["routes"][path] != app["routes"].get(path)
    }
    assert not differs, f"routes answer differently from the installed app: {differs}"
    assert app["claude_md"] == checkout["claude_md"]
    assert app["plugin_root_is_code_root"] is True
