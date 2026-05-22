#!/usr/bin/env python3
"""Prompt validation hook - validates user input for security risks."""

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Maximum age (seconds) before a pending-handoff.json is considered stale
# and discarded. Prevents in_progress files from persisting across sessions.
HANDOFF_STALE_TTL_S = 300

# Window (seconds) during which a "pending" handoff can still be injected.
HANDOFF_INJECTION_WINDOW_S = 60

try:
    from guardrails.scanners.rebuff_validator import validate_user_input

    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False


def _log_stale_handoff_discarded(state_dir: Path, age: float, reason: str) -> None:
    """Write a diagnostic entry when a stale handoff file is discarded."""
    try:
        import os

        diag_dir = Path(os.environ.get("DS_DIAGNOSTICS_DIR", str(state_dir.parent / "diagnostics")))
        diag_dir.mkdir(parents=True, exist_ok=True)
        diag_file = diag_dir / "stale-handoff.jsonl"
        entry = json.dumps(
            {
                "event": "stale_handoff_discarded",
                "reason": reason,
                "age_seconds": round(age, 1),
                "discarded_at": int(time.time()),
            }
        )
        with diag_file.open("a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def _check_pending_handoff(payload: dict) -> bool:
    """
    If a pending handoff was triggered (within the last 60 seconds), inject
    the ds-core:handoff skill instruction before the user's message so the
    current session produces a structured continuation document.

    Returns True if the prompt was modified and written to stdout (caller
    should exit 0 immediately). Returns False if no action was taken.
    """
    state_dir = Path.home() / ".dream-studio" / "state"
    pending = state_dir / "pending-handoff.json"

    if not pending.is_file():
        return False

    try:
        ph = json.loads(pending.read_text(encoding="utf-8"))
        age = time.time() - ph.get("triggered_at", 0)

        # Discard and delete stale files so they don't persist across sessions.
        if age >= HANDOFF_STALE_TTL_S:
            try:
                pending.unlink(missing_ok=True)
            except OSError:
                pass
            _log_stale_handoff_discarded(state_dir, age, "stale_ttl_expired")
            return False

        if age >= HANDOFF_INJECTION_WINDOW_S or ph.get("status") != "pending":
            # Injection window passed or already consumed — clean up in_progress files.
            if ph.get("status") == "in_progress" and age >= HANDOFF_INJECTION_WINDOW_S:
                try:
                    pending.unlink(missing_ok=True)
                except OSError:
                    pass
                _log_stale_handoff_discarded(state_dir, age, "injection_window_expired")
            return False

        ph["status"] = "in_progress"
        pending.write_text(json.dumps(ph), encoding="utf-8")

        handoff_instruction = (
            "SYSTEM: Context threshold reached. "
            "Before responding to the user's message, invoke the handoff skill:\n\n"
            "handoff:\n\n"
            "After the handoff document is complete, write it to "
            "~/.dream-studio/state/handoff-latest.json as:\n"
            '{"content": "<full handoff text>", "written_at": <unix timestamp>}\n\n'
            "Then tell the user: Dream Studio is opening a continuation session "
            "with this handoff."
        )

        original = payload.get("prompt", "")
        payload["prompt"] = handoff_instruction + "\n\n" + original
        sys.stdout.write(json.dumps(payload))
        return True

    except Exception:
        return False


def main() -> None:
    """Validate user prompt for injection attempts and security risks."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return

    if _check_pending_handoff(payload):
        sys.exit(0)

    if not _VALIDATOR_AVAILABLE:
        return

    try:
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
