"""Tool activity tracking logic for on-tool-activity hook."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from core.config import paths
from core.event_store.studio_db import has_sentinel, set_sentinel

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
MAX_AGENTS = 6
NUDGE_TOOLS = {"Edit", "Write"}
MAX_AGE_SECS = 300

TOOL_AGENT_MAP = {
    "mcp__github__": "GitHub Agent",
    "mcp__filesystem__": "Filesystem Agent",
    "mcp__shell__": "Shell Agent",
    "mcp__cloudflare__": "Cloudflare Agent",
    "mcp__basic_memory__": "Memory Agent",
    "Task": "Sub-Agent",
    "Bash": "Shell",
    "Edit": "Code Editor",
    "Write": "File Writer",
    "Read": "File Reader",
    "Glob": "File Search",
    "Grep": "Code Search",
    "WebSearch": "Web Search",
    "WebFetch": "Web Fetch",
}

SECURITY_PATTERNS = {
    "auth",
    "login",
    "logout",
    "signup",
    "register",
    "password",
    "oauth",
    "token",
    "credential",
    "session",
    "payment",
    "checkout",
    "billing",
    "stripe",
    "webhook",
    "secret",
    "api_key",
}


def activity_path() -> Path:
    return paths.state_dir() / "activity.json"


def _sentinel_db_path() -> Path:
    return paths.state_dir() / "studio.db"


def agent_name(tool: str) -> str:
    for prefix, name in TOOL_AGENT_MAP.items():
        if tool.startswith(prefix):
            return name
    return "dream-studio Agent"


def short_task(tool: str, tool_input: dict) -> str:
    if tool in ("Edit", "Write", "Read"):
        p = tool_input.get("file_path", tool_input.get("path", ""))
        if p:
            return f"{tool}: {Path(p).name}"
    if tool == "Bash":
        cmd = tool_input.get("command", "")
        return f"$ {cmd[:60]}" if cmd else "Bash"
    if tool in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        return f"{tool}: {pattern[:50]}" if pattern else tool
    if tool == "Task":
        desc = tool_input.get("description", tool_input.get("prompt", ""))
        return f"Task: {str(desc)[:55]}" if desc else "Spawning sub-agent"
    if tool.startswith("mcp__github__"):
        return tool.replace("mcp__github__", "GitHub: ")
    return tool[:70]


def elapsed(ts: float) -> str:
    secs = int(time.time() - ts)
    if secs < 60:
        return f"{secs}s ago"
    return f"{secs // 60}m ago"


def project_root(file_path: str) -> Path:
    """Walk up from file_path to the nearest .git or pyproject.toml."""
    p = Path(file_path).resolve().parent
    for _ in range(10):
        if (p / ".git").exists() or (p / "pyproject.toml").exists() or (p / "Makefile").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path(file_path).resolve().parent


def maybe_harden_nudge(tool_name: str, tool_input: dict) -> None:
    """Nudge to run /harden if project lacks hardening artifacts."""
    if tool_name not in NUDGE_TOOLS:
        return
    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    if not file_path:
        return
    root = project_root(file_path)
    if (root / "Makefile").exists() or (root / "SECURITY.md").exists():
        return
    slug = str(root).replace("\\", "-").replace("/", "-").replace(":", "-").replace(" ", "-")[:80]
    key = f"harden-nudge-{slug}"
    if has_sentinel(key, db_path=_sentinel_db_path()):
        return
    set_sentinel(key, "harden-nudge", db_path=_sentinel_db_path())
    print(
        "\n[dream-studio] This project hasn't been hardened. Run /harden audit to check.\n",
        flush=True,
    )


def maybe_security_suggest(tool_name: str, tool_input: dict) -> None:
    """Suggest /secure when editing security-sensitive files."""
    if tool_name not in NUDGE_TOOLS:
        return
    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    if not file_path:
        return
    name_lower = Path(file_path).stem.lower()
    parts_lower = {p.lower() for p in Path(file_path).parts}
    matched = SECURITY_PATTERNS & (parts_lower | {name_lower})
    if not matched:
        return
    root = project_root(file_path)
    slug = str(root).replace("\\", "-").replace("/", "-").replace(":", "-")[:80]
    key = f"security-suggest-{slug}"
    if has_sentinel(key, db_path=_sentinel_db_path()):
        return
    set_sentinel(key, "security-suggest", db_path=_sentinel_db_path())
    label = next(iter(matched))
    print(
        f"\n[dream-studio] Security: editing {Path(file_path).name} ({label}) — consider running /secure.\n",
        flush=True,
    )


def update_activity_feed(tool_name: str, tool_input: dict) -> None:
    """Update rolling activity feed with new tool usage."""
    now = time.time()
    target = activity_path()
    lock_path = target.parent / f"{target.name}.lock"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 2.0
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    try:
                        lock_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                time.sleep(0.005)

        try:
            activity: dict = {}
            try:
                if target.exists():
                    activity = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                activity = {}

            agents: list[dict] = [
                a
                for a in activity.get("agents", [])
                if a.get("ts") and now - a["ts"] < MAX_AGE_SECS
            ]

            new_entry = {
                "id": int(now * 1000) & 0x7FFFFFFF,
                "name": agent_name(tool_name),
                "status": "running",
                "task": short_task(tool_name, tool_input),
                "elapsed": "just now",
                "ts": now,
            }

            agents = [new_entry] + agents[: MAX_AGENTS - 1]
            for i, a in enumerate(agents):
                if i == 0:
                    continue
                a["status"] = "idle"
                a["elapsed"] = elapsed(a["ts"])

            activity["agents"] = agents
            activity["timestamp"] = now

            target.write_text(json.dumps(activity, indent=2), encoding="utf-8")
            _emit_hook_tool_activity(tool_name, tool_input)
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        pass


def _emit_hook_tool_activity(tool_name: str, tool_input: dict) -> None:
    try:
        from core.telemetry.emitters import TelemetryContext, emit_hook_tool_activity

        path_value = tool_input.get("file_path", tool_input.get("path", ""))
        root = project_root(path_value) if path_value else None
        context = TelemetryContext(
            project_id=root.name if root else "dream-studio",
            source_refs=(
                "runtime/hooks/meta/on-tool-activity.py",
                "core/telemetry/tool_tracking.py",
            ),
        )
        emit_hook_tool_activity(
            hook_name="on-tool-activity",
            tool_name=tool_name,
            tool_input=tool_input,
            context=context,
        )
    except Exception:
        pass
