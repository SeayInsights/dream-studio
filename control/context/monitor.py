"""Context monitoring logic extracted from on-context-threshold hook.

Handles context percentage tracking, threshold evaluation, and auto-handoff/blocking.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from control.context.handoff import (
    COMPACT_PCT,
    HANDOFF_PCT,
    URGENT_PCT,
    WARN_PCT,
    draft_handoff_lesson,
    git_context,
    scaled_kb_thresholds,
    write_handoff,
    write_recap,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import paths  # noqa: E402

MILESTONE_BOOST = 10


def read_bridge_pct(session_id: str | None) -> float | None:
    """Read used_pct from the statusline bridge file in temp dir."""
    if not session_id:
        return None
    try:
        bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
        if not bp.exists():
            return None
        data = json.loads(bp.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        if time.time() - ts > 600:
            return None
        return float(data.get("used_pct", 0))
    except Exception:
        return None


def pct_to_band(pct: float) -> tuple[str, str]:
    """Map a used_pct to a threshold band and label."""
    if pct >= URGENT_PCT:
        return "urgent", f"~{pct:.0f}%"
    if pct >= HANDOFF_PCT:
        return "handoff", f"~{pct:.0f}%"
    if pct >= COMPACT_PCT:
        return "compact", f"~{pct:.0f}%"
    if pct >= WARN_PCT:
        return "warn", f"~{pct:.0f}%"
    return "ok", f"~{pct:.0f}%"


def kb_to_band(kb: float, db_path: "Path | None" = None) -> tuple[str, str]:
    """Fallback: map JSONL KB to a threshold band.

    The KB thresholds are scaled to the active context window (WO-CONTEXT-THRESHOLD-SCALE)
    so the same transcript size does not trip 'handoff'/'compact' at ~50% on the 1M-token
    model the way the fixed 200k-tuned thresholds did.
    """
    th = scaled_kb_thresholds(db_path)
    if kb >= th["urgent"]:
        return "urgent", f"~{kb:.0f} KB"
    if kb >= th["handoff"]:
        return "handoff", f"~{kb:.0f} KB"
    if kb >= th["compact"]:
        return "compact", f"~{kb:.0f} KB"
    if kb >= th["warn"]:
        return "warn", f"~{kb:.0f} KB"
    return "ok", f"~{kb:.0f} KB"


def projects_dir_for_cwd(cwd: Path) -> Path:
    """Return ~/.claude/projects/<slug> for the given cwd."""
    override = os.environ.get("CLAUDE_PROJECTS_DIR")
    if override:
        return Path(override)
    s = str(cwd).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        slug = s[0].upper() + "-" + s[2:]
    else:
        slug = s
    cleaned = ""
    for ch in slug:
        if ch.isascii() and (ch.isalnum() or ch in "-_."):
            cleaned += ch
        elif ch in ":\\/  ":
            cleaned += "-"
        else:
            cleaned += f"-u{ord(ch):04x}-"
    slug = cleaned[:200]
    return Path.home() / ".claude" / "projects" / slug


def kb_baseline(projects: Path, session_id: str | None) -> float:
    """Read the post-compact KB baseline (JSONL size recorded at the last /compact).

    The session JSONL is append-only and survives /compact, so its raw size reflects
    the entire session history, not the live context window. Subtracting this baseline
    makes the KB fallback measure growth *since the last compact*.
    """
    try:
        base = sentinel(projects, session_id, "kb-baseline")
        if base.exists():
            return float(base.read_text(encoding="utf-8").strip())
    except Exception:
        pass
    return 0.0


def session_kb(projects: Path, session_id: str | None) -> float:
    """Get current session context KB: JSONL size minus the post-compact baseline."""
    try:
        if session_id:
            p = projects / f"{session_id}.jsonl"
            raw = p.stat().st_size / 1024 if p.exists() else 0.0
        else:
            if not projects.exists():
                return 0.0
            files = list(projects.glob("*.jsonl"))
            if not files:
                return 0.0
            current = max(files, key=lambda f: f.stat().st_mtime)
            if time.time() - current.stat().st_mtime > 3600:
                return 0.0
            raw = current.stat().st_size / 1024
        return max(0.0, raw - kb_baseline(projects, session_id))
    except Exception:
        return 0.0


def sentinel(projects: Path, session_id: str | None, label: str) -> Path:
    """Get sentinel file path for given label."""
    return projects / f".{label}-sentinel-{session_id or 'unknown'}"


def milestone_boost() -> int:
    """Get milestone boost value if milestone is active."""
    try:
        return MILESTONE_BOOST if (paths.state_dir() / "milestone-active.txt").exists() else 0
    except Exception:
        return 0


def handle_urgent_reminder(projects: Path, session_id: str | None, label: str) -> None:
    """Strong chat reminder when context is urgent — does NOT block the prompt.

    Fires once per session (gated by the urgent-msg sentinel, cleared on /compact) so it
    does not repeat every turn. Blocking was removed: a stale measurement must never be
    able to hard-stop the operator's prompt.
    """
    msg_sentinel = sentinel(projects, session_id, "urgent-msg")
    if msg_sentinel.exists():
        return
    try:
        msg_sentinel.parent.mkdir(parents=True, exist_ok=True)
        msg_sentinel.write_text(label)
    except Exception:
        pass
    print(f"\n[dream-studio] Context at {label} — urgent; run /compact now.\n", flush=True)


def _write_handoff_packet_to_db(
    session_id: str | None, cwd: Path, handoff_path: Path | None = None
) -> int | None:
    """Insert a handoff packet into raw_handoffs and write a thin pending-handoff.json pointer.

    If handoff_path is provided (the markdown file written by write_handoff), its content
    is stored in files.db (category='handoff') and the returned file_id is recorded in
    raw_handoffs so the two stores are linked.

    Returns the handoff_id on success, None on failure. Never raises.
    """
    try:
        import hashlib
        import subprocess as _sp
        import time as _time

        from core.event_store.studio_db import insert_handoff
        from core.files.store import write_file
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        ctx = resolve_project_from_cwd()
        project_id = ctx.project_id if ctx is not None else "unknown"
        sid = session_id or "unknown"

        branch = ""
        try:
            result = _sp.run(
                ["git", "branch", "--show-current"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = result.stdout.strip()
        except Exception:
            pass

        # Store markdown content blob in files.db and capture the file_id pointer
        file_id: str | None = None
        checksum: str | None = None
        if handoff_path is not None and handoff_path.exists():
            try:
                content_bytes = handoff_path.read_bytes()
                checksum = hashlib.sha256(content_bytes).hexdigest()
                file_id = write_file(
                    name=f"handoff-{sid}",
                    content=content_bytes,
                    content_type="text/markdown",
                    category="handoff",
                    project_id=project_id,
                    correlation_id=sid,
                )
            except Exception:
                pass

        handoff_id = insert_handoff(
            sid,
            project_id,
            "context threshold handoff",
            branch=branch or None,
            next_action="invoke ds-project:resume to rehydrate work order context",
            file_id=file_id,
            checksum=checksum,
        )
        if handoff_id is None:
            return None

        state_dir = paths.state_dir()
        pending = state_dir / "pending-handoff.json"
        pending.write_text(
            __import__("json").dumps(
                {
                    "handoff_id": handoff_id,
                    "session_id": sid,
                    "triggered_at": _time.time(),
                    "status": "pending",
                    "cwd": str(cwd),
                }
            ),
            encoding="utf-8",
        )
        return handoff_id
    except Exception:
        return None


def handle_handoff(
    projects: Path, session_id: str | None, cwd: Path, label: str, kb_val: float, using_pct: bool
) -> None:
    """Write handoff to authority DB and markdown docs."""
    handoff_sentinel = sentinel(projects, session_id, "handoff")
    if not handoff_sentinel.exists():
        try:
            handoff_sentinel.parent.mkdir(parents=True, exist_ok=True)
            handoff_sentinel.write_text(label)
        except Exception:
            pass
        handoff_path = write_handoff(cwd, kb_val, session_id, is_pct=using_pct)
        _write_handoff_packet_to_db(session_id, cwd, handoff_path=handoff_path)
        write_recap(cwd, kb_val, session_id, handoff_path)
        draft_handoff_lesson(kb_val, git_context(cwd), session_id, is_pct=using_pct)
    else:
        print(
            f"\n[dream-studio] Context at {label} — handoff already sent. Run /compact.\n",
            flush=True,
        )


def handle_compact_warning(projects: Path, session_id: str | None, label: str) -> None:
    """Print compact recommendation once per session."""
    msg_sentinel = sentinel(projects, session_id, "compact-msg")
    if not msg_sentinel.exists():
        try:
            msg_sentinel.parent.mkdir(parents=True, exist_ok=True)
            msg_sentinel.write_text(label)
        except Exception:
            pass
        print(f"\n[dream-studio] Context at {label} — run /compact soon.\n", flush=True)


def handle_warn(
    projects: Path, session_id: str | None, label: str, bridge_pct: float | None
) -> None:
    """Print warning message based on context growth."""
    warn_sentinel = sentinel(projects, session_id, "warn-pct")
    try:
        last = float(warn_sentinel.read_text(encoding="utf-8")) if warn_sentinel.exists() else -1.0
    except Exception:
        last = -1.0

    if bridge_pct is not None:
        current_floor = float((int(bridge_pct) // 5) * 5)
        should_fire = current_floor > last
        save_val = str(current_floor)
    else:
        should_fire = last < 0.0
        save_val = "0"

    if should_fire:
        try:
            warn_sentinel.parent.mkdir(parents=True, exist_ok=True)
            warn_sentinel.write_text(save_val, encoding="utf-8")
        except Exception:
            pass
        print(f"\n[dream-studio] Context at {label} — growing.\n", flush=True)
