"""Skill invocation: load SKILL.md, record the invocation event, and seed
gate-artifact files for the work order/milestone the skill runs against.

This module replaces the heaviest CLI handler in `interfaces/cli/ds.py`
(`_skill_invoke`) by decomposing it into three pure functions so the
upcoming Phase A3 workflow runner can compose them directly instead of
shelling out to the CLI:

- `load_skill_content(specifier, source_root)`
    Validates the `pack:mode` specifier, resolves the SKILL.md path
    (honoring the `skill_path` override in packs.yaml), and returns the
    file content. Pure read. No spool, no DB, no print.

- `record_skill_invocation(specifier, target, work_order_id, project_id,
                            source_root, dream_studio_home)`
    Resolves a project_id when one was not supplied (best-effort: from
    the work_order_id's project, then from the Claude-Code marker file),
    emits the `skill.invoked` spool event, and returns the resolved
    fields. The spool emission is best-effort — exceptions are swallowed
    so the caller never sees an `IOError` from a missing spool root.

- `seed_gate_artifact_files(specifier, target, work_order_id,
                              milestone_id, project_id, planning_root,
                              source_root, dream_studio_home)`
    For the small set of skills whose output gates expect a pre-shaped
    artifact (website:critique → design-critique.md, security:scan →
    security-scan.md), write the template under `planning_root/...`. For
    website:discover with a project_id, ensure a design brief row exists
    so the wizard can `update` into it.

The `website:discover` branch calls `create_design_brief` directly
from `core.design_briefs.mutations` (lifted in A2.5).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.skills.queries import _load_packs

_SKILL_SPECIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")

# Phase 20 (WO-P20-MARKETPLACE): the Claude plugin marketplace namespaces every
# skill under the plugin name. Accept `dream-studio:<spec>` as equivalent to the
# bare `<spec>` so marketplace installs and direct installs invoke identically.
_PLUGIN_NAMESPACE = "dream-studio:"


def _strip_plugin_namespace(specifier: str) -> str:
    """Drop a leading `dream-studio:` plugin namespace if present."""
    if specifier.startswith(_PLUGIN_NAMESPACE):
        return specifier[len(_PLUGIN_NAMESPACE) :]  # noqa: E203
    return specifier


def _resolve_pack_token(token: str, packs: dict) -> str | None:
    """Resolve a pack token to a packs.yaml key.

    Accepts either the pack key (e.g. ``core``) or the skill id (e.g. ``ds-core``),
    so namespaced marketplace IDs (``dream-studio:ds-core:build``) and bare pack
    IDs (``core:build``) both resolve. Returns the pack key or None.
    """
    if token in packs:
        return token
    for key, cfg in packs.items():
        if not isinstance(cfg, dict):
            continue
        skill_id = cfg.get("skill", key)
        if not skill_id.startswith("ds-"):
            skill_id = f"ds-{skill_id}"
        if token == skill_id:
            return key
    return None


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path | None:
    """Like the other `_require_db` helpers, but returns None instead of
    raising when the runtime DB is missing — `_skill_invoke` runs even
    without an installed runtime (it just degrades to no-DB best-effort)."""

    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    return paths.sqlite_path if paths.sqlite_path.exists() else None


def load_skill_content(
    *,
    specifier: str,
    source_root: Path,
) -> dict[str, Any]:
    """Validate the `pack:mode` specifier and read its SKILL.md.

    Returns either::

        {"ok": True, "specifier": str, "pack": str, "mode": str,
         "skill_path": Path, "skill_content": str}

    or::

        {"ok": False, "error": "Unknown skill: ...", "specifier": str}
        {"ok": False, "error": "Skill content not found ...", "specifier": str}
    """

    unknown = f"Unknown skill: {specifier}. Run `ds skill list` to see available skills."

    # Accept an optional `dream-studio:` plugin namespace (marketplace installs).
    bare = _strip_plugin_namespace(specifier)

    if not _SKILL_SPECIFIER_RE.match(bare):
        return {"ok": False, "error": unknown, "specifier": specifier}

    token, mode = bare.split(":", 1)
    packs_data = _load_packs(source_root)
    packs = packs_data.get("packs", {})

    pack = _resolve_pack_token(token, packs)
    if pack is None:
        return {"ok": False, "error": unknown, "specifier": specifier}
    if mode not in packs[pack].get("modes", []):
        return {"ok": False, "error": unknown, "specifier": specifier}

    skill_path_key = packs[pack].get("skill_path")
    if skill_path_key:
        skill_md = source_root / skill_path_key / "modes" / mode / "SKILL.md"
    else:
        skill_md = source_root / "canonical" / "skills" / pack / "modes" / mode / "SKILL.md"

    if not skill_md.is_file():
        return {
            "ok": False,
            "error": f"Skill content not found for {specifier} (expected {skill_md})",
            "specifier": specifier,
        }

    return {
        "ok": True,
        "specifier": specifier,
        "pack": pack,
        "mode": mode,
        "skill_path": skill_md,
        "skill_content": skill_md.read_text(encoding="utf-8"),
    }


def _resolve_project_id(
    *,
    explicit_project_id: str | None,
    work_order_id: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> str | None:
    """Best-effort project_id resolution: explicit → WO lookup → marker file."""

    if explicit_project_id is not None:
        return explicit_project_id

    if work_order_id is not None:
        try:
            db_path = _require_db(source_root, dream_studio_home)
            if db_path is not None:
                with _connect(db_path) as conn:
                    row = conn.execute(
                        "SELECT project_id FROM business_work_orders WHERE work_order_id = ?",
                        (work_order_id,),
                    ).fetchone()
                    if row:
                        return row[0]
        except Exception:
            pass

    try:
        from emitters.claude_code.project import read_project_id

        return read_project_id(None)
    except Exception:
        return None


def record_skill_invocation(
    *,
    specifier: str,
    target: str | None,
    work_order_id: str | None,
    project_id: str | None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Resolve project_id (if missing) and emit a `skill.invoked` spool event.

    Spool emission is best-effort: if the spool writer is unavailable or
    the root is unwritable, the event is silently dropped — the caller
    still receives the resolved fields. Returns::

        {"ok": True, "specifier": str, "skill_id": str, "mode": str,
         "invocation_mode": "pipeline" | "direct",
         "resolved_project_id": str | None, "timestamp": str,
         "event_emitted": bool}
    """

    pack, mode = specifier.split(":", 1)
    skill_id = f"ds-{pack}"
    invocation_mode = "pipeline" if work_order_id else "direct"

    resolved_project_id = _resolve_project_id(
        explicit_project_id=project_id,
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    now = datetime.now(UTC).isoformat()
    try:
        from core.sdlc.active_task import get_active_task as _get_active_task

        _active_ctx = _get_active_task()
    except Exception:
        _active_ctx = None
    event_emitted = False
    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "skill.invoked",
                "timestamp": now,
                "skill_id": skill_id,
                "mode": mode,
                "invocation_mode": invocation_mode,
                "project_id": resolved_project_id,
                "trace": {
                    "domain": "sdlc",
                    "skill_specifier": specifier,
                    "project_id": (
                        _active_ctx.project_id if _active_ctx is not None else resolved_project_id
                    ),
                    "task_id": _active_ctx.task_id if _active_ctx is not None else None,
                    "work_order_id": _active_ctx.work_order_id if _active_ctx is not None else None,
                    "milestone_id": _active_ctx.milestone_id if _active_ctx is not None else None,
                    "attribution_status": (
                        "fully_attributed" if _active_ctx is not None else "orphan"
                    ),
                },
                "severity": "info",
                "payload": {
                    "skill_specifier": specifier,
                    "target": target,
                    "work_order_id": work_order_id,
                },
                "source_type": "confirmed",
                "schema_version": 1,
            }
        )
        event_emitted = True

        # Persist active skill so token_capture can stamp skill_id on token.consumed.
        # WO-FILESDB-P2: authority row first; the legacy JSON file only when the
        # raw_runtime_state table is absent (migration 146 unreleased).
        try:
            _active_skill = {"skill_id": skill_id, "set_at": now}
            from core.runtime_state import db_write_runtime_state

            if not db_write_runtime_state("active_skill", _active_skill):
                _state_dir = Path.home() / ".dream-studio" / "state"
                _state_dir.mkdir(parents=True, exist_ok=True)
                (_state_dir / "active_skill.json").write_text(
                    json.dumps(_active_skill), encoding="utf-8"
                )
        except Exception:
            pass
    except Exception:
        pass

    return {
        "ok": True,
        "specifier": specifier,
        "skill_id": skill_id,
        "mode": mode,
        "invocation_mode": invocation_mode,
        "resolved_project_id": resolved_project_id,
        "timestamp": now,
        "event_emitted": event_emitted,
    }


