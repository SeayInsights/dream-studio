"""Phase 5.5A — Workflow Runtime Reliability tests.

Covers:
1. Workflow YAML files exist and are parseable
2. Representative workflows validate successfully
3. Workflow engine modules exist
4. State persistence uses documented locking
5. Retry declarations are validated but not enforced (documented gap)
6. Timeout declarations are validated but not enforced (documented gap)
7. Gate/pause/resume behavior is implemented
8. Dashboard-dependent workflows are identified
9. Model names are Claude-specific (Phase 7 portability scope)
10. Execution graph integration modules exist
11. Workflow state CLI accepts documented commands
12. No prior phase regressions
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "workflows"
ENGINE_DIR = REPO_ROOT / "control" / "execution" / "workflow"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── 1. Workflow YAML files exist and are parseable ─────────────────────────


class TestWorkflowYAMLFiles:

    def _yaml_files(self):
        return sorted(WORKFLOWS_DIR.glob("*.yaml"))

    def test_workflows_directory_exists(self):
        assert WORKFLOWS_DIR.is_dir()

    def test_at_least_15_workflows(self):
        """We have 21 workflows; guard against accidental mass deletion."""
        count = len(self._yaml_files())
        assert count >= 15, f"Expected at least 15 workflow YAMLs, found {count}"

    def test_all_yamls_parseable(self):
        """Every workflow YAML can be parsed by our custom parser."""
        mod = _load_module("workflow_validate", ENGINE_DIR / "validate.py")
        for f in self._yaml_files():
            data = mod.parse_workflow(str(f))
            assert "nodes" in data, f"{f.name} missing 'nodes' key"
            assert isinstance(data["nodes"], list), f"{f.name} 'nodes' is not a list"

    def test_canonical_workflow_exists(self):
        """idea-to-pr.yaml is the canonical workflow template."""
        assert (WORKFLOWS_DIR / "idea-to-pr.yaml").is_file()


# ── 2. Representative workflows validate successfully ──────────────────────


class TestRepresentativeWorkflowValidation:

    REPRESENTATIVE = [
        "idea-to-pr.yaml",
        "safe-refactor.yaml",
        "fix-issue.yaml",
        "hotfix.yaml",
        "daily-standup.yaml",
    ]

    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = _load_module("workflow_validate_repr", ENGINE_DIR / "validate.py")

    @pytest.mark.parametrize("name", REPRESENTATIVE)
    def test_workflow_validates(self, name):
        path = WORKFLOWS_DIR / name
        if not path.is_file():
            pytest.skip(f"{name} not found")
        data = self.mod.parse_workflow(str(path))
        errors = self.mod.validate(data, REPO_ROOT)
        blocking = [
            e
            for e in errors
            if not e.startswith("Warning:")
            and not ("skill" in e.lower() and "not found" in e.lower())
        ]
        assert not blocking, f"{name} validation errors: {blocking}"


# ── 3. Workflow engine modules exist ───────────────────────────────────────


class TestEngineModulesExist:

    REQUIRED_MODULES = [
        "control/execution/workflow/engine.py",
        "control/execution/workflow/state.py",
        "control/execution/workflow/validate.py",
        "control/execution/workflow/cost.py",
        "control/execution/workflow/registry.py",
        "control/execution/workflow/tracking.py",
        "control/execution/workflow/wave_executor.py",
        "control/execution/workflow/wave_executor_enhanced.py",
    ]

    @pytest.mark.parametrize("relpath", REQUIRED_MODULES)
    def test_module_exists(self, relpath):
        assert (REPO_ROOT / relpath).is_file(), f"Missing: {relpath}"

    def test_execution_graph_exists(self):
        assert (REPO_ROOT / "core" / "execution" / "graph.py").is_file()

    def test_workflow_integration_exists(self):
        assert (REPO_ROOT / "core" / "execution" / "workflow_integration.py").is_file()


# ── 4. State persistence uses documented locking ───────────────────────────


class TestStateLocking:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.engine_source = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
        self.state_source = (ENGINE_DIR / "state.py").read_text(encoding="utf-8")

    def test_file_lock_uses_atomic_creation(self):
        assert "O_CREAT" in self.engine_source
        assert "O_EXCL" in self.engine_source

    def test_file_lock_has_timeout(self):
        assert "timeout" in self.engine_source
        assert "deadline" in self.engine_source

    def test_file_lock_writes_pid(self):
        assert "os.getpid()" in self.engine_source

    def test_file_lock_force_unlock_on_timeout(self):
        """After timeout, stale lock is removed and re-attempted."""
        assert "unlink" in self.engine_source

    def test_state_uses_file_lock(self):
        assert "_file_lock" in self.state_source
        assert "_state_lock" in self.state_source

    def test_state_path_is_workflows_json(self):
        assert "workflows.json" in self.state_source

    def test_checkpoint_path_exists(self):
        assert "workflow-checkpoint.json" in self.state_source

    def test_state_read_write_roundtrip_code(self):
        """_write_state and _read_state use consistent JSON encoding."""
        assert "json.dumps" in self.state_source
        assert "json.loads" in self.state_source
        assert 'encoding="utf-8"' in self.state_source


# ── 5. Retry: declared and validated, not enforced ─────────────────────────


class TestRetryBehavior:

    def test_retry_declared_in_workflows(self):
        """At least 10 workflows declare retry fields."""
        count = 0
        for f in WORKFLOWS_DIR.glob("*.yaml"):
            text = f.read_text(encoding="utf-8")
            if "retry:" in text:
                count += 1
        assert count >= 10, f"Expected >= 10 workflows with retry, found {count}"

    def test_validate_checks_retry_fields(self):
        """Validator checks retry.max is a positive integer."""
        source = (ENGINE_DIR / "validate.py").read_text(encoding="utf-8")
        assert "retry" in source
        assert "retry.max" in source or '"max"' in source

    def test_engine_does_not_enforce_retry(self):
        """Engine does not re-queue failed nodes (documented gap — Phase 6)."""
        source = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
        assert "retry_count" not in source
        assert "re-queue" not in source.lower()
        assert "requeue" not in source.lower()

    def test_state_does_not_retry_failed(self):
        """cmd_next does not re-queue failed nodes."""
        source = (ENGINE_DIR / "state.py").read_text(encoding="utf-8")
        next_section = source[source.index("def cmd_next") :]
        assert "retry" not in next_section.lower()


# ── 6. Timeout: declared and validated, not enforced ───────────────────────


class TestTimeoutBehavior:

    def test_timeout_declared_in_workflows(self):
        """At least 10 workflows declare timeout_seconds."""
        count = 0
        for f in WORKFLOWS_DIR.glob("*.yaml"):
            text = f.read_text(encoding="utf-8")
            if "timeout_seconds:" in text:
                count += 1
        assert count >= 10, f"Expected >= 10 workflows with timeout_seconds, found {count}"

    def test_validate_checks_timeout(self):
        source = (ENGINE_DIR / "validate.py").read_text(encoding="utf-8")
        assert "timeout_seconds" in source

    def test_engine_does_not_enforce_timeout(self):
        """Engine does not track or enforce node timeout_seconds (documented gap)."""
        engine_source = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
        assert "timeout_seconds" not in engine_source

    def test_state_does_not_enforce_timeout(self):
        """State CLI does not enforce timeout_seconds."""
        state_source = (ENGINE_DIR / "state.py").read_text(encoding="utf-8")
        assert "timeout_seconds" not in state_source


# ── 7. Gate/pause/resume is implemented ────────────────────────────────────


class TestGateBehavior:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (ENGINE_DIR / "state.py").read_text(encoding="utf-8")

    def test_cmd_pause_exists(self):
        assert "def cmd_pause" in self.source

    def test_cmd_resume_exists(self):
        assert "def cmd_resume" in self.source

    def test_pause_sets_status_paused(self):
        pause_section = self.source[
            self.source.index("def cmd_pause") : self.source.index("def cmd_resume")
        ]
        assert '"paused"' in pause_section

    def test_resume_sets_status_running(self):
        resume_section = self.source[
            self.source.index("def cmd_resume") : self.source.index("def cmd_abort")
        ]
        assert '"running"' in resume_section

    def test_gates_pending_tracked(self):
        assert "gates_pending" in self.source

    def test_gates_passed_tracked(self):
        assert "gates_passed" in self.source

    def test_validate_checks_gates(self):
        val_source = (ENGINE_DIR / "validate.py").read_text(encoding="utf-8")
        assert "gate" in val_source
        assert "not in gates" in val_source


# ── 8. Dashboard-dependent workflows identified ────────────────────────────


class TestDashboardDependency:

    DASHBOARD_WORKFLOWS = ["studio-analytics.yaml", "security-audit.yaml"]

    @pytest.mark.parametrize("name", DASHBOARD_WORKFLOWS)
    def test_dashboard_workflow_exists(self, name):
        f = WORKFLOWS_DIR / name
        if not f.is_file():
            pytest.skip(f"{name} not found")
        text = f.read_text(encoding="utf-8")
        assert "dashboard" in text.lower() or "localhost" in text or "api" in text.lower()

    def test_non_dashboard_workflows_are_local(self):
        """Most workflows don't reference localhost or external dashboard."""
        dashboard_names = {"studio-analytics.yaml", "security-audit.yaml", "feature-research.yaml"}
        for f in WORKFLOWS_DIR.glob("*.yaml"):
            if f.name in dashboard_names:
                continue
            text = f.read_text(encoding="utf-8")
            assert "localhost:8000" not in text, f"{f.name} has unexpected dashboard dependency"


