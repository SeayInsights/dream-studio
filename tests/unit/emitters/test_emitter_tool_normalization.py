"""Emitter and tool normalization boundary guardrails.

Replaces tests/unit/test_adapter_tool_boundaries.py.
Verifies that emitters/ is a pure normalization layer: no vendor SDK
imports, no authority DB writes, no network calls, no subprocess.
"""

from __future__ import annotations

import ast
import re
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


# test_importing_core_execution_is_opt_in_and_side_effect_free RETIRED:
# core/execution/ package deleted — ci_collector.py, real_feedback.py, github_adapter.py
# removed (zero production callers; lazy-export __init__ also deleted).

# test_github_and_ci_execution_tools_remain_explicit_method_only_adapters RETIRED:
# Same — source files deleted along with the package.


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
    studio_db_source = _read(REPO_ROOT / "core" / "event_store" / "event_writer.py")

    assert 'os.environ.get("CLAUDE_MODEL", "claude")' not in skill_complete
    assert 'model = "sonnet"' not in skill_metrics
    assert 'model: str = "claude"' not in studio_db_source
    assert '"CLAUDE_MODEL"' in skill_complete
    assert '"DREAM_STUDIO_MODEL"' in skill_complete
    assert '"unspecified"' in skill_complete
    assert '"unspecified"' in skill_metrics
    assert 'model: str = "unspecified"' in studio_db_source


# test_discovery_provider_names_remain_catalog_metadata_only RETIRED:
# control/research/tools.py deleted — no live caller, tool_registry table dropped
# in migration 131, confirmed test-only per invoked-not-imported audit.


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
