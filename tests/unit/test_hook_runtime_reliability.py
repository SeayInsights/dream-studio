"""Phase 5.4A — Hook Runtime Reliability tests.

Covers:
1. Hook infrastructure files exist
2. hooks/hooks.json is valid and references resolvable handlers
3. hooks/run.py, run.sh, and run.cmd use runtime/hooks as canonical root
4. hooks/run.py, run.sh, and run.cmd include PLUGIN_ROOT in PYTHONPATH
5. run.sh and run.cmd use version-aware Python fallback
6. All registered hook handlers resolve to existing files
7. Dispatcher sub-handlers all resolve to existing files
8. Unregistered/dead handlers are classified
9. Legacy handlers are classified
10. No active hook command points to obsolete hooks/lib paths
11. run.sh and run.cmd search the same pack directories
12. Dispatcher paths use runtime/hooks/ (not packs/)
13. Dispatch infrastructure modules exist
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_PACKS = ["core", "quality", "career", "analyze", "domains", "meta"]


# ── 1. Hook infrastructure files exist ─────────────────────────────────────


class TestHookInfrastructureExists:

    REQUIRED_FILES = [
        "hooks/hooks.json",
        "hooks/run.py",
        "hooks/run.sh",
        "hooks/run.cmd",
    ]

    @pytest.mark.parametrize("relpath", REQUIRED_FILES)
    def test_infrastructure_file_exists(self, relpath):
        assert (REPO_ROOT / relpath).is_file(), f"Missing: {relpath}"

    def test_dispatch_tracking_exists(self):
        assert (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").is_file()

    def test_dispatch_helpers_exists(self):
        assert (REPO_ROOT / "control" / "execution" / "dispatch_helpers.py").is_file()


# ── 2. hooks/hooks.json is valid JSON with expected structure ──────────────


class TestHooksJsonValid:

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(REPO_ROOT / "hooks" / "hooks.json", encoding="utf-8") as f:
            self.config = json.load(f)

    def test_has_hooks_key(self):
        assert "hooks" in self.config

    def test_registered_events(self):
        events = set(self.config["hooks"].keys())
        assert "UserPromptSubmit" in events
        assert "Stop" in events
        assert "PostToolUse" in events

    def test_all_commands_use_cross_platform_launcher(self):
        """Every hook command routes through hooks/run.py without env-only expansion."""

        def extract_commands(obj):
            cmds = []
            if isinstance(obj, dict):
                if "command" in obj:
                    cmds.append(obj["command"])
                for v in obj.values():
                    cmds.extend(extract_commands(v))
            elif isinstance(obj, list):
                for item in obj:
                    cmds.extend(extract_commands(item))
            return cmds

        for cmd in extract_commands(self.config):
            assert "'hooks'/'run.py'" in cmd, f"Command does not use run.py: {cmd}"
            assert '"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh"' not in cmd

    def test_user_prompt_submit_command_resolves_without_env_root(self, tmp_path):
        """Registered prompt hook resolves from repo descendants without CLAUDE_PLUGIN_ROOT."""
        home = tmp_path / "home"
        home.mkdir()
        env = os.environ.copy()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env["USERPROFILE"] = str(home)
        env["HOME"] = str(home)
        env["DREAM_STUDIO_DB_PATH"] = str(tmp_path / "studio.db")
        command = self.config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]

        result = subprocess.run(
            command,
            input="{}",
            text=True,
            capture_output=True,
            cwd=REPO_ROOT / "runtime",
            env=env,
            shell=True,
            timeout=45,
        )

        assert result.returncode == 0, result.stderr
        assert "/hooks/run.sh" not in result.stderr


# ── 3. Registered handlers exist as files ──────────────────────────────────


class TestRegisteredHandlersExist:

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(REPO_ROOT / "hooks" / "hooks.json", encoding="utf-8") as f:
            self.config = json.load(f)

    def _extract_handler_names(self):
        """Extract handler names from hooks.json commands."""
        names = []

        def walk(obj):
            if isinstance(obj, dict):
                if "command" in obj:
                    parts = obj["command"].strip().split()
                    if len(parts) >= 2:
                        names.append(parts[-1].strip('"'))
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(self.config)
        return names

    def test_all_registered_handlers_resolve(self):
        """Every handler name in hooks.json resolves to a file in runtime/hooks/."""
        for name in self._extract_handler_names():
            found = False
            for pack in CANONICAL_PACKS:
                candidate = REPO_ROOT / "runtime" / "hooks" / pack / f"{name}.py"
                if candidate.is_file():
                    found = True
                    break
            if not found:
                candidate = REPO_ROOT / "hooks" / "handlers" / f"{name}.py"
                if candidate.is_file():
                    found = True
            assert found, f"Registered handler not found: {name}"


# ── 4. run.sh and run.cmd use runtime/hooks as canonical root ──────────────


class TestLauncherCanonicalRoot:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.run_py = (REPO_ROOT / "hooks" / "run.py").read_text(encoding="utf-8")
        self.run_sh = (REPO_ROOT / "hooks" / "run.sh").read_text(encoding="utf-8")
        self.run_cmd = (REPO_ROOT / "hooks" / "run.cmd").read_text(encoding="utf-8")

    def test_run_py_searches_runtime_hooks(self):
        assert '"runtime" / "hooks"' in self.run_py

    def test_run_sh_searches_runtime_hooks(self):
        assert "runtime/hooks" in self.run_sh

    def test_run_cmd_searches_runtime_hooks(self):
        assert "runtime\\hooks" in self.run_cmd


# ── 5. run.sh and run.cmd include PLUGIN_ROOT in PYTHONPATH ────────────────


class TestLauncherPythonPath:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.run_py = (REPO_ROOT / "hooks" / "run.py").read_text(encoding="utf-8")
        self.run_sh = (REPO_ROOT / "hooks" / "run.sh").read_text(encoding="utf-8")
        self.run_cmd = (REPO_ROOT / "hooks" / "run.cmd").read_text(encoding="utf-8")

    def test_run_py_plugin_root_in_pythonpath(self):
        assert 'os.environ["PYTHONPATH"]' in self.run_py
        assert 'os.environ["CLAUDE_PLUGIN_ROOT"]' in self.run_py

    def test_run_sh_plugin_root_in_pythonpath(self):
        assert "${PLUGIN_ROOT}:${PLUGIN_ROOT}/hooks" in self.run_sh

    def test_run_cmd_plugin_root_in_pythonpath(self):
        assert (
            "%PLUGIN_ROOT%;%PLUGIN_ROOT%\\hooks" in self.run_cmd
            or "!PLUGIN_ROOT!;!PLUGIN_ROOT!\\hooks" in self.run_cmd
        )

    def test_run_sh_exports_claude_plugin_root(self):
        assert 'CLAUDE_PLUGIN_ROOT="${PLUGIN_ROOT}"' in self.run_sh

    def test_run_cmd_sets_claude_plugin_root(self):
        assert (
            "CLAUDE_PLUGIN_ROOT=%PLUGIN_ROOT%" in self.run_cmd
            or "CLAUDE_PLUGIN_ROOT=!PLUGIN_ROOT!" in self.run_cmd
        )


class TestWindowsPromptDispatcherLauncher:

    @pytest.mark.skipif(os.name != "nt", reason="run.cmd is Windows-only")
    def test_run_cmd_resolves_prompt_dispatcher_without_env_root(self, tmp_path):
        """Windows launcher must resolve the repo root when Claude omits CLAUDE_PLUGIN_ROOT."""
        home = tmp_path / "home"
        home.mkdir()
        env = os.environ.copy()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env["USERPROFILE"] = str(home)
        env["HOME"] = str(home)
        env["DREAM_STUDIO_DB_PATH"] = str(tmp_path / "studio.db")

        result = subprocess.run(
            [str(REPO_ROOT / "hooks" / "run.cmd"), "on-prompt-dispatch"],
            input="{}",
            text=True,
            capture_output=True,
            cwd=REPO_ROOT,
            env=env,
            timeout=30,
        )

        assert result.returncode == 0, result.stderr
        assert "handler not found" not in result.stderr


# ── 6. run.sh and run.cmd use version-aware Python fallback ────────────────


class TestLauncherPythonSelection:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.run_sh = (REPO_ROOT / "hooks" / "run.sh").read_text(encoding="utf-8")
        self.run_cmd = (REPO_ROOT / "hooks" / "run.cmd").read_text(encoding="utf-8")

    def test_run_sh_tries_version_pinned(self):
        assert "py -3.12" in self.run_sh

    def test_run_cmd_tries_version_pinned(self):
        assert "py -3.12" in self.run_cmd

    def test_run_sh_has_fallback(self):
        assert "python3" in self.run_sh
        assert "python" in self.run_sh

    def test_run_cmd_has_fallback(self):
        assert "python3" in self.run_cmd or "python" in self.run_cmd


# ── 7. run.sh and run.cmd search the same pack directories ─────────────────


class TestLauncherPackParity:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.run_sh = (REPO_ROOT / "hooks" / "run.sh").read_text(encoding="utf-8")
        self.run_cmd = (REPO_ROOT / "hooks" / "run.cmd").read_text(encoding="utf-8")

    def test_same_pack_search_order(self):
        """Both launchers search the same packs in the same order."""
        sh_match = re.search(r"for pack in ([^;]+);", self.run_sh)
        cmd_match = re.search(r"for %%K in \(([^)]+)\)", self.run_cmd)
        assert sh_match, "run.sh pack loop not found"
        assert cmd_match, "run.cmd pack loop not found"
        sh_packs = sh_match.group(1).split()
        cmd_packs = cmd_match.group(1).split()
        assert sh_packs == cmd_packs, f"Pack order mismatch: sh={sh_packs} cmd={cmd_packs}"


# ── 8. Dispatcher sub-handlers resolve to existing files ───────────────────


class TestDispatcherSubHandlerPaths:

    DISPATCHERS = [
        "runtime/hooks/meta/on-prompt-dispatch.py",
        "runtime/hooks/meta/on-stop-dispatch.py",
        "runtime/hooks/meta/on-edit-dispatch.py",
    ]

    @pytest.mark.parametrize("dispatcher_path", DISPATCHERS)
    def test_dispatcher_exists(self, dispatcher_path):
        assert (REPO_ROOT / dispatcher_path).is_file()

    def test_dispatchers_use_runtime_hooks_not_packs(self):
        """No dispatcher should reference packs/*/hooks/ paths."""
        for dp in self.DISPATCHERS:
            source = (REPO_ROOT / dp).read_text(encoding="utf-8")
            packs_refs = re.findall(r'"packs".*"hooks"', source)
            assert not packs_refs, f"{dp} still references packs/*/hooks/"

    def test_prompt_dispatch_sub_handlers_exist(self):
        source = (REPO_ROOT / "runtime" / "hooks" / "meta" / "on-prompt-dispatch.py").read_text(
            encoding="utf-8"
        )
        paths = re.findall(r'PLUGIN_ROOT / "runtime" / "hooks" / "(\w+)" / "([\w-]+)\.py"', source)
        for pack, handler in paths:
            target = REPO_ROOT / "runtime" / "hooks" / pack / f"{handler}.py"
            assert target.is_file(), f"Missing sub-handler: runtime/hooks/{pack}/{handler}.py"

    def test_stop_dispatch_sub_handlers_exist(self):
        source = (REPO_ROOT / "runtime" / "hooks" / "meta" / "on-stop-dispatch.py").read_text(
            encoding="utf-8"
        )
        paths = re.findall(r'PLUGIN_ROOT / "runtime" / "hooks" / "(\w+)" / "([\w-]+)\.py"', source)
        for pack, handler in paths:
            target = REPO_ROOT / "runtime" / "hooks" / pack / f"{handler}.py"
            assert target.is_file(), f"Missing sub-handler: runtime/hooks/{pack}/{handler}.py"

    def test_edit_dispatch_sub_handlers_exist(self):
        source = (REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-dispatch.py").read_text(
            encoding="utf-8"
        )
        paths = re.findall(r'PLUGIN_ROOT / "runtime" / "hooks" / "(\w+)" / "([\w-]+)\.py"', source)
        for pack, handler in paths:
            target = REPO_ROOT / "runtime" / "hooks" / pack / f"{handler}.py"
            assert target.is_file(), f"Missing sub-handler: runtime/hooks/{pack}/{handler}.py"


