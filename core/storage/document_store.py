"""Universal CRUD API for the document store (ds_documents table) — facade
over the split modules.

ds_documents lives in files.db (the three-store document/artifact store),
NOT in studio.db (the canonical event authority).  All reads and writes go
through connect_files() / files_db_path() from core.files.store.

WO-GF-CORE-DATA-split: implementation moved to
document_store_{schema,crud}.py; this module re-exports the public API so
existing `from core.storage.document_store import X` callers are unchanged.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from .document_store_schema import (
    _ACTIVE,
    _ARCHIVED,
    _DOCUMENTS_DDL,
    _docs_connection,
    _docs_transaction,
    ensure_documents_schema,
    logger,
)
from .document_store_crud import (
    DocumentStore,
    _NOW,
    _SECURITY_ENABLED,
    scan_llm_output,
)

__all__ = [
    "DocumentStore",
    "PROJECT_ROOT",
    "_ACTIVE",
    "_ARCHIVED",
    "_DOCUMENTS_DDL",
    "_NOW",
    "_SECURITY_ENABLED",
    "_docs_connection",
    "_docs_transaction",
    "ensure_documents_schema",
    "logger",
    "scan_llm_output",
]
