"""Phase 11Y portable primitive contract guardrails."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTRACTS = {
    "skill": REPO_ROOT / "docs" / "contracts" / "skill-contract.md",
    "workflow": REPO_ROOT / "docs" / "contracts" / "workflow-contract.md",
    "hook": REPO_ROOT / "docs" / "contracts" / "hook-contract.md",
    "agent": REPO_ROOT / "docs" / "contracts" / "agent-contract.md",
    "portable": REPO_ROOT / "docs" / "contracts" / "portable-execution-contract.md",
}

RETIRED_HELPER_TOKENS = {
    "hooks/lib",
    r"hooks\lib",
    "HOOKS_LIB",
    "workflow_state.py",
    "workflow_validate.py",
    "context_compiler.py",
    "prompt_assembler.py",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _active_instruction_files() -> list[Path]:
    roots = [
        REPO_ROOT / "skills",
        REPO_ROOT / "workflows",
        REPO_ROOT / "agents",
    ]
    suffixes = {".md", ".yml", ".yaml", ".py"}
    files: list[Path] = [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "README.md"]
    for root in roots:
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in suffixes
                and "__pycache__" not in path.parts
            )
    return sorted(set(files))


def _skill_frontmatter(path: Path) -> str:
    text = _read(path)
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    return match.group(1) if match else ""


def test_required_portable_primitive_contract_docs_exist():
    missing = [_rel(path) for path in CONTRACTS.values() if not path.is_file()]
    assert missing == []


def test_contract_docs_define_required_fields_and_authority_boundaries():
    required_by_contract = {
        "skill": [
            "skill_id",
            "purpose",
            "inputs",
            "required context",
            "allowed tools",
            "forbidden actions",
            "output contract",
            "validation expectations",
            "event/telemetry obligations",
            "security/governance constraints",
            "adapter/rendering expectations",
            "ds-<slug>",
        ],
        "workflow": [
            "workflow_id",
            "states",
            "transitions",
            "gates",
            "required artifacts",
            "stop conditions",
            "approval points",
            "rollback/recovery rules",
            "validation commands",
            "event emissions",
            "local state authority boundaries",
            "portable rendering expectations",
        ],
        "hook": [
            "hook_id",
            "canonical Dream Studio trigger event",
            "target adapter event mapping",
            "conditions",
            "actions",
            "artifacts",
            "allowed state access",
            "failure behavior",
            "event emissions",
            "runtime/hooks",
            "hooks/lib",
        ],
        "agent": [
            "agent_id",
            "role",
            "allowed skills",
            "allowed workflows",
            "allowed tools",
            "forbidden actions",
            "approval requirements",
            "state access level",
            "output contract",
            "audit obligations",
            "execution environment requirements",
        ],
        "portable": [
            "canonical primitive definition",
            "target-specific rendering",
            "Claude rendering",
            "Codex rendering",
            "ChatGPT rendering",
            "Cursor rendering",
            "MCP/local model rendering",
            "Docker validation/sandbox rendering",
            "adapter boundaries",
            "governance/privacy boundaries",
            "event/telemetry expectations",
        ],
    }

    missing: list[str] = []
    for name, required_terms in required_by_contract.items():
        text = _read(CONTRACTS[name])
        lower_text = text.lower()
        for term in required_terms:
            if term.lower() not in lower_text:
                missing.append(f"{_rel(CONTRACTS[name])}: {term}")

        assert "do not own" in lower_text or "not authority" in lower_text

    assert missing == []


def test_active_skill_ids_use_canonical_ds_slug_form():
    offenders: list[str] = []
    skill_files = sorted((REPO_ROOT / "skills").rglob("SKILL.md"))
    assert skill_files

    for path in skill_files:
        frontmatter = _skill_frontmatter(path)
        if not frontmatter:
            continue
        for skill_id in re.findall(r"^\s*skill_id:\s*([^\s#]+)", frontmatter, re.MULTILINE):
            if not re.fullmatch(r"ds-[a-z0-9-]+", skill_id):
                offenders.append(f"{_rel(path)}: {skill_id}")

    assert offenders == []


def test_forbidden_skill_identifier_forms_absent_from_active_metadata():
    forbidden_patterns = {
        "dream" "-studio:": re.compile(r"(?<![A-Za-z0-9_-])" + re.escape("dream" "-studio:")),
        "d" "s:": re.compile(r"(?<![A-Za-z0-9_-])" + re.escape("d" "s:")),
    }
    metadata_files = [
        *sorted((REPO_ROOT / "skills").rglob("SKILL.md")),
        *sorted((REPO_ROOT / "skills").rglob("metadata.yml")),
        REPO_ROOT / "CLAUDE.md",
    ]

    offenders: list[str] = []
    for path in metadata_files:
        if not path.exists():
            continue
        text = _skill_frontmatter(path) if path.name == "SKILL.md" else _read(path)
        for token, pattern in forbidden_patterns.items():
            if pattern.search(text):
                offenders.append(f"{_rel(path)} contains {token}")

    assert offenders == []


def test_active_primitive_instructions_do_not_reference_retired_hook_helpers():
    offenders: list[str] = []

    for path in _active_instruction_files():
        text = _read(path)
        for token in RETIRED_HELPER_TOKENS:
            if token in text:
                offenders.append(f"{_rel(path)} references {token}")

    assert offenders == []


def test_hook_contract_and_filesystem_classify_active_and_retired_hook_paths():
    hook_contract = _read(CONTRACTS["hook"])

    assert "runtime/hooks" in hook_contract
    assert "hooks/lib" in hook_contract
    assert "retired" in hook_contract.lower()
    assert "absent" in hook_contract.lower()
    assert (REPO_ROOT / "runtime" / "hooks").is_dir()
    assert not (REPO_ROOT / "hooks" / "lib").exists()


def test_agent_contract_requires_tool_state_approval_output_and_audit_fields():
    agent_contract = _read(CONTRACTS["agent"]).lower()

    for term in [
        "allowed tools",
        "state access level",
        "approval requirements",
        "output contract",
        "audit obligations",
        "execution environment requirements",
        "not canonical state owners",
    ]:
        assert term in agent_contract


def test_portable_execution_targets_are_non_authoritative():
    portable_contract = _read(CONTRACTS["portable"]).lower()

    for target in ["claude", "codex", "chatgpt", "cursor", "mcp", "local model", "docker"]:
        assert target in portable_contract

    for phrase in [
        "not authority",
        "not the canonical primitive definitions",
        "adapters must not own canonical state",
        "docker is optional infrastructure",
    ]:
        assert phrase in portable_contract


def test_docker_and_adapter_contracts_keep_rendering_non_authoritative():
    docker_doc = _read(REPO_ROOT / "docs" / "operations" / "docker-clean-room.md").lower()
    adapter_doc = _read(REPO_ROOT / "docs" / "contracts" / "adapter-contract.md").lower()
    portable_doc = _read(CONTRACTS["portable"]).lower()

    assert "optional validation harness" in docker_doc
    assert "not a runtime authority" in docker_doc
    assert "mount `~/.dream-studio`" in docker_doc
    assert "adapters must not" in adapter_doc
    assert "own canonical" in adapter_doc
    assert "target-specific files are renderings" in portable_doc
