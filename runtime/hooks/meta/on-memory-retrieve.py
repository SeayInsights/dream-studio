#!/usr/bin/env python3
"""Hook: on-memory-retrieve — inject relevant memories into context."""

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

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
