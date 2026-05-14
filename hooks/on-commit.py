#!/usr/bin/env python3
"""Hook: on-commit — guardrail integration for commit-time enforcement.

This hook can be called from git pre-commit hooks to enforce guardrails.
For now, it runs in advisory mode (prints warnings, doesn't block).

Usage:
    py hooks/on-commit.py --event-id=<id>

Exit codes:
    0 = allow (no violations or advisory mode)
    1 = block (violations found, action=block)
    2 = require_approval (violations needing approval)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails.evaluator import evaluate  # noqa: E402
from guardrails.models import GuardrailAction  # noqa: E402


def main() -> int:
    """Evaluate guardrails for current commit.

    Returns:
        Exit code (0=allow, 1=block, 2=require_approval)
    """
    parser = argparse.ArgumentParser(description="Guardrail integration for commits")
    parser.add_argument("--event-id", help="Activity log event ID to evaluate")
    parser.add_argument("--rules-dir", type=Path, help="Custom rules directory")
    parser.add_argument(
        "--mode",
        choices=["advisory", "enforce"],
        default="advisory",
        help="Enforcement mode (default: advisory)",
    )
    args = parser.parse_args()

    print("\n[dream-studio] Running guardrail checks...", flush=True)

    try:
        action = evaluate(event_id=args.event_id, rules_dir=args.rules_dir)
    except Exception as e:
        print(f"\n[dream-studio] ❌ Guardrail evaluation failed: {e}", file=sys.stderr)
        # In advisory mode, don't block on errors
        if args.mode == "advisory":
            print("[dream-studio] Advisory mode: allowing commit despite error\n", file=sys.stderr)
            return 0
        return 1  # Fail closed in enforce mode

    if action == GuardrailAction.ALLOW:
        print("[dream-studio] ✅ All guardrail checks passed\n", flush=True)
        return 0

    # In advisory mode, print violations but don't block
    if args.mode == "advisory":
        print(
            "\n[dream-studio] ℹ️  Advisory mode: violations detected but not blocking", flush=True
        )
        print("[dream-studio] Review the warnings above before committing.\n", flush=True)
        return 0

    # In enforce mode, respect the guardrail action
    exit_codes = {
        GuardrailAction.ALLOW: 0,
        GuardrailAction.BLOCK: 1,
        GuardrailAction.REQUIRE_APPROVAL: 2,
        GuardrailAction.ADVISORY: 0,
    }

    exit_code = exit_codes.get(action, 1)

    if exit_code == 1:
        print("\n[dream-studio] ❌ BLOCKED: Fix violations before committing\n", file=sys.stderr)
    elif exit_code == 2:
        print(
            "\n[dream-studio] ⏸️  APPROVAL REQUIRED: Contact Director before proceeding\n",
            file=sys.stderr,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
