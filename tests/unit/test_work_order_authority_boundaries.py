from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO_ROOT / "docs" / "contracts"
OPERATIONS_ROOT = REPO_ROOT / "docs" / "operations"

WORK_ORDER_DOCS = [
    CONTRACT_ROOT / "work-order-contract.md",
    CONTRACT_ROOT / "approval-contract.md",
    CONTRACT_ROOT / "execution-packet-contract.md",
    CONTRACT_ROOT / "work-result-contract.md",
    CONTRACT_ROOT / "work-ledger-contract.md",
    CONTRACT_ROOT / "human-in-the-loop-contract.md",
    CONTRACT_ROOT / "eval-artifact-contract.md",
    OPERATIONS_ROOT / "work-orders.md",
]

NON_EXECUTION_COMMANDS = [
    "create",
    "validate",
    "render",
    "status",
    "record-result",
    "report",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined_text() -> str:
    return "\n".join(_read(path) for path in WORK_ORDER_DOCS)


def test_phase16_contracts_require_file_backed_storage_only() -> None:
    text = _combined_text()

    assert "file_backed" in text
    assert "file-backed only" in text
    assert "Phase 16 ledger is file-backed only" in text
    assert "DB/event integration is deferred" in text


def test_phase16_contracts_prohibit_db_schema_and_real_runtime_event_writes() -> None:
    text = _combined_text()
    schema_updates = "schema " + "migra" + "tions"

    expected_terms = [
        "must not add DB tables",
        "add Work Order DB tables in Phase 16",
        f"add {schema_updates}",
        f"{schema_updates} in Phase 16",
        "write events to the real runtime DB by default",
        "write real-runtime-DB events by default",
        "write `canonical_events`",
        "must not imply real-runtime-DB writes",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_non_execution_commands_are_contractually_non_mutating() -> None:
    work_order = _read(CONTRACT_ROOT / "work-order-contract.md")
    operations = _read(OPERATIONS_ROOT / "work-orders.md")

    for command in NON_EXECUTION_COMMANDS:
        assert command in work_order
        assert command in operations

    assert (
        "must not mutate target repositories during `create`, `validate`, `render`, "
        "`status`, `record-result`, or `report`"
    ) in work_order
    assert "These commands must not mutate target repos during Phase 16" in operations


def test_dreamysuite_remains_phase17_only_and_not_phase16_execution() -> None:
    operations = _read(OPERATIONS_ROOT / "work-orders.md")
    contract = _read(CONTRACT_ROOT / "work-order-contract.md")

    assert "DreamySuite is Phase 17 only" in operations
    assert (
        "must not touch, inspect, clone, modify, validate, or execute against DreamySuite"
        in operations
    )
    assert "execute DreamySuite work before Phase 17" in contract


def test_retired_hooks_lib_reference_is_only_absence_language() -> None:
    for path in WORK_ORDER_DOCS:
        text = _read(path)
        if "hooks/lib" not in text:
            continue

        lowered = text.lower()
        assert "retired" in lowered
        assert "recreate" in lowered or "recreated" in lowered or "absent" in lowered


def test_contracts_do_not_grant_authority_to_non_authoritative_surfaces() -> None:
    text = _combined_text().lower()

    forbidden_grants = [
        "dashboards own canonical",
        "telemetry owns canonical",
        "adapters own canonical",
        "research owns canonical",
        "enterprise owns canonical",
        "docker owns canonical",
        "cloud owns canonical",
        "org/global owns canonical",
        "docker is canonical",
        "dashboards are canonical",
        "telemetry is canonical",
        "adapters are canonical",
        "research is canonical",
        "enterprise is canonical",
    ]

    violations = [phrase for phrase in forbidden_grants if phrase in text]

    assert violations == []
    assert "do not become work order authority" in text
    assert "remain non-authoritative" in text
