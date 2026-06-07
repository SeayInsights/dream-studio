"""GitHub capability probe — deterministic check used by execute-work-orders workflow.

Returns a CapabilityResult indicating whether the GitHub path (branch → PR → merge)
is available in the current environment.

Reuses the same signals computed by the pulse hook (github_repo config + gh CLI auth).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class CapabilityResult:
    github_usable: bool
    reason: str
    details: dict = field(default_factory=dict)


def is_github_usable() -> CapabilityResult:
    """Check if the GitHub path is available.

    Passes when:
      1. github_repo is configured in Dream Studio config (non-empty string)
      2. gh CLI is authenticated (gh auth status exits 0)

    Returns CapabilityResult.github_usable == False and a plain-English reason
    when either condition fails.  Never raises.
    """
    try:
        from core.state import state

        repo = str(state.read_config().get("github_repo") or "").strip()
    except Exception:
        repo = ""

    if not repo:
        return CapabilityResult(
            github_usable=False,
            reason="github_repo not configured in Dream Studio config",
            details={"github_repo": ""},
        )

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=10,
        )
        gh_authed = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        gh_authed = False

    if not gh_authed:
        return CapabilityResult(
            github_usable=False,
            reason="gh CLI not authenticated (run: gh auth login)",
            details={"github_repo": repo, "gh_authed": False},
        )

    return CapabilityResult(
        github_usable=True,
        reason="GitHub path available",
        details={"github_repo": repo, "gh_authed": True},
    )
