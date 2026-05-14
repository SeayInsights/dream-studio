"""Centralized database configuration - SINGLE SOURCE OF TRUTH.

This module provides the ONLY way to connect to the dream-studio database.
All sqlite3.connect() calls throughout the codebase should be replaced with
get_connection() from this module.

Created: 2026-05-07 (Phase 1 - Database Unification)
Updated: 2026-05-07 (Execution OS Convergence - Added singleton runtime)
"""

import os
from pathlib import Path
import sqlite3
import logging
import threading
import atexit
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH_ENV = "DREAM_STUDIO_DB_PATH"


def _default_db_path() -> Path:
    """Return the canonical runtime DB path without creating directories."""
    override = os.environ.get(DB_PATH_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "studio.db"


def _read_only_db_path() -> Path:
    """Resolve the DB path for read-only callers without initializing runtime."""
    if DatabaseRuntime._instance is not None:
        return DatabaseRuntime._instance.db_path
    return _default_db_path()


# ============================================================================
# SINGLETON DATABASE RUNTIME
# ============================================================================


class DatabaseRuntime:
    """
    Centralized database connection manager (singleton).

    Ensures all connections use:
    - WAL mode for better concurrency
    - Foreign keys enabled
    - Proper busy timeout
    - Row factory for dict-like access
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database runtime."""
        self.db_path = db_path or self._get_default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
        atexit.register(self.cleanup)
        logger.info(f"DatabaseRuntime initialized at {self.db_path}")

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None):
        """Get singleton database runtime instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.cleanup()
            cls._instance = None

    def _get_default_db_path(self) -> Path:
        """Get default database path."""
        return _default_db_path()

    def _initialize_database(self):
        """Initialize database with proper settings."""
        from core.config.sqlite_bootstrap import run_migrations

        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            # Enable WAL mode
            result = conn.execute("PRAGMA journal_mode=WAL")
            wal_mode = result.fetchone()[0]

            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")

            # Set busy timeout (30 seconds)
            conn.execute("PRAGMA busy_timeout=30000")

            # Verify settings
            fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]

            if wal_mode != "wal":
                logger.warning(f"WAL mode not enabled (got {wal_mode})")

            if not fk_enabled:
                raise RuntimeError("Failed to enable foreign keys")

            run_migrations(conn)

            logger.debug("Database initialized with WAL mode and foreign keys")
        finally:
            conn.close()

    @contextmanager
    def get_connection_context(self, read_only: bool = False):
        """Get database connection as context manager."""
        conn = self._create_connection(read_only)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction_context(self, immediate: bool = False):
        """Execute operations in a transaction."""
        conn = self._create_connection(read_only=False)
        try:
            if immediate:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("BEGIN")

            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_connection(self, read_only: bool = False) -> sqlite3.Connection:
        """Create a database connection with proper configuration."""
        if read_only:
            uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")

        return conn

    def cleanup(self):
        """Cleanup on shutdown."""
        logger.debug("DatabaseRuntime cleanup")


# ============================================================================
# LEGACY FUNCTIONS (preserved for backwards compatibility)
# ============================================================================


# SINGLE SOURCE OF TRUTH FOR DATABASE LOCATION
def get_db_path() -> Path:
    """
    Returns the canonical database path.
    This is the ONLY function that should determine database location.

    Returns:
        Path: ~/.dream-studio/state/studio.db
    """
    runtime = DatabaseRuntime.get_instance()
    return runtime.db_path


def get_connection(read_only: bool = False) -> sqlite3.Connection:
    """
    Get a properly configured database connection.

    This is the ONLY function that should create database connections.
    Replaces all direct sqlite3.connect() calls.

    Args:
        read_only: If True, open in read-only mode

    Returns:
        sqlite3.Connection with proper settings

    Example:
        from core.config.database import get_connection

        conn = get_connection()
        cursor = conn.execute("SELECT * FROM events")
        conn.commit()
        conn.close()
    """
    if read_only:
        db_path = _read_only_db_path()
        if not db_path.is_file():
            raise FileNotFoundError(
                f"Dream Studio database not found for read-only access: {db_path}"
            )
    else:
        db_path = get_db_path()

    # Ensure directory exists (unless read-only)
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Use URI for read-only mode
    if read_only:
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0)
        conn.execute("PRAGMA query_only = ON")
    else:
        conn = sqlite3.connect(str(db_path), timeout=30.0)

    # Enable row factory for dict-like access
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Set busy timeout (30 seconds)
    conn.execute("PRAGMA busy_timeout = 30000")

    if not read_only:
        # Enable WAL mode for better concurrency on writable runtime connections.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            # WAL might not be available in all environments
            pass

    logger.debug(f"[DB] Connected to {db_path} (read_only={read_only})")

    return conn


class DatabaseContext:
    """
    Context manager for database operations with automatic commit/rollback.

    Usage:
        from core.config.database import DatabaseContext

        # Automatic commit on success, rollback on error
        with DatabaseContext() as conn:
            conn.execute("INSERT INTO table ...")
            conn.execute("UPDATE other_table ...")
        # Automatically committed

        # Read-only connection
        with DatabaseContext(read_only=True) as conn:
            rows = conn.execute("SELECT * FROM table").fetchall()
    """

    def __init__(self, read_only: bool = False):
        """
        Initialize database context.

        Args:
            read_only: If True, open in read-only mode (no commit)
        """
        self.read_only = read_only
        self.conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
        """Enter context - open connection."""
        self.conn = get_connection(self.read_only)
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - commit or rollback, then close."""
        if exc_type is None:
            # Success - commit if not read-only
            if not self.read_only:
                self.conn.commit()
                logger.debug("[DB] Transaction committed")
        else:
            # Error - rollback if not read-only
            if not self.read_only:
                self.conn.rollback()
                logger.error(f"[DB] Transaction rolled back: {exc_val}")

        self.conn.close()
        return False  # Don't suppress exceptions


# Convenience function for getting db_path (used by many modules)
def db_path() -> Path:
    """Alias for get_db_path() for backwards compatibility."""
    return get_db_path()


# ============================================================================
# NEW CONVERGENCE CONVENIENCE FUNCTIONS
# ============================================================================


@contextmanager
def transaction(immediate: bool = False):
    """
    Execute in transaction.

    Args:
        immediate: If True, use BEGIN IMMEDIATE

    Yields:
        sqlite3.Connection in transaction

    Example:
        with transaction() as conn:
            conn.execute("INSERT INTO table VALUES (?)", [value])
            # Auto-commits on success, rolls back on exception
    """
    runtime = DatabaseRuntime.get_instance()
    with runtime.transaction_context(immediate=immediate) as conn:
        yield conn


def health_check() -> dict:
    """
    Check database health.

    Returns:
        Dict with health status
    """
    try:
        runtime = DatabaseRuntime.get_instance()
        with runtime.get_connection_context() as conn:
            # Check WAL mode
            wal = conn.execute("PRAGMA journal_mode").fetchone()[0]

            # Check foreign keys
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]

            # Check database size
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            size = page_count * page_size

            # Check integrity
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

            return {
                "status": "healthy" if integrity == "ok" else "degraded",
                "wal_mode": wal == "wal",
                "foreign_keys_enabled": bool(fk),
                "size_bytes": size,
                "integrity": integrity,
                "db_path": str(runtime.db_path),
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def initialize_database(db_path: Optional[Path] = None):
    """
    Initialize database runtime with custom path.

    Args:
        db_path: Optional custom database path

    Returns:
        DatabaseRuntime instance
    """
    return DatabaseRuntime.get_instance(db_path)
