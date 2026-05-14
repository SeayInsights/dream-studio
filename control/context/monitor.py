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
    COMPACT_KB,
    COMPACT_PCT,
    HANDOFF_KB,
    HANDOFF_PCT,
    URGENT_KB,
    URGENT_PCT,
    WARN_KB,
    WARN_PCT,
    draft_handoff_lesson,
    git_context,
    write_handoff,
    write_recap,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import paths  # noqa: E402

MILESTONE_BOOST = 10
COMPACT_COOLDOWN_TURNS = 2


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


def kb_to_band(kb: float) -> tuple[str, str]:
    """Fallback: map JSONL KB to a threshold band."""
    if kb >= URGENT_KB:
        return "urgent", f"~{kb:.0f} KB"
    if kb >= HANDOFF_KB:
        return "handoff", f"~{kb:.0f} KB"
    if kb >= COMPACT_KB:
        return "compact", f"~{kb:.0f} KB"
    if kb >= WARN_KB:
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


def session_kb(projects: Path, session_id: str | None) -> float:
    """Get current session KB from JSONL file size."""
    try:
        if session_id:
            p = projects / f"{session_id}.jsonl"
            return p.stat().st_size / 1024 if p.exists() else 0.0
        if not projects.exists():
            return 0.0
        files = list(projects.glob("*.jsonl"))
        if not files:
            return 0.0
        current = max(files, key=lambda f: f.stat().st_mtime)
        if time.time() - current.stat().st_mtime > 3600:
            return 0.0
        return current.stat().st_size / 1024
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


def handle_compact_cooldown(projects: Path, session_id: str | None, is_compact_cmd: bool) -> bool:
    """Manage post-/compact suppression. Returns True if this turn should be suppressed."""
    cd_sentinel = sentinel(projects, session_id, "compact-cooldown")
    if is_compact_cmd:
        try:
            cd_sentinel.parent.mkdir(parents=True, exist_ok=True)
            cd_sentinel.write_text(str(COMPACT_COOLDOWN_TURNS))
            sentinel(projects, session_id, "compact-msg").unlink(missing_ok=True)
            sentinel(projects, session_id, "warn-pct").unlink(missing_ok=True)
            bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id or 'unknown'}.json"
            bp.write_text(
                json.dumps(
                    {
                        "session_id": session_id or "",
                        "used_pct": 0.0,
                        "raw_pct": 0.0,
                        "remaining_percentage": 100.0,
                        "timestamp": int(time.time()),
                        "post_compact": True,
                    }
                )
            )
        except Exception:
            pass
        return True
    if cd_sentinel.exists():
        try:
            count = int(cd_sentinel.read_text(encoding="utf-8").strip())
            if count > 1:
                cd_sentinel.write_text(str(count - 1))
            else:
                cd_sentinel.unlink(missing_ok=True)
            return True
        except Exception:
            pass
    return False


def handle_urgent_block(projects: Path, session_id: str | None, label: str) -> None:
    """Block prompt when context is urgent."""
    compact_sentinel = sentinel(projects, session_id, "compact")
    try:
        compact_sentinel.parent.mkdir(parents=True, exist_ok=True)
        compact_sentinel.write_text(label)
    except Exception:
        pass
    msg = f"Context auto-blocked at {label} — run /compact to continue."
    print(json.dumps({"continue": False, "stopReason": msg}), flush=True)


def handle_handoff(
    projects: Path, session_id: str | None, cwd: Path, label: str, kb_val: float, using_pct: bool
) -> None:
    """Write handoff and recap documents."""
    handoff_sentinel = sentinel(projects, session_id, "handoff")
    if not handoff_sentinel.exists():
        try:
            handoff_sentinel.parent.mkdir(parents=True, exist_ok=True)
            handoff_sentinel.write_text(label)
        except Exception:
            pass
        handoff_path = write_handoff(cwd, kb_val, session_id, is_pct=using_pct)
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
