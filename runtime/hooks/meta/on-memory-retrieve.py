#!/usr/bin/env python3
"""Hook: on-memory-retrieve — inject relevant memories into context."""

import json, sys
from pathlib import Path
from core.config import paths
from core.telemetry.debug import debug
from control.research.memory import MemorySearch


def main(payload: dict) -> None:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return
    try:
        mem_dir = paths.memory_dir()
        if not mem_dir.exists():
            return
        results = MemorySearch(mem_dir).refresh_if_stale().search(prompt, top_k=5)
        debug("on-memory-retrieve", f"Found {len(results)} results")
    except Exception as e:
        debug("on-memory-retrieve", f"Search failed: {e}")
        return
    if not results:
        return
    try:
        paths.state_dir().joinpath("memory-last-score.json").write_text(
            json.dumps({"top_score": results[0]["score"]}), encoding="utf-8"
        )
    except Exception:
        pass
    lines = ["<relevant-context>"]
    for r in results:
        lines.extend([f'  <memory path="{r["path"]}">', f"    {r['snippet']}", "  </memory>"])
    lines.append("</relevant-context>")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    try:
        data = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
        main(data)
    except Exception:
        pass
