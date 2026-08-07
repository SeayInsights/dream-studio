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
_MARKETPLACE_MANIFEST = _REPO_ROOT / ".claude-plugin" / "marketplace.json"

PLUGIN_NAME = "dream-studio"
#: Component slots the built plugin artifact actually delivers. ``commands`` is dropped —
#: Dream Studio ships no top-level commands (skills replace them), so declaring it would name
#: an undeliverable payload (WO 90a13043).
PLUGIN_COMPONENTS: tuple[str, ...] = ("agents", "skills", ".mcp.json")
#: The public canonical source a marketplace install resolves the plugin from.
#: For public distribution this must be a hosted repo, never a "local" path.
MARKETPLACE_REPO = "SeayInsights/dream-studio"
MARKETPLACE_GIT_URL = "https://github.com/SeayInsights/dream-studio.git"
#: The plugin artifact is a SYNTHESIZED build (frontmatter-injected skills the canonical
#: sources ship without) assembled under this repo-relative subdir by the release flow
#: (integrations/marketplace/plugin_dist.py). The marketplace resolves it via a git-subdir
#: source so a github install gets a loadable plugin root, not the raw canonical tree.
MARKETPLACE_PLUGIN_SUBDIR = "dist/plugin"
MARKETPLACE_SCHEMA_VERSION = 1


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


def validate_plugin_manifest_component_delivery(manifest: dict, plugin_root: Path) -> list[str]:
    """Return the declared components with no backing payload at *plugin_root*.

    A github/git-subdir marketplace install resolves components relative to the plugin root, so
    every declared component must exist there or the install loads nothing for it. ``skills`` and
    ``agents`` resolve to same-named directories; ``.mcp.json`` (and any other dotted entry) to a
    file of that name.
    """
    problems: list[str] = []
    for component in manifest.get("components", []):
        target = plugin_root / component
        expect_file = component.startswith(".") or component.endswith(".json")
        ok = target.is_file() if expect_file else target.is_dir()
        if not ok:
            problems.append(f"component {component!r} has no payload at the plugin root")
    return problems


def write_plugin_manifest(output_path: Path | None = None) -> Path:
    """Generate and write `.claude-plugin/plugin.json`. Returns the path."""
    out = output_path or _PLUGIN_MANIFEST
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_plugin_manifest(), indent=2) + "\n", encoding="utf-8")
    return out


def build_marketplace_manifest(packs_yaml_path: Path | None = None) -> dict:
    """Return the `.claude-plugin/marketplace.json` manifest dict (deterministic).

    Name + description are drawn from the same source as the plugin manifest so the
    two distribution channels stay at parity. The ``source`` resolves the plugin
    from the public canonical repo (``MARKETPLACE_REPO``) — a marketplace entry for
    public distribution must never point at a ``local`` path.
    """
    plugin = build_plugin_manifest(packs_yaml_path)
    return {
        "schema_version": MARKETPLACE_SCHEMA_VERSION,
        "plugins": [
            {
                "name": plugin["name"],
                "description": plugin["description"],
                # git-subdir: the loadable plugin root is the synthesized artifact under
                # MARKETPLACE_PLUGIN_SUBDIR, not the repo root (the raw canonical tree is
                # frontmatter-less and not a plugin layout). Sparse-cloned on install.
                "source": {
                    "source": "git-subdir",
                    "url": MARKETPLACE_GIT_URL,
                    "path": MARKETPLACE_PLUGIN_SUBDIR,
                },
            }
        ],
    }


def validate_marketplace_manifest(manifest: dict) -> list[str]:
    """Return a list of problems with *manifest*; empty list means valid."""
    problems: list[str] = []
    if manifest.get("schema_version") != MARKETPLACE_SCHEMA_VERSION:
        problems.append(f"schema_version must be {MARKETPLACE_SCHEMA_VERSION}")
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        problems.append("plugins must be a non-empty list")
        return problems
    entry = plugins[0]
    if entry.get("name") != PLUGIN_NAME:
        problems.append(f"plugin name must be {PLUGIN_NAME!r}")
    if not entry.get("description"):
        problems.append("plugin description must be non-empty")
    source = entry.get("source") or {}
    # Public distribution: a hosted git source, never a local path. The synthesized plugin
    # root lives in a subdir, so the source is git-subdir (github/url resolve the repo root,
    # which is not a loadable plugin layout here).
    if source.get("source") == "local" or "repo" in source:
        problems.append("source must be a hosted git-subdir source, not local/repo-root")
    elif source.get("source") != "git-subdir" or not source.get("url") or not source.get("path"):
        problems.append("source must be git-subdir ({'source':'git-subdir','url':...,'path':...})")
    return problems


def write_marketplace_manifest(output_path: Path | None = None) -> Path:
    """Generate and write `.claude-plugin/marketplace.json`. Returns the path."""
    out = output_path or _MARKETPLACE_MANIFEST
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_marketplace_manifest(), indent=2) + "\n", encoding="utf-8")
    return out
