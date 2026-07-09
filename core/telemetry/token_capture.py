"""PostToolUse hook handler — emits token.consumed canonical events.

This is the real work module; the hook shim delegates here.
All errors are logged to the diagnostic stream. This function never raises.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType
from core.telemetry.diagnostics import log_diagnostic
from core.telemetry.machine_id import get_machine_id
import emitters.shared.spool_writer as _spool_writer_mod

# Performance thresholds (ms)
_THRESH_TOTAL = 100.0
_THRESH_SPOOL = 50.0
_THRESH_GIT = 50.0
_THRESH_ACTIVE_TASK = 20.0

_SOURCE = "token_capture.handle_post_tool_use"


def _extract_usage(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract token usage from payload. Returns dict or None if absent."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        # Some Claude Code versions may nest usage under tool_response
        tr = payload.get("tool_response")
        if isinstance(tr, dict):
            usage = tr.get("usage")
    if not isinstance(usage, dict):
        return None
    return usage


# Synthetic / placeholder model labels that must never be recorded as a real model.
_PLACEHOLDER_MODELS = {"<synthetic>", "synthetic", "unspecified", "unknown", ""}


def _model_from_transcript(transcript_path: str) -> str | None:
    """Recover the model from the session transcript JSONL.

    Claude Code's PostToolUse hook input carries ``transcript_path`` but not the
    model for main-loop tool calls.  The transcript records ``message.model`` on
    every assistant turn, so the model that issued this tool call is the model of
    the most recent real (non-synthetic) assistant message.  This is recovered
    truth, not a heuristic — the same value the API billed.

    Returns the model string, or None if the transcript is unreadable / carries
    only synthetic turns.  Never raises.
    """
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return None
        # Scan from the end: the issuing turn is the last real assistant message.
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line or '"model"' not in line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if rec.get("type") != "assistant":
                continue
            model = (rec.get("message") or {}).get("model")
            if model and model not in _PLACEHOLDER_MODELS:
                return model
    except Exception:
        return None
    return None


def _resolve_model(payload: dict[str, Any]) -> str | None:
    """Resolve the model for this token event.

    Order: explicit ``payload.model`` (subagent SDK supplies it) → the issuing
    assistant turn's model recovered from ``transcript_path`` (main-loop tool
    calls, where the hook omits the model).  Returns None when neither yields a
    real model — NULL is recorded honestly rather than a placeholder.
    """
    model = payload.get("model")
    if model and model not in _PLACEHOLDER_MODELS:
        return model
    transcript_path = payload.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        return _model_from_transcript(transcript_path)
    return None


def _has_nonzero_tokens(usage: dict[str, Any]) -> bool:
    return any(
        int(usage.get(k) or 0) > 0
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    )


def _resolve_attribution(
    session_id: str | None,
    machine_id: str,
    tool_name: str,
    tool_use_id: str | None,
) -> dict[str, Any]:
    """Resolve attribution trace: active_task → CWD marker → orphan."""
    # Read active skill written by record_skill_invocation() (best-effort).
    active_skill_id: str | None = None
    try:
        _skill_path = Path.home() / ".dream-studio" / "state" / "active_skill.json"
        _skill_data = json.loads(_skill_path.read_text(encoding="utf-8"))
        active_skill_id = _skill_data.get("skill_id") or None
    except Exception:
        pass

    t0 = time.monotonic()
    task_ctx = None
    try:
        from core.sdlc.active_task import get_active_task

        task_ctx = get_active_task()
    except Exception as exc:
        log_diagnostic(
            category="anomaly",
            source=_SOURCE,
            context={"step": "active_task_lookup"},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
            session_id=session_id,
            machine_id=machine_id,
        )
    elapsed_at = (time.monotonic() - t0) * 1000
    if elapsed_at > _THRESH_ACTIVE_TASK:
        log_diagnostic(
            category="performance",
            source=_SOURCE,
            context={"step": "active_task_lookup"},
            duration_ms=elapsed_at,
            session_id=session_id,
            machine_id=machine_id,
        )

    if task_ctx is not None:
        return {
            "domain": "telemetry",
            "attribution_status": "fully_attributed",
            "task_id": task_ctx.task_id,
            "work_order_id": task_ctx.work_order_id,
            "milestone_id": task_ctx.milestone_id,
            "project_id": task_ctx.project_id,
            "skill_id": active_skill_id,
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "session_id": session_id,
            "machine_id": machine_id,
        }

    # Try CWD marker.
    cwd_ctx = None
    try:
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        cwd_ctx = resolve_project_from_cwd()
    except Exception as exc:
        log_diagnostic(
            category="anomaly",
            source=_SOURCE,
            context={"step": "cwd_resolution"},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
            session_id=session_id,
            machine_id=machine_id,
        )

    if cwd_ctx is not None:
        return {
            "domain": "telemetry",
            "attribution_status": "partial",
            "task_id": None,
            "work_order_id": None,
            "milestone_id": None,
            "project_id": cwd_ctx.project_id,
            "skill_id": active_skill_id,
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "session_id": session_id,
            "machine_id": machine_id,
            "_cwd_ctx": cwd_ctx,  # internal; stripped before building envelope
        }

    return {
        "domain": "telemetry",
        "attribution_status": "orphan",
        "task_id": None,
        "work_order_id": None,
        "milestone_id": None,
        "project_id": None,
        "skill_id": active_skill_id,
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "machine_id": machine_id,
    }


def _capture_git_context(cwd_ctx: Any) -> dict[str, Any]:
    """Capture git metadata without absolute paths."""
    t0 = time.monotonic()
    git_ctx: dict[str, Any] = {}

    def _run_git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    commit = _run_git("rev-parse", "HEAD")
    if commit:
        git_ctx["git_commit"] = commit
    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        git_ctx["git_branch"] = branch
    remote = _run_git("config", "--get", "remote.origin.url")
    if remote:
        git_ctx["git_remote_url"] = remote

    # cwd relative to project root — no absolute paths in event.
    if cwd_ctx is not None:
        try:
            from pathlib import Path

            cwd = Path.cwd().resolve()
            project_root = cwd_ctx.marker_path.parent.resolve()
            try:
                rel = cwd.relative_to(project_root)
                git_ctx["cwd_relative_to_project"] = str(rel).replace("\\", "/") or "."
            except ValueError:
                git_ctx["cwd_relative_to_project"] = None
        except Exception:
            pass

    elapsed = (time.monotonic() - t0) * 1000
    return git_ctx, elapsed


def _capture_platform_context() -> dict[str, Any]:
    try:
        from core.config.platform import get_platform_profile

        profile = get_platform_profile()
        if profile is not None:
            return {
                "os": profile.os_name,
                "os_version": profile.os_version,
                "shell": profile.shell,
            }
    except Exception:
        pass
    return {}


def _update_session_accumulator(session_id: str, token_payload: dict[str, Any]) -> None:
    """Merge new token counts into the per-session accumulator file.

    The accumulator lets normalize_stop() reconstruct per-session totals when
    Claude Code's Stop payload carries no usage field.
    """
    # WO-FILESDB-P2: prefer the authority table; fall back to the legacy JSON file
    # when raw_session_token_accumulators is absent (migration 145 unreleased).
    try:
        from core.telemetry.session_accumulator import db_update_accumulator

        if db_update_accumulator(session_id, token_payload):
            return
    except Exception:
        pass

    acc_path = Path.home() / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
    try:
        try:
            existing: dict[str, Any] = json.loads(acc_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            existing = {}
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            existing[key] = int(existing.get(key) or 0) + int(token_payload.get(key) or 0)
        # Persist the model (last real value wins) so normalize_stop can stamp it
        # onto the token.consumption.recorded event. Without it the DuckDB
        # token_usage_records view cannot price the session turn (estimated_cost
        # stays NULL and dashboard cost never moves). Model is recovered truth
        # (SDK payload / transcript), never fabricated.
        if token_payload.get("model"):
            existing["model"] = token_payload["model"]
        acc_path.parent.mkdir(parents=True, exist_ok=True)
        acc_path.write_text(json.dumps(existing), encoding="utf-8")
    except Exception:
        pass


def handle_post_tool_use(payload: dict[str, Any]) -> None:
    """Process a PostToolUse hook payload and emit token.consumed to spool.

    Never raises.
    """
    t_total = time.monotonic()
    session_id: str | None = payload.get("session_id")
    machine_id = get_machine_id()

    try:
        # Step 1: Extract and validate usage.
        usage = _extract_usage(payload)
        if usage is None:
            log_diagnostic(
                category="anomaly",
                source=_SOURCE,
                context={"tool_name": payload.get("tool_name")},
                details={
                    "error_message": "PostToolUse payload has no usage block; skipping emission"
                },
                session_id=session_id,
                machine_id=machine_id,
            )
            return

        if not _has_nonzero_tokens(usage):
            log_diagnostic(
                category="anomaly",
                source=_SOURCE,
                context={"tool_name": payload.get("tool_name")},
                details={
                    "error_message": "PostToolUse usage block has all-zero counts; skipping emission"
                },
                session_id=session_id,
                machine_id=machine_id,
            )
            return

        # Validate token counts are non-negative.
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            val = usage.get(k)
            if val is not None and int(val) < 0:
                log_diagnostic(
                    category="anomaly",
                    source=_SOURCE,
                    context={"token_key": k, "value": val},
                    details={
                        "error_message": "Negative token count in usage block; skipping emission"
                    },
                    session_id=session_id,
                    machine_id=machine_id,
                )
                return

        # Step 2: Resolve attribution.
        tool_name: str = payload.get("tool_name", payload.get("tool", ""))
        tool_use_id: str | None = payload.get("tool_use_id")
        attr = _resolve_attribution(session_id, machine_id, tool_name, tool_use_id)
        cwd_ctx = attr.pop("_cwd_ctx", None)

        # Step 3: Git context.
        git_ctx, git_elapsed = _capture_git_context(cwd_ctx)
        if git_elapsed > _THRESH_GIT:
            log_diagnostic(
                category="performance",
                source=_SOURCE,
                context={"step": "git_context"},
                duration_ms=git_elapsed,
                session_id=session_id,
                machine_id=machine_id,
            )

        # Step 4: Platform context.
        platform_ctx = _capture_platform_context()

        # Step 5: Build token payload.
        token_payload: dict[str, Any] = {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "granularity": "tool_invocation",
        }
        model = _resolve_model(payload)
        if model:
            token_payload["model"] = model

        # project_name only from JSON markers (denormalized cache).
        if cwd_ctx is not None and cwd_ctx.marker_format == "json" and cwd_ctx.project_name:
            token_payload["project_name"] = cwd_ctx.project_name

        exec_ctx: dict[str, Any] = {}
        exec_ctx.update(git_ctx)
        if platform_ctx:
            exec_ctx["platform"] = platform_ctx
        if exec_ctx:
            token_payload["execution_context"] = exec_ctx

        # Step 6: Build trace (clean copy, no internal keys).
        trace = {k: v for k, v in attr.items() if not k.startswith("_")}

        # WO-AGENT-TELEMETRY: a Task tool call is a subagent invocation — attribute
        # its tokens to the invoked agent so the agent_id dimension (previously
        # always NULL) carries token cost. subagent_type is the hook surface's
        # agent identity (see emitters/claude_code/emitter.py).
        tool_input = payload.get("tool_input", payload.get("input", {}))
        if tool_name == "Task" and isinstance(tool_input, dict):
            subagent = tool_input.get("subagent_type") or tool_input.get("subagentType")
            if subagent:
                trace["agent_id"] = str(subagent).strip()
                trace["agent_type"] = str(subagent).strip()

        # Step 7: Write to spool.
        envelope = CanonicalEventEnvelope(
            event_type=EventType.TOKEN_CONSUMED.value,
            session_id=session_id,
            payload=token_payload,
            project_id=attr.get("project_id"),
            trace=trace,
            severity="info",
        )

        t_spool = time.monotonic()
        _spool_writer_mod.write_envelopes([envelope])
        spool_elapsed = (time.monotonic() - t_spool) * 1000
        if spool_elapsed > _THRESH_SPOOL:
            log_diagnostic(
                category="performance",
                source=_SOURCE,
                context={"step": "spool_write"},
                duration_ms=spool_elapsed,
                session_id=session_id,
                machine_id=machine_id,
            )

        # Step 8: Update per-session accumulator so normalize_stop can source totals.
        if session_id:
            _update_session_accumulator(session_id, token_payload)

    except Exception as exc:
        log_diagnostic(
            category="failure",
            source=_SOURCE,
            context={"tool_name": payload.get("tool_name")},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
            session_id=session_id,
            machine_id=machine_id,
        )

    finally:
        total_elapsed = (time.monotonic() - t_total) * 1000
        if total_elapsed > _THRESH_TOTAL:
            log_diagnostic(
                category="performance",
                source=_SOURCE,
                context={"step": "total"},
                duration_ms=total_elapsed,
                session_id=session_id,
                machine_id=machine_id,
            )
