#!/usr/bin/env python3
"""Hook: on-skill-complete — advisory chain-suggest after skill invocation.

Trigger: PostToolUse on Skill tool (after on-skill-metrics).

Reads the completed skill's SKILL.md frontmatter for chain_suggests entries,
evaluates conditions against session state, and prints a suggestion line.
Never auto-invokes — advisory only.

Logs suggestions to ~/.dream-studio/state/chain-suggestions.jsonl.
Exits 0 always — suggestion failure must never block skill execution.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

# ---------------------------------------------------------------------------
# Pack → directory mapping
# ---------------------------------------------------------------------------

_PACK_SKILL_DIRS: dict[str, str] = {
    "dream-studio:core": "skills/core/modes",
    "dream-studio:quality": "skills/quality/modes",
    "dream-studio:security": "skills/security/modes",
    "dream-studio:career": "skills/career/modes",
    "dream-studio:analyze": "skills/analyze/modes",
    "dream-studio:domains": "skills/domains/modes",
    "dream-studio:setup": "skills/setup/modes",
}

_UI_EXTENSIONS = {".tsx", ".vue", ".svelte", ".astro", ".css", ".scss", ".jsx"}

# ---------------------------------------------------------------------------
# YAML frontmatter parsing (stdlib only)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    return _parse_yaml_subset(m.group(1))


def _parse_yaml_subset(yaml_text: str) -> dict:
    result: dict = {}
    current_key = ""
    current_list: list | None = None

    for line in yaml_text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue

        list_item = re.match(r"^\s+-\s+(.*)", line)
        if list_item and current_list is not None:
            value = list_item.group(1).strip()
            if ":" in value and not value.startswith('"'):
                entry: dict = {}
                for pair in re.finditer(r'(\w+)\s*:\s*"([^"]*)"', line):
                    entry[pair.group(1)] = pair.group(2)
                if not entry:
                    k, v = value.split(":", 1)
                    entry[k.strip()] = v.strip().strip('"').strip("'")
                current_list.append(entry)
            else:
                current_list.append(value.strip('"').strip("'"))
            continue

        kv = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", line)
        if kv:
            if current_list is not None:
                result[current_key] = current_list
                current_list = None

            key = kv.group(1)
            val = kv.group(2).strip()

            if val == "" or val == "[]":
                current_key = key
                current_list = [] if val != "[]" else None
                if val == "[]":
                    result[key] = []
                continue

            result[key] = val.strip('"').strip("'")

    if current_list is not None:
        result[current_key] = current_list

    return result


def _parse_chain_suggests_robust(text: str) -> list[dict]:
    """Fallback: parse chain_suggests from frontmatter using regex directly."""
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return []

    fm = m.group(1)
    cs_match = re.search(r"chain_suggests:\s*\n((?:[ \t]+[^\n]*\n?)*)", fm)
    if not cs_match:
        return []

    entries = []
    for entry_match in re.finditer(
        r'-\s+condition:\s*"([^"]*)"\s*\n\s+next:\s*"([^"]*)"\s*\n\s+prompt:\s*"([^"]*)"',
        cs_match.group(1),
    ):
        entries.append({
            "condition": entry_match.group(1),
            "next": entry_match.group(2),
            "prompt": entry_match.group(3),
        })

    return entries


# ---------------------------------------------------------------------------
# Condition evaluators
# ---------------------------------------------------------------------------

def _read_activity() -> list[dict]:
    activity_path = Path.home() / ".dream-studio" / "state" / "activity.json"
    if not activity_path.exists():
        return []
    try:
        data = json.loads(activity_path.read_text(encoding="utf-8"))
        return data.get("agents", [])
    except Exception:
        return []


def _check_ui_build() -> bool:
    for agent in _read_activity():
        task = agent.get("task", "")
        if not any(task.startswith(prefix) for prefix in ("Edit:", "Write:")):
            continue
        if any(task.endswith(ext) or ext in task for ext in _UI_EXTENSIONS):
            return True
    return False


def _check_findings_found() -> bool:
    cwd = Path.cwd()
    for f in cwd.iterdir():
        if f.is_file() and (
            f.name.startswith("review-") and f.name.endswith("-findings.md")
            or f.name.startswith("audit-") and f.name.endswith(".md")
        ):
            return True
    return False


def _check_critical_findings() -> bool:
    cwd = Path.cwd()
    for f in cwd.iterdir():
        if not f.is_file():
            continue
        if not (
            f.name.startswith("review-") and f.name.endswith("-findings.md")
            or f.name.startswith("audit-") and f.name.endswith(".md")
        ):
            continue
        try:
            text = f.read_text(encoding="utf-8")
            if re.search(r"\b(Critical|High)\b", text, re.IGNORECASE):
                return True
        except Exception:
            continue
    return False


def _check_root_cause_found() -> bool:
    for agent in _read_activity():
        task = agent.get("task", "")
        if "root cause" in task.lower():
            return True
    return False


def _evaluate_condition(condition: str) -> bool:
    if condition == "always":
        return True
    if condition == "ui_build":
        return _check_ui_build()
    if condition == "findings_found":
        return _check_findings_found()
    if condition == "critical_findings":
        return _check_critical_findings()
    if condition == "root_cause_found":
        return _check_root_cause_found()
    if condition == "clean":
        return not _check_findings_found()
    return False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log_suggestion(skill: str, suggested_next: str, condition: str) -> None:
    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "chain-suggestions.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": skill,
        "suggested_next": suggested_next,
        "condition": condition,
        "accepted": None,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# SKILL.md locator
# ---------------------------------------------------------------------------

def _locate_skill_md(skill_full: str, args_text: str) -> Path | None:
    plugin_root = Path(__file__).resolve().parents[3]

    pack_prefix = ""
    mode_name = ""

    if ":" in skill_full:
        pack_prefix = skill_full
        mode_name = args_text.split()[0] if args_text else ""
    else:
        pack_prefix = skill_full
        mode_name = args_text.split()[0] if args_text else ""

    if pack_prefix in _PACK_SKILL_DIRS and mode_name:
        candidate = plugin_root / _PACK_SKILL_DIRS[pack_prefix] / mode_name / "SKILL.md"
        if candidate.exists():
            return candidate

    if pack_prefix in _PACK_SKILL_DIRS and not mode_name:
        modes_dir = plugin_root / _PACK_SKILL_DIRS[pack_prefix]
        if modes_dir.is_dir():
            for d in sorted(modes_dir.iterdir()):
                sk = d / "SKILL.md"
                if sk.exists():
                    return sk

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    skill_name = tool_input.get("skill", "")
    skill_args = tool_input.get("args", "")

    if not skill_name:
        return

    skill_md = _locate_skill_md(skill_name, skill_args)
    if skill_md is None:
        return

    text = skill_md.read_text(encoding="utf-8")

    chain_suggests = _parse_chain_suggests_robust(text)
    if not chain_suggests:
        fm = _parse_frontmatter(text)
        chain_suggests = fm.get("chain_suggests", [])

    if not chain_suggests:
        return

    for entry in chain_suggests:
        condition = entry.get("condition", "")
        next_skill = entry.get("next", "")
        prompt = entry.get("prompt", "")

        if not condition or not next_skill:
            continue

        if _evaluate_condition(condition):
            line = f"→ [{next_skill}] {prompt}\n"
            sys.stdout.buffer.write(line.encode("utf-8"))
            sys.stdout.buffer.flush()
            _log_suggestion(skill_name, next_skill, condition)
            break


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
