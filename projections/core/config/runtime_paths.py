"""Runtime Filesystem Governance — DEPRECATED.

DEPRECATED: Import from core.config.paths directly.
This wrapper exists only for backward compatibility and will be
removed in a future release. All methods delegate to core.config.paths.
"""

import warnings as _warnings

_warnings.warn(
    "projections.core.config.runtime_paths is deprecated — import from core.config.paths directly",
    DeprecationWarning,
    stacklevel=2,
)

from pathlib import Path
from typing import Optional
from datetime import datetime

from core.config import paths as _canonical


class RuntimePaths:
    """Centralized runtime path management — delegates to core.config.paths."""

    def __init__(self, custom_root: Optional[Path] = None):
        if custom_root:
            self.root = Path(custom_root)
        else:
            self.root = _canonical.user_data_dir()

        self.state_dir = self.root / "state"
        self.logs_dir = self.root / "logs"
        self.cache_dir = self.root / "cache"
        self.meta_dir = self.root / "meta"
        self.projects_dir = self.root / "projects"
        self.audit_dir = self.meta_dir / "audit"
        self.research_cache_dir = self.meta_dir / "research"

        self._ensure_directories()

    def _ensure_directories(self):
        for d in [
            self.state_dir,
            self.logs_dir,
            self.cache_dir,
            self.audit_dir,
            self.research_cache_dir,
            self.projects_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def database_path(self, db_name: str = "studio.db") -> Path:
        return self.state_dir / db_name

    def get_db_path(self) -> str:
        return str(self.database_path())

    def log_file(self, filename: str) -> Path:
        return self.logs_dir / filename

    def timestamped_log(self, prefix: str, extension: str = "log") -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return self.logs_dir / f"{prefix}_{timestamp}.{extension}"

    def cache_file(self, filename: str) -> Path:
        return self.cache_dir / filename

    def research_cache_file(self, topic: str) -> Path:
        safe_topic = "".join(c for c in topic if c.isalnum() or c in (" ", "-", "_")).strip()
        safe_topic = safe_topic.replace(" ", "_").lower()
        return self.research_cache_dir / f"{safe_topic}.json"

    def audit_report(self, filename: str) -> Path:
        return self.audit_dir / filename

    def timestamped_audit_report(self, prefix: str, extension: str = "md") -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d")
        return self.audit_dir / f"{prefix}_{timestamp}.{extension}"

    def project_dir(self, project_name: str) -> Path:
        path = self.projects_dir / project_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def project_planning_dir(self, project_name: str) -> Path:
        path = self.project_dir(project_name) / "planning"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def project_reports_dir(self, project_name: str) -> Path:
        path = self.project_dir(project_name) / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def skill_report_dir(self, project_name: str, skill_name: str) -> Path:
        path = self.project_reports_dir(project_name) / skill_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def is_runtime_path(self, path: Path) -> bool:
        return _canonical.is_runtime_path(path)

    def is_source_path(self, path: Path) -> bool:
        return _canonical.is_repo_path(path)

    def validate_path(self, path: Path, expected_type: str = "runtime") -> bool:
        if expected_type == "runtime":
            if not self.is_runtime_path(path):
                raise ValueError(
                    f"Path {path} should be in runtime directory {self.root}, not source repo"
                )
        elif expected_type == "source":
            if self.is_runtime_path(path):
                raise ValueError(
                    f"Path {path} should be in source repository, not runtime directory {self.root}"
                )
        return True

    def migrate_from_legacy(self, legacy_path: Path) -> Path:
        filename = legacy_path.name
        if filename.endswith(".db"):
            return self.database_path(filename)
        elif filename.endswith(".log"):
            return self.log_file(filename)
        elif filename.endswith(".md") and "audit" in filename.lower():
            return self.audit_report(filename)
        elif filename.endswith(".json") and "cache" in str(legacy_path).lower():
            return self.cache_file(filename)
        return self.cache_file(filename)

    def info(self) -> dict:
        return {
            "root": str(self.root),
            "state_dir": str(self.state_dir),
            "logs_dir": str(self.logs_dir),
            "cache_dir": str(self.cache_dir),
            "audit_dir": str(self.audit_dir),
            "research_cache_dir": str(self.research_cache_dir),
            "projects_dir": str(self.projects_dir),
            "database": str(self.database_path()),
        }

    def __repr__(self) -> str:
        return f"RuntimePaths(root={self.root})"


_runtime_paths: Optional[RuntimePaths] = None


def get_runtime_paths() -> RuntimePaths:
    global _runtime_paths
    if _runtime_paths is None:
        _runtime_paths = RuntimePaths()
    return _runtime_paths


def get_db_path() -> str:
    return get_runtime_paths().get_db_path()


def get_audit_report_path(filename: str) -> Path:
    return get_runtime_paths().audit_report(filename)


def get_log_path(filename: str) -> Path:
    return get_runtime_paths().log_file(filename)
