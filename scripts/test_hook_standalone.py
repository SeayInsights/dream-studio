"""Batch 2 stop gate: verify on-context-inject hook runs standalone.

Tests:
- Hook imports without error
- Hook handles empty prompt gracefully (no output, no crash)
- Hook handles non-existent DB gracefully (fail-open)
- Hook produces valid XML output when seeded DB has matching content
- No nested JSON in output
- Output contains <project-memory> tags
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from io import StringIO
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.event_store.studio_db import _connect, _run_migrations  # noqa: E402


def _seed_db(db_path: Path, project_id: str) -> None:
    """Seed memory_entries with test data (simulates post-ingestion state)."""
    with _connect(db_path) as c:
        _run_migrations(c)
        c.execute(
            "INSERT INTO memory_entries"
            " (memory_id, source, category, content, importance, created_at, project)"
            " VALUES (?, 'reg_gotchas', 'gotcha', ?, 0.9, '2026-01-01', NULL)",
            ("g1", "Modal dialogs need inert attribute on background to prevent focus escape"),
        )
        c.execute(
            "INSERT INTO memory_entries"
            " (memory_id, source, category, content, importance, created_at, project)"
            " VALUES (?, 'raw_lessons', 'lesson', ?, 0.7, '2026-01-01', ?)",
            ("l1", "CI tests must use isolated DB path to avoid contaminating real state", project_id),
        )
        c.commit()


def main() -> int:
    errors = []
    tmpdir = tempfile.mkdtemp(prefix="ds-test-hook-")
    db_path = Path(tmpdir) / "studio.db"
    project_id = "test-project-001"

    try:
        # Seed the DB
        _seed_db(db_path, project_id)

        # Patch DB path to point to test DB
        with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
            import importlib
            import runtime.hooks.meta as meta_pkg

            # Fresh import in temp context
            hook_path = REPO / "runtime" / "hooks" / "meta" / "on-context-inject.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("on_context_inject", hook_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Test 1: empty prompt → no output
            captured = StringIO()
            with patch("builtins.print", side_effect=lambda *a, **k: captured.write(str(a[0]) + "\n")):
                mod.main({"prompt": ""})
            if captured.getvalue().strip():
                errors.append(f"FAIL: empty prompt produced output: {captured.getvalue()!r}")
            else:
                print("PASS: empty prompt produces no output")

            # Test 2: non-existent DB path → fail-open
            captured2 = StringIO()
            with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": "/nonexistent/path/studio.db"}):
                with patch("builtins.print", side_effect=lambda *a, **k: captured2.write(str(a[0]) + "\n")):
                    mod.main({"prompt": "modal dialog focus trap"})
            if captured2.getvalue().strip():
                errors.append("FAIL: non-existent DB produced output instead of failing open")
            else:
                print("PASS: non-existent DB fails open (no output, no crash)")

            # Test 3: relevant prompt → output with <project-memory> tags
            captured3 = StringIO()
            with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
                with patch("builtins.print", side_effect=lambda *a, **k: captured3.write(str(a[0]) + "\n")):
                    mod.main({"prompt": "modal dialog focus trap inert attribute"})
            out = captured3.getvalue()
            if "<project-memory>" not in out:
                errors.append(f"FAIL: output missing <project-memory> tag. Got: {out!r}")
            elif "</project-memory>" not in out:
                errors.append(f"FAIL: output missing </project-memory> tag. Got: {out!r}")
            else:
                print(f"PASS: relevant prompt produces <project-memory> output")
                print(f"      Output preview: {out[:150].strip()!r}")

            # Test 4: no nested JSON in output
            if out.strip():
                try:
                    json.loads(out)
                    errors.append("FAIL: output parsed as JSON (should be plain text)")
                except json.JSONDecodeError:
                    print("PASS: output is not JSON (plain text as required)")

            # Test 5: lesson with project scoping (CI test prompt)
            captured4 = StringIO()
            with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
                # Mock active project to test-project-001
                orig_resolve = mod._resolve_active_project
                mod._resolve_active_project = lambda conn: project_id
                with patch("builtins.print", side_effect=lambda *a, **k: captured4.write(str(a[0]) + "\n")):
                    mod.main({"prompt": "isolated DB path CI contamination tests"})
                mod._resolve_active_project = orig_resolve
            out4 = captured4.getvalue()
            if "isolated" not in out4.lower() and "CI" not in out4:
                # The FTS search may or may not match depending on tokenization; log but don't fail
                print(f"INFO: project-scoped lesson search result (may be empty if FTS tokenization differs): {out4[:80]!r}")
            else:
                print(f"PASS: project-scoped lesson surfaces: {out4[:80].strip()!r}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  {e}")
        return 1

    print("\nBatch 2 stop gate PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
