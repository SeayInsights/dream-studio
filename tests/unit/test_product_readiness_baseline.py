"""Phase 14B product-readiness baseline guardrails."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTERPRISE_ROOT = REPO_ROOT.parent / "dream-studio-enterprise"
AUDIT_ROOT = Path.home() / ".dream-studio" / "meta" / "audit"

CONTRACT_DOCS = [
    "event-contract.md",
    "state-contract.md",
    "projection-contract.md",
    "adapter-contract.md",
    "governance-contract.md",
    "skill-contract.md",
    "workflow-contract.md",
    "hook-contract.md",
    "agent-contract.md",
    "portable-execution-contract.md",
    "research-source-contract.md",
    "enterprise-aggregation-contract.md",
]

OPERATION_DOCS = [
    "local-runtime.md",
    "windows-dev-commands.md",
    "docker-clean-room.md",
    "product-readiness.md",
    "code-history-impact-guardrail.md",
    "lint-format-baseline-policy.md",
]

KEY_SCRIPTS = [
    "scripts/dev.ps1",
    "scripts/runtime_state_hash_guard.py",
]

CRITICAL_TESTS = [
    "tests/unit/test_dashboard_projection_boundaries.py",
    "tests/unit/test_governance_privacy_boundaries.py",
    "tests/unit/test_portable_primitive_contracts.py",
    "tests/unit/test_research_source_contract.py",
    "tests/unit/test_enterprise_aggregation_boundaries.py",
]

PRIOR_REPORTS = [
    "2026-05-10-phase8j-closeout-report.md",
    "2026-05-10-phase9d-closeout-report.md",
    "2026-05-10-phase10d-closeout-report.md",
    "2026-05-10-phase11y-portable-primitive-contracts-report.md",
    "2026-05-10-phase12d-research-source-closeout-report.md",
    "2026-05-11-phase13d-enterprise-boundary-closeout-report.md",
    "2026-05-11-phase14a-validation-readiness-inventory.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _files_under(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    text_suffixes = {
        ".cfg",
        ".ini",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".sql",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    for raw in paths:
        root = REPO_ROOT / raw
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in text_suffixes
                and "__pycache__" not in path.parts
                and ".pytest_cache" not in path.parts
            )
    return sorted(files)


def test_required_product_readiness_artifacts_exist():
    required_paths = [
        *(REPO_ROOT / "docs" / "contracts" / name for name in CONTRACT_DOCS),
        *(REPO_ROOT / "docs" / "operations" / name for name in OPERATION_DOCS),
        *(REPO_ROOT / path for path in KEY_SCRIPTS),
        *(REPO_ROOT / path for path in CRITICAL_TESTS),
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    assert missing == []


def test_product_readiness_doc_documents_commands_warnings_and_risks():
    doc = _read(REPO_ROOT / "docs" / "operations" / "product-readiness.md").lower()

    for phrase in [
        "product-readiness",
        "runtime_state_hash_guard.py",
        "phase15_verify",
        "phase15_full_suite",
        "not a replacement for hash-guarded",
        "docker is optional",
        "enterprise remains adjacent",
        "missing temp session root warning",
        "requestsdependencywarning",
        "coverage warning for absent retired `hooks/lib`",
        "statsmodels",
        "dreamstudio_enterprise_key",
        "observed schema version",
        "must not hard-code one operator machine's historical schema skew",
        "enterprise aggregate/redacted input package schema",
        "not implemented by this baseline",
        "code-history-impact-guardrail.md",
        "lint-format-baseline-policy.md",
    ]:
        assert phrase in doc


def test_dev_script_exposes_narrow_product_readiness_target():
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")

    assert "product-readiness" in dev_script
    assert "test_product_readiness_baseline.py" in dev_script

    match = re.search(
        r'(?ms)^\s+"product-readiness"\s*\{\s*(?P<body>.*?)^\s*\}',
        dev_script,
    )
    assert match is not None
    body = match.group("body")

    assert "tests/unit/test_product_readiness_baseline.py" in body
    assert "runtime_state_hash_guard.py" not in body
    assert "docker-runtime-check" not in body
    assert '"tests/"' not in body
    assert "dream-studio-enterprise" not in body


def test_local_marketplace_declares_structured_source_for_codex_loader():
    marketplace = json.loads(_read(REPO_ROOT / ".claude-plugin" / "marketplace.json"))
    plugins = marketplace.get("plugins", [])
    dream_studio = next(item for item in plugins if item.get("name") == "dream-studio")
    source = dream_studio.get("source")

    assert source == {"source": "local", "path": "."}


def test_authority_invariants_are_part_of_readiness_baseline():
    assert not (REPO_ROOT / "hooks" / "lib").exists()
    assert (REPO_ROOT / "runtime" / "hooks").is_dir()
    assert (REPO_ROOT / "core" / "event_store" / "migrations" / "034_execution_graph.sql").is_file()

    checks = [
        (
            ["skills"],
            re.compile(r"name:\s*" + re.escape("dream-" "studio:") + r"\s*", re.IGNORECASE),
            "forbidden skill name prefix",
        ),
        (
            [
                "control",
                "core",
                "interfaces",
                "projections",
                "skills",
                "docs/contracts",
                "tests/unit",
            ],
            re.compile(re.escape("dream-" "studio:") + r"\s*"),
            "forbidden legacy authority identifier",
        ),
        (
            ["control", "tests", "projections", "core", "interfaces"],
            re.compile(r'"' + re.escape("d" "s:")),
            "forbidden ds colon fixture",
        ),
        (
            ["skills"],
            re.compile(r"name:\s*ds-", re.IGNORECASE),
            "skill name must not replace skill_id semantics",
        ),
    ]

    # Phase 20 (WO-P20-MARKETPLACE) sanctions `dream-studio:` as the Claude plugin
    # *namespace* for skill IDs (e.g. dream-studio:ds-core:build), distinct from the
    # banned legacy authority identifier. These files implement/exercise that
    # namespace and are exempt from the "forbidden legacy authority identifier" check
    # only. The ban remains in force everywhere else.
    _PHASE20_NAMESPACE_ALLOW = {
        "core/skills/invocation.py",
        "tests/unit/test_plugin_manifest.py",
        # This file documents the sanctioned namespace in the comment above.
        "tests/unit/test_product_readiness_baseline.py",
    }

    offenders: list[str] = []
    for roots, pattern, label in checks:
        for path in _files_under(roots):
            rel = _rel(path).replace("\\", "/")
            if label == "forbidden legacy authority identifier" and rel in _PHASE20_NAMESPACE_ALLOW:
                continue
            if pattern.search(_read(path)):
                offenders.append(f"{label}: {rel}")

    assert offenders == []


def test_docker_and_enterprise_remain_non_authoritative_and_excluded():
    docker_doc = _read(REPO_ROOT / "docs" / "operations" / "docker-clean-room.md").lower()
    enterprise_contract = _read(
        REPO_ROOT / "docs" / "contracts" / "enterprise-aggregation-contract.md"
    ).lower()
    readiness_doc = _read(REPO_ROOT / "docs" / "operations" / "product-readiness.md").lower()
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")

    assert "optional validation harness" in docker_doc
    assert "not a runtime authority" in docker_doc
    assert "optional derived consumers" in enterprise_contract
    assert "not normal main validation" in enterprise_contract
    assert "enterprise remains adjacent" in readiness_doc
    assert "dream-studio-enterprise" not in dev_script
    assert "tests/test_ml.py" not in dev_script.replace("\\", "/")


def test_adjacent_enterprise_static_boundaries_remain_clean():
    if not ENTERPRISE_ROOT.exists():
        pytest.skip("Adjacent enterprise repo is not present in this workspace")

    checks = [
        (
            ["api", "ml", "org_intelligence", "tests", "README.md", "pyproject.toml"],
            re.compile(r"~/\.dream-studio|studio\.db"),
            "live native DB reference",
        ),
        (
            ["api", "ml", "org_intelligence", "tests", "generate_org_intelligence.py"],
            re.compile(
                r"from projections|import projections|from core|import core|sys\.path\.insert"
            ),
            "main internal import",
        ),
        (
            ["tests", "api", "ml", "org_intelligence", "README.md"],
            re.compile(re.escape("dream-" "studio:") + r'|"' + re.escape("d" "s:")),
            "legacy skill identifier",
        ),
    ]

    offenders: list[str] = []
    for roots, pattern, label in checks:
        for raw in roots:
            root = ENTERPRISE_ROOT / raw
            if root.is_file():
                paths = [root]
            elif root.is_dir():
                paths = [
                    path
                    for path in root.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                ]
            else:
                paths = []
            for path in paths:
                if pattern.search(_read(path)):
                    offenders.append(f"{label}: {path.relative_to(ENTERPRISE_ROOT).as_posix()}")

    assert offenders == []


def test_phase15_readiness_risks_are_documented_not_implemented():
    readiness_doc = _read(REPO_ROOT / "docs" / "operations" / "product-readiness.md").lower()
    enterprise_contract = _read(
        REPO_ROOT / "docs" / "contracts" / "enterprise-aggregation-contract.md"
    ).lower()
    local_runtime_doc = _read(REPO_ROOT / "docs" / "operations" / "local-runtime.md").lower()

    for phrase in [
        "read-only guards",
        "record the observed schema version in local evidence",
        "not implemented by this baseline",
        "must not be treated as a main runtime dependency",
    ]:
        assert phrase in readiness_doc

    assert "phase 13b adds no schema migrations" in enterprise_contract
    assert "blocked_newer_than_code" in local_runtime_doc
