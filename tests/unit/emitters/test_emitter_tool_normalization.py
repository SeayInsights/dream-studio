"""Emitter and tool normalization boundary guardrails.

Replaces tests/unit/test_adapter_tool_boundaries.py.
Verifies that emitters/ is a pure normalization layer: no vendor SDK
imports, no authority DB writes, no network calls, no subprocess.
"""

from __future__ import annotations

import ast
import importlib
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[3]
EMITTER_ROOT = REPO_ROOT / "emitters"
RUNTIME_HOOKS_ROOT = REPO_ROOT / "runtime" / "hooks"

VENDOR_SDK_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(openai|anthropic|google\.generativeai|google_genai|litellm|ollama|"
    r"mistralai|cohere|groq|cursor|mcp|claude)\b",
    re.MULTILINE,
)

TOP_LEVEL_ADAPTER_IMPORT_PATTERN = re.compile(
    r"^\s*from\s+adapters\s+import\b",
    re.MULTILINE,
)

SQL_ADAPTER_EXECUTION_WRITE_PATTERN = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+adapter_executions\b",
    re.IGNORECASE,
)

PROVIDER_OR_NETWORK_IMPORT_PREFIXES = {
    "openai",
    "anthropic",
    "google.generativeai",
    "google_genai",
    "litellm",
    "ollama",
    "mistralai",
    "cohere",
    "groq",
    "cursor",
    "mcp",
    "claude",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "websocket",
}

EMITTER_FORBIDDEN_IMPORT_PREFIXES = PROVIDER_OR_NETWORK_IMPORT_PREFIXES | {
    "sqlite3",
    "subprocess",
    "core.config.database",
    "core.event_store",
    "interfaces.adapters",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts and ".venv" not in path.parts]


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _matches_any_prefix(module: str, prefixes: set[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _top_level_subprocess_calls(path: Path) -> list[str]:
    source = _read(path)
    tree = ast.parse(source)
    calls: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                calls.append(f"{_rel(path)}:{child.lineno} subprocess.{func.attr}()")
    return calls


def test_authority_paths_do_not_import_provider_sdks_directly():
    roots = [
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "runtime",
        REPO_ROOT / "projections",
        REPO_ROOT / "integrations",
        REPO_ROOT / "emitters",
        REPO_ROOT / "hooks",
    ]
    offenders: list[str] = []

    for path in _python_files(*roots):
        source = _read(path)
        for match in VENDOR_SDK_IMPORT_PATTERN.finditer(source):
            offenders.append(f"{_rel(path)} imports {match.group(1)}")

    assert offenders == []


def test_emitter_layer_is_pure_normalization_only():
    """emitters/ must not import vendor SDKs, sqlite3, subprocess, or interfaces.adapters."""
    offenders: list[str] = []

    for path in _python_files(EMITTER_ROOT):
        modules = _imported_modules(_read(path))
        for module in sorted(modules):
            if _matches_any_prefix(module, EMITTER_FORBIDDEN_IMPORT_PREFIXES):
                offenders.append(f"{_rel(path)} imports {module}")

    assert offenders == []


def test_importing_core_execution_is_opt_in_and_side_effect_free(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_profile = tmp_path / "profile"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_profile))

    def forbidden_call(*_args, **_kwargs):
        raise AssertionError("core.execution import attempted an external/runtime side effect")

    monkeypatch.setattr(subprocess, "run", forbidden_call)
    monkeypatch.setattr(subprocess, "Popen", forbidden_call)
    monkeypatch.setattr(socket, "create_connection", forbidden_call)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_call)

    for name in list(sys.modules):
        if name == "core.execution" or name.startswith("core.execution."):
            sys.modules.pop(name)

    module = importlib.import_module("core.execution")

    assert "core.execution.github_adapter" not in sys.modules
    assert "core.execution.ci_collector" not in sys.modules
    assert "core.execution.real_feedback" not in sys.modules
    assert module.GitHubAdapter.__name__ == "GitHubAdapter"
    assert module.CICollector.__name__ == "CICollector"
    assert not (fake_home / ".dream-studio").exists()
    assert not (fake_profile / ".dream-studio").exists()