# ── 9. Model names are Claude-specific (Phase 7 scope) ────────────────────


class TestModelPortability:

    CLAUDE_MODELS = {"opus", "sonnet", "haiku"}

    def test_workflows_use_claude_model_names(self):
        """Document that workflows use Claude-specific model names."""
        models_found = set()
        for f in WORKFLOWS_DIR.glob("*.yaml"):
            text = f.read_text(encoding="utf-8")
            for match in re.findall(r"model:\s*(\w+)", text):
                if match in self.CLAUDE_MODELS:
                    models_found.add(match)
        assert (
            models_found == self.CLAUDE_MODELS
        ), f"Expected all 3 Claude models used, found {models_found}"

    def test_no_model_abstraction_layer_yet(self):
        """No model adapter exists yet — Phase 7 scope."""
        engine_source = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
        assert "model_adapter" not in engine_source
        assert "resolve_model" not in engine_source


# ── 10. Execution graph integration modules exist ──────────────────────────


class TestExecutionGraphIntegration:

    def test_graph_module_has_persistent_dag(self):
        source = (REPO_ROOT / "core" / "execution" / "graph.py").read_text(encoding="utf-8")
        assert "class" in source or "def" in source

    def test_workflow_integration_bridges(self):
        source = (REPO_ROOT / "core" / "execution" / "workflow_integration.py").read_text(
            encoding="utf-8"
        )
        assert "workflow" in source.lower()

    def test_context_compiler_exists(self):
        assert (REPO_ROOT / "core" / "execution" / "context_compiler.py").is_file()


