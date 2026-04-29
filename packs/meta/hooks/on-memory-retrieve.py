#!/usr/bin/env python3
"""Hook: on-memory-retrieve — inject relevant memories into prompt context.

Trigger: UserPromptSubmit
Reads the prompt, searches the memory index for top-5 relevant files,
and prints a <relevant-context> XML block to stdout for Claude to consume.
Exits 0 silently on any error — never blocks a prompt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402
from lib.memory_search import MemorySearch  # noqa: E402

STATE_FILE_NAME = "memory-last-score.json"


def main(payload: dict) -> None:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return

    try:
        mem_dir = paths.memory_dir()
    except Exception:
        return

    if not mem_dir.exists():
        return

    try:
        results = MemorySearch(mem_dir).refresh_if_stale().search(prompt, top_k=5)
    except Exception:
        return

    if not results:
        return

    # Persist top score so on-pulse can read it
    try:
        state_path = paths.state_dir() / STATE_FILE_NAME
        state_path.write_text(
            json.dumps({"top_score": results[0]["score"]}), encoding="utf-8"
        )
    except Exception:
        pass

    lines = ["<relevant-context>"]
    for r in results:
        lines.append(f'  <memory path="{r["path"]}">')
        lines.append(f"    {r['snippet']}")
        lines.append("  </memory>")
    lines.append("</relevant-context>")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        main(data)
    except Exception:
        pass
