#!/usr/bin/env python3
"""Hook: on-tool-activity — rolling snapshot of recent tool usage.

Trigger: PostToolUse.
Maintains a short activity feed at `~/.dream-studio/state/activity.json`
with the last MAX_AGENTS entries. Each tool call becomes one entry with a
readable agent name, a concise task description, and an elapsed-time
label; entries older than MAX_AGE_SECS are dropped on each write.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

MAX_AGENTS = 6
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


def activity_path() -> Path:
    return paths.state_dir() / "activity.json"


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


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

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
                a for a in activity.get("agents", [])
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
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