def _design_critique_template(work_order_id: str, target: str | None, date_str: str) -> str:
    return (
        f"# Design Critique — Work Order {work_order_id}\n"
        f"Date: {date_str}\n"
        f"Skill: website:critique\n"
        f"Target: {target or 'not specified'}\n\n"
        "## Scores\n"
        "Score: [PENDING]/4\n\n"
        "## Dimension Scores\n"
        "- Visual Hierarchy: [score]/1\n"
        "- Typography: [score]/1\n"
        "- Spacing & Layout: [score]/1\n"
        "- Color & Contrast: [score]/1\n"
        "- Component Cohesion: [score]/1\n\n"
        "## Findings\n"
        "[AI to complete after critique]\n\n"
        "## Verdict\n"
        "[PASS/FAIL]\n"
    )


def _security_scan_template(work_order_id: str, target: str | None, date_str: str) -> str:
    return (
        f"# Security Scan — Work Order {work_order_id}\n"
        f"Date: {date_str}\n"
        f"Skill: security:scan\n"
        f"Target: {target or 'not specified'}\n\n"
        "## Result\n"
        "Status: [PENDING]\n\n"
        "## Findings\n"
        "[AI to complete]\n\n"
        "## Verdict\n"
        "[PASS/BLOCKED]\n"
    )


