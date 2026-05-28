"""Batch 8: Real-world verification of Chain 7 (Memory Loop) closure.

Tests the on-context-inject hook against REAL memory_entries data
(1488 reg_gotchas ingested by Batch 7.5).

Does NOT claim "cross-session intelligence proven" — this confirms the
MECHANISM works with real data. True cross-session verification happens
when memory accumulates naturally across future operator sessions.
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import importlib.util
from unittest.mock import patch


def load_hook():
    hook_path = REPO / "runtime" / "hooks" / "meta" / "on-context-inject.py"
    spec = importlib.util.spec_from_file_location("on_context_inject_live", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    errors = []
    live_db = os.path.expanduser("~/.dream-studio/state/studio.db")

    if not os.path.exists(live_db):
        print(f"SKIP: Live DB not found at {live_db}")
        return 0

    import sqlite3
    c = sqlite3.connect(live_db)
    mem_count = c.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
    fts_count = c.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0]
    c.close()

    print(f"INFO: memory_entries={mem_count}, memory_fts={fts_count}")

    if mem_count == 0:
        print("SKIP: memory_entries is empty — run `ds memory ingest-entries` first")
        return 0

    mod = load_hook()

    # Test 1: Hook finds memories for a real gotcha-relevant prompt
    output_lines: list[str] = []
    with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": live_db}):
        with patch("builtins.print", side_effect=lambda *a, **kw: output_lines.append(str(a[0]))):
            mod.main({"prompt": "tabindex keyboard navigation focus order form label"})

    output = "\n".join(output_lines)
    if not output.strip():
        errors.append("FAIL: Hook produced no output for real accessibility prompt")
    elif "<project-memory>" not in output:
        errors.append(f"FAIL: Output missing <project-memory> tag. Got: {output[:200]!r}")
    else:
        print(f"PASS: Hook surfaces real memory data")
        print(f"      Output: {output[:200].strip()!r}")

    # Test 2: Output has no nested JSON or tool-call-shaped content
    import json
    if output.strip():
        try:
            json.loads(output)
            errors.append("FAIL: Output is valid JSON (should be plain text)")
        except json.JSONDecodeError:
            print("PASS: Output is plain text (not JSON)")

    # Test 3: Output contains importance label and content preview
    if output.strip():
        has_label = "[high]" in output or "[medium]" in output or "[low]" in output
        if not has_label:
            errors.append("FAIL: Output missing importance label [high/medium/low]")
        else:
            print("PASS: Output contains importance labels")

    # Test 4: Hook handles an unrelated prompt gracefully (may or may not match)
    unrelated_lines: list[str] = []
    with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": live_db}):
        with patch("builtins.print", side_effect=lambda *a, **kw: unrelated_lines.append(str(a[0]))):
            mod.main({"prompt": "XYZABCQWERTY123 completely_nonsense_prompt_no_match"})
    # Either empty output (no match) or output (some match) — both are valid
    print(f"INFO: Nonsense prompt result: {'no output (expected)' if not unrelated_lines else 'produced output'}")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"\nBatch 8 PASSED — Chain 7 mechanism verified with real data")
    print(f"  memory_entries: {mem_count} rows (reg_gotchas from Batch 7.5)")
    print(f"  memory_fts: {fts_count} rows (backfilled)")
    print(f"  NOTE: This confirms mechanism with real source data.")
    print(f"  Cross-session intelligence will accumulate naturally over future sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
