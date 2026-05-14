"""Dream-Studio Configuration Management — DEPRECATED path properties.

Loads config from ~/.dream-studio/config.json. Path properties delegate to
core.config.paths (the canonical path authority) with config.json providing
only user-specific overrides like project_roots.

DEPRECATED: For path resolution, import from core.config.paths directly.
DreamStudioConfig.project_roots management is the only non-delegated feature.
"""

import json
from pathlib import Path
from typing import List, Optional

from core.config import paths as _canonical


class DreamStudioConfig:
    """Manages dream-studio configuration from config.json.

    Config structure (portable — no absolute paths except project_roots):
    {
        "version": "1.0",
        "project_roots": ["~/builds"],
        "auto_cleanup_temp": true,
        "keep_temp_days": 0
    }
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = _canonical.user_data_dir() / "config.json"
        self.config_path = config_path
        self.config = self.load_or_create()

    def load_or_create(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[WARN] Failed to load config: {e}")
                return self._create_default()
        else:
            return self._create_default()

    def _create_default(self) -> dict:
        from datetime import datetime, timezone

        default_config = {
            "version": "1.0",
            "project_roots": [str(Path.home() / "builds")],
            "auto_cleanup_temp": True,
            "keep_temp_days": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "migration_version": 13,
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.save(default_config)
        return default_config

    def save(self, config: Optional[dict] = None):
        if config is not None:
            self.config = config
        self.config_path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    @property
    def project_roots(self) -> List[Path]:
        roots = self.config.get("project_roots", [])
        return [Path(r) for r in roots]

    @property
    def temp_workspace(self) -> Path:
        return _canonical.temp_dir()

    @property
    def planning_root(self) -> Path:
        return _canonical.projects_dir()

    @property
    def sessions_root(self) -> Path:
        return _canonical.projects_dir()

    @property
    def cache_root(self) -> Path:
        return _canonical.cache_dir()

    @property
    def auto_cleanup_temp(self) -> bool:
        return self.config.get("auto_cleanup_temp", True)

    @property
    def keep_temp_days(self) -> int:
        return self.config.get("keep_temp_days", 0)

    def add_project_root(self, root: Path):
        root_str = str(root)
        if root_str not in self.config.get("project_roots", []):
            self.config.setdefault("project_roots", []).append(root_str)
            self.save()

    def remove_project_root(self, root: Path):
        root_str = str(root)
        roots = self.config.get("project_roots", [])
        if root_str in roots:
            roots.remove(root_str)
            self.save()


_config_instance: Optional[DreamStudioConfig] = None


def get_config() -> DreamStudioConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = DreamStudioConfig()
    return _config_instance
