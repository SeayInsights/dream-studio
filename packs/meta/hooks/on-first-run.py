#!/usr/bin/env python3
"""Hook: on-first-run — welcome new users and prompt Director profile setup.

Trigger: UserPromptSubmit (fires on every prompt until config has director_name).

Checks whether ~/.dream-studio/config.json contains a `director_name` key.
If absent, prints a setup prompt that Claude sees and responds to — Claude
then asks the user the three questions and writes config.json.

Exits 0 always. Never blocks a session.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import state  # noqa: E402


def main() -> None:
    try:
        cfg = state.read_config()
    except Exception:
        cfg = {}

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
