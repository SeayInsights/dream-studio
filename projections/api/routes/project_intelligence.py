"""Project Intelligence API routes for health scores, analysis runs, and real-time progress"""

import ast
import json
import logging
import sqlite3
import tomllib
import uuid
from collections import Counter
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..websocket.connection_manager import ConnectionManager
from core.config.database import get_connection
from core.module_contracts import module_contract_map
from core.module_profiles import module_profile_map
from core.production_readiness import production_readiness_dashboard_summary
from core.security.lifecycle import build_security_lifecycle_gate
from core.shared_intelligence.prd_authority import project_details_prd_authority
from core.shared_intelligence.task_attribution import project_recent_attributed_work
from projections.api.routes.sqlite_schema import object_exists, table_columns

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection manager instance for project intelligence subscriptions
pi_connection_manager = ConnectionManager()

SAFE_STACK_FILE_NAMES = {
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "requirements-dev.txt",
    "go.mod",
    "Cargo.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "justfile",
}
SAFE_STACK_DIR_NAMES = {
    ".github",
    "adapter-projections",
    "core",
    "docs",
    "hooks",
    "interfaces",
    "migrations",
    "projections",
    "runtime",
    "skills",
    "tests",
    "workflows",
}
SENSITIVE_PATH_PARTS = {
    ".git",
    ".claude",
    ".codex",
    ".env",
    ".venv",
    "secrets",
    "credentials",
    "node_modules",
}


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def get_db_connection():
    """Get database connection with row factory"""
    db_path = get_db_path()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    return conn


def _active_project_where(conn) -> str:
    """Filter out quarantined/temp project records.

    reg_projects deleted in migration 084; this function is retained for callers
    that have not yet been updated. Returns a WHERE clause for business_projects.
    """
    # business_projects: status IN ('active', 'paused', 'deleted') — exclude deleted
    return "p.status != 'deleted'"


def _optional_column_expr(
    columns: set[str],
    column: str,
    *,
    table_alias: str = "p",
    alias: str | None = None,
) -> str:
    output = alias or column
    return f"{table_alias}.{column} AS {output}" if column in columns else f"NULL AS {output}"


def _security_alias_expr(project_ref: str) -> str:
    return (
        f"project_id IN ({project_ref}, "
        f"'project_' || replace({project_ref}, '-', '_'), "
        f"replace({project_ref}, '_', '-'))"
    )


def _security_aliases(project_id: str) -> list[str]:
    aliases = [
        project_id,
        f"project_{project_id.replace('-', '_')}",
        project_id.replace("_", "-"),
    ]
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _default_operator_exclusion_terms(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("pytest", "temp", "demo", "placeholder"))


