#!/usr/bin/env python3
"""Prompt validation hook - validates user input for security risks.

Runs first in the UserPromptSubmit hook chain to detect prompt injection
attempts before any other processing occurs.

Integration: Wave 4 (T031) - Security scanning
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add hooks/lib to path
HOOKS_LIB = Path(__file__).resolve().parents[3] / "hooks" / "lib"
sys.path.insert(0, str(HOOKS_LIB))

try:
    from security.rebuff_validator import validate_user_input
    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False


def main() -> None:
    """Validate user prompt for injection attempts and security risks."""
    if not _VALIDATOR_AVAILABLE:
        return  # Silent fail if validator not available

    try:
        payload = json.loads(sys.stdin.read())
        user_prompt = payload.get("prompt", "")

        if not user_prompt or len(user_prompt.strip()) == 0:
            return  # Empty prompt, nothing to validate

        # Validate the input
        result = validate_user_input(user_prompt, {"source": "user_prompt"})

        # High and critical risks get warnings
        risk_score = result.get("risk_score", 0.0)
        is_injection = result.get("is_injection", False)

        if is_injection and risk_score >= 0.8:
            # Critical: Block (would need a way to actually block in the hook system)
            print(f"🚨 CRITICAL: Possible prompt injection detected (risk: {risk_score:.2f})")
            for pattern in result.get("detected_patterns", [])[:3]:
                print(f"   - {pattern.get('description', 'Unknown pattern')}")
            print("   Recommendation:", result.get("recommendation", "Review input"))
        elif is_injection and risk_score >= 0.6:
            # High: Warn
            print(f"⚠️  WARNING: Suspicious prompt patterns detected (risk: {risk_score:.2f})")
            print("   Recommendation:", result.get("recommendation", "Proceed with caution"))
        # Medium and low risks are logged silently

    except (json.JSONDecodeError, KeyError):
        pass  # Invalid payload, skip validation


if __name__ == "__main__":
    main()
