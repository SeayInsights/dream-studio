"""Shared reviewed-no-change context for the release-gate CLIs.

Both ``contract_docs_drift_gate.py`` and ``contract_atlas_lifecycle_gate.py`` map
a change set to contract-domain doc obligations via ``change_impact_report``, and
both must honor the same evidence-backed reviewed-no-change escape in the
blocking pre-push/CI lane — which invokes them with no ``--docs-reviewed-no-change``
flag. Centralizing the gathering here keeps the two gates from diverging:
WO-DOCS-DRIFT-REVIEWED-ESCAPE fixed exactly such a divergence, where the drift
gate honored the escape but the lifecycle gate did not, so a green pre-push push
still failed CI's lifecycle step.

A behavior change still requires a real doc refresh; ``change_impact_report``
applies a declaration only to *impacted* domains, so naming a non-impacted or
unknown domain never rescues a different impacted-but-undeclared domain.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def split_ids(raw: str) -> list[str]:
    """Split a comma/semicolon/newline-separated id list into trimmed tokens."""
    normalized = raw.replace(";", "\n").replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def reviewed_no_change_domains(
    *,
    cli_domains: list[str] | None,
    repo_root: Path,
    base_ref: str | None = None,
) -> list[str]:
    """Union the reviewed-no-change domain ids from every evidence source.

    Sources, all honored in the blocking lane:

    - ``cli_domains``: the gate's ``--docs-reviewed-no-change`` flag values.
    - ``DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE`` env var (local convenience).
    - ``Docs-Reviewed-No-Change: <domain_id>`` commit trailers in the diff range
      (primary: travels with the change set through push and CI, reviewable in
      the PR).
    """

    domains: list[str] = list(cli_domains or [])
    env_value = os.environ.get("DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE")
    if env_value:
        domains.extend(split_ids(env_value))
    domains.extend(_trailer_domains(repo_root=repo_root, base_ref=base_ref))
    return sorted({item for item in domains if item})


def _trailer_domains(*, repo_root: Path, base_ref: str | None) -> list[str]:
    base_ref = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    log_range = [f"{base_ref}..HEAD"] if base_ref else ["-1", "HEAD"]
    domains: list[str] = []
    for message in _git_log_messages(repo_root, log_range):
        for line in message.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("docs-reviewed-no-change:"):
                domains.extend(split_ids(stripped.split(":", 1)[1]))
    return domains


def _git_log_messages(repo_root: Path, range_args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%B%x00", *range_args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [chunk for chunk in result.stdout.split("\x00") if chunk.strip()]
