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


def resolve_base_ref(explicit: str | None) -> str | None:
    """CLI flag wins, then DREAM_STUDIO_BASE_REF, then GITHUB_BASE_REF
    (prefixed with origin/) as a last resort. Both gates' own --changed-files
    resolution and this module's own trailer scan must all agree on this same
    precedence -- a third, independently-coded copy of it is exactly how they
    silently disagreed before (a --base-ref flag added to one gate that drove
    its own diff but was never forwarded to the trailer scan)."""
    base_ref = explicit or os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    return base_ref


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


def _trailer_entries(*, repo_root: Path, base_ref: str | None) -> list[tuple[str, str]]:
    """``(commit sha, domain id)`` for every Docs-Reviewed-No-Change trailer in range."""
    base_ref = resolve_base_ref(base_ref)
    log_range = [f"{base_ref}..HEAD"] if base_ref else ["-1", "HEAD"]
    entries: list[tuple[str, str]] = []
    for sha, message in _git_log_entries(repo_root, log_range):
        for line in message.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("docs-reviewed-no-change:"):
                entries.extend((sha, d) for d in split_ids(stripped.split(":", 1)[1]))
    return entries


def _trailer_domains(*, repo_root: Path, base_ref: str | None) -> list[str]:
    return [d for _sha, d in _trailer_entries(repo_root=repo_root, base_ref=base_ref)]


def trailer_commits(
    *, repo_root: Path, base_ref: str | None, domains: list[str] | set[str]
) -> list[str]:
    """Shas of the commits whose trailer names one of ``domains``, oldest first.

    A domain cleared through the CLI flag or the env var has no commit, so it adds none:
    an empty list means "no trailer commit accounts for these", not "unknown".
    """
    wanted = set(domains)
    shas: list[str] = []
    for sha, domain in _trailer_entries(repo_root=repo_root, base_ref=base_ref):
        if domain in wanted and sha not in shas:
            shas.append(sha)
    return list(reversed(shas))


def _git_log_entries(repo_root: Path, range_args: list[str]) -> list[tuple[str, str]]:
    """``(sha, full message)`` per commit in range, newest first."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H%x01%B%x00", *range_args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    entries: list[tuple[str, str]] = []
    for chunk in result.stdout.split("\x00"):
        sha, sep, message = chunk.strip().partition("\x01")
        if sep and message.strip():
            entries.append((sha.strip(), message))
    return entries
