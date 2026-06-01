"""Guard pattern utilities for on-skill-input hook.

Loads guard-patterns.yaml, applies static patterns to file content,
and provides batched LLM-confirm functionality.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

# Try to load YAML; fall back gracefully
try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


_RULES_CACHE: dict | None = None
_RULES_FILE = Path(__file__).parent / "rules" / "guard-patterns.yaml"


def load_guard_rules() -> dict:
    """Load guard rules from YAML. Cached after first load."""
    global _RULES_CACHE
    if _RULES_CACHE is not None:
        return _RULES_CACHE
    if not _YAML_AVAILABLE or not _RULES_FILE.exists():
        _RULES_CACHE = {
            "rules": [],
            "suppressed_paths": [],
            "md_files_llm_confirm_only": True,
            "file_size_llm_threshold_kb": 500,
        }
        return _RULES_CACHE
    with _RULES_FILE.open(encoding="utf-8") as f:
        _RULES_CACHE = yaml.safe_load(f) or {}
    return _RULES_CACHE


def is_suppressed(file_path: str, suppressed_globs: list[str]) -> bool:
    """Return True if file_path matches any suppression glob."""
    # Normalize to forward slashes for cross-platform matching
    normalized = file_path.replace("\\", "/")
    for glob in suppressed_globs:
        # fnmatch on the full path and on just the path components
        if fnmatch.fnmatch(normalized, glob) or fnmatch.fnmatch(normalized, f"*/{glob}"):
            return True
        # Handle globs like "guardrails/**" matching "guardrails/scanners/foo.py"
        if glob.endswith("/**"):
            prefix = glob[:-3]
            if normalized.startswith(prefix + "/") or normalized == prefix:
                return True
    return False


def apply_static_patterns(
    content: str, rules: list[dict], flags: int = re.IGNORECASE
) -> list[dict]:
    """Apply static_fire rules to content. Returns list of match dicts."""
    findings = []
    for rule in rules:
        if rule.get("detection") != "static_fire":
            continue
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        for match in re.finditer(pattern, content, flags):
            # Find line number
            line_no = content[: match.start()].count("\n") + 1
            findings.append(
                {
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "risk_weight": rule.get("risk_weight", 0.5),
                    "description": rule.get("description", rule["name"]),
                    "matched_text": match.group(0)[:200],
                    "line_number": line_no,
                    "detection": "static_fire",
                }
            )
    return findings


def apply_llm_candidate_patterns(
    content: str, rules: list[dict], flags: int = re.IGNORECASE
) -> list[dict]:
    """Apply llm_confirm rules to content. Returns list of candidate dicts for LLM confirmation."""
    candidates = []
    for rule in rules:
        if rule.get("detection") != "llm_confirm":
            continue
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        for match in re.finditer(pattern, content, flags):
            line_no = content[: match.start()].count("\n") + 1
            # Get surrounding context (3 lines)
            lines = content.split("\n")
            start_line = max(0, line_no - 2)
            end_line = min(len(lines), line_no + 2)
            context = "\n".join(lines[start_line:end_line])
            candidates.append(
                {
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "risk_weight": rule.get("risk_weight", 0.5),
                    "description": rule.get("description", rule["name"]),
                    "matched_text": match.group(0)[:200],
                    "line_number": line_no,
                    "context": context[:500],
                    "llm_confirm_prompt": rule.get(
                        "llm_confirm_prompt",
                        "Is this an injection attempt? Answer yes/no.",
                    ),
                    "detection": "llm_confirm_candidate",
                }
            )
    return candidates