def test_github_and_ci_execution_tools_remain_explicit_method_only_adapters():
    github_adapter = REPO_ROOT / "core" / "execution" / "github_adapter.py"
    ci_collector = REPO_ROOT / "core" / "execution" / "ci_collector.py"
    offenders: list[str] = []

    for path in [github_adapter, ci_collector]:
        source = _read(path)
        modules = _imported_modules(source)

        offenders.extend(_top_level_subprocess_calls(path))

        if "subprocess" not in modules:
            offenders.append(f"{_rel(path)} no longer declares explicit subprocess dependency")
        # Accept either legacy core.events path or new canonical.events spool pipeline (Slice 3)
        routes_events = (
            "core.events" in modules
            or "core.events.types" in modules
            or "canonical.events.envelope" in modules
            or "emitters.shared.spool_writer" in modules
        )
        if not routes_events:
            offenders.append(f"{_rel(path)} does not route events through core contracts")
        if "core.decisions" not in modules:
            offenders.append(f"{_rel(path)} does not route decisions through core contracts")
        for module in sorted(modules):
            if _matches_any_prefix(module, {"sqlite3", "core.config.database", "core.event_store"}):
                offenders.append(f"{_rel(path)} imports DB authority module {module}")

    assert offenders == []


def test_adapter_executions_stays_diagnostic_without_runtime_writer():
    migration = _read(
        REPO_ROOT / "core" / "event_store" / "migrations" / "030_adapter_metadata.sql"
    )
    writers: list[str] = []

    for path in _python_files(
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "runtime",
        REPO_ROOT / "projections",
        REPO_ROOT / "integrations",
        REPO_ROOT / "emitters",
    ):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        source = _read(path)
        if SQL_ADAPTER_EXECUTION_WRITE_PATTERN.search(source):
            writers.append(_rel(path))

    assert "CREATE TABLE IF NOT EXISTS adapter_executions" in migration
    assert "FOREIGN KEY (activity_id) REFERENCES activity_log" in migration
    assert writers == []


def test_runtime_hooks_do_not_import_provider_sdks_or_adapters_directly():
    offenders: list[str] = []

    for path in _python_files(RUNTIME_HOOKS_ROOT):
        source = _read(path)
        modules = _imported_modules(source)
        for module in sorted(modules):
            if _matches_any_prefix(module, PROVIDER_OR_NETWORK_IMPORT_PREFIXES):
                offenders.append(f"{_rel(path)} imports provider/network module {module}")
            if module == "interfaces.adapters" or module.startswith("interfaces.adapters."):
                offenders.append(f"{_rel(path)} imports adapter interface {module}")
            if module == "adapters" or module.startswith("adapters."):
                offenders.append(f"{_rel(path)} imports legacy adapter package {module}")

    assert offenders == []


def test_runtime_model_metadata_defaults_are_provider_neutral():
    skill_complete = _read(REPO_ROOT / "runtime" / "hooks" / "meta" / "on-skill-complete.py")
    skill_metrics = _read(REPO_ROOT / "runtime" / "hooks" / "meta" / "on-skill-metrics.py")
    studio_db_source = _read(REPO_ROOT / "core" / "event_store" / "studio_db.py")

    assert 'os.environ.get("CLAUDE_MODEL", "claude")' not in skill_complete
    assert 'model = "sonnet"' not in skill_metrics
    assert 'model: str = "claude"' not in studio_db_source
    assert '"CLAUDE_MODEL"' in skill_complete
    assert '"DREAM_STUDIO_MODEL"' in skill_complete
    assert '"unspecified"' in skill_complete
    assert '"unspecified"' in skill_metrics
    assert 'model: str = "unspecified"' in studio_db_source


def test_discovery_provider_names_remain_catalog_metadata_only():
    files = [
        REPO_ROOT / "control" / "research" / "tools.py",
        REPO_ROOT / "projections" / "api" / "routes" / "discovery_external.py",
    ]
    offenders: list[str] = []

    for path in files:
        source = _read(path)
        modules = _imported_modules(source)
        for module in sorted(modules):
            if _matches_any_prefix(module, PROVIDER_OR_NETWORK_IMPORT_PREFIXES):
                offenders.append(f"{_rel(path)} imports provider/network module {module}")
        for token in ["subprocess.", "requests.", "httpx.", "urllib.", "socket.", "websocket."]:
            if token in source:
                offenders.append(f"{_rel(path)} contains external call token {token}")

    tool_source = _read(files[0])
    route_source = _read(files[1])

    assert "class ToolMatch" in tool_source
    assert "tool_registry" in tool_source
    assert "tool_registry" in route_source
    assert offenders == []


def test_legacy_top_level_adapter_import_residue_is_absent():
    top_level_imports: set[str] = set()

    for path in _python_files(
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "runtime",
        REPO_ROOT / "projections",
        REPO_ROOT / "integrations",
        REPO_ROOT / "emitters",
    ):
        source = _read(path)
        if TOP_LEVEL_ADAPTER_IMPORT_PATTERN.search(source):
            top_level_imports.add(_rel(path))

    assert top_level_imports == set()
