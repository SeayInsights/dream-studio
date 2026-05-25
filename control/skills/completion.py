"""Skill completion helpers — chain suggestion evaluation and logging."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import paths

# Import event emission bridge for dual-write pattern
try:
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

_bridge_instance = None


def _get_bridge():
    """Lazy init of LegacyBridge for event emission."""
    global _bridge_instance
    if not _BRIDGE_AVAILABLE:
        return None
    if _bridge_instance is None:
        try:
            repo_root = Path(__file__).resolve().parents[2]
            docs_dir = repo_root / "docs" / "canonical"
            if not docs_dir.exists():
                return None

            taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
            schema_path = str(docs_dir / "canonical_event_v1_schema.json")

            if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
                return None

            validator = EventValidator(taxonomy_path, schema_path)
            event_store = EventStore(
                db_path=str(paths.state_dir() / "studio.db"),
                validator=validator,
                emit_validation_failures=True,
            )
            _bridge_instance = LegacyBridge(event_store)
        except Exception:
            return None
    return _bridge_instance


PACK_SKILL_DIRS: dict[str, str] = {
    "ds-core": "canonical/skills/core/modes",
    "ds-quality": "canonical/skills/quality/modes",
    "ds-security": "canonical/skills/security/modes",
    "ds-career": "skills/career/modes",  # career pack still at legacy location pending 18.1.15a migration
    "ds-analyze": "canonical/skills/analyze/modes",
    "ds-domains": "canonical/skills/domains/modes",
    "ds-setup": "canonical/skills/setup/modes",
}

UI_EXTENSIONS = {".tsx", ".vue", ".svelte", ".astro", ".css", ".scss", ".jsx"}


def read_chain_suggests(config_yml: Path) -> list[dict]:
    """Read chain_suggests from a config.yml file."""
    if not config_yml.is_file():
        return []
    try:
        if _yaml is not None:
            data = _yaml.safe_load(config_yml.read_text(encoding="utf-8-sig"))
        else:
            data = parse_config_yml_fallback(config_yml)
        if not isinstance(data, dict):
            return []
        suggests = data.get("chain_suggests", [])
        return suggests if isinstance(suggests, list) else []
    except Exception:
        return []


def parse_config_yml_fallback(config_yml: Path) -> dict:
    """Minimal config.yml parser when PyYAML is unavailable."""
    text = config_yml.read_text(encoding="utf-8-sig")
    result: dict = {}
    current_key = ""
    current_list: list | None = None

    for line in text.splitlines():
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


def read_activity() -> list[dict]:
    """Read recent tool activity."""
    activity_path = Path.home() / ".dream-studio" / "state" / "activity.json"
    if not activity_path.exists():
        return []
    try:
        data = json.loads(activity_path.read_text(encoding="utf-8"))
        return data.get("agents", [])
    except Exception:
        return []


def check_ui_build() -> bool:
    """Check if recent activity includes UI file edits."""
    for agent in read_activity():
        task = agent.get("task", "")
        if not any(task.startswith(prefix) for prefix in ("Edit:", "Write:")):
            continue
        if any(task.endswith(ext) or ext in task for ext in UI_EXTENSIONS):
            return True
    return False


def check_findings_found() -> bool:
    """Check if review/audit findings files exist in cwd."""
    cwd = Path.cwd()
    for f in cwd.iterdir():
        if f.is_file() and (
            f.name.startswith("review-")
            and f.name.endswith("-findings.md")
            or f.name.startswith("audit-")
            and f.name.endswith(".md")
        ):
            return True
    return False


def check_critical_findings() -> bool:
    """Check if findings contain Critical or High severity."""
    cwd = Path.cwd()
    for f in cwd.iterdir():
        if not f.is_file():
            continue
        if not (
            f.name.startswith("review-")
            and f.name.endswith("-findings.md")
            or f.name.startswith("audit-")
            and f.name.endswith(".md")
        ):
            continue
        try:
            text = f.read_text(encoding="utf-8")
            if re.search(r"\b(Critical|High)\b", text, re.IGNORECASE):
                return True
        except Exception:
            continue
    return False


def check_root_cause_found() -> bool:
    """Check if recent activity mentions root cause."""
    for agent in read_activity():
        task = agent.get("task", "")
        if "root cause" in task.lower():
            return True
    return False


def check_debug_iterations_gte(threshold: int) -> bool:
    """Check if debug skill invoked >= threshold times today."""
    usage_path = Path.home() / ".dream-studio" / "state" / "skill-usage.jsonl"
    if not usage_path.exists():
        return False
    count = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        for line in usage_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("skill") != "debug":
                continue
            ts = record.get("ts", "")
            if ts.startswith(today):
                count += 1
    except Exception:
        return False
    return count >= threshold


def evaluate_condition(condition: str) -> bool:
    """Evaluate a chain suggestion condition."""
    if condition == "always":
        return True
    if condition == "ui_build":
        return check_ui_build()
    if condition == "findings_found":
        return check_findings_found()
    if condition == "critical_findings":
        return check_critical_findings()
    if condition == "root_cause_found":
        return check_root_cause_found()
    if condition == "clean":
        return not check_findings_found()
    if condition == "debug_iterations_gte_3":
        return check_debug_iterations_gte(3)
    return False


def log_suggestion(skill: str, suggested_next: str, condition: str) -> None:
    """Log suggestion to chain-suggestions.jsonl."""
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

    # Emit skill completion event (suggestion made indicates completion)
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="skill.execution.completed",
                stream_id=f"skill-{skill}",
                stream_type="skill",
                event_data={
                    "skill_id": skill,
                    "suggested_next": suggested_next,
                    "condition": condition,
                },
            )
    except Exception:
        pass  # Never fail on event emission


def locate_skill_dir(skill_full: str, args_text: str, plugin_root: Path) -> Path | None:
    """Return the mode directory containing config.yml and SKILL.md."""
    pack_prefix = skill_full
    mode_name = args_text.split()[0] if args_text else ""

    if pack_prefix in PACK_SKILL_DIRS and mode_name:
        candidate = plugin_root / PACK_SKILL_DIRS[pack_prefix] / mode_name
        if (candidate / "config.yml").exists() or (candidate / "SKILL.md").exists():
            return candidate

    if pack_prefix in PACK_SKILL_DIRS and not mode_name:
        modes_dir = plugin_root / PACK_SKILL_DIRS[pack_prefix]
        if modes_dir.is_dir():
            for d in sorted(modes_dir.iterdir()):
                if (d / "config.yml").exists() or (d / "SKILL.md").exists():
                    return d

    return None


def parse_skill_payload(raw_stdin: str) -> tuple[str, str]:
    """Parse stdin payload and extract skill name and args."""
    try:
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
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
    return skill_name, skill_args


def process_chain_suggests(skill_name: str, skill_dir: Path) -> None:
    """Process and emit chain suggestions for completed skill."""
    chain_suggests = read_chain_suggests(skill_dir / "config.yml")
    if not chain_suggests:
        return

    for entry in chain_suggests:
        condition = entry.get("condition", "")
        next_skill = entry.get("next", "")
        prompt = entry.get("prompt", "")

        if not condition or not next_skill:
            continue

        if evaluate_condition(condition):
            line = f"→ [{next_skill}] {prompt}\n"
            import sys

            sys.stdout.buffer.write(line.encode("utf-8"))
            sys.stdout.buffer.flush()
            log_suggestion(skill_name, next_skill, condition)
            break
