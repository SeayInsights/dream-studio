#!/usr/bin/env python3
"""Hook: on-first-run — welcome new users and prompt Director profile setup.

Trigger: UserPromptSubmit (fires on every prompt until config has director_name).

Checks whether ~/.dream-studio/config.json contains a `director_name` key.
If absent, prints a setup prompt that Claude sees and responds to — Claude
then asks the user the three questions and writes config.json.

Also hydrates the SQLite registry on first run so gotchas/approaches are
available immediately instead of appearing empty until first use.

Exits 0 always. Never blocks a session.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths, state  # noqa: E402


def _hydrate_registry_once() -> None:
    """Run hydrate_registry.py if not already run. Log to first-run.log, never block."""
    sentinel = paths.meta_dir() / ".registry-hydrated"
    if sentinel.exists():
        return

    log_path = paths.meta_dir() / "first-run.log"
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Locate hydrate_registry.py — prefer plugin root
        script_path = paths.plugin_root() / "scripts" / "hydrate_registry.py"
        if not script_path.is_file():
            # If running from dev checkout, scripts/ is at root
            fallback = Path(__file__).resolve().parents[3] / "scripts" / "hydrate_registry.py"
            if fallback.is_file():
                script_path = fallback
            else:
                # Can't find script — log and skip
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{timestamp}] SKIP: hydrate_registry.py not found at {script_path} "
                        f"or {fallback}\n"
                    )
                return

        # Run hydration
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Log result
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Hydrating registry via {script_path}\n")
            f.write(f"  Exit code: {result.returncode}\n")
            if result.stdout:
                f.write(f"  stdout: {result.stdout}\n")
            if result.stderr:
                f.write(f"  stderr: {result.stderr}\n")

        # Write sentinel if successful (exit code 0)
        if result.returncode == 0:
            sentinel.write_text(timestamp, encoding="utf-8")

    except subprocess.TimeoutExpired:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] WARN: hydrate_registry.py timed out after 30s\n")
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] WARN: hydrate_registry.py failed: {exc}\n")


def main() -> None:
    try:
        cfg = state.read_config()
    except Exception:
        cfg = {}

    # Always attempt registry hydration (idempotent via sentinel)
    _hydrate_registry_once()

    if cfg.get("director_name"):
        return

    print(
        "\n[dream-studio] Welcome! Setup is not complete yet.\n\n"
        "To finish onboarding correctly:\n\n"
        "  1. Close this session\n"
        "  2. Open a NEW Claude Code session\n"
        "  3. Run: workflow: run studio-onboard\n\n"
        "The onboarding workflow will configure your Director profile, projects root,\n"
        "and Claude memory path — then audit your environment for any gaps.\n\n"
        "Why a new session? The onboarding workflow needs fresh context to run correctly.\n"
        "This message will not appear again once setup is complete.\n",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block the session on setup hook failure
