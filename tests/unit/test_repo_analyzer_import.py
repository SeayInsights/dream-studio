"""WO 88949ce5 regression: control/analysis/repo_analyzer.py imported a
non-existent sibling `.document_store`, making interfaces/cli/check_repo_updates.py
(its only importer) non-importable. The real DocumentStore lives at
core.storage.document_store. These imports must resolve."""

from __future__ import annotations

import importlib


def test_repo_analyzer_imports() -> None:
    mod = importlib.import_module("control.analysis.repo_analyzer")
    assert hasattr(mod, "analyze_repo")


def test_check_repo_updates_imports() -> None:
    importlib.import_module("interfaces.cli.check_repo_updates")


def test_document_store_create_is_available() -> None:
    from control.analysis.repo_analyzer import DocumentStore

    assert callable(DocumentStore.create)
