"""Path Resolution for Dream-Studio — DEPRECATED.

DEPRECATED: Import from core.config.paths directly.
This wrapper exists only for backward compatibility and will be
removed in a future release. All methods delegate to core.config.paths.
"""

import warnings as _warnings

_warnings.warn(
    "shared.paths is deprecated — import from core.config.paths directly",
    DeprecationWarning,
    stacklevel=2,
)

from pathlib import Path
from typing import Optional
import uuid

from core.config import paths as _canonical


class PathResolver:
    """Resolves paths for projects, planning, sessions, and temp workspace.

    Delegates to core.config.paths — the single source of truth.
    """

    def __init__(self, config=None):
        self._config = config

    def get_planning_path(self, project_name: str) -> Path:
        return _canonical.project_planning_dir(project_name)

    def get_planning_specs_path(self, project_name: str) -> Path:
        path = self.get_planning_path(project_name) / "specs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_sessions_path(self, project_name: str) -> Path:
        return _canonical.project_sessions_dir(project_name)

    def get_project_path(self, project_name: str) -> Optional[Path]:
        return _canonical.resolve_project_path(project_name)

    def get_temp_clone_path(self, repo_id: Optional[str] = None) -> Path:
        if repo_id is None:
            repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        path = _canonical.temp_dir() / "clones" / repo_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_temp_artifacts_path(self) -> Path:
        path = _canonical.temp_dir() / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_cache_path(self, cache_type: str) -> Path:
        path = _canonical.cache_dir() / cache_type
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_reports_path(self, project_name: str, skill_name: Optional[str] = None) -> Path:
        return _canonical.project_reports_dir(project_name, skill_name)

    def get_artifacts_path(self, project_name: str) -> Path:
        return _canonical.project_artifacts_dir(project_name)

    def get_meta_audit_path(self) -> Path:
        return _canonical.audit_dir()

    def is_external_repo(self, path: Path) -> bool:
        try:
            path.relative_to(_canonical.temp_dir())
            return True
        except ValueError:
            return False

    def is_project_root(self, path: Path) -> bool:
        for root in _canonical.get_project_roots():
            try:
                path.relative_to(root)
                if path.parent == root:
                    return True
            except ValueError:
                continue
        return False


_resolver_instance: Optional[PathResolver] = None


def get_resolver() -> PathResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = PathResolver()
    return _resolver_instance
