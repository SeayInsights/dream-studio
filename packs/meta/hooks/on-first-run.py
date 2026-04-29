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
        "\n[dream-studio] Welcome! It looks like this is your first session.\n"
        "To personalise dream-studio, please ask the user the following questions\n"
        "and write the answers to ~/.dream-studio/config.json:\n\n"
        "  1. What is your name? (director_name)\n"
        "  2. What is your primary domain? e.g. Power BI, SaaS, game dev, security (domain)\n"
        "  3. What will you mainly use dream-studio for? (primary_use)\n\n"
        "Example config.json additions:\n"
        '  "director_name": "Dannis",\n'
        '  "domain": "Power BI",\n'
        '  "primary_use": "client reporting and security dashboards"\n\n'
        "Once config.json is updated, this message will not appear again.\n"
        "You can also run `workflow: run studio-onboard` for a full setup walkthrough.\n",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block the session on setup hook failure
