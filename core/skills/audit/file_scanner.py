"""File-scan wrappers that extend build-mode auditors to scan whole directories.

Reuses the static detection logic from core/skills/build/ but applies it to every
matching file in a scope_path rather than to a single generated code artifact.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# File patterns for each Python-native skill
_PYTHON_PATTERNS = ("*.py",)
_SQL_PATTERNS = ("*.sql",)
_PY_AND_SQL = ("*.py", "*.sql")

# Directories to always skip
_SKIP_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "__pycache__",
        ".planning",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
    }
)


def _iter_files(scope_path: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Yield files matching patterns, skipping _SKIP_DIRS."""
    results: list[Path] = []
    for pattern in patterns:
        for f in scope_path.rglob(pattern):
            if any(part in _SKIP_DIRS for part in f.parts):
                continue
            results.append(f)
    return sorted(set(results))


def scan_security(scope_path: Path, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan all Python files in scope_path using security build auditor patterns."""
    from core.skills.build.security import audit_generated_python

    findings: list[dict[str, Any]] = []
    for file_path in _iter_files(scope_path, _PYTHON_PATTERNS):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            raw = audit_generated_python(content, {**context, "file_path": str(file_path)})
            for f in raw:
                f["file_path"] = str(file_path.relative_to(scope_path))
            findings.extend(raw)
        except Exception as exc:
            logger.debug("security scan error on %s: %s", file_path, exc)
    return findings


def scan_code_quality(scope_path: Path, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan all Python files in scope_path using code-quality build auditor patterns."""
    from core.skills.build.code_quality import audit_generated_python

    findings: list[dict[str, Any]] = []
    for file_path in _iter_files(scope_path, _PYTHON_PATTERNS):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            raw = audit_generated_python(content, {**context, "file_path": str(file_path)})
            for f in raw:
                f["file_path"] = str(file_path.relative_to(scope_path))
            findings.extend(raw)
        except Exception as exc:
            logger.debug("code-quality scan error on %s: %s", file_path, exc)
    return findings


def scan_database(scope_path: Path, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan Python and SQL files in scope_path using database build auditor patterns."""
    from core.skills.build.database import audit_generated_sql_or_python

    findings: list[dict[str, Any]] = []
    for file_path in _iter_files(scope_path, _PY_AND_SQL):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            raw = audit_generated_sql_or_python(content, {**context, "file_path": str(file_path)})
            for f in raw:
                f["file_path"] = str(file_path.relative_to(scope_path))
            findings.extend(raw)
        except Exception as exc:
            logger.debug("database scan error on %s: %s", file_path, exc)
    return findings
