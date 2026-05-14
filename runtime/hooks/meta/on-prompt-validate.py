#!/usr/bin/env python3
"""Prompt validation hook - validates user input for security risks."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from guardrails.scanners.rebuff_validator import validate_user_input

    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False


def main() -> None:
    """Validate user prompt for injection attempts and security risks."""
    if not _VALIDATOR_AVAILABLE:
        return
    try:
        payload = json.loads(sys.stdin.read())
        user_prompt = payload.get("prompt", "")
        if not user_prompt or len(user_prompt.strip()) == 0:
            return
        result = validate_user_input(user_prompt, {"source": "user_prompt"})
        risk_score = result.get("risk_score", 0.0)
        is_injection = result.get("is_injection", False)
        if is_injection and risk_score >= 0.8:
            print(f"🚨 CRITICAL: Possible prompt injection detected (risk: {risk_score:.2f})")
            for pattern in result.get("detected_patterns", [])[:3]:
                print(f"   - {pattern.get('description', 'Unknown pattern')}")
            print("   Recommendation:", result.get("recommendation", "Review input"))
        elif is_injection and risk_score >= 0.6:
            print(f"⚠️  WARNING: Suspicious prompt patterns detected (risk: {risk_score:.2f})")
            print("   Recommendation:", result.get("recommendation", "Proceed with caution"))
    except (json.JSONDecodeError, KeyError):
        pass


if __name__ == "__main__":
    main()
