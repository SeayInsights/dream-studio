#!/usr/bin/env python3
"""Hook: on-memory-retrieve — inject relevant memories into prompt context.

Trigger: UserPromptSubmit
Reads the prompt, searches the memory index for top-5 relevant files,
and prints a <relevant-context> XML block to stdout for Claude to consume.
Exits 0 silently on any error — never blocks a prompt.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402
from lib.memory_search import MemorySearch  # noqa: E402

STATE_FILE_NAME = "memory-last-score.json"

# Debug logging controlled via environment variable
DEBUG = os.environ.get("DREAM_STUDIO_DEBUG", "").lower() in ("1", "true")


def _debug(msg: str) -> None:
    """Log debug message to stderr if debug mode is enabled."""
    if DEBUG:
        print(f"[on-memory-retrieve] {msg}", file=sys.stderr, flush=True)


def main(payload: dict) -> None:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _debug("No prompt provided, skipping memory search")
        return

    try:
        mem_dir = paths.memory_dir()
        _debug(f"Memory directory: {mem_dir}")
    except Exception as e:
        _debug(f"Failed to resolve memory directory: {e}")
        return

    if not mem_dir.exists():
        _debug(f"Memory directory does not exist: {mem_dir}")
        return

    try:
        searcher = MemorySearch(mem_dir).refresh_if_stale()
        results = searcher.search(prompt, top_k=5)
        _debug(f"Memory search returned {len(results)} results")
    except Exception as e:
        _debug(f"Memory search failed: {e}")
        return

    if not results:
        _debug("No relevant memories found for this prompt")
        return

    # Persist top score so on-pulse can read it
    try:
        state_path = paths.state_dir() / STATE_FILE_NAME
        state_path.write_text(
            json.dumps({"top_score": results[0]["score"]}), encoding="utf-8"
        )
        _debug(f"Persisted top score: {results[0]['score']}")
    except Exception as e:
        _debug(f"Failed to persist top score: {e}")

    lines = ["<relevant-context>"]
    for r in results:
        lines.append(f'  <memory path="{r["path"]}">')
        lines.append(f"    {r['snippet']}")
        lines.append("  </memory>")
    lines.append("</relevant-context>")
    print("\n".join(lines), flush=True)
    _debug(f"Injected {len(results)} memories into context")


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        main(data)
    except Exception:
        pass
