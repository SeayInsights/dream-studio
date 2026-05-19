#!/usr/bin/env python3
"""Hook: on-first-run — welcome new users and prompt Director profile setup."""

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

from core.config import state
from core.utils.init_helpers import hydrate_registry_once


def main() -> None:
    try:
        cfg = state.read_config()
    except Exception:
        cfg = {}

    # Always attempt registry hydration (idempotent via sentinel)
    hydrate_registry_once()

    if cfg.get("director_name"):
        if not cfg.get("onboarding_mode"):
            cfg["onboarding_mode"] = "full"
            state.write_config(cfg)
        return

    print(
        "\n[dream-studio] Welcome! Setup is not complete yet.\n\n"
        "To finish onboarding correctly:\n\n"
        "  1. Close this session\n"
        "  2. Open a NEW Claude Code session\n"
        "  3. Run: workflow: run studio-onboard\n\n"
        "The onboarding workflow will configure your Director profile, projects root,\n"
        "and Claude memory path — then audit your environment for any gaps.\n\n"
        "During onboarding, you'll be asked to choose an onboarding mode:\n"
        "  • progressive — Start with 5 core modes, unlock more as you use them (recommended for new users)\n"
        "  • full        — All 40 modes available immediately (recommended for power users)\n\n"
        "Why a new session? The onboarding workflow needs fresh context to run correctly.\n"
        "This message will not appear again once setup is complete.\n",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
