"""AI adapter usage accounting read/write models.

This module records how Dream Studio understands adapter usage without turning
tokens into money unless a source explicitly provides cost data.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

ACCOUNTING_SOURCE_TABLES: tuple[str, ...] = (
    "ai_adapter_accounting_profiles",
    "ai_usage_operational_records",
    "token_usage_records",
    "adapter_authority_profiles",
    "model_provider_profiles",
)

REPORTABLE_COST_VISIBILITIES = {
    "exact",
    "provider_reported",
    "estimated",
    "allocated_subscription_cost",
}

DEFAULT_ACCOUNTING_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile_id": "claude-code-subscription",
        "adapter_id": "claude",
        "provider": "anthropic",
        "configuration_label": "Claude Code subscription",
        "billing_mode": "subscription_plan",
        "token_visibility": "partial",
        "cost_visibility": "unavailable",
        "usage_source": "manual_config",
        "cost_source": "unavailable",
        "confidence": "medium",
        "notes": "Plan usage can expose operational tokens, but Dream Studio must not convert them into API dollars.",
    },
    {
        "profile_id": "claude-api-token-metered",
        "adapter_id": "claude",
        "provider": "anthropic",
        "configuration_label": "Claude API token-metered",
        "billing_mode": "token_metered",
        "token_visibility": "exact",
        "cost_visibility": "provider_reported",
        "usage_source": "provider_metadata",
        "cost_source": "provider_metadata",
        "confidence": "high",
        "active": 0,
        "notes": "Use only when provider metadata or usage exports are attached.",
    },
    {
        "profile_id": "codex-chatgpt-plan",
        "adapter_id": "codex",
        "provider": "openai",
        "configuration_label": "Codex via ChatGPT plan",
        "billing_mode": "subscription_plan",
        "token_visibility": "partial",
        "cost_visibility": "unavailable",
        "usage_source": "manual_config",
        "cost_source": "unavailable",
        "confidence": "medium",
        "notes": "Plan-based Codex usage must not invent per-run token or cost values.",
    },
    {
        "profile_id": "codex-token-metered-flexible",
        "adapter_id": "codex",
        "provider": "openai",
        "configuration_label": "Codex token-metered/flexible",
        "billing_mode": "token_metered",
        "token_visibility": "exact",
        "cost_visibility": "provider_reported",
        "usage_source": "provider_metadata",
        "cost_source": "provider_metadata",
        "confidence": "high",
        "active": 0,
        "notes": "Use only when usage metadata, provider export, or billing API evidence exists.",
    },
    {
        "profile_id": "chatgpt-plan",
        "adapter_id": "chatgpt",
        "provider": "openai",
        "configuration_label": "ChatGPT plan",
        "billing_mode": "subscription_plan",
        "token_visibility": "unavailable",
        "cost_visibility": "unavailable",
        "usage_source": "plan_usage_panel",
        "cost_source": "unavailable",
        "confidence": "low",
    },
    {
        "profile_id": "cursor-plan",
        "adapter_id": "cursor",
        "provider": "cursor",
        "configuration_label": "Cursor plan or allowance",
        "billing_mode": "plan_allowance",
        "token_visibility": "partial",
        "cost_visibility": "unavailable",
        "usage_source": "plan_usage_panel",
        "cost_source": "unavailable",
        "confidence": "low",
    },
    {
        "profile_id": "copilot-subscription",
        "adapter_id": "copilot",
        "provider": "github",
        "configuration_label": "GitHub Copilot subscription",
        "billing_mode": "subscription_plan",
        "token_visibility": "unavailable",
        "cost_visibility": "unavailable",
        "usage_source": "manual_config",
        "cost_source": "unavailable",
        "confidence": "low",
    },
    {
        "profile_id": "mcp-usage-router",
        "adapter_id": "mcp",
        "provider": "mcp",
        "configuration_label": "MCP-capable tools",
        "billing_mode": "unknown",
        "token_visibility": "unavailable",
        "cost_visibility": "unknown",
        "usage_source": "local_telemetry",
        "cost_source": "unknown",
        "confidence": "unknown",
    },
    {
        "profile_id": "local-model-runtime",
        "adapter_id": "local-model",
        "provider": "local",
        "configuration_label": "Local model runtime",
        "billing_mode": "unavailable",
        "token_visibility": "estimated",
        "cost_visibility": "unavailable",
        "usage_source": "local_telemetry",
        "cost_source": "unavailable",
        "confidence": "medium",
    },
    {
        "profile_id": "shell-tool-usage",
        "adapter_id": "shell",
        "provider": "local",
        "configuration_label": "Shell tools",
        "billing_mode": "unavailable",
        "token_visibility": "unavailable",
        "cost_visibility": "unavailable",
        "usage_source": "local_telemetry",
        "cost_source": "unavailable",
        "confidence": "high",
    },
)


def register_default_adapter_accounting_profiles(conn: sqlite3.Connection) -> None:
    """Install non-secret default accounting declarations."""

    require_shared_intelligence_tables(conn)
    _require_accounting_tables(conn)
    for profile in DEFAULT_ACCOUNTING_PROFILES:
        record_adapter_accounting_profile(conn, **profile)


def record_adapter_accounting_profile(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    _require_accounting_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO ai_adapter_accounting_profiles (
            profile_id, adapter_id, provider, model_id, configuration_label,
            billing_mode, token_visibility, cost_visibility, usage_source,
            cost_source, confidence, active, notes, source_refs_json,
            evidence_refs_json, updated_at
        ) VALUES (
            :profile_id, :adapter_id, :provider, :model_id, :configuration_label,
            :billing_mode, :token_visibility, :cost_visibility, :usage_source,
            :cost_source, :confidence, :active, :notes, :source_refs_json,
            :evidence_refs_json, datetime('now')
        )
        """,
        {
            "profile_id": values["profile_id"],
            "adapter_id": values["adapter_id"],
            "provider": values.get("provider"),
            "model_id": values.get("model_id"),
            "configuration_label": values["configuration_label"],
            "billing_mode": values["billing_mode"],
            "token_visibility": values["token_visibility"],
            "cost_visibility": values["cost_visibility"],
            "usage_source": values["usage_source"],
            "cost_source": values.get("cost_source", "unavailable"),
            "confidence": values.get("confidence", "unknown"),
            "active": 1 if values.get("active", 1) else 0,
            "notes": values.get("notes"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_ai_usage_operational_record(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    _require_accounting_tables(conn)
    cost_amount = values.get("cost_amount")
    cost_visibility = values.get("cost_visibility", "unknown")
    if cost_visibility not in REPORTABLE_COST_VISIBILITIES:
        cost_amount = None
    conn.execute(
        """
        INSERT OR REPLACE INTO ai_usage_operational_records (
            usage_record_id, project_id, milestone_id, task_id, work_order_id,
            process_run_id, adapter_id, provider, model_id, accounting_profile_id,
            token_usage_id, billing_mode, token_visibility, cost_visibility,
            usage_source, cost_source, confidence, input_tokens, output_tokens,
            cached_tokens, total_tokens, cost_amount, cost_currency, run_count,
            files_touched_json, commands_run_json, validation_result,
            pr_result_outcome, success, failure_reason, rework_needed,
            security_findings_json, readiness_findings_json, duration_ms,
            source_refs_json, evidence_refs_json
        ) VALUES (
            :usage_record_id, :project_id, :milestone_id, :task_id, :work_order_id,
            :process_run_id, :adapter_id, :provider, :model_id, :accounting_profile_id,
            :token_usage_id, :billing_mode, :token_visibility, :cost_visibility,
            :usage_source, :cost_source, :confidence, :input_tokens, :output_tokens,
            :cached_tokens, :total_tokens, :cost_amount, :cost_currency, :run_count,
            :files_touched_json, :commands_run_json, :validation_result,
            :pr_result_outcome, :success, :failure_reason, :rework_needed,
            :security_findings_json, :readiness_findings_json, :duration_ms,
            :source_refs_json, :evidence_refs_json
        )
        """,
        {
            "usage_record_id": values["usage_record_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "work_order_id": values.get("work_order_id"),
            "process_run_id": values.get("process_run_id"),
            "adapter_id": values["adapter_id"],
            "provider": values.get("provider"),
            "model_id": values.get("model_id"),
            "accounting_profile_id": values.get("accounting_profile_id"),
            "token_usage_id": values.get("token_usage_id"),
            "billing_mode": values.get("billing_mode", "unknown"),
            "token_visibility": values.get("token_visibility", "unavailable"),
            "cost_visibility": cost_visibility,
            "usage_source": values.get("usage_source", "local_telemetry"),
            "cost_source": values.get("cost_source", "unknown"),
            "confidence": values.get("confidence", "unknown"),
            "input_tokens": values.get("input_tokens"),
            "output_tokens": values.get("output_tokens"),
            "cached_tokens": values.get("cached_tokens"),
            "total_tokens": values.get("total_tokens"),
            "cost_amount": cost_amount,
            "cost_currency": values.get("cost_currency"),
            "run_count": int(values.get("run_count", 1)),
            "files_touched_json": _json(values.get("files_touched"), []),
            "commands_run_json": _json(values.get("commands_run"), []),
            "validation_result": values.get("validation_result"),
            "pr_result_outcome": values.get("pr_result_outcome"),
            "success": _optional_bool(values.get("success")),
            "failure_reason": values.get("failure_reason"),
            "rework_needed": _optional_bool(values.get("rework_needed")),
            "security_findings_json": _json(values.get("security_findings"), []),
            "readiness_findings_json": _json(values.get("readiness_findings"), []),
            "duration_ms": values.get("duration_ms"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def adapter_usage_accounting_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    missing = _missing_accounting_tables(conn)
    if missing:
        return _empty_accounting_summary(project_id=project_id, missing=missing)
    profiles = _accounting_profiles(conn)
    operations = _operational_records(conn, project_id=project_id)
    token_rows = _token_accounting_rows(conn, project_id=project_id)
    by_adapter: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "run_count": 0,
            "token_records": 0,
            "total_tokens": 0,
            "reportable_cost": None,
            "cost_unknown_count": 0,
            "files_touched_count": 0,
            "commands_run_count": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "rework_needed_count": 0,
            "validation_results": Counter(),
            "billing_modes": Counter(),
            "token_visibility": Counter(),
            "cost_visibility": Counter(),
        }
    )
    for row in token_rows:
        adapter = row.get("adapter_id") or _adapter_from_provider(row.get("provider"))
        bucket = by_adapter[adapter]
        bucket["token_records"] += 1
        bucket["total_tokens"] += int(row.get("total_tokens") or 0)
        bucket["billing_modes"][row.get("billing_mode") or "unknown"] += 1
        bucket["token_visibility"][row.get("token_visibility") or "unavailable"] += 1
        cost_visibility = row.get("cost_visibility") or "unknown"
        bucket["cost_visibility"][cost_visibility] += 1
        if cost_visibility in REPORTABLE_COST_VISIBILITIES:
            bucket["reportable_cost"] = (bucket["reportable_cost"] or 0) + float(
                row.get("estimated_cost") or 0
            )
        else:
            bucket["cost_unknown_count"] += 1
    for row in operations:
        bucket = by_adapter[row["adapter_id"]]
        bucket["run_count"] += int(row.get("run_count") or 1)
        bucket["files_touched_count"] += len(row.get("files_touched") or [])
        bucket["commands_run_count"] += len(row.get("commands_run") or [])
        if row.get("success") == 1:
            bucket["successful_runs"] += 1
        elif row.get("success") == 0:
            bucket["failed_runs"] += 1
        if row.get("rework_needed") == 1:
            bucket["rework_needed_count"] += 1
        if row.get("validation_result"):
            bucket["validation_results"][row["validation_result"]] += 1
        bucket["billing_modes"][row.get("billing_mode") or "unknown"] += 1
        bucket["token_visibility"][row.get("token_visibility") or "unavailable"] += 1
        bucket["cost_visibility"][row.get("cost_visibility") or "unknown"] += 1
    return {
        "model_name": "dream_studio_ai_usage_accounting",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": project_id,
        "source_tables": list(ACCOUNTING_SOURCE_TABLES),
        "profiles": profiles,
        "profile_count": len(profiles),
        "operational_records": operations,
        "operational_record_count": len(operations),
        "token_record_count": len(token_rows),
        "by_adapter": {
            adapter: _finalize_adapter_bucket(bucket)
            for adapter, bucket in sorted(by_adapter.items())
        },
        "policy": {
            "tokens_are_usage_not_cost": True,
            "no_token_to_dollar_conversion_without_cost_source": True,
            "plan_usage_uses_operational_value_metrics": True,
            "provider_billing_credentials_inspected": False,
            "cost_unknown_display": "unknown",
        },
        "empty_state": "No AI usage accounting facts are recorded for this scope.",
    }


def _missing_accounting_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
        f"({','.join('?' for _ in ACCOUNTING_SOURCE_TABLES)})",
        tuple(ACCOUNTING_SOURCE_TABLES),
    ).fetchall()
    found = {str(row[0]) for row in rows}
    return sorted(set(ACCOUNTING_SOURCE_TABLES) - found)


def _require_accounting_tables(conn: sqlite3.Connection) -> None:
    missing = _missing_accounting_tables(conn)
    if missing:
        raise RuntimeError(f"AI usage accounting schema missing tables: {missing}")


def _empty_accounting_summary(*, project_id: str | None, missing: list[str]) -> dict[str, Any]:
    return {
        "model_name": "dream_studio_ai_usage_accounting",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": project_id,
        "source_tables": list(ACCOUNTING_SOURCE_TABLES),
        "profiles": [],
        "profile_count": 0,
        "operational_records": [],
        "operational_record_count": 0,
        "token_record_count": 0,
        "by_adapter": {},
        "schema_status": "migration_required",
        "missing_tables": missing,
        "policy": {
            "tokens_are_usage_not_cost": True,
            "no_token_to_dollar_conversion_without_cost_source": True,
            "plan_usage_uses_operational_value_metrics": True,
            "provider_billing_credentials_inspected": False,
            "cost_unknown_display": "unknown",
        },
        "empty_state": "AI usage accounting requires migration 043 before records are available.",
    }


def _accounting_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("""
        SELECT *
        FROM ai_adapter_accounting_profiles
        ORDER BY adapter_id, active DESC, configuration_label
        """).fetchall()
    return [_decode_profile(row) for row in rows]


def _operational_records(
    conn: sqlite3.Connection, *, project_id: str | None = None
) -> list[dict[str, Any]]:
    where = ""
    params: tuple[Any, ...] = ()
    if project_id:
        where = "WHERE project_id = ?"
        params = (project_id,)
    rows = conn.execute(
        f"""
        SELECT *
        FROM ai_usage_operational_records
        {where}
        ORDER BY created_at DESC, usage_record_id DESC
        """,
        params,
    ).fetchall()
    return [_decode_operational(row) for row in rows]


def _token_accounting_rows(
    conn: sqlite3.Connection, *, project_id: str | None = None
) -> list[dict[str, Any]]:
    where = ""
    params: tuple[Any, ...] = ()
    if project_id:
        where = "WHERE project_id = ?"
        params = (project_id,)
    rows = conn.execute(
        f"""
        SELECT token_usage_id, project_id, process_run_id, adapter_id, provider,
               model_id, billing_mode, token_visibility, cost_visibility,
               usage_source, cost_source, accounting_confidence, input_tokens,
               output_tokens, cached_tokens, total_tokens, estimated_cost
        FROM token_usage_records
        {where}
        ORDER BY created_at DESC, token_usage_id DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _decode_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = dict(row)
    profile["active"] = bool(profile["active"])
    profile["source_refs"] = _loads(profile.pop("source_refs_json"), [])
    profile["evidence_refs"] = _loads(profile.pop("evidence_refs_json"), [])
    return profile


def _decode_operational(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for key in (
        "files_touched",
        "commands_run",
        "security_findings",
        "readiness_findings",
        "source_refs",
        "evidence_refs",
    ):
        record[key] = _loads(record.pop(f"{key}_json"), [])
    return record


def _finalize_adapter_bucket(bucket: Mapping[str, Any]) -> dict[str, Any]:
    reportable_cost = bucket["reportable_cost"]
    return {
        "run_count": bucket["run_count"],
        "token_records": bucket["token_records"],
        "total_tokens": bucket["total_tokens"],
        "reportable_cost": round(reportable_cost, 6) if reportable_cost is not None else None,
        "cost_display": (f"{reportable_cost:.6f}" if reportable_cost is not None else "unknown"),
        "cost_unknown_count": bucket["cost_unknown_count"],
        "files_touched_count": bucket["files_touched_count"],
        "commands_run_count": bucket["commands_run_count"],
        "successful_runs": bucket["successful_runs"],
        "failed_runs": bucket["failed_runs"],
        "rework_needed_count": bucket["rework_needed_count"],
        "validation_results": dict(sorted(bucket["validation_results"].items())),
        "billing_modes": dict(sorted(bucket["billing_modes"].items())),
        "token_visibility": dict(sorted(bucket["token_visibility"].items())),
        "cost_visibility": dict(sorted(bucket["cost_visibility"].items())),
    }


def _adapter_from_provider(provider: str | None) -> str:
    normalized = (provider or "").lower()
    if normalized == "anthropic":
        return "claude"
    if normalized == "openai":
        return "codex"
    if normalized in {"local", "local_model"}:
        return "local-model"
    return "unknown"


def _optional_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