# ── 9. Legacy handlers are classified ──────────────────────────────────────


class TestLegacyHandlerClassification:

    def _legacy_files(self):
        return sorted((REPO_ROOT / "runtime" / "hooks").rglob("*_legacy.py"))

    def test_no_legacy_files_remain(self):
        """All legacy fallback handlers were removed in Phase 6B."""
        legacy = self._legacy_files()
        assert len(legacy) == 0, f"Legacy handlers should be removed: {[f.name for f in legacy]}"


# ── 10. Dead/unregistered handler classification ───────────────────────────


class TestDeadHandlerClassification:

    def test_on_session_resume_removed(self):
        """hooks/handlers/on-session-resume.py was removed in Phase 6B (dead import)."""
        f = REPO_ROOT / "hooks" / "handlers" / "on-session-resume.py"
        assert not f.is_file(), "Dead handler should have been removed in Phase 6B"

    def test_orphaned_handlers_removed(self):
        """Orphaned root-level and unwired handlers removed in Phase 6C."""
        for path in [
            REPO_ROOT / "runtime" / "hooks" / "on-startup-health.py",
            REPO_ROOT / "runtime" / "hooks" / "on-periodic-health.py",
            REPO_ROOT / "runtime" / "hooks" / "meta" / "on-skill-gate.py",
        ]:
            assert not path.is_file(), f"Orphaned handler should have been removed: {path.name}"