def seed_gate_artifact_files(
    *,
    specifier: str,
    target: str | None,
    work_order_id: str | None,
    milestone_id: str | None = None,
    project_id: str | None = None,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Seed pre-shaped artifact files for gates that follow this skill.

    Only acts when ``work_order_id`` or ``milestone_id`` is supplied
    (matches the legacy handler's behaviour — no work-order context
    means there's no canonical place to write artifacts).

    Returns::

        {"ok": True, "artifacts_written": [str, ...],
         "design_brief_seeded": bool}
    """

    if not (work_order_id or milestone_id):
        return {"ok": True, "artifacts_written": [], "design_brief_seeded": False}

    p_root = planning_root or Path.cwd() / ".planning"
    if milestone_id:
        target_dir = p_root / "milestones" / milestone_id
    else:
        target_dir = p_root / "work-orders" / work_order_id  # type: ignore[arg-type]
    target_dir.mkdir(parents=True, exist_ok=True)

    artifacts_written: list[str] = []
    design_brief_seeded = False
    date_str = datetime.now(UTC).isoformat()[:10]

    if specifier == "website:critique":
        artifact = target_dir / "design-critique.md"
        artifact.write_text(
            _design_critique_template(work_order_id or milestone_id or "", target, date_str),
            encoding="utf-8",
        )
        artifacts_written.append(str(artifact))

    elif specifier == "security:scan":
        artifact = target_dir / "security-scan.md"
        artifact.write_text(
            _security_scan_template(work_order_id or milestone_id or "", target, date_str),
            encoding="utf-8",
        )
        artifacts_written.append(str(artifact))

    elif specifier == "website:discover" and project_id:
        try:
            db_path = _require_db(source_root, dream_studio_home)
            if db_path is not None:
                with _connect(db_path) as conn:
                    existing = conn.execute(
                        "SELECT brief_id FROM business_design_briefs"
                        " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                        (project_id,),
                    ).fetchone()
                if existing is None:
                    from core.design_briefs.mutations import create_design_brief

                    create_design_brief(
                        project_id=project_id,
                        source_root=source_root,
                        dream_studio_home=dream_studio_home,
                    )
                    design_brief_seeded = True
        except Exception:
            pass

    return {
        "ok": True,
        "artifacts_written": artifacts_written,
        "design_brief_seeded": design_brief_seeded,
    }