def _classify_project_authority(project: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a project belongs in normal operator portfolio views."""

    project_id = str(project.get("project_id") or "")
    project_name = str(project.get("project_name") or "")
    raw_path = str(project.get("project_path") or "")
    project_type = str(project.get("project_type") or "")
    project_source = str(project.get("project_source") or "")
    status = str(project.get("status") or "")
    path = Path(raw_path) if raw_path else None
    if path and not path.is_absolute():
        path = Path.home() / "builds" / path
    path_exists = bool(path and path.exists())
    path_text = str(path or raw_path)

    reasons: list[str] = []
    include_default = True
    classification = "current_legitimate_project"
    operational_classification = "local_active"
    retention_class = "current_authority"

    if not project_name:
        include_default = False
        classification = "manual_review_required"
        retention_class = "manual_review_required"
        reasons.append("project_name is missing")
    if not path_exists:
        include_default = False
        classification = "manual_review_required"
        retention_class = "manual_review_required"
        reasons.append("project path is missing or unverified")
    if status.lower() in {"inactive", "archived", "deactivated", "quarantined"}:
        include_default = False
        classification = "quarantined"
        retention_class = "retention_only"
        operational_classification = "inactive_or_quarantined"
        reasons.append(f"status is {status}")
    if _default_operator_exclusion_terms(" ".join((project_id, project_name))):
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "excluded_test_demo_or_placeholder"
        reasons.append("project id/name/path matches test, temp, demo, or placeholder policy")
    if any(part in path_text.lower() for part in (".claude", ".codex", "worktrees")):
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "adapter_runtime_scratch"
        reasons.append("path is adapter scratch/worktree state")
    if project_source and project_source not in {"local_builds", "current_authority"}:
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "legacy_or_external_retained"
        reasons.append(f"project_source is {project_source}")
    if project_type and project_type not in {
        "local_first_project",
        "local_first_ai_ops",
        "external_project",
    }:
        include_default = False
        classification = "manual_review_required"
        retention_class = "manual_review_required"
        reasons.append(f"project_type is {project_type}")

    return {
        "include_in_default_operator_view": include_default,
        "classification": classification,
        "operational_classification": operational_classification,
        "retention_class": retention_class,
        "source_authority": "business_projects",
        "path_status": "confirmed" if path_exists else "unverified_missing_path",
        "reasons": reasons or ["current project path and authority record are confirmed"],
        "manual_review_required": classification == "manual_review_required",
        "derived_view": True,
        "primary_authority": False,
    }


def _optional_count_expr(table: str, where_column: str, *, condition: str | None = None) -> str:
    base = f"(SELECT COUNT(*) FROM {table} WHERE {where_column} = p.project_id"
    if condition:
        base += f" AND {condition}"
    return base + ")"


def _project_path_exists(project_path: str | None) -> bool:
    if not project_path:
        return False
    path = Path(project_path)
    if not path.is_absolute():
        path = Path.home() / "builds" / project_path
    return path.exists()


def _resolve_prd_file(project: dict[str, Any], file_path: str | None) -> Path | None:
    if not file_path:
        return None
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    project_path = project.get("project_path")
    if not project_path:
        return None
    root = Path(str(project_path))
    if not root.is_absolute():
        root = Path.home() / "builds" / root
    return root / candidate


def _safe_prd_summary(project: dict[str, Any]) -> dict[str, Any]:
    prd_file = _resolve_prd_file(project, project.get("latest_prd_file_path"))
    if not prd_file or not prd_file.exists() or not prd_file.is_file():
        return {
            "available": False,
            "summary": "PRD content was not available from the recorded source ref.",
            "source_ref": project.get("latest_prd_file_path"),
            "safe_read": False,
        }
    lowered_parts = {part.lower() for part in prd_file.parts}
    if lowered_parts.intersection({".git", ".claude", ".codex", "secrets", "credentials"}):
        return {
            "available": False,
            "summary": "PRD path is in a sensitive or adapter-runtime area and was not read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    try:
        text = prd_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "available": False,
            "summary": "PRD source ref could not be read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    lines = [
        line.strip("# ").strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    summary_lines = lines[:6]
    return {
        "available": True,
        "summary": " / ".join(summary_lines)[:800] if summary_lines else "PRD file exists.",
        "source_ref": str(prd_file),
        "safe_read": True,
        "line_count": len(text.splitlines()),
    }


def _parse_stack_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_project_root(project: dict[str, Any]) -> Path | None:
    raw_path = project.get("project_path")
    if not raw_path:
        return None
    root = Path(str(raw_path))
    if not root.is_absolute():
        root = Path.home() / "builds" / root
    try:
        resolved = root.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_dir():
        return None
    lowered_parts = {part.lower() for part in resolved.parts}
    if lowered_parts.intersection(SENSITIVE_PATH_PARTS):
        return None
    if "appdata" in lowered_parts and "temp" not in lowered_parts:
        return None
    return resolved


def _safe_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return path.name


def _safe_read_text(path: Path, *, max_bytes: int = 200_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _safe_manifest_dependencies(path: Path) -> list[str]:
    name = path.name.lower()
    if name == "package.json":
        text = _safe_read_text(path)
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        dependencies: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            section = payload.get(key)
            if isinstance(section, dict):
                dependencies.update(str(item) for item in section if item)
        return sorted(dependencies)
    if name == "pyproject.toml":
        try:
            if path.stat().st_size > 200_000:
                return []
            payload = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, tomllib.TOMLDecodeError):
            return []
        dependencies: set[str] = set()
        project = payload.get("project")
        if isinstance(project, dict):
            for dep in project.get("dependencies") or []:
                if isinstance(dep, str):
                    dependencies.add(dep.split(";", 1)[0].strip())
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for deps in optional.values():
                    if isinstance(deps, list):
                        dependencies.update(
                            dep.split(";", 1)[0].strip() for dep in deps if isinstance(dep, str)
                        )
        return sorted(dep for dep in dependencies if dep)
    if name.startswith("requirements") and name.endswith(".txt"):
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-", "http:", "https:", "git+")):
                continue
            dependencies.append(stripped.split(";", 1)[0].strip())
        return sorted(dict.fromkeys(dependencies))
    if name == "go.mod":
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("module ", "go ", "require (", ")")):
                dependencies.append(stripped.split()[0])
        return sorted(dict.fromkeys(dependencies))
    if name == "cargo.toml":
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        in_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_deps = stripped in {"[dependencies]", "[dev-dependencies]"}
                continue
            if in_deps and stripped and not stripped.startswith("#") and "=" in stripped:
                dependencies.append(stripped.split("=", 1)[0].strip())
        return sorted(dict.fromkeys(dependencies))
    return []


def _repo_stack_evidence(project: dict[str, Any]) -> dict[str, Any]:
    root = _safe_project_root(project)
    if root is None:
        return {
            "classification": "unavailable",
            "reason": "Project path is missing, unverified, or in a sensitive runtime area.",
            "source_refs": [],
            "confirmed_dependency_edges": False,
            "inferred_dependency_edges": [],
            "secret_contents_read": False,
            "derived_view": True,
            "primary_authority": False,
        }

    manifests: list[dict[str, Any]] = []
    config_files: list[str] = []
    workflow_files: list[str] = []
    frontend_surfaces: list[str] = []
    api_route_files: list[str] = []
    migration_files: list[str] = []
    skill_files: list[str] = []
    hook_files: list[str] = []
    adapter_projection_files: list[str] = []
    language_counts: Counter[str] = Counter()
    inferred_edges: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        if len(config_files) + len(workflow_files) + len(frontend_surfaces) > 600:
            break
        if not path.is_file():
            continue
        rel = _safe_rel(root, path)
        lowered_parts = {part.lower() for part in Path(rel).parts}
        if lowered_parts.intersection(SENSITIVE_PATH_PARTS):
            continue
        suffix = path.suffix.lower()
        if suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".go", ".rs"}:
            language_counts[suffix.lstrip(".")] += 1
        if path.name in SAFE_STACK_FILE_NAMES:
            deps = _safe_manifest_dependencies(path)
            manifests.append(
                {
                    "path": rel,
                    "dependency_names": deps[:50],
                    "dependency_count": len(deps),
                    "evidence_kind": "package_or_runtime_manifest",
                    "source_ref": rel,
                }
            )
            for dep in deps[:50]:
                inferred_edges.append(
                    {
                        "from": rel,
                        "to": dep,
                        "type": "manifest_declared_dependency",
                        "confirmation_status": "inferred_unverified",
                        "rendered_by_default": False,
                        "source_refs": [rel],
                    }
                )
        if path.name in SAFE_STACK_FILE_NAMES or any(
            part in SAFE_STACK_DIR_NAMES for part in Path(rel).parts
        ):
            config_files.append(rel)
        if rel.startswith(".github/workflows/"):
            workflow_files.append(rel)
        if suffix in {".html", ".jsx", ".tsx"} and any(
            part in {"frontend", "src", "app", "pages", "components", "projections"}
            for part in Path(rel).parts
        ):
            frontend_surfaces.append(rel)
        if suffix == ".py" and ("routes" in Path(rel).parts or "api" in Path(rel).parts):
            api_route_files.append(rel)
        if "migrations" in Path(rel).parts:
            migration_files.append(rel)
        if Path(rel).name == "SKILL.md" or "skills" in Path(rel).parts:
            skill_files.append(rel)
        if "hooks" in Path(rel).parts:
            hook_files.append(rel)
        if "adapter-projections" in Path(rel).parts:
            adapter_projection_files.append(rel)

    evidence_refs = sorted(
        dict.fromkeys(
            [item["path"] for item in manifests]
            + config_files[:40]
            + workflow_files[:20]
            + api_route_files[:20]
            + frontend_surfaces[:20]
            + migration_files[:20]
            + skill_files[:20]
            + hook_files[:20]
            + adapter_projection_files[:20]
        )
    )
    return {
        "classification": "confirmed" if evidence_refs else "honest_empty_state",
        "reason": (
            "Read-only repo scan found stack/config evidence."
            if evidence_refs
            else "No safe stack/config evidence was found under the project path."
        ),
        "project_root": str(root),
        "package_manifests": manifests[:20],
        "config_files": sorted(dict.fromkeys(config_files))[:80],
        "workflow_files": sorted(dict.fromkeys(workflow_files))[:40],
        "api_route_files": sorted(dict.fromkeys(api_route_files))[:60],
        "frontend_surfaces": sorted(dict.fromkeys(frontend_surfaces))[:60],
        "migration_files": sorted(dict.fromkeys(migration_files))[:60],
        "skill_files": sorted(dict.fromkeys(skill_files))[:60],
        "hook_files": sorted(dict.fromkeys(hook_files))[:60],
        "adapter_projection_files": sorted(dict.fromkeys(adapter_projection_files))[:60],
        "languages": dict(sorted(language_counts.items())),
        "source_refs": evidence_refs,
        "inferred_dependency_edges": inferred_edges[:200],
        "inferred_dependency_count": len(inferred_edges),
        "confirmed_dependency_edges": False,
        "secret_contents_read": False,
        "repo_mutation_authorized": False,
        "derived_view": True,
        "primary_authority": False,
    }


def _module_runtime_fit(
    project: dict[str, Any],
    stack_evidence: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> dict[str, Any]:
    contracts = module_contract_map()
    profiles = module_profile_map()
    candidate_profiles = ["core"]
    reasons = ["core fits every installed Dream Studio project authority view"]
    if project.get("security_package_status", {}).get("open_findings", 0) or project.get(
        "security_lifecycle_status"
    ):
        candidate_profiles.append("security_only")
        reasons.append("security authority or lifecycle status is present")
    if stack_evidence.get("classification") == "confirmed" or dependency_graph.get("edge_count"):
        candidate_profiles.append("analytics_only")
        reasons.append("stack/dependency evidence can be consumed by analytics-only")
    if project.get("telemetry_status", {}).get("event_count") or project.get(
        "telemetry_status", {}
    ).get("validation_passed_count"):
        candidate_profiles.append("telemetry_only")
        reasons.append("telemetry or validation evidence exists")
    if project.get("project_id") == "dream-studio":
        candidate_profiles.extend(["shared_intelligence_only", "adapter_router_only", "full"])
        reasons.append(
            "Dream Studio project exposes shared-intelligence and adapter-router surfaces"
        )
    candidate_profiles = list(dict.fromkeys(candidate_profiles))
    fit_modules = [
        module_id
        for module_id, contract in contracts.items()
        if set(contract.get("install_runtime_profile_membership", [])).intersection(
            candidate_profiles
        )
    ]
    return {
        "classification": "evidence_backed_profile_fit",
        "candidate_profiles": [
            {
                "profile_id": profile_id,
                "commands": profiles.get(profile_id, {}).get("exposed_commands", []),
                "routes": profiles.get(profile_id, {}).get("exposed_routes", []),
                "docker_required": profiles.get(profile_id, {}).get("docker_required"),
                "empty_state": profiles.get(profile_id, {}).get("honest_empty_state"),
            }
            for profile_id in candidate_profiles
            if profile_id in profiles
        ],
        "fit_modules": sorted(fit_modules),
        "reasons": reasons,
        "source_refs": ["core.module_profiles", "core.module_contracts"],
        "derived_view": True,
        "primary_authority": False,
    }


def _recent_validation_state(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "validation_results"):
        return {
            "classification": "unavailable",
            "reason": "validation_results table is not present.",
            "recent": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "validation_results")
    validation_id = "validation_id" if "validation_id" in columns else "result_id"
    validation_type = (
        "validation_type" if "validation_type" in columns else "NULL AS validation_type"
    )
    command = "command" if "command" in columns else "NULL AS command"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {validation_id} AS validation_id, {validation_type}, status, {command},
               {summary}, {evidence}, {created}
        FROM validation_results
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (project_id,),
    ).fetchall()
    recent = [
        {
            **dict(row),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    failed = sum(1 for row in recent if row.get("status") in {"failed", "error", "incomplete"})
    return {
        "classification": "fresh" if recent else "honest_empty_state",
        "recent": recent,
        "recent_count": len(recent),
        "failed_recent_count": failed,
        "source_tables": ["validation_results"],
        "derived_view": True,
        "primary_authority": False,
    }


def _attention_detail_items(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "dashboard_attention_items"):
        return {
            "classification": "unavailable",
            "items": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "dashboard_attention_items")
    attention_id = "attention_id" if "attention_id" in columns else "item_id"
    title = "title" if "title" in columns else "NULL AS title"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    severity = "severity" if "severity" in columns else "NULL AS severity"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    source_refs = (
        "source_refs_json" if "source_refs_json" in columns else "'[]' AS source_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {attention_id} AS attention_id, status, {severity}, {title}, {summary},
               {source_refs}, {evidence}, {created}
        FROM dashboard_attention_items
        WHERE project_id = ?
          AND COALESCE(status, 'open') NOT IN ('resolved', 'closed', 'dismissed')
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (project_id,),
    ).fetchall()
    items = [
        {
            **dict(row),
            "source_refs": _json_list(row["source_refs_json"]),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    return {
        "classification": "fresh" if items else "honest_empty_state",
        "items": items,
        "open_count": len(items),
        "source_tables": ["dashboard_attention_items"],
        "derived_view": True,
        "primary_authority": False,
    }


def _component_index(conn: sqlite3.Connection, project_id: str) -> dict[str, dict[str, Any]]:
    if not object_exists(conn, "pi_components"):
        return {}
    columns = table_columns(conn, "pi_components")
    select_cols = ["component_id"]
    for column in ("name", "path", "component_type", "lines", "complexity_score", "last_analyzed"):
        if column in columns:
            select_cols.append(column)
    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM pi_components WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        component_id = str(item.get("component_id") or "")
        if component_id:
            index[component_id] = {
                **item,
                "evidence_refs": [item.get("path")] if item.get("path") else [],
                "source_tables": ["pi_components"],
                "confirmation_status": "confirmed_component_record",
            }
    return index


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_list(raw: Any) -> list[Any]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return [raw]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return parsed if isinstance(parsed, list) else [parsed]


def _build_prd_authority_status(project: dict[str, Any]) -> dict[str, Any]:
    prd_count = _as_int(project.get("prd_count"))
    latest_status = str(project.get("latest_prd_status") or "").lower()
    summary = _safe_prd_summary(project) if prd_count else None
    if not prd_count:
        status = "draft_generated"
        confidence = "low"
        reason = "No current PRD authority row is linked; the dashboard exposes an explicit draft-required state instead of inventing claims."
        manual_review_flags = ["prd_missing_current_authority"]
    elif latest_status in {"superseded", "stale", "archived"}:
        status = "stale_superseded"
        confidence = "medium"
        reason = "Latest linked PRD status indicates stale or superseded authority."
        manual_review_flags = ["prd_supersession_review"]
    elif summary and summary["available"]:
        status = "current"
        confidence = "medium"
        reason = "A linked PRD authority row and readable source ref are available."
        manual_review_flags = []
    else:
        status = "needs_update"
        confidence = "low"
        reason = "A PRD row exists but the recorded source ref is missing or unreadable."
        manual_review_flags = ["prd_source_ref_review"]
    return {
        "status": status,
        "latest_lifecycle_status": project.get("latest_prd_status"),
        "title": project.get("latest_prd_title"),
        "file_path": project.get("latest_prd_file_path"),
        "created_at": project.get("latest_prd_created_at"),
        "count": prd_count,
        "confidence": confidence,
        "reason": reason,
        "summary": (
            summary["summary"]
            if summary
            else "Draft PRD required; evidence is insufficient for product claims."
        ),
        "source_refs": (
            [project.get("latest_prd_file_path")] if project.get("latest_prd_file_path") else []
        ),
        "evidence_refs": [summary["source_ref"]] if summary and summary.get("source_ref") else [],
        "manual_review_flags": manual_review_flags,
        "derived_view": True,
        "primary_authority": False,
    }


def _build_health_model(project: dict[str, Any]) -> dict[str, Any]:
    """Derive dashboard health from current evidence instead of stored legacy scores."""

    signals = {
        "path_confirmed": project.get("path_status") == "confirmed",
        "prd_count": _as_int(project.get("prd_count")),
        "security_open_count": _as_int(project.get("security_open_count")),
        "validation_failed_count": _as_int(project.get("validation_failed_count")),
        "validation_passed_count": _as_int(project.get("validation_passed_count")),
        "attention_open_count": _as_int(project.get("attention_open_count")),
        "route_blocker_count": _as_int(project.get("route_blocker_count")),
        "telemetry_event_count": _as_int(project.get("telemetry_event_count")),
        "dependency_count": _as_int(project.get("dependency_count")),
        "security_lifecycle_manual_review_count": _as_int(
            project.get("security_lifecycle_manual_review_count")
        ),
        "security_lifecycle_unknown_count": _as_int(
            project.get("security_lifecycle_unknown_count")
        ),
    }
    evidence_points = sum(
        1
        for value in (
            signals["prd_count"],
            signals["security_open_count"],
            signals["validation_failed_count"],
            signals["validation_passed_count"],
            signals["attention_open_count"],
            signals["route_blocker_count"],
            signals["telemetry_event_count"],
            signals["dependency_count"],
            signals["security_lifecycle_manual_review_count"],
            signals["security_lifecycle_unknown_count"],
        )
        if value > 0
    )
    if not signals["path_confirmed"] and evidence_points == 0:
        return {
            "status": "unavailable",
            "score": None,
            "label": "Health unavailable",
            "reason": "Project path is unverified and there are no current telemetry, PRD, security, validation, attention, or dependency signals.",
            "signals": signals,
            "derived_view": True,
            "primary_authority": False,
        }

    score = 100
    penalties: list[str] = []
    if not signals["path_confirmed"]:
        score -= 30
        penalties.append("project path is not confirmed")
    if signals["security_open_count"]:
        penalty = min(35, signals["security_open_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['security_open_count']} open security finding(s)")
    if signals["validation_failed_count"]:
        penalty = min(25, signals["validation_failed_count"] * 10)
        score -= penalty
        penalties.append(f"{signals['validation_failed_count']} failed/incomplete validation(s)")
    if signals["attention_open_count"]:
        penalty = min(20, signals["attention_open_count"] * 4)
        score -= penalty
        penalties.append(f"{signals['attention_open_count']} open attention item(s)")
    if signals["route_blocker_count"]:
        penalty = min(20, signals["route_blocker_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['route_blocker_count']} route blocker/approval item(s)")
    if signals["prd_count"] == 0:
        score -= 5
        penalties.append("no PRD authority linked")
    if signals["dependency_count"] == 0:
        score -= 5
        penalties.append("no confirmed dependency evidence")
    if signals["security_lifecycle_manual_review_count"]:
        penalty = min(20, signals["security_lifecycle_manual_review_count"] * 4)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_manual_review_count']} security lifecycle manual review control(s)"
        )
    if signals["security_lifecycle_unknown_count"]:
        penalty = min(30, signals["security_lifecycle_unknown_count"] * 10)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_unknown_count']} unknown security lifecycle control(s)"
        )

    score = max(0, min(100, score))
    if score >= 85:
        label = "Healthy"
    elif score >= 65:
        label = "Watch"
    elif score >= 40:
        label = "At risk"
    else:
        label = "Needs attention"
    return {
        "status": "scored",
        "score": score,
        "label": label,
        "reason": "; ".join(penalties) if penalties else "Current evidence has no active blockers.",
        "signals": signals,
        "derived_view": True,
        "primary_authority": False,
    }


def _decorate_project_for_dashboard(project: dict[str, Any]) -> dict[str, Any]:
    stack = _parse_stack_json(project.get("stack_json"))
    dependencies = stack.get("dependencies") if isinstance(stack.get("dependencies"), list) else []
    config_files = stack.get("config_files") if isinstance(stack.get("config_files"), list) else []
    entry_points = stack.get("entry_points") if isinstance(stack.get("entry_points"), list) else []
    path_exists = _project_path_exists(project.get("project_path"))
    framework = project.get("stack_detected") or stack.get("framework")
    project["path_status"] = "confirmed" if path_exists else "unverified_missing_path"
    project["project_authority_status"] = _classify_project_authority(project)
    project["authority_source"] = {
        "source_table": "business_projects",
        "source_authority": "current_project_registry",
        "derived_view": True,
        "primary_authority": False,
    }
    project["stack_evidence"] = {
        "classification": (
            "confirmed" if framework and framework != "unknown" else "honest_empty_state"
        ),
        "framework": framework or "unknown",
        "dependency_count": len(dependencies),
        "config_files": config_files[:8],
        "entry_points": entry_points[:8],
        "source_tables": ["business_projects"],
        "source_fields": ["stack_detected", "stack_json", "project_path"],
        "inferred": False,
        "path_status": project["path_status"],
    }
    project["dependency_source_status"] = {
        "classification": (
            "confirmed" if int(project.get("dependency_count") or 0) > 0 else "empty by design"
        ),
        "source_tables": ["pi_dependencies"],
        "reason": (
            "Dependency edges are read from pi_dependencies."
            if int(project.get("dependency_count") or 0) > 0
            else "No confirmed dependency edges recorded for this project."
        ),
        "inferred": False,
    }
    prd_status = project.get("latest_prd_status")
    prd_authority = _build_prd_authority_status(project)
    project["prd_status"] = {
        "count": _as_int(project.get("prd_count")),
        "latest_status": prd_status,
        "latest_title": project.get("latest_prd_title"),
        "latest_file_path": project.get("latest_prd_file_path"),
        "status": prd_authority["status"],
        "classification": prd_authority["status"],
        "authority": prd_authority,
        "source_tables": ["prd_documents"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["security_package_status"] = {
        "open_findings": _as_int(project.get("security_open_count")),
        "classification": "fresh" if _as_int(project.get("security_open_count")) else "fresh_empty",
        "source_tables": ["security_findings"],
        "source_package": "security-review-source-47-enterprise-scans.md",
        "derived_view": True,
        "primary_authority": False,
    }
    security_lifecycle = build_security_lifecycle_gate(
        lifecycle_event="project_health",
        project_id=str(project.get("project_id") or "dream-studio"),
        open_finding_count=_as_int(project.get("security_open_count")),
    )
    project["security_lifecycle_status"] = security_lifecycle
    project["security_lifecycle_manual_review_count"] = security_lifecycle["applicability_summary"][
        "manual_review_required"
    ]
    project["security_lifecycle_unknown_count"] = security_lifecycle["applicability_summary"][
        "unknown"
    ]
    project["work_order_status"] = {
        "route_blockers": _as_int(project.get("route_blocker_count")),
        "attention_open": _as_int(project.get("attention_open_count")),
        "source_tables": ["route_decision_records", "dashboard_attention_items"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["telemetry_status"] = {
        "event_count": _as_int(project.get("telemetry_event_count")),
        "validation_passed_count": _as_int(project.get("validation_passed_count")),
        "validation_failed_count": _as_int(project.get("validation_failed_count")),
        "source_tables": ["execution_events", "validation_results"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["health_model"] = _build_health_model(project)
    if project["health_model"].get("score") is not None:
        project["health_score"] = round(float(project["health_model"]["score"]) / 10, 1)
    else:
        project["health_score"] = None
    open_findings = _as_int(project.get("security_open_count"))
    project["security_score"] = round(max(0, 100 - min(100, open_findings * 10)) / 10, 1)
    return project


def _missing_tables(conn, names: list[str]) -> list[str]:
    return [name for name in names if not object_exists(conn, name)]


def _empty_project_source_status(missing: list[str], *, reason: str) -> dict[str, Any]:
    return {
        "classification": "empty by design",
        "reason": reason,
        "missing": missing,
        "derived_view": True,
        "primary_authority": False,
    }


def _project_surface_availability(conn) -> dict[str, bool]:
    dependency_columns = (
        table_columns(conn, "pi_dependencies") if object_exists(conn, "pi_dependencies") else []
    )
    return {
        "overview": True,
        "prds": object_exists(conn, "prd_documents"),
        "security": any(
            object_exists(conn, name)
            for name in ("security_findings", "sec_sarif_findings", "pi_violations")
        ),
        "dependencies": object_exists(conn, "pi_dependencies")
        and {"from_component", "to_component"}.issubset(dependency_columns),
        "activity": any(
            object_exists(conn, name)
            for name in ("execution_events", "process_runs", "pi_analysis_runs")
        ),
        "health_trend": object_exists(conn, "pi_analysis_runs"),
        "bugs_summary": object_exists(conn, "pi_bugs"),
        "violations_summary": object_exists(conn, "pi_violations"),
    }


def _project_row_for_authority(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    # reg_projects deleted in migration 084; use business_projects
    if not object_exists(conn, "business_projects"):
        return None
    row = conn.execute(
        "SELECT project_id, name AS project_name, description, status, project_path,"
        " total_sessions, total_tokens, last_session_at, created_at, updated_at"
        " FROM business_projects WHERE project_id = ? LIMIT 1",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def _unavailable_project_surfaces(availability: dict[str, bool]) -> list[str]:
    return [name for name, available in availability.items() if not available]


def _security_assignment_summary(
    conn: sqlite3.Connection,
    visible_projects: list[dict[str, Any]],
) -> dict[str, Any]:
    if not object_exists(conn, "security_findings"):
        return {
            "classification": "unavailable",
            "unassigned_legacy_finding_count": 0,
            "unassigned_project_ids": [],
            "source_tables": [],
        }
    if "project_id" not in table_columns(conn, "security_findings"):
        return {
            "classification": "unavailable",
            "reason": "security_findings has no project_id column in this schema snapshot.",
            "mapped_project_alias_count": 0,
            "unassigned_legacy_finding_count": 0,
            "unassigned_project_ids": [],
            "source_tables": ["security_findings"],
            "derived_view": True,
            "primary_authority": False,
        }
    aliases: set[str] = set()
    for project in visible_projects:
        aliases.update(_security_aliases(str(project.get("project_id") or "")))
    rows = conn.execute("""
        SELECT COALESCE(project_id, '<null>') AS project_id, COUNT(*) AS count
        FROM security_findings
        GROUP BY COALESCE(project_id, '<null>')
        ORDER BY count DESC
        """).fetchall()
    unassigned = [
        {"project_id": row["project_id"], "count": row["count"]}
        for row in rows
        if row["project_id"] not in aliases
    ]
    return {
        "classification": "fresh",
        "mapped_project_alias_count": len(aliases),
        "unassigned_legacy_finding_count": sum(item["count"] for item in unassigned),
        "unassigned_project_ids": unassigned,
        "unassigned_policy": "manual_review_required_or_retention_only; not shown in normal project cards until mapped",
        "source_tables": ["security_findings"],
        "derived_view": True,
        "primary_authority": False,
    }


# ── HTTP Endpoints ───────────────────────────────────────────────────────────


@router.get("")
async def list_projects(
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """
    List all analyzed projects with their latest health scores.

    Returns projects sorted by last_analyzed (most recent first).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "business_projects"):
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "projects": [],
                "source_status": {
                    "classification": "missing because live DB schema is behind repo migrations",
                    "reason": "business_projects is not available.",
                },
            }

        # Get total count of distinct projects — business_projects (UUID ids, no path dedup needed)
        project_columns = table_columns(conn, "business_projects")
        # Analysis columns removed in migration 084; return NULL/0 placeholders for compatibility
        stack_detected_expr = "NULL AS stack_detected"
        stack_json_expr = "NULL AS stack_json"
        project_type_expr = "NULL AS project_type"
        project_source_expr = "NULL AS project_source"
        status_expr = "p.status AS status" if "status" in project_columns else "NULL AS status"
        is_temp_expr = "0 AS is_temp"

        # Get projects with pagination (deduplicated by path, prioritizing entries with most sessions)
        prd_columns = (
            table_columns(conn, "prd_documents") if object_exists(conn, "prd_documents") else set()
        )
        prd_count_expr = (
            "(SELECT COUNT(*) FROM prd_documents WHERE project_id = p.project_id)"
            if object_exists(conn, "prd_documents")
            else "0"
        )
        latest_prd_status_expr = (
            "(SELECT status FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "status" in prd_columns
            else "NULL"
        )
        latest_prd_title_expr = (
            "(SELECT title FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "title" in prd_columns
            else "NULL"
        )
        latest_prd_file_path_expr = (
            "(SELECT file_path FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "file_path" in prd_columns
            else "NULL"
        )
        latest_prd_created_at_expr = (
            "(SELECT created_at FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "created_at" in prd_columns
            else "NULL"
        )
        bug_count_expr = (
            _optional_count_expr("pi_bugs", "project_id", condition="status != 'fixed'")
            if object_exists(conn, "pi_bugs")
            else "0"
        )
        critical_bug_count_expr = (
            _optional_count_expr(
                "pi_bugs", "project_id", condition="status != 'fixed' AND severity = 'critical'"
            )
            if object_exists(conn, "pi_bugs")
            else "0"
        )
        violation_count_expr = (
            _optional_count_expr("pi_violations", "project_id", condition="status != 'resolved'")
            if object_exists(conn, "pi_violations")
            else "0"
        )
        dependency_count_expr = (
            _optional_count_expr("pi_dependencies", "project_id")
            if object_exists(conn, "pi_dependencies")
            else "0"
        )
        security_columns = (
            table_columns(conn, "security_findings")
            if object_exists(conn, "security_findings")
            else set()
        )
        security_open_count_expr = (
            _optional_count_expr(
                "security_findings",
                "project_id",
                condition="status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed')",
            ).replace("project_id = p.project_id", _security_alias_expr("p.project_id"))
            if "project_id" in security_columns
            else "0"
        )
        attention_open_count_expr = (
            _optional_count_expr(
                "dashboard_attention_items",
                "project_id",
                condition="status NOT IN ('resolved', 'closed', 'dismissed')",
            )
            if object_exists(conn, "dashboard_attention_items")
            else "0"
        )
        validation_failed_count_expr = (
            _optional_count_expr(
                "validation_results",
                "project_id",
                condition="status IN ('failed', 'error', 'incomplete')",
            )
            if object_exists(conn, "validation_results")
            else "0"
        )
        validation_passed_count_expr = (
            _optional_count_expr("validation_results", "project_id", condition="status = 'passed'")
            if object_exists(conn, "validation_results")
            else "0"
        )
        telemetry_event_count_expr = (
            _optional_count_expr("execution_events", "project_id")
            if object_exists(conn, "execution_events")
            else "0"
        )
        route_blocker_count_expr = (
            _optional_count_expr(
                "route_decision_records",
                "project_id",
                condition=(
                    "(handoff_required = 1 OR operator_action_required = 1 OR prompt_required = 1 "
                    "OR (recommended_next_work_order IS NOT NULL AND recommended_next_work_order != 'none'))"
                ),
            )
            if object_exists(conn, "route_decision_records")
            else "0"
        )
        # business_projects has UUID ids — no path deduplication needed (no ranked_projects CTE)
        # Analysis columns (health_score, pi_* counts) removed in migration 084; return NULL/0.
        # Column mapping: reg_projects.project_name → business_projects.name
        query = """
        SELECT
            p.project_id,
            p.name AS project_name,
            p.project_path,
            {project_type_expr},
            {project_source_expr},
            {status_expr},
            {is_temp_expr},
            {stack_detected_expr},
            {stack_json_expr},
            NULL AS health_score,
            NULL AS security_score,
            NULL AS maintainability_score,
            NULL AS total_files,
            NULL AS lines_of_code,
            NULL AS first_analyzed,
            NULL AS last_analyzed,
            COALESCE(p.total_sessions, 0) AS total_sessions,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            {latest_prd_created_at_expr} as latest_prd_created_at,
            0 as bug_count,
            0 as critical_bug_count,
            0 as violation_count,
            0 as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM business_projects p
        WHERE p.status != 'deleted'
        ORDER BY COALESCE(p.last_session_at, p.updated_at) DESC
        """.format(
            project_type_expr=project_type_expr,
            project_source_expr=project_source_expr,
            status_expr=status_expr,
            is_temp_expr=is_temp_expr,
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            prd_count_expr=prd_count_expr,
            latest_prd_status_expr=latest_prd_status_expr,
            latest_prd_title_expr=latest_prd_title_expr,
            latest_prd_file_path_expr=latest_prd_file_path_expr,
            latest_prd_created_at_expr=latest_prd_created_at_expr,
            security_open_count_expr=security_open_count_expr,
            attention_open_count_expr=attention_open_count_expr,
            validation_failed_count_expr=validation_failed_count_expr,
            validation_passed_count_expr=validation_passed_count_expr,
            telemetry_event_count_expr=telemetry_event_count_expr,
            route_blocker_count_expr=route_blocker_count_expr,
        )

        rows = cursor.execute(query).fetchall()
        candidate_projects = []
        excluded_projects = []
        for row in rows:
            project = _decorate_project_for_dashboard(dict(row))
            if not project["project_authority_status"]["include_in_default_operator_view"]:
                excluded_projects.append(project)
                continue
            project["project_readiness_status"] = production_readiness_dashboard_summary(
                conn,
                project_id=project["project_id"],
            )["readiness_score"]
            candidate_projects.append(project)
        total = len(candidate_projects)
        projects = candidate_projects[offset : offset + limit]  # noqa: E203
        excluded_summary = Counter(
            project["project_authority_status"]["retention_class"] for project in excluded_projects
        )

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": projects,
            "derived_view": True,
            "primary_authority": False,
            "source_status": {
                "classification": "fresh",
                "reason": "Default All Projects shows only current legitimate project authority rows; temp, pytest, demo, placeholder, inactive, adapter-worktree, missing-path, and retained legacy rows are excluded from normal operator views.",
                "source_tables": ["business_projects"]
                + (["prd_documents"] if object_exists(conn, "prd_documents") else [])
                + (["security_findings"] if object_exists(conn, "security_findings") else [])
                + (
                    ["dashboard_attention_items"]
                    if object_exists(conn, "dashboard_attention_items")
                    else []
                )
                + (["validation_results"] if object_exists(conn, "validation_results") else [])
                + (["execution_events"] if object_exists(conn, "execution_events") else [])
                + (
                    ["route_decision_records"]
                    if object_exists(conn, "route_decision_records")
                    else []
                )
                + (
                    ["production_readiness_assessment_runs"]
                    if object_exists(conn, "production_readiness_assessment_runs")
                    else []
                )
                + (
                    ["project_readiness_scorecards"]
                    if object_exists(conn, "project_readiness_scorecards")
                    else []
                ),
                "missing": [] if object_exists(conn, "prd_documents") else ["prd_documents"],
                "excluded_from_default_view": {
                    "count": len(excluded_projects),
                    "by_retention_class": dict(excluded_summary),
                    "sample_project_ids": [
                        project["project_id"] for project in excluded_projects[:12]
                    ],
                },
                "security_finding_assignment_summary": _security_assignment_summary(
                    conn, candidate_projects
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/health")
async def get_project_health(project_id: str) -> Dict[str, Any]:
    """
    Get detailed health metrics for a specific project.

    Returns:
    - Current health score, security score, maintainability score
    - Violation counts by severity
    - Bug counts by severity
    - Improvement suggestions count
    - Latest analysis run info
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get project details — reg_projects deleted in migration 084; use business_projects
        project_columns = table_columns(conn, "business_projects")
        stack_detected_expr = "NULL AS stack_detected"
        stack_json_expr = "NULL AS stack_json"
        project_type_expr = "NULL AS project_type"
        project_source_expr = "NULL AS project_source"
        status_expr = "status AS status" if "status" in project_columns else "NULL AS status"
        is_temp_expr = "0 AS is_temp"
        prd_columns = (
            table_columns(conn, "prd_documents") if object_exists(conn, "prd_documents") else set()
        )
        prd_count_expr = (
            "(SELECT COUNT(*) FROM prd_documents WHERE project_id = business_projects.project_id)"
            if object_exists(conn, "prd_documents")
            else "0"
        )
        latest_prd_status_expr = (
            "(SELECT status FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "status" in prd_columns
            else "NULL"
        )
        latest_prd_title_expr = (
            "(SELECT title FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "title" in prd_columns
            else "NULL"
        )
        latest_prd_file_path_expr = (
            "(SELECT file_path FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "file_path" in prd_columns
            else "NULL"
        )
        latest_prd_created_at_expr = (
            "(SELECT created_at FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "created_at" in prd_columns
            else "NULL"
        )
        dependency_count_expr = "0"  # pi_dependencies dropped in migration 084
        security_columns = (
            table_columns(conn, "security_findings")
            if object_exists(conn, "security_findings")
            else set()
        )
        security_open_count_expr = (
            "(SELECT COUNT(*) FROM security_findings WHERE "
            f"{_security_alias_expr('business_projects.project_id')} "
            "AND status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed'))"
            if "project_id" in security_columns
            else "0"
        )
        attention_open_count_expr = (
            "(SELECT COUNT(*) FROM dashboard_attention_items WHERE project_id = business_projects.project_id AND status NOT IN ('resolved', 'closed', 'dismissed'))"
            if object_exists(conn, "dashboard_attention_items")
            else "0"
        )
        validation_failed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = business_projects.project_id AND status IN ('failed', 'error', 'incomplete'))"
            if object_exists(conn, "validation_results")
            else "0"
        )
        validation_passed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = business_projects.project_id AND status = 'passed')"
            if object_exists(conn, "validation_results")
            else "0"
        )
        telemetry_event_count_expr = (
            "(SELECT COUNT(*) FROM execution_events WHERE project_id = business_projects.project_id)"
            if object_exists(conn, "execution_events")
            else "0"
        )
        route_blocker_count_expr = (
            "(SELECT COUNT(*) FROM route_decision_records WHERE project_id = business_projects.project_id "
            "AND (handoff_required = 1 OR operator_action_required = 1 OR prompt_required = 1 "
            "OR (recommended_next_work_order IS NOT NULL AND recommended_next_work_order != 'none')))"
            if object_exists(conn, "route_decision_records")
            else "0"
        )
        project_query = """
        SELECT
            project_id,
            name AS project_name,
            project_path,
            {project_type_expr},
            {project_source_expr},
            {status_expr},
            {is_temp_expr},
            {stack_detected_expr},
            {stack_json_expr},
            NULL AS health_score,
            NULL AS security_score,
            NULL AS maintainability_score,
            NULL AS total_files,
            NULL AS lines_of_code,
            NULL AS first_analyzed,
            NULL AS last_analyzed,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            {latest_prd_created_at_expr} as latest_prd_created_at,
            0 as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM business_projects
        WHERE project_id = ?
        """.format(
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            project_type_expr=project_type_expr,
            project_source_expr=project_source_expr,
            status_expr=status_expr,
            is_temp_expr=is_temp_expr,
            prd_count_expr=prd_count_expr,
            latest_prd_status_expr=latest_prd_status_expr,
            latest_prd_title_expr=latest_prd_title_expr,
            latest_prd_file_path_expr=latest_prd_file_path_expr,
            latest_prd_created_at_expr=latest_prd_created_at_expr,
            dependency_count_expr=dependency_count_expr,
            security_open_count_expr=security_open_count_expr,
            attention_open_count_expr=attention_open_count_expr,
            validation_failed_count_expr=validation_failed_count_expr,
            validation_passed_count_expr=validation_passed_count_expr,
            telemetry_event_count_expr=telemetry_event_count_expr,
            route_blocker_count_expr=route_blocker_count_expr,
        )

        project_row = cursor.execute(project_query, (project_id,)).fetchone()

        if not project_row:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        project = _decorate_project_for_dashboard(dict(project_row))

        # pi_violations, pi_bugs, pi_improvements, pi_analysis_runs dropped in migration 084
        missing_optional = []
        violations = {}
        bugs = {}
        improvements = {}

        latest_run = None
        if object_exists(conn, "pi_analysis_runs"):
            run_query = """
            SELECT
                run_id,
                run_type,
                started_at,
                completed_at,
                duration_seconds,
                status,
                violations_found,
                bugs_found,
                improvements_suggested
            FROM pi_analysis_runs
            WHERE project_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """
            latest_run_row = cursor.execute(run_query, (project_id,)).fetchone()
            latest_run = dict(latest_run_row) if latest_run_row else None
        availability = _project_surface_availability(conn)
        production_readiness = production_readiness_dashboard_summary(conn, project_id=project_id)

        return {
            "project": project,
            "health": {
                "overall_score": project["health_score"],
                "security_score": project["security_score"],
                "maintainability_score": project["maintainability_score"],
            },
            "readiness": production_readiness["readiness_score"],
            "production_readiness": production_readiness,
            "violations": violations,
            "bugs": bugs,
            "improvements": improvements,
            "latest_run": latest_run,
            "available_surfaces": availability,
            "removed_surfaces": _unavailable_project_surfaces(availability),
            "source_status": {
                "classification": "fresh" if not missing_optional else "empty by design",
                "reason": (
                    "Project health includes current project authority and available project intelligence tables."
                    if not missing_optional
                    else "Project authority exists, but optional project-intelligence detail tables are absent in this DB snapshot."
                ),
                "missing": missing_optional,
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project health: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/details")
async def get_project_details(project_id: str) -> Dict[str, Any]:
    """Return project detail view data with health and readiness separated."""

    health_payload = await get_project_health(project_id)
    conn = get_db_connection()
    try:
        production_readiness = production_readiness_dashboard_summary(conn, project_id=project_id)
        security_controls = health_payload["project"]["security_lifecycle_status"]
        dependency_graph = await get_project_dependencies(project_id, limit=200)
        repo_stack = _repo_stack_evidence(health_payload["project"])
        module_fit = _module_runtime_fit(
            health_payload["project"],
            repo_stack,
            dependency_graph,
        )
        validation_state = _recent_validation_state(conn, project_id)
        attention_detail = _attention_detail_items(conn, project_id)
        attributed_work = project_recent_attributed_work(conn, project_id, limit=10)
        prd_lifecycle = project_details_prd_authority(conn, project_id)
        return {
            "project_id": project_id,
            "derived_view": True,
            "primary_authority": False,
            "project_identity": {
                "project_id": project_id,
                "project_name": health_payload["project"].get("project_name"),
                "project_path": health_payload["project"].get("project_path"),
                "project_authority_status": health_payload["project"].get(
                    "project_authority_status"
                ),
                "authority_source": health_payload["project"].get("authority_source"),
            },
            "prd_status": health_payload["project"].get("prd_status"),
            "prd_summary": (health_payload["project"].get("prd_status") or {})
            .get("authority", {})
            .get("summary"),
            "prd_lifecycle_authority": prd_lifecycle["summary"],
            "prd_version": prd_lifecycle["prd_version"],
            "prd_confidence": prd_lifecycle["prd_confidence"],
            "in_flight_formalization_status": prd_lifecycle["in_flight_formalization_status"],
            "pending_prd_questions": prd_lifecycle["pending_prd_questions"],
            "prd_assumptions": prd_lifecycle["prd_assumptions"],
            "current_milestones": prd_lifecycle["current_milestones"],
            "active_work_orders": prd_lifecycle["active_work_orders"],
            "change_order_history": prd_lifecycle["change_order_history"],
            "pending_change_orders": prd_lifecycle["pending_change_orders"],
            "route_reconciliation_status": prd_lifecycle["route_reconciliation_status"],
            "planned_vs_actual_route_summary": prd_lifecycle["planned_vs_actual_route_summary"],
            "health_score": health_payload["health"],
            "readiness_score": production_readiness["readiness_score"],
            "readiness_control_coverage": production_readiness["control_summary"],
            "enterprise_security_controls": security_controls["applicability_summary"],
            "enterprise_security_control_status": {
                "controls": security_controls.get("applicability", []),
                "summary": security_controls["applicability_summary"],
                "source_framework": security_controls["source_framework"],
                "manual_review_required": security_controls["applicability_summary"].get(
                    "manual_review_required", 0
                ),
                "unknown": security_controls["applicability_summary"].get("unknown", 0),
                "derived_view": True,
                "primary_authority": False,
            },
            "production_readiness_controls": production_readiness["controls"],
            "findings_by_severity_status": _finding_summary(
                production_readiness["findings"],
                health_payload.get("project", {})
                .get("security_package_status", {})
                .get("open_findings", 0),
            ),
            "not_applicable_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "not_applicable"
            ],
            "manual_review_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "manual_review"
            ],
            "remediation_work_orders": production_readiness["remediation_work_orders"],
            "evidence_refs": _collect_evidence_refs(production_readiness["controls"]),
            "release_blockers": [
                item for item in production_readiness["controls"] if item.get("blocking")
            ],
            "compliance_legal_review_flags": production_readiness["compliance_review_flags"],
            "stack_status": health_payload["project"].get("stack_evidence"),
            "stack_evidence": {
                "registry_stack": health_payload["project"].get("stack_evidence"),
                "repo_scan": repo_stack,
                "source_refs": sorted(
                    set(
                        (repo_stack.get("source_refs") or [])
                        + (
                            health_payload["project"]
                            .get("stack_evidence", {})
                            .get("config_files", [])
                        )
                    )
                ),
                "secret_contents_read": False,
                "repo_mutation_authorized": False,
                "derived_view": True,
                "primary_authority": False,
            },
            "confirmed_dependencies": {
                "nodes": dependency_graph.get("nodes", []),
                "edges": dependency_graph.get("edges", []),
                "node_count": dependency_graph.get("node_count", 0),
                "edge_count": dependency_graph.get("edge_count", 0),
                "rendered_by_default": True,
                "source_status": dependency_graph.get("source_status"),
                "knowledge_graph_status": dependency_graph.get("knowledge_graph_status"),
            },
            "inferred_or_unverified_dependencies": {
                "edges": dependency_graph.get("inferred_edges", [])
                + repo_stack.get("inferred_dependency_edges", []),
                "edge_count": dependency_graph.get("inferred_edge_count", 0)
                + repo_stack.get("inferred_dependency_count", 0),
                "rendered_by_default": False,
                "reason": "Manifest-derived or unverified dependencies are labeled separately and hidden from the default confirmed graph.",
            },
            "dependency_drilldown": {
                "project_to_stack_component": "/api/v1/projects/{project_id}/details",
                "stack_component_to_dependency": "/api/v1/projects/{project_id}/dependencies",
                "dependency_to_evidence": "edge.source_refs and node.evidence_refs",
                "confirmed_edges_only_by_default": True,
            },
            "dependency_status": health_payload["project"].get("dependency_source_status"),
            "module_runtime_profile_fit": module_fit,
            "security_status": health_payload["project"].get("security_package_status"),
            "validation_state": {
                "summary": health_payload["project"].get("telemetry_status"),
                "recent": validation_state,
            },
            "recent_attributed_work": attributed_work,
            "work_order_status": health_payload["project"].get("work_order_status"),
            "attention_items": attention_detail,
            "known_gaps": _project_detail_known_gaps(health_payload, production_readiness),
            "current_next_action": _project_detail_next_action(
                health_payload, production_readiness
            ),
            "source_status": {
                "classification": (
                    "fresh" if production_readiness.get("assessment_id") else "empty by design"
                ),
                "source_tables": production_readiness.get("source_tables", []),
                "derived_view": True,
                "primary_authority": False,
            },
        }
    finally:
        conn.close()


def _finding_summary(findings: list[dict[str, Any]], open_security_findings: int) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for finding in findings:
        key = f"{finding.get('severity', 'unknown')}:{finding.get('status', 'unknown')}"
        summary[key] = summary.get(key, 0) + 1
    if open_security_findings:
        summary["security_open:open"] = int(open_security_findings)
    return {
        "counts": summary,
        "security_open_findings": open_security_findings,
        "production_readiness_finding_count": len(findings),
    }


def _collect_evidence_refs(controls: list[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    for control in controls:
        evidence = control.get("evidence_refs") or control.get("evidence_refs_json") or []
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = [evidence]
        refs.update(str(item) for item in evidence if item)
    return sorted(refs)


def _project_detail_known_gaps(
    health_payload: dict[str, Any],
    production_readiness: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    project = health_payload.get("project", {})
    prd_authority = (project.get("prd_status") or {}).get("authority") or {}
    if prd_authority.get("status") != "current":
        gaps.append(f"prd_status:{prd_authority.get('status', 'unknown')}")
    if production_readiness.get("status") == "unavailable":
        gaps.append("production_readiness_assessment_missing")
    dependency_status = project.get("dependency_source_status") or {}
    if dependency_status.get("classification") != "confirmed":
        gaps.append("confirmed_dependency_graph_unavailable")
    if project.get("health_model", {}).get("status") != "scored":
        gaps.append("health_score_unavailable")
    return gaps


def _project_detail_next_action(
    health_payload: dict[str, Any],
    production_readiness: dict[str, Any],
) -> str:
    gaps = _project_detail_known_gaps(health_payload, production_readiness)
    if "production_readiness_assessment_missing" in gaps:
        return "Run or persist a project-scoped production readiness assessment when approved."
    if any(gap.startswith("prd_status:") for gap in gaps):
        return "Review or update PRD authority before release planning."
    if "confirmed_dependency_graph_unavailable" in gaps:
        return "Collect confirmed dependency evidence before drawing a Knowledge Graph."
    return "Continue with the next evidence-backed Work Order."


@router.get("/{project_id}/history")
async def get_project_history(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Get analysis run history for a project.

    Returns recent analysis runs with health score trends.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_analysis_runs"):
            return {
                "project_id": project_id,
                "runs": [],
                "total_runs": 0,
                "source_status": _empty_project_source_status(
                    ["pi_analysis_runs"],
                    reason="Analysis run history table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            run_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            status,
            violations_found,
            bugs_found,
            improvements_suggested
        FROM pi_analysis_runs
        WHERE project_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """

        rows = cursor.execute(query, (project_id, limit)).fetchall()
        runs = [dict(row) for row in rows]

        return {"project_id": project_id, "runs": runs, "total_runs": len(runs)}

    except Exception as e:
        logger.error(f"Error getting project history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific analysis run.

    Returns full run details including progress and findings.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_analysis_runs"):
            raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

        query = """
        SELECT
            run_id,
            project_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            discovery_completed,
            research_completed,
            audit_completed,
            bug_analysis_completed,
            synthesis_completed,
            status,
            violations_found,
            bugs_found,
            improvements_suggested,
            error_message
        FROM pi_analysis_runs
        WHERE run_id = ?
        """

        row = cursor.execute(query, (run_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

        run = dict(row)

        # Calculate progress percentage
        phases = [
            run["discovery_completed"],
            run["research_completed"],
            run["audit_completed"],
            run["bug_analysis_completed"],
            run["synthesis_completed"],
        ]
        completed_phases = sum(1 for p in phases if p)
        progress = (completed_phases / len(phases)) * 100 if phases else 0

        run["progress_percent"] = progress
        run["phases_complete"] = completed_phases
        run["phases_total"] = len(phases)

        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis run: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── WebSocket Endpoints ──────────────────────────────────────────────────────


@router.websocket("/ws/project-health/{project_id}")
async def websocket_project_health(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time project health updates.

    Clients subscribe to a specific project and receive updates when:
    - Analysis runs complete
    - Health score changes
    - New violations/bugs detected
    - Improvements implemented

    Message protocol:
    - Server sends: {"type": "health_update", "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to project health updates
        pi_connection_manager.subscribe(client_id, [f"project_health_{project_id}"])

        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "project_id": project_id,
                "message": f"Subscribed to health updates for project {project_id}",
            }
        )

        # Send current health data immediately
        # reg_projects deleted in migration 084; analysis scores are NULL until rebuilt
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT NULL AS health_score, NULL AS security_score,
                   NULL AS maintainability_score, NULL AS last_analyzed
            FROM business_projects
            WHERE project_id = ?
            """
            row = cursor.execute(query, (project_id,)).fetchone()

            if row:
                await websocket.send_json({"type": "health_update", "data": dict(row)})
        finally:
            conn.close()

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_json()
                # Echo back for now (could add commands later)
                await websocket.send_json({"type": "ack", "message": message})
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from project health stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


@router.websocket("/ws/analysis-progress/{run_id}")
async def websocket_analysis_progress(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time analysis progress updates.

    Streams progress updates during an analysis run:
    - Phase completions (discovery, research, audit, bugs, synthesis)
    - Partial findings counts
    - ETA updates

    Message protocol:
    - Server sends: {"type": "progress_update", "phase": "...", "percent": ..., "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to analysis progress
        pi_connection_manager.subscribe(client_id, [f"analysis_progress_{run_id}"])

        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "run_id": run_id,
                "message": f"Subscribed to progress updates for analysis run {run_id}",
            }
        )

        # Send current progress immediately
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT
                discovery_completed,
                research_completed,
                audit_completed,
                bug_analysis_completed,
                synthesis_completed,
                status
            FROM pi_analysis_runs
            WHERE run_id = ?
            """
            row = cursor.execute(query, (run_id,)).fetchone()

            if row:
                data = dict(row)
                phases = [
                    data["discovery_completed"],
                    data["research_completed"],
                    data["audit_completed"],
                    data["bug_analysis_completed"],
                    data["synthesis_completed"],
                ]
                progress = (sum(1 for p in phases if p) / len(phases)) * 100

                await websocket.send_json(
                    {"type": "progress_update", "percent": progress, "data": data}
                )
        finally:
            conn.close()

        # Keep connection alive
        while True:
            try:
                message = await websocket.receive_json()
                await websocket.send_json({"type": "ack", "message": message})
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from analysis progress stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


# ── Helper function for broadcasting updates ─────────────────────────────────


async def broadcast_health_update(project_id: str, data: Dict[str, Any]):
    """
    Broadcast health update to all subscribers of a project.

    Called by the analysis engine when a run completes.
    """
    await pi_connection_manager.send_to_subscribers(
        f"project_health_{project_id}",
        {"type": "health_update", "project_id": project_id, "data": data},
    )


async def broadcast_progress_update(run_id: str, phase: str, percent: float, data: Dict[str, Any]):
    """
    Broadcast progress update to all subscribers of an analysis run.

    Called by the analysis engine during phase completions.
    """
    await pi_connection_manager.send_to_subscribers(
        f"analysis_progress_{run_id}",
        {
            "type": "progress_update",
            "run_id": run_id,
            "phase": phase,
            "percent": percent,
            "data": data,
        },
    )


@router.get("/{project_id}/prds")
async def get_project_prds(project_id: str) -> Dict[str, Any]:
    """
    Get all PRDs associated with a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "prd_documents"):
            return {
                "project_id": project_id,
                "prds": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["prd_documents"],
                    reason="PRD documents table is not present in this DB snapshot.",
                ),
            }

        prd_columns = table_columns(conn, "prd_documents")
        file_path_expr = "file_path" if "file_path" in prd_columns else "NULL AS file_path"
        approved_at_expr = "approved_at" if "approved_at" in prd_columns else "NULL AS approved_at"
        completed_at_expr = (
            "completed_at" if "completed_at" in prd_columns else "NULL AS completed_at"
        )
        total_tasks_expr = "total_tasks" if "total_tasks" in prd_columns else "0 AS total_tasks"
        completed_tasks_expr = (
            "completed_tasks" if "completed_tasks" in prd_columns else "0 AS completed_tasks"
        )
        pct_complete_expr = (
            "ROUND(100.0 * completed_tasks / NULLIF(total_tasks, 0), 1) AS pct_complete"
            if {"completed_tasks", "total_tasks"}.issubset(prd_columns)
            else "NULL AS pct_complete"
        )

        query = f"""
        SELECT
            prd_id,
            title,
            status,
            {file_path_expr},
            created_at,
            {approved_at_expr},
            {completed_at_expr},
            {total_tasks_expr},
            {completed_tasks_expr},
            {pct_complete_expr}
        FROM prd_documents
        WHERE project_id = ?
        ORDER BY created_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        prds = [dict(row) for row in rows]
        project = _project_row_for_authority(conn, project_id)
        if project:
            project.update(
                {
                    "prd_count": len(prds),
                    "latest_prd_status": prds[0].get("status") if prds else None,
                    "latest_prd_title": prds[0].get("title") if prds else None,
                    "latest_prd_file_path": prds[0].get("file_path") if prds else None,
                    "latest_prd_created_at": prds[0].get("created_at") if prds else None,
                }
            )
            prd_authority = _build_prd_authority_status(project)
        else:
            prd_authority = {
                "status": "manual_review_required",
                "reason": "Project authority row is missing for this PRD request.",
                "manual_review_flags": ["project_authority_missing"],
            }

        return {
            "project_id": project_id,
            "prds": prds,
            "count": len(prds),
            "prd_authority": prd_authority,
            "source_status": {
                "classification": "fresh" if prds else "honest_empty_state",
                "reason": (
                    "PRD records are linked to current project authority."
                    if prds
                    else "No PRD authority rows are linked; draft_generated/manual review status is exposed instead."
                ),
                "source_tables": ["prd_documents", "business_projects"],
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except Exception as e:
        logger.error(f"Error getting project PRDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/security")
async def get_project_security(project_id: str) -> Dict[str, Any]:
    """
    Get security findings for a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if object_exists(conn, "security_findings"):
            finding_columns = table_columns(conn, "security_findings")
            if "project_id" not in finding_columns:
                return {
                    "project_id": project_id,
                    "findings": [],
                    "count": 0,
                    "source_status": {
                        "classification": "unavailable",
                        "reason": "security_findings has no project_id column in this schema snapshot.",
                        "source_tables": ["security_findings"],
                        "derived_view": True,
                        "primary_authority": False,
                    },
                }
            aliases = _security_aliases(project_id)
            placeholders = ",".join("?" for _ in aliases)
            rule_id_expr = "rule_id" if "rule_id" in finding_columns else "NULL AS rule_id"
            recommendation_expr = (
                "recommendation"
                if "recommendation" in finding_columns
                else "NULL AS recommendation"
            )
            end_line_expr = "end_line" if "end_line" in finding_columns else "NULL AS end_line"
            evidence_refs_expr = (
                "evidence_refs_json"
                if "evidence_refs_json" in finding_columns
                else "'[]' AS evidence_refs_json"
            )
            query = """
            SELECT
                finding_id,
                project_id,
                category,
                {rule_id_expr},
                severity,
                description,
                {recommendation_expr},
                file_path,
                start_line,
                {end_line_expr},
                status,
                {evidence_refs_expr},
                created_at
            FROM security_findings
            WHERE project_id IN ({placeholders})
              AND COALESCE(status, 'open') NOT IN ('resolved', 'mitigated', 'false_positive')
            ORDER BY
                CASE lower(severity)
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                created_at DESC
            """.format(
                placeholders=placeholders,
                rule_id_expr=rule_id_expr,
                recommendation_expr=recommendation_expr,
                end_line_expr=end_line_expr,
                evidence_refs_expr=evidence_refs_expr,
            )
            rows = cursor.execute(query, aliases).fetchall()
            findings = [
                {
                    "id": row["finding_id"],
                    "source_project_id": row["project_id"],
                    "project_id": project_id,
                    "title": row["category"] or "security finding",
                    "rule_id": row["rule_id"],
                    "severity": str(row["severity"] or "unknown").lower(),
                    "description": row["description"],
                    "recommendation": row["recommendation"],
                    "file_path": row["file_path"],
                    "line": row["start_line"],
                    "end_line": row["end_line"],
                    "location": (
                        f"{row['file_path']}:{row['start_line']}" if row["file_path"] else "Unknown"
                    ),
                    "status": row["status"],
                    "evidence_refs": _json_list(row["evidence_refs_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "findings": findings,
                "count": len(findings),
                "alias_policy": {
                    "aliases": aliases,
                    "reason": "Migrated legacy findings may use high-confidence project_<id_with_underscores> aliases.",
                },
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project security detail is read from current security_findings authority.",
                    "source_tables": ["security_findings"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if not object_exists(conn, "pi_violations"):
            return {
                "project_id": project_id,
                "findings": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["pi_violations"],
                    reason="Project security detail table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            violation_id,
            violation_type,
            severity,
            description,
            files,
            lines,
            status,
            detected_at
        FROM pi_violations
        WHERE project_id = ? AND status != 'resolved'
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            detected_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        findings = []

        for row in rows:
            findings.append(
                {
                    "id": row["violation_id"],
                    "title": row["violation_type"],
                    "severity": row["severity"],
                    "description": row["description"],
                    "location": f"{row['files']}:{row['lines']}" if row["files"] else "Unknown",
                    "status": row["status"],
                    "created_at": row["detected_at"],
                }
            )

        return {"project_id": project_id, "findings": findings, "count": len(findings)}

    except Exception as e:
        logger.error(f"Error getting project security: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/activity")
async def get_project_activity(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Get recent activity timeline for a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if object_exists(conn, "execution_events"):
            rows = cursor.execute(
                """
                SELECT
                    event_type,
                    event_name,
                    created_at,
                    outcome_status
                FROM execution_events
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            activities = [
                {
                    "activity_type": row["event_type"],
                    "timestamp": row["created_at"],
                    "message": row["event_name"] or row["event_type"],
                    "status": row["outcome_status"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "activities": activities,
                "count": len(activities),
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project activity is read from current execution_events authority.",
                    "source_tables": ["execution_events"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if object_exists(conn, "process_runs"):
            rows = cursor.execute(
                """
                SELECT
                    run_type,
                    started_at,
                    status,
                    summary
                FROM process_runs
                WHERE project_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            activities = [
                {
                    "activity_type": row["run_type"],
                    "timestamp": row["started_at"],
                    "message": row["summary"] or row["run_type"],
                    "status": row["status"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "activities": activities,
                "count": len(activities),
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project activity is read from current process_runs authority.",
                    "source_tables": ["process_runs"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if not object_exists(conn, "pi_analysis_runs"):
            return {
                "project_id": project_id,
                "activities": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["pi_analysis_runs"],
                    reason="Project activity analysis-run table is not present in this DB snapshot.",
                ),
            }

        # Get analysis runs
        runs_query = """
        SELECT
            'analysis_run' as activity_type,
            started_at as timestamp,
            'Completed ' || run_type || ' analysis - Found ' ||
            violations_found || ' violations, ' || bugs_found || ' bugs' as message
        FROM pi_analysis_runs
        WHERE project_id = ? AND status = 'completed'
        ORDER BY started_at DESC
        LIMIT ?
        """

        rows = cursor.execute(runs_query, (project_id, limit)).fetchall()
        activities = [dict(row) for row in rows]

        return {"project_id": project_id, "activities": activities, "count": len(activities)}

    except Exception as e:
        logger.error(f"Error getting project activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/dependencies")
async def get_project_dependencies(
    project_id: str, limit: int = Query(100, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Get dependency graph for a specific project.
    Returns nodes and edges for visualization.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_dependencies"):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies"],
                    reason="Project dependency table is not present in this DB snapshot.",
                ),
            }

        dependency_columns = table_columns(conn, "pi_dependencies")
        if not {"from_component", "to_component"}.issubset(dependency_columns):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies.from_component", "pi_dependencies.to_component"],
                    reason="Project dependency table exists but lacks the required endpoint columns.",
                ),
            }

        dependency_type_expr = (
            "dependency_type"
            if "dependency_type" in dependency_columns
            else "'confirmed' AS dependency_type"
        )
        strength_expr = "strength" if "strength" in dependency_columns else "1.0 AS strength"
        dependency_id_expr = (
            "dependency_id"
            if "dependency_id" in dependency_columns
            else "from_component || '->' || to_component AS dependency_id"
        )

        # Get dependencies
        deps_query = """
        SELECT
            {dependency_id_expr},
            from_component,
            to_component,
            {dependency_type_expr},
            {strength_expr}
        FROM pi_dependencies
        WHERE project_id = ?
        LIMIT ?
        """.format(
            dependency_id_expr=dependency_id_expr,
            dependency_type_expr=dependency_type_expr,
            strength_expr=strength_expr,
        )

        rows = cursor.execute(deps_query, (project_id, limit)).fetchall()
        components = _component_index(conn, project_id)

        # Build nodes and edges
        nodes = {}
        edges = []

        for row in rows:
            dependency_id = row["dependency_id"]
            from_comp = row["from_component"]
            to_comp = row["to_component"]
            dep_type = row["dependency_type"]
            strength = row["strength"] or 1.0

            # Extract simple names
            from_name = from_comp.split(":")[-1] if ":" in from_comp else from_comp
            to_name = to_comp.split(":")[-1] if ":" in to_comp else to_comp

            # Add nodes
            if from_comp not in nodes:
                nodes[from_comp] = {
                    "id": from_comp,
                    "name": components.get(from_comp, {}).get("name") or from_name,
                    "type": components.get(from_comp, {}).get("component_type") or "component",
                    "path": components.get(from_comp, {}).get("path"),
                    "evidence_refs": components.get(from_comp, {}).get("evidence_refs", []),
                    "confirmation_status": "confirmed",
                    "source_tables": ["pi_components", "pi_dependencies"],
                }
            if to_comp not in nodes:
                nodes[to_comp] = {
                    "id": to_comp,
                    "name": components.get(to_comp, {}).get("name") or to_name,
                    "type": components.get(to_comp, {}).get("component_type") or "component",
                    "path": components.get(to_comp, {}).get("path"),
                    "evidence_refs": components.get(to_comp, {}).get("evidence_refs", []),
                    "confirmation_status": "confirmed",
                    "source_tables": ["pi_components", "pi_dependencies"],
                }

            # Add edge
            edge_source_refs = []
            for component_id in (from_comp, to_comp):
                edge_source_refs.extend(components.get(component_id, {}).get("evidence_refs", []))
            edges.append(
                {
                    "id": dependency_id,
                    "from": from_comp,
                    "to": to_comp,
                    "type": dep_type,
                    "strength": strength,
                    "confirmation_status": "confirmed",
                    "rendered_by_default": True,
                    "source_tables": ["pi_dependencies"],
                    "source_refs": sorted(dict.fromkeys(edge_source_refs)),
                    "evidence_refs": sorted(dict.fromkeys(edge_source_refs)),
                }
            )

        # Group by dependency type
        type_counts = {}
        for edge in edges:
            t = edge["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "project_id": project_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "confirmed_edges": edges,
            "inferred_edges": [],
            "unverified_edges": [],
            "node_count": len(nodes),
            "edge_count": len(edges),
            "confirmed_edge_count": len(edges),
            "inferred_edge_count": 0,
            "unverified_edge_count": 0,
            "type_counts": type_counts,
            "knowledge_graph_status": {
                "classification": "confirmed" if edges else "unavailable",
                "reason": (
                    "Confirmed dependency edges are available from pi_dependencies."
                    if edges
                    else "No confirmed dependency edges exist; the dashboard must not draw placeholder graph nodes or inferred edges."
                ),
                "source_tables": ["pi_dependencies"],
                "placeholder_edges_rendered": False,
                "confirmed_edges_rendered_by_default": True,
                "inferred_edges_rendered_by_default": False,
                "derived_view": True,
                "primary_authority": False,
            },
            "source_status": {
                "classification": "fresh" if edges else "honest_empty_state",
                "source_tables": ["pi_dependencies"]
                + (["pi_components"] if object_exists(conn, "pi_components") else []),
                "derived_view": True,
                "primary_authority": False,
            },
            "drilldown": {
                "project": project_id,
                "node_to_component_evidence": "nodes[].evidence_refs",
                "edge_to_dependency_evidence": "edges[].source_refs",
                "confirmed_edges_only_by_default": True,
            },
        }

    except Exception as e:
        logger.error(f"Error getting project dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
