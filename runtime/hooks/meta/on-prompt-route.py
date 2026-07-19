#!/usr/bin/env python3
"""Hook: on-prompt-route — deterministic ds-* dispatch on an explicit trigger.

Runs under UserPromptSubmit via on-prompt-dispatch.py HANDLERS. Classifies the
prompt against the Dream Studio pack trigger keywords (packs.yaml + each mode's
metadata.yml) and, when a trigger matches, writes a <dream-studio-routing> block
to stdout so the model knows exactly which Skill(skill=..., args=<mode>) to
invoke. This is the "push" half of auto-activation (WO-AUTOACT-B): skill
description frontmatter (WO-AUTOACT-A) lets Claude Code auto-discover skills;
this handler makes an explicit trigger deterministic rather than a matter of the
model choosing to read the AGENTS.md prose table.

Output: a plain-text <dream-studio-routing> block to stdout (added as context).
Fail-open: any error (missing PyYAML, unreadable packs.yaml, etc.) produces empty
output; the handler never blocks the prompt. Escape hatch: DS_ROUTING=0 disables.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(6):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3]


_PLUGIN_ROOT = _get_plugin_root()


def _read_triggers(path: Path) -> list[str]:
    """Return the trigger strings (with trailing colon) from a metadata.yml."""
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    out: list[str] = []
    for item in data.get("triggers", []) or []:
        if isinstance(item, str):
            t = item.strip()
        elif isinstance(item, dict):
            # unquoted "keyword:" parses to {keyword: None}
            keys = list(item.keys())
            t = str(keys[0]).strip() if keys else ""
            if t and not t.endswith(":"):
                t += ":"
        else:
            continue
        if t:
            out.append(t)
    return out


def _load_trigger_map(plugin_root: Path) -> list[tuple[str, str, str]]:
    """Build [(trigger_lower, skill_id, mode)], longest trigger first.

    Longest-first so a specific trigger ('review pr:') wins over a shorter
    prefix of another ('review:'). Derived from the same single source as the
    routing table — packs.yaml modes + mode metadata.yml triggers.
    """
    try:
        import yaml

        data = yaml.safe_load((plugin_root / "packs.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return []

    canonical = plugin_root / "canonical"
    entries: list[tuple[str, str, str]] = []
    for pack_key, cfg in (data.get("packs", {}) or {}).items():
        if not isinstance(cfg, dict):
            continue
        skill_id = cfg.get("skill", pack_key)
        if not skill_id.startswith("ds-"):
            skill_id = f"ds-{skill_id}"
        skill_path = cfg.get("skill_path")
        base = (plugin_root / skill_path) if skill_path else (canonical / "skills" / pack_key)
        modes = cfg.get("modes", []) or []
        if modes:
            for mode in modes:
                for trig in _read_triggers(base / "modes" / mode / "metadata.yml") or [f"{mode}:"]:
                    entries.append((trig.lower(), skill_id, mode))
        else:
            for trig in _read_triggers(base / "metadata.yml"):
                entries.append((trig.lower(), skill_id, ""))

    entries.sort(key=lambda e: len(e[0]), reverse=True)
    return entries


def _match(prompt: str, entries: list[tuple[str, str, str]]) -> tuple[str, str, str] | None:
    low = prompt.lower()
    for trig, skill, mode in entries:
        if trig and trig in low:
            return (trig, skill, mode)
    return None


def main(payload: dict) -> None:
    if os.environ.get("DS_ROUTING") == "0":
        return
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return
    entries = _load_trigger_map(_PLUGIN_ROOT)
    if not entries:
        return
    matched = _match(prompt, entries)
    if not matched:
        return
    trig, skill, mode = matched
    args = f', args="{mode}"' if mode else ""
    print(
        "<dream-studio-routing>\n"
        f"This request matches the Dream Studio trigger '{trig}'. Invoke the matching "
        f'skill before other work: Skill(skill="{skill}"{args}).\n'
        "</dream-studio-routing>",
        flush=True,
    )


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        main(data)
    except Exception:
        pass
