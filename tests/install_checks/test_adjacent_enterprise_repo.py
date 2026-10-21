"""Install checks: the adjacent ``dream-studio-enterprise`` checkout honours the contract.

These read ANOTHER repository, checked out beside this one on the operator's machine, so
their answer is a fact about that checkout and that machine rather than about this code.
They used to run in the unit suite and skip when the sibling was absent -- which is every
CI runner and every git worktree (a worktree's parent directory is not the folder that holds
the sibling) -- so they could not fail and were never run. They are now opt-in, and they
fail when the checkout is absent::

    py -m pytest -m install_check tests/install_checks/test_adjacent_enterprise_repo.py

The checkout is ``$DS_ENTERPRISE_REPO`` when set, else ``dream-studio-enterprise`` beside the
main checkout.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.install_check

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTERPRISE_ROOT = Path(
    os.environ.get("DS_ENTERPRISE_REPO") or REPO_ROOT.parent / "dream-studio-enterprise"
)
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "enterprise-aggregation-contract.md"

LEGACY_SKILL_PREFIX = "dream-" "studio:"
LEGACY_DS_PREFIX = "d" "s:"

CANONICAL_AUTHORITY_TABLES = {
    "canonical_events",
    "business_canonical_events",
    # decision_log / decision_event_link dropped migration 136 (WO-DBA-EVAL-DECISION
    # T4): decisions are decision.recorded events in business_canonical_events.
    "execution_nodes",
    "execution_dependencies",
    "execution_outputs",
    "hook_executions",
    "memory_entries",
    "raw_sessions",
    "raw_token_usage",
    "raw_workflow_nodes",
    "raw_workflow_runs",
    "workflow_executions",
    "workflow_phases",
    "workflow_kpis",
    "phase_kpis",
    "guardrail_decisions",
    "audit_runs",
    "sec_sarif_findings",
    "sec_manual_reviews",
    "sec_cve_matches",
}

SQL_WRITE_PATTERNS = [
    (
        "CREATE TABLE",
        re.compile(
            r"\bCREATE\s+(?:VIRTUAL\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?"
            r"\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            re.IGNORECASE,
        ),
    ),
    (
        "INSERT INTO",
        re.compile(
            r"\bINSERT(?:\s+OR\s+(?:REPLACE|IGNORE|ROLLBACK|ABORT|FAIL))?"
            r"\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|VALUES\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "UPDATE",
        re.compile(
            r"\bUPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+SET\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DELETE FROM",
        re.compile(
            r"\bDELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:WHERE\b|$)",
            re.IGNORECASE,
        ),
    ),
]

KNOWN_LIVE_DB_REFERENCE_BLOCKERS: set[str] = set()

KNOWN_INTERNAL_IMPORT_BLOCKERS: set[tuple[str, str]] = set()


def _require_enterprise_repo() -> Path:
    assert ENTERPRISE_ROOT.exists(), (
        f"the adjacent enterprise repository is not at {ENTERPRISE_ROOT}; check it out there "
        "or set DS_ENTERPRISE_REPO, or do not run the install checks"
    )
    return ENTERPRISE_ROOT


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path, root: Path = REPO_ROOT) -> str:
    return path.relative_to(root).as_posix()


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    ]


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _sql_writes_in_file(path: Path, root: Path) -> list[tuple[str, str, str]]:
    source = _read(path)
    writes: list[tuple[str, str, str]] = []
    for operation, pattern in SQL_WRITE_PATTERNS:
        for match in pattern.finditer(source):
            writes.append((_rel(path, root), operation, match.group(1)))
    return writes


def test_enterprise_live_db_defaults_are_known_pre_integration_blockers():
    enterprise = _require_enterprise_repo()
    contract = _read(CONTRACT_PATH).lower()
    offenders: set[str] = set()

    for path in _python_files(enterprise):
        source = _read(path)
        if "~/.dream-studio/state/studio.db" in source:
            offenders.add(_rel(path, enterprise))

    assert offenders == KNOWN_LIVE_DB_REFERENCE_BLOCKERS
    assert "pre-integration blocker" in contract
    assert "forbidden live db defaults" in contract
    assert "must not read `~/.dream-studio/state/studio.db`" in contract
    assert "guardrails should fail if they return" in contract


def test_enterprise_imports_main_internals_only_as_classified_blockers():
    enterprise = _require_enterprise_repo()
    offenders: set[tuple[str, str]] = set()

    for path in _python_files(enterprise):
        for module in _imported_modules(_read(path)):
            if module == "core" or module.startswith("core."):
                offenders.add((_rel(path, enterprise), module))
            if module == "projections" or module.startswith("projections."):
                offenders.add((_rel(path, enterprise), module))

    assert offenders == KNOWN_INTERNAL_IMPORT_BLOCKERS

    contract = _read(CONTRACT_PATH).lower()
    assert "named shim" in contract
    assert "pre-integration blockers" in contract
    assert "not allowed in promoted normal validation" in contract
    assert "guardrails should fail if they return" in contract


def test_enterprise_artifacts_are_derived_and_require_explicit_paths():
    enterprise = _require_enterprise_repo()
    storage = _read(enterprise / "ml" / "storage.py")
    generator = _read(enterprise / "generate_org_intelligence.py")
    evaluation = _read(enterprise / "ml" / "evaluation.py")
    contract = _read(CONTRACT_PATH).lower()

    assert "def save_model(" in storage
    assert "filepath: str" in storage
    assert "joblib.dump" in storage or "pickle.dump" in storage
    assert "json.dump(model_metadata" in storage

    assert "def generate_org_intelligence(" in generator
    assert "output_dir: str" in generator
    assert "org_graph.json" in generator
    assert "vp_metrics.json" in generator
    assert "consolidation_opportunities.md" in generator

    assert "def export_evaluation_report(" in evaluation
    assert "filename: Union[str, Path]" in evaluation

    assert "ml artifacts include" in contract
    assert "derived enterprise-local artifacts" in contract
    assert "organization graphs" in contract
    assert "derived aggregate projections" in contract
    assert "explicit output path semantics" in contract


def test_enterprise_tests_with_legacy_identifiers_are_not_promotable_yet():
    enterprise = _require_enterprise_repo()
    test_source = _read(enterprise / "tests" / "test_ml.py")
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")
    contract = _read(CONTRACT_PATH).lower()

    assert LEGACY_SKILL_PREFIX not in test_source
    assert LEGACY_DS_PREFIX not in test_source
    assert "dream-studio-enterprise" not in dev_script
    assert "tests/test_ml.py" not in dev_script.replace("\\", "/")
    assert "tests are not normal main validation" in contract
    assert "retired or legacy skill identifier forms" in contract
    assert "must not silently promote them into normal validation" in contract
    assert "ds-core" in test_source


def test_enterprise_outputs_do_not_write_canonical_authority_tables():
    enterprise = _require_enterprise_repo()
    writes: list[tuple[str, str, str]] = []

    for path in _python_files(enterprise):
        if path.parts[-2:] == ("tests", "test_ml.py"):
            continue
        writes.extend(_sql_writes_in_file(path, enterprise))

    offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table in CANONICAL_AUTHORITY_TABLES
    ]

    assert offenders == []


def test_enterprise_tests_remain_excluded_until_isolated_and_contracted():
    enterprise = _require_enterprise_repo()
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")
    contract = _read(CONTRACT_PATH).lower()
    enterprise_test = enterprise / "tests" / "test_ml.py"

    assert enterprise_test.exists()
    assert "dream-studio-enterprise" not in dev_script
    assert str(enterprise_test) not in dev_script
    assert "enterprise tests are package-local" in contract
    assert "until all of these are true" in contract
    assert "tests use isolated temp state" in contract
    assert "tests import enterprise modules through the contracted package boundary" in contract


def test_adjacent_enterprise_static_boundaries_remain_clean():
    _require_enterprise_repo()

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
                if pattern.search(path.read_text(encoding="utf-8")):
                    offenders.append(f"{label}: {path.relative_to(ENTERPRISE_ROOT).as_posix()}")

    assert offenders == []