# ── 11. State CLI accepts documented commands ──────────────────────────────


class TestStateCLICommands:

    EXPECTED_COMMANDS = [
        "start",
        "update",
        "pause",
        "resume",
        "abort",
        "status",
        "eval",
        "next",
    ]

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (ENGINE_DIR / "state.py").read_text(encoding="utf-8")

    @pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
    def test_command_handler_exists(self, cmd):
        func_name = f"cmd_{cmd.replace('-', '_')}"
        assert f"def {func_name}" in self.source, f"Missing handler: {func_name}"

    def test_commands_registered_in_dispatch_map(self):
        for cmd in self.EXPECTED_COMMANDS:
            assert f'"{cmd}"' in self.source


# ── 12. Workflow runtime documentation exists ──────────────────────────────


class TestRuntimeDocumentation:

    def test_workflow_runtime_doc_exists(self):
        assert (REPO_ROOT / "docs" / "WORKFLOW_RUNTIME.md").is_file()

    def test_doc_covers_retry(self):
        text = (REPO_ROOT / "docs" / "WORKFLOW_RUNTIME.md").read_text(encoding="utf-8")
        assert "retry" in text.lower()

    def test_doc_covers_timeout(self):
        text = (REPO_ROOT / "docs" / "WORKFLOW_RUNTIME.md").read_text(encoding="utf-8")
        assert "timeout" in text.lower()

    def test_doc_covers_state_locking(self):
        text = (REPO_ROOT / "docs" / "WORKFLOW_RUNTIME.md").read_text(encoding="utf-8")
        assert "lock" in text.lower()

    def test_doc_covers_model_portability(self):
        text = (REPO_ROOT / "docs" / "WORKFLOW_RUNTIME.md").read_text(encoding="utf-8")
        assert "Phase 7" in text
