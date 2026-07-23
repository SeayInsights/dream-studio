"""Phase 5.2A — Database / Migration Governance tests.

Covers:
1. MIGRATION_AUTHORITY.md exists and documents canonical directory
2. core/config/database.py is SSOT for connections
3. No direct sqlite3.connect in projection routes
4. No direct sqlite3.connect in core/security/
5. Canonical migration directory has sequential numbering (011 gap was closed in phase 18.1.13)
6. Root migrations/ directory is legacy-only (no new files expected)
7. _schema_version table managed exclusively by studio_db
8. Projection routes import get_connection from canonical module
9. project_resolver.py uses canonical get_connection
10. analytics.py uses canonical get_connection
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO_ROOT / "projections" / "api" / "routes"
CANONICAL_MIGRATIONS = REPO_ROOT / "core" / "event_store" / "migrations"
ROOT_MIGRATIONS = REPO_ROOT / "migrations"


def _module_surface(py_path: Path) -> str:
    """Full source surface of a module: the file itself plus any facade-split
    ``<stem>_*.py`` siblings beside it. WO-GF-API-ROUTES (#539) reduced
    ``intelligence.py`` to a thin re-export facade over ``intelligence_*.py``, so the
    canonical-connection import moved into the siblings; a source-text check must read
    the whole surface. Route files with no siblings read as themselves."""
    parts = [py_path.read_text(encoding="utf-8")]
    for sib in sorted(py_path.parent.glob(f"{py_path.stem}_*.py")):
        parts.append(sib.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ── 1. MIGRATION_AUTHORITY.md exists ────────────────────────────────────────


class TestMigrationAuthority:

    def test_migration_authority_exists(self):
        assert (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").is_file()

    def test_documents_canonical_directory(self):
        text = (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").read_text(encoding="utf-8")
        assert "core/event_store/migrations/" in text

    def test_documents_connection_authority(self):
        text = (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").read_text(encoding="utf-8")
        assert "core/config/database.py" in text

    def test_documents_schema_version(self):
        text = (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").read_text(encoding="utf-8")
        assert "_schema_version" in text

    def test_documents_migration_011_gap(self):
        text = (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").read_text(encoding="utf-8")
        assert "011" in text


# ── 2. core/config/database.py is SSOT ─────────────────────────────────────


class TestDatabaseSSOT:

    def test_database_module_exists(self):
        assert (REPO_ROOT / "core" / "config" / "database.py").is_file()

    def test_exports_get_connection(self):
        source = (REPO_ROOT / "core" / "config" / "database.py").read_text(encoding="utf-8")
        assert "def get_connection" in source

    def test_exports_database_context(self):
        source = (REPO_ROOT / "core" / "config" / "database.py").read_text(encoding="utf-8")
        assert "class DatabaseContext" in source or "def DatabaseContext" in source

    def test_exports_transaction(self):
        source = (REPO_ROOT / "core" / "config" / "database.py").read_text(encoding="utf-8")
        assert "def transaction" in source

    def test_exports_get_db_path(self):
        source = (REPO_ROOT / "core" / "config" / "database.py").read_text(encoding="utf-8")
        assert "def get_db_path" in source


# ── 3. No direct sqlite3.connect in projection routes ──────────────────────


class TestNoDirectConnectRoutes:

    def _route_files(self):
        return sorted(ROUTES_DIR.glob("*.py"))

    def test_no_sqlite3_connect_in_routes(self):
        """No projection route file calls sqlite3.connect() directly."""
        for f in self._route_files():
            source = f.read_text(encoding="utf-8")
            matches = re.findall(r"sqlite3\.connect\(", source)
            assert not matches, f"{f.name} still has direct sqlite3.connect()"


# ── 4. No direct sqlite3.connect in core/security ──────────────────────────


class TestNoDirectConnectSecurity:

    def test_no_sqlite3_connect_in_project_resolver(self):
        source = (REPO_ROOT / "core" / "security" / "project_resolver.py").read_text(
            encoding="utf-8"
        )
        assert "sqlite3.connect" not in source

    def test_project_resolver_uses_canonical(self):
        source = (REPO_ROOT / "core" / "security" / "project_resolver.py").read_text(
            encoding="utf-8"
        )
        assert "from core.config.database import get_connection" in source


# ── 5. Canonical migration numbering ───────────────────────────────────────


class TestMigrationNumbering:

    def test_canonical_migrations_exist(self):
        sql_files = sorted(CANONICAL_MIGRATIONS.glob("*.sql"))
        assert len(sql_files) > 0, "No canonical migration files found"

    # WO-SQUASH-TESTS: test_migration_011_exists deleted — it asserted a 011_*
    # file exists (a historical numbering-gap closure). Migrations 001-141 are
    # folded into the lean baseline (142_lean_baseline.sql); individual numbered
    # files no longer exist, so the gap concern is moot.

    def test_migrations_are_numbered(self):
        for f in CANONICAL_MIGRATIONS.glob("*.sql"):
            assert re.match(r"^\d{3}_", f.name), f"{f.name} doesn't follow NNN_ numbering"


# ── 6. Root migrations are legacy ──────────────────────────────────────────


class TestRootMigrationsLegacy:

    def test_root_migrations_exist_as_legacy(self):
        """Root migrations/ dir exists with legacy files — no enforcement, just presence check."""
        if ROOT_MIGRATIONS.is_dir():
            files = list(ROOT_MIGRATIONS.glob("*.sql"))
            assert len(files) > 0, "Root migrations/ exists but is empty"

    def test_migration_authority_marks_legacy(self):
        text = (REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md").read_text(encoding="utf-8")
        assert "legacy" in text.lower() or "Legacy" in text


# ── 7. _schema_version managed by studio_db ─────────────────────────────────


class TestSchemaVersionAuthority:

    def test_studio_db_manages_schema_version(self):
        source = (REPO_ROOT / "core" / "event_store" / "migration_runner.py").read_text(
            encoding="utf-8"
        )
        assert "_schema_version" in source

    def test_no_schema_version_in_routes(self):
        """Projection routes must not touch _schema_version."""
        for f in ROUTES_DIR.glob("*.py"):
            source = f.read_text(encoding="utf-8")
            assert (
                "_schema_version" not in source
            ), f"{f.name} references _schema_version (should only be in migration runner)"


# ── 8. Routes import get_connection from canonical module ───────────────────


class TestCanonicalImports:

    ROUTE_FILES_EXPECTED = [
        "analytics.py",
        "audits.py",
        "hooks.py",
        "intelligence.py",
        "security.py",
        "alerts.py",
        "discovery_internal.py",
    ]

    def test_routes_use_canonical_connection(self):
        """Key route files import get_connection from core.config.database."""
        for name in self.ROUTE_FILES_EXPECTED:
            f = ROUTES_DIR / name
            if not f.is_file():
                continue
            source = _module_surface(f)
            assert (
                "core.config.database" in source
            ), f"{name} does not import from core.config.database"


# ── 9. project_resolver uses canonical ──────────────────────────────────────


class TestProjectResolverCanonical:

    def test_no_hardcoded_db_path(self):
        source = (REPO_ROOT / "core" / "security" / "project_resolver.py").read_text(
            encoding="utf-8"
        )
        assert "~/.dream-studio" not in source
        assert ".dream-studio/state/studio.db" not in source

    def test_no_import_sqlite3(self):
        source = (REPO_ROOT / "core" / "security" / "project_resolver.py").read_text(
            encoding="utf-8"
        )
        assert "import sqlite3" not in source


# ── 10. analytics.py uses canonical ─────────────────────────────────────────


class TestAnalyticsCanonical:

    def test_analytics_uses_canonical(self):
        source = (ROUTES_DIR / "analytics.py").read_text(encoding="utf-8")
        assert "from core.config.database import get_connection" in source

    def test_analytics_no_hardcoded_path(self):
        source = (ROUTES_DIR / "analytics.py").read_text(encoding="utf-8")
        assert "~/.dream-studio" not in source
        assert "expanduser" not in source

    def test_analytics_no_sqlite3_import(self):
        source = (ROUTES_DIR / "analytics.py").read_text(encoding="utf-8")
        assert "import sqlite3" not in source
