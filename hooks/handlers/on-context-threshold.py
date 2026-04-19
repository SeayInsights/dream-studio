#!/usr/bin/env python3
"""Hook: on-context-threshold — warn, auto-handoff, or block when context fills.

Trigger: UserPromptSubmit.
Reads the statusline bridge file (written by statusline-command.sh) for real
context usage percentage. Falls back to JSONL file size as a crude proxy.

Thresholds are in used_percentage (0-100, where ~83% triggers auto-compact):

  WARN_PCT     -> surface a mild warning
  COMPACT_PCT  -> recommend /compact soon
  HANDOFF_PCT  -> write a structured handoff + recap to `.sessions/<date>/`
                  and draft a retrospective lesson
  URGENT_PCT   -> block the prompt with a stopReason asking for /compact;
                  one subsequent prompt passes through (compact sentinel)

Projects live under `~/.claude/projects/<slug>/` where <slug> is the cwd
path with path separators replaced by `-` (plus a drive-letter prefix on
Windows). When `CLAUDE_PROJECTS_DIR` is set the hook uses that instead —
useful for tests and unusual platforms.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402
from lib.context_handoff import (  # noqa: E402
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
    """Return `~/.claude/projects/<slug>` for the given cwd.

    Claude Code slug format: drive letter + path with `:`, `\\`, `/`, and
    spaces all replaced by `-`. E.g., `C:\\Users\\Jane Doe\\studio` →
    `C--Users-Jane-Doe-studio`. The space replacement matters on every
    Windows user profile that has a space in its name (and any other path
    containing spaces), or the hook silently fails to find the session JSONL.
    """
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
    return projects / f".{label}-sentinel-{session_id or 'unknown'}"


def main() -> None:
    session_id = None
    payload_cwd = None
    try:
        payload = json.loads(sys.stdin.read())
        session_id = payload.get("session_id")
        payload_cwd = payload.get("cwd")
    except Exception:
        pass

    cwd = Path(payload_cwd) if payload_cwd else paths.project_root()
    projects = projects_dir_for_cwd(cwd)

    bridge_pct = read_bridge_pct(session_id)
    if bridge_pct is not None:
        band, label = pct_to_band(bridge_pct)
    else:
        kb = session_kb(projects, session_id)
        if kb <= 0:
            return
        band, label = kb_to_band(kb)

    if band == "ok":
        return

    compact_sentinel = sentinel(projects, session_id, "compact")
    handoff_sentinel = sentinel(projects, session_id, "handoff")

    if compact_sentinel.exists():
        compact_sentinel.unlink(missing_ok=True)
        return

    if band == "urgent":
        try:
            compact_sentinel.parent.mkdir(parents=True, exist_ok=True)
            compact_sentinel.write_text(label)
        except Exception:
            pass
        msg = f"Context auto-blocked at {label} — run /compact to continue."
        print(json.dumps({"continue": False, "stopReason": msg}), flush=True)
        return

    if band == "handoff":
        if not handoff_sentinel.exists():
            try:
                handoff_sentinel.parent.mkdir(parents=True, exist_ok=True)
                handoff_sentinel.write_text(label)
            except Exception:
                pass
            using_pct = bridge_pct is not None
            kb_val = bridge_pct if using_pct else session_kb(projects, session_id)
            handoff_path = write_handoff(cwd, kb_val, session_id, is_pct=using_pct)
            write_recap(cwd, kb_val, session_id, handoff_path)
            draft_handoff_lesson(kb_val, git_context(cwd), session_id, is_pct=using_pct)
        else:
            print(
                f"\n[dream-studio] Context at {label} — handoff already sent. Run /compact.\n",
                flush=True,
            )
        return

    if band == "compact":
        print(f"\n[dream-studio] Context at {label} — run /compact soon.\n", flush=True)
        return

    if band == "warn":
        print(f"\n[dream-studio] Context at {label} — growing.\n", flush=True)


if __name__ == "__main__":
    main()
