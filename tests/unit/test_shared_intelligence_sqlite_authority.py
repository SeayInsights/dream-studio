from __future__ import annotations

from pathlib import Path

from core.config.sqlite_bootstrap import latest_migration_version
from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import (
    REQUIRED_SHARED_INTELLIGENCE_TABLES,
    require_shared_intelligence_tables,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "shared-intelligence" / "studio.db"


def test_migration_038_creates_shared_intelligence_tables(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert schema_version == latest_migration_version()
        assert schema_version >= 38
        require_shared_intelligence_tables(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert tables >= REQUIRED_SHARED_INTELLIGENCE_TABLES


def test_shared_intelligence_tests_use_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        require_shared_intelligence_tables(conn)

    assert db_path.is_file()
    assert db_path != live_db
