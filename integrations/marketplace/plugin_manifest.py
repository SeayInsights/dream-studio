"""Claude plugin manifest generator (Phase 20, WO-P20-MARKETPLACE).

Wraps Dream Studio as a Claude plugin for the marketplace discovery channel. The
manifest + layout are GENERATED from the same canonical packs.yaml as the direct
install, so the two distribution channels stay at parity (modulo namespacing).

Plugin namespace: ``dream-studio``. Every skill is reachable both bare
(``ds-core:build``) and namespaced (``dream-studio:ds-core:build``) — see
core.skills.invocation._strip_plugin_namespace.
"""

from __future__ import annotations

import json
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent
_PACKS_YAML = _REPO_ROOT / "packs.yaml"
_PLUGIN_MANIFEST = _REPO_ROOT / ".claude-plugin" / "plugin.json"

PLUGIN_NAME = "dream-studio"
#: Component directories a Claude plugin may provide.
PLUGIN_COMPONENTS: tuple[str, ...] = ("commands", "agents", "skills", ".mcp.json")


def _version() -> str:
    vf = _REPO_ROOT / "VERSION"
    try:
        return vf.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _load_packs(packs_yaml_path: Path) -> dict:
    import yaml

    try:
        return yaml.safe_load(packs_yaml_path.read_text(encoding="utf-8")) or {}
    except (OSError, Exception):
        return {}


def skill_ids(packs_yaml_path: Path | None = None) -> list[str]:
    """Bare skill ids (``ds-core``, …) for every pack, sorted and de-duplicated."""
    data = _load_packs(packs_yaml_path or _PACKS_YAML)
    ids: set[str] = set()
    for key, cfg in (data.get("packs") or {}).items():
        if not isinstance(cfg, dict):
            continue
        sid = cfg.get("skill", key)
        if not sid.startswith("ds-"):
            sid = f"ds-{sid}"
        ids.add(sid)
    return sorted(ids)


def namespaced_skill_ids(packs_yaml_path: Path | None = None) -> list[str]:
    """Plugin-namespaced skill ids (``dream-studio:ds-core``, …)."""
    return [f"{PLUGIN_NAME}:{sid}" for sid in skill_ids(packs_yaml_path)]


def build_plugin_manifest(packs_yaml_path: Path | None = None) -> dict:
    """Return the `.claude-plugin/plugin.json` manifest dict (deterministic)."""
    return {
        "name": PLUGIN_NAME,
        "version": _version(),
        "description": (
            "Dream Studio — local-first AI orchestration and operational " "intelligence platform."
        ),
        "author": {"name": "Dream Studio"},
        "components": list(PLUGIN_COMPONENTS),
        "skills": skill_ids(packs_yaml_path),
        "mcpServers": ".mcp.json",
    }


def validate_manifest(manifest: dict) -> list[str]:
    """Return a list of problems with *manifest*; empty list means valid."""
    problems: list[str] = []
    for field in ("name", "version", "description", "components", "skills"):
        if field not in manifest:
            problems.append(f"missing required field: {field}")
    if manifest.get("name") != PLUGIN_NAME:
        problems.append(f"name must be {PLUGIN_NAME!r}")
    if not manifest.get("skills"):
        problems.append("skills must be non-empty")
    for comp in PLUGIN_COMPONENTS:
        if comp not in (manifest.get("components") or []):
            problems.append(f"components missing {comp}")
    return problems


def write_plugin_manifest(output_path: Path | None = None) -> Path:
    """Generate and write `.claude-plugin/plugin.json`. Returns the path."""
    out = output_path or _PLUGIN_MANIFEST
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_plugin_manifest(), indent=2) + "\n", encoding="utf-8")
    return out