# ── 11. No active hook references obsolete hooks/lib paths ─────────────────


class TestNoObsoleteLibReferences:

    def test_hooks_json_no_lib_reference(self):
        source = (REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        assert "hooks/lib" not in source

    def test_dispatchers_no_hooks_lib_import(self):
        """Dispatchers must not import from legacy hook library (legacy compat)."""
        for dp in ["on-prompt-dispatch.py", "on-stop-dispatch.py", "on-edit-dispatch.py"]:
            source = (REPO_ROOT / "runtime" / "hooks" / "meta" / dp).read_text(encoding="utf-8")
            assert (
                "from legacy hook library" not in source
            ), f"{dp} imports from obsolete legacy hook library"


# ── 12. Dispatch infrastructure has required functions ──────────────────────


class TestDispatchInfrastructure:

    def test_dispatch_tracking_has_run_handlers(self):
        source = (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").read_text(
            encoding="utf-8"
        )
        assert "def run_handlers" in source

    def test_dispatch_tracking_has_execute_handlers(self):
        source = (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").read_text(
            encoding="utf-8"
        )
        assert "def execute_handlers" in source

    def test_dispatch_helpers_has_load_module(self):
        source = (REPO_ROOT / "control" / "execution" / "dispatch_helpers.py").read_text(
            encoding="utf-8"
        )
        assert "def load_module" in source

    def test_dispatch_helpers_has_write_timing(self):
        source = (REPO_ROOT / "control" / "execution" / "dispatch_helpers.py").read_text(
            encoding="utf-8"
        )
        assert "def write_timing" in source

    def test_run_handlers_skips_missing_files(self):
        """run_handlers checks path.is_file() before loading."""
        source = (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").read_text(
            encoding="utf-8"
        )
        assert "path.is_file()" in source


# ── 13. External service check ─────────────────────────────────────────────


class TestNoDefaultExternalCalls:

    EXTERNAL_PATTERNS = [
        r"https?://(?!127\.0\.0\.1|localhost)",
        r"firecrawl",
        r"jina\.ai",
        r"webhook",
    ]

    def test_active_handlers_no_external_calls(self):
        """No active (non-legacy) handler calls external services by default."""
        for pack in CANONICAL_PACKS:
            pack_dir = REPO_ROOT / "runtime" / "hooks" / pack
            if not pack_dir.is_dir():
                continue
            for f in pack_dir.glob("*.py"):
                if "_legacy" in f.name or f.name == "__init__.py":
                    continue
                source = f.read_text(encoding="utf-8")
                for pattern in self.EXTERNAL_PATTERNS:
                    matches = re.findall(pattern, source, re.IGNORECASE)
                    assert (
                        not matches
                    ), f"{f.name} makes external call matching '{pattern}': {matches}"
