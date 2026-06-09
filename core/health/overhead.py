"""Setup overhead analyzer — advisory checks for heavy MCPs, skill YAML gaps, permission sprawl.

All findings are advisory only. This module never raises or blocks. Called by run_doctor_checks()
and the WO-V first-run wizard (they both consume the shared run_overhead_checks() entry point).

Promoted from interfaces/cli/lint_skills.py (CI-only) to core/health/ (shared health layer):
  - _parse_frontmatter() — minimal key:value frontmatter extractor
  - skill-missing-YAML check — SKILL.md files without frontmatter delimiters
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ── Frontmatter parser (promoted from lint_skills.py) ────────────────────────


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Extract YAML-like frontmatter from a Markdown file.

    Looks for a fenced block: ^--- ... ---^. Returns a flat key:value dict or None
    when no frontmatter block is found. Does not support nested structures or
    multi-line values — intentionally minimal and safe.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"').strip("'")
    return fields


# ── Individual checks ─────────────────────────────────────────────────────────


def _check_mcp_footprint(claude_dir: Path) -> list[dict[str, str]]:
    """Flag MCP server entries that use a Python launch command.

    Python MCP servers can have heavy startup times and large disk footprints.
    This is an advisory signal only — some Python MCPs are fine.
    """
    findings: list[dict[str, str]] = []
    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        return findings

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return findings

    mcps = settings.get("mcpServers", {})
    for name, config in mcps.items():
        cmd = str(config.get("command", ""))
        basename = Path(cmd).name.lower().split(".")[0]
        is_python = basename in ("python", "python3", "py")
        if is_python:
            findings.append(
                {
                    "check": "mcp_heavy_python",
                    "server": name,
                    "command": cmd,
                    "severity": "advisory",
                    "summary": (
                        f"MCP server '{name}' uses Python ({cmd}) — verify disk footprint"
                        " and startup latency."
                    ),
                    "remediation": (
                        "Check the server's installed package size. Consider a lightweight"
                        " wrapper or a pre-compiled alternative if startup is slow."
                    ),
                }
            )

    return findings


def _check_permission_sprawl(claude_dir: Path) -> list[dict[str, str]]:
    """Detect overly broad allow/deny permission rules in settings.json.

    Broad wildcards like "Bash" (allows all shell commands) or ".*" bypass
    intent-level review and should be flagged for tightening.
    """
    findings: list[dict[str, str]] = []
    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        return findings

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return findings

    # Tools whose bare presence as an allow rule is too broad
    _BROAD_TOOLS = frozenset({"Bash", "computer", ".*", "*"})

    permissions = settings.get("permissions", {})
    for rule in permissions.get("allow", []):
        tool = (
            rule
            if isinstance(rule, str)
            else (rule.get("tool", "") if isinstance(rule, dict) else "")
        )
        if tool in _BROAD_TOOLS or (isinstance(tool, str) and tool.endswith("*") and len(tool) < 4):
            findings.append(
                {
                    "check": "permission_sprawl",
                    "list": "allow",
                    "rule": str(rule),
                    "severity": "advisory",
                    "summary": f"Broad allow permission '{tool}' may bypass intent review.",
                    "remediation": "Prefer specific tool names (e.g. 'Bash(git status)') over broad wildcards.",
                }
            )

    return findings


def _check_skills_missing_yaml(source_root: Path) -> list[dict[str, str]]:
    """Find SKILL.md files that lack YAML frontmatter.

    Frontmatter (name, description, pack) is required for skill-sync and routing.
    A missing block means the skill may not be discoverable or correctly routed.
    """
    findings: list[dict[str, str]] = []
    canonical_skills = source_root / "canonical" / "skills"
    if not canonical_skills.exists():
        return findings

    for skill_md in sorted(canonical_skills.rglob("SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _parse_frontmatter(text) is None:
            rel = str(skill_md.relative_to(source_root))
            findings.append(
                {
                    "check": "skill_missing_yaml",
                    "path": rel,
                    "severity": "advisory",
                    "summary": f"{rel} lacks YAML frontmatter.",
                    "remediation": "Add --- frontmatter with name, description, and pack fields.",
                }
            )

    return findings


# ── Public entry point ────────────────────────────────────────────────────────


def run_overhead_checks(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path | None = None,
    claude_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run all setup overhead checks and return advisory findings.

    Advisory only — never raises, never blocks. Callers should treat status='warn'
    as informational and surface findings to the user without gating on them.

    Returns:
        ok           → True (always, even if findings exist)
        status       → "pass" | "warn"
        advisory_only→ True
        findings     → list of finding dicts ({check, severity, summary, remediation, ...})
        finding_count→ len(findings)
    """
    _source_root = Path(source_root)
    _claude_dir = Path(claude_dir) if claude_dir is not None else Path.home() / ".claude"

    try:
        findings: list[dict[str, str]] = []
        findings.extend(_check_mcp_footprint(_claude_dir))
        findings.extend(_check_permission_sprawl(_claude_dir))
        findings.extend(_check_skills_missing_yaml(_source_root))
    except Exception:
        findings = []

    return {
        "ok": True,
        "status": "warn" if findings else "pass",
        "advisory_only": True,
        "findings": findings,
        "finding_count": len(findings),
    }
