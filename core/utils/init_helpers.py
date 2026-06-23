"""Initialization helpers for first-run hook."""

import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

from core.config import paths

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def hydrate_registry_once() -> None:
    """Run hydrate_registry.py if not already run. Log to first-run.log, never block."""
    sentinel = paths.meta_dir() / ".registry-hydrated"
    if sentinel.exists():
        return

    log_path = paths.meta_dir() / "first-run.log"
    timestamp = datetime.now(UTC).isoformat()

    try:
        # Locate hydrate_registry.py — prefer plugin root
        script_path = paths.plugin_root() / "scripts" / "hydrate_registry.py"
        if not script_path.is_file():
            fallback = Path(__file__).resolve().parents[2] / "scripts" / "hydrate_registry.py"
            if fallback.is_file():
                script_path = fallback
            else:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] SKIP: hydrate_registry.py not found\n")
                return

        # Run hydration
        result = subprocess.run(
            [sys.executable, str(script_path)], capture_output=True, text=True, timeout=30
        )

        # Log result
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"[{timestamp}] Hydrating registry via {script_path}\n  Exit code: {result.returncode}\n"
            )
            if result.stdout:
                f.write(f"  stdout: {result.stdout}\n")
            if result.stderr:
                f.write(f"  stderr: {result.stderr}\n")

        if result.returncode == 0:
            sentinel.write_text(timestamp, encoding="utf-8")

    except subprocess.TimeoutExpired:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] WARN: hydrate_registry.py timed out after 30s\n")
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] WARN: hydrate_registry.py failed: {exc}\n")
