#!/usr/bin/env python3
"""Hook: on-memory-retrieve — inject relevant memories into context.

Phase 2 (LLM Guard): filters tainted memory entries before surfacing.
A memory entry is tainted if it was extracted from a repo where CRITICAL
guard findings were logged (source_repo_id + tainted=1 in memory_entries).
Tainted entries are skipped and a guard_event is logged instead.
"""

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

try:
    from guardrails.memory_taint import get_tainted_paths, emit_memory_skip_event

    _TAINT_AVAILABLE = True
except ImportError:
    _TAINT_AVAILABLE = False


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

    # Phase 2: filter tainted memory entries before surfacing
    project_id = payload.get("project_id")
    if _TAINT_AVAILABLE:
        tainted_paths = get_tainted_paths()
        clean_results = []
        for r in results:
            if r["path"] in tainted_paths:
                debug("on-memory-retrieve", f"Skipping tainted entry: {r['path']}")
                print(
                    f"[GUARD] Memory entry skipped (tainted source): {r['path']}",
                    flush=True,
                    file=sys.stderr,
                )
                emit_memory_skip_event(r["path"], project_id)
            else:
                clean_results.append(r)
    else:
        clean_results = results

    if not clean_results:
        return

    try:
        paths.state_dir().joinpath("memory-last-score.json").write_text(
            json.dumps({"top_score": clean_results[0]["score"]}), encoding="utf-8"
        )
    except Exception:
        pass
    lines = ["<relevant-context>"]
    for r in clean_results:
        lines.extend([f'  <memory path="{r["path"]}">', f"    {r['snippet']}", "  </memory>"])
    lines.append("</relevant-context>")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    try:
        data = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
        main(data)
    except Exception:
        pass
