"""Retrieval capability boundary tests.

Verifies:
1. Core module load does not import sentence-transformers at the top level.
2. semantic_retrieval_status() returns correct controlled status values.
3. check_fts5_capability() uses an in-memory connection, never the active DB.
4. search_tools() default routes to TF-IDF, not embeddings.
5. FTS5 status label is correct when FTS5 is unavailable.
6. semantic_retrieval_status() always reports default_active=False.
7. Backward compatibility: existing search_tools()/hybrid_search() return List[ToolMatch].
8. search_tools_with_status() reports retrieval mode honestly.
9. hybrid_search_with_status() reports retrieval mode honestly.
"""

import ast
import inspect
import sqlite3
import sys
from unittest.mock import MagicMock, patch

from control.research.tools import (
    SearchResultWithStatus,
    ToolMatch,
    hybrid_search_with_status,
    search_tools,
    search_tools_with_status,
    semantic_retrieval_status,
)
from core.memory.retrieval import FTS5MemoryRetriever, check_fts5_capability


class TestNoEagerSentenceTransformersImport:
    """Guarantee 1: sentence_transformers is never imported at module load time."""

    def test_tools_module_has_no_top_level_sentence_transformers_import(self):
        """No top-level import of sentence_transformers in control.research.tools.

        The import is only allowed inside build_embedding_index() (a function body).
        ast.iter_child_nodes() returns only direct children of the Module node,
        which are top-level statements — nested function bodies are not included.
        """
        import control.research.tools as tools_mod

        source = inspect.getsource(tools_mod)
        tree = ast.parse(source)

        top_level_st_imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "sentence_transformers" in node.module:
                    top_level_st_imports.append(ast.unparse(node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "sentence_transformers" in alias.name:
                        top_level_st_imports.append(ast.unparse(node))

        assert top_level_st_imports == [], (
            f"sentence_transformers found at module level: {top_level_st_imports}. "
            "Must remain a lazy import inside build_embedding_index() only."
        )


class TestSemanticRetrievalStatus:
    """Guarantee 2: semantic_retrieval_status() returns controlled status values."""

    def test_status_when_unavailable(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            status = semantic_retrieval_status()

        assert status["status"] == "unavailable_dependency_missing"
        assert status["available"] is False
        assert status["default_active"] is False

    def test_status_when_available(self):
        mock_st = MagicMock()
        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            status = semantic_retrieval_status()

        assert status["status"] == "available"
        assert status["available"] is True
        assert status["default_active"] is False

    def test_default_active_always_false(self):
        """Guarantee 6: default_active must be False regardless of installation state."""
        mock_st = MagicMock()
        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            installed = semantic_retrieval_status()
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            missing = semantic_retrieval_status()

        assert installed["default_active"] is False
        assert missing["default_active"] is False

    def test_default_provider_is_tfidf(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            status = semantic_retrieval_status()
        assert status["default_provider"] == "tfidf"

    def test_unavailable_status_includes_hint(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            status = semantic_retrieval_status()
        assert "hint" in status
        assert status["hint"]


class TestFTS5CapabilityCheck:
    """Guarantee 3: check_fts5_capability() uses in-memory connection only."""

    def test_returns_required_keys(self):
        result = check_fts5_capability()
        assert isinstance(result, dict)
        assert "available" in result
        assert "status" in result

    def test_does_not_touch_active_db(self):
        """FTS5 probe must only connect to :memory:."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value = None
            mock_connect.return_value = mock_conn

            check_fts5_capability()

        mock_connect.assert_called_once_with(":memory:")

    def test_status_label_when_available(self):
        result = check_fts5_capability()
        if result["available"]:
            assert result["status"] == "fts5_available"

    def test_status_label_when_unavailable(self):
        """Guarantee 5: unavailable FTS5 must return unavailable_fts5_missing."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")
            mock_connect.return_value = mock_conn

            result = check_fts5_capability()

        assert result["available"] is False
        assert result["status"] == "unavailable_fts5_missing"

    def test_connection_is_closed_on_success(self):
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value = None
            mock_connect.return_value = mock_conn

            check_fts5_capability()

        mock_conn.close.assert_called_once()

    def test_connection_is_closed_on_failure(self):
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")
            mock_connect.return_value = mock_conn

            check_fts5_capability()

        mock_conn.close.assert_called_once()


class TestDefaultSearchUsesTFIDF:
    """Guarantee 4: search_tools() defaults to TF-IDF, not embeddings."""

    def test_default_use_embeddings_is_false(self):
        """search_tools() signature must default use_embeddings to False."""
        import inspect as _inspect

        sig = _inspect.signature(search_tools)
        default = sig.parameters["use_embeddings"].default
        assert (
            default is False
        ), f"search_tools() use_embeddings default must be False, got {default!r}"

    def test_default_call_routes_to_tfidf_not_embeddings(self):
        """Default search_tools() call must invoke TF-IDF, not embedding search."""
        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
            patch("control.research.tools._search_with_embeddings") as mock_embed,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            mock_embed.return_value = []

            search_tools("test query default routing")

        mock_tfidf.assert_called_once()
        mock_embed.assert_not_called()

    def test_explicit_use_embeddings_true_routes_to_embeddings(self):
        """Passing use_embeddings=True must route to embedding search."""
        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
            patch("control.research.tools._search_with_embeddings") as mock_embed,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            mock_embed.return_value = []

            search_tools("test query explicit embeddings", use_embeddings=True)

        mock_embed.assert_called_once()
        mock_tfidf.assert_not_called()


class TestBackwardCompatibility:
    """Guarantee 7: existing search_tools() and hybrid_search() return List[ToolMatch]."""

    def test_search_tools_returns_list(self):
        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            result = search_tools("backward compat check")
        assert isinstance(result, list)

    def test_hybrid_search_returns_list(self):
        from control.research.tools import hybrid_search

        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
            patch("control.research.tools._search_with_embeddings") as mock_embed,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            mock_embed.return_value = []
            result = hybrid_search("backward compat check")
        assert isinstance(result, list)

    def test_search_tools_with_status_does_not_affect_search_tools_signature(self):
        """search_tools_with_status must not alter search_tools() return type."""
        import inspect as _inspect

        sig = _inspect.signature(search_tools)
        # Return annotation is List[ToolMatch] — verify it has not changed
        assert "ToolMatch" in str(sig.return_annotation)


class TestSearchToolsWithStatus:
    """Guarantee 8: search_tools_with_status() reports retrieval mode honestly."""

    def test_returns_search_result_with_status(self):
        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            result = search_tools_with_status("test query")
        assert isinstance(result, SearchResultWithStatus)
        assert isinstance(result.results, list)

    def test_default_use_embeddings_false_reports_tfidf_default(self):
        """Default call must report tfidf_default and embeddings_used=False."""
        with (
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            result = search_tools_with_status("test tfidf default")
        assert result.retrieval_mode == "tfidf_default"
        assert result.embeddings_used is False
        assert result.semantic_status == "disabled_by_default"

    def test_use_embeddings_true_dep_missing_reports_fallback(self):
        """use_embeddings=True with missing dep must report tfidf_fallback_dependency_missing."""
        with (
            patch.dict(sys.modules, {"sentence_transformers": None}),
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            result = search_tools_with_status("test dep missing", use_embeddings=True)
        assert result.retrieval_mode == "tfidf_fallback_dependency_missing"
        assert result.semantic_status == "unavailable_dependency_missing"
        assert result.embeddings_used is False

    def test_use_embeddings_true_runtime_error_reports_semantic_error(self):
        """Embedding build failure with dep present must report tfidf_fallback_semantic_error."""
        mock_st = MagicMock()
        with (
            patch.dict(sys.modules, {"sentence_transformers": mock_st}),
            patch(
                "control.research.tools.build_embedding_index",
                side_effect=RuntimeError("model load failed"),
            ),
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            result = search_tools_with_status("test runtime error", use_embeddings=True)
        assert result.retrieval_mode == "tfidf_fallback_semantic_error"
        assert result.semantic_status == "available"
        assert result.embeddings_used is False

    def test_reuses_semantic_retrieval_status(self):
        """search_tools_with_status() must call semantic_retrieval_status(), not duplicate logic."""
        with (
            patch(
                "control.research.tools.semantic_retrieval_status",
                return_value={"available": False, "status": "unavailable_dependency_missing"},
            ) as mock_st_status,
            patch("control.research.tools._query_cache") as mock_cache,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_cache.get.return_value = None
            mock_tfidf.return_value = []
            search_tools_with_status("test reuse status", use_embeddings=True)
        mock_st_status.assert_called_once()


class TestHybridSearchWithStatus:
    """Guarantee 9: hybrid_search_with_status() reports retrieval mode honestly."""

    def test_returns_search_result_with_status(self):
        with (
            patch.dict(sys.modules, {"sentence_transformers": None}),
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_tfidf.return_value = []
            result = hybrid_search_with_status("test query")
        assert isinstance(result, SearchResultWithStatus)
        assert isinstance(result.results, list)

    def test_empty_query_reports_disabled_by_default(self):
        result = hybrid_search_with_status("")
        assert result.retrieval_mode == "disabled_by_default"
        assert result.embeddings_used is False
        assert result.results == []

    def test_dep_missing_reports_tfidf_fallback_dependency_missing(self):
        """Missing sentence-transformers must be reported as tfidf_fallback_dependency_missing."""
        with (
            patch.dict(sys.modules, {"sentence_transformers": None}),
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_tfidf.return_value = []
            result = hybrid_search_with_status("data pipeline tools")
        assert result.retrieval_mode == "tfidf_fallback_dependency_missing"
        assert result.semantic_status == "unavailable_dependency_missing"
        assert result.embeddings_used is False

    def test_dep_present_build_fails_reports_semantic_error(self):
        """Runtime embedding build failure with dep present must report tfidf_fallback_semantic_error."""
        mock_st = MagicMock()
        with (
            patch.dict(sys.modules, {"sentence_transformers": mock_st}),
            patch(
                "control.research.tools.build_embedding_index",
                side_effect=RuntimeError("index build failed"),
            ),
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_tfidf.return_value = []
            result = hybrid_search_with_status("data pipeline tools")
        assert result.retrieval_mode == "tfidf_fallback_semantic_error"
        assert result.semantic_status == "available"
        assert result.embeddings_used is False

    def test_dep_present_build_succeeds_reports_semantic_embeddings(self):
        """Successful embedding build must report semantic_embeddings and embeddings_used=True."""
        mock_st = MagicMock()
        with (
            patch.dict(sys.modules, {"sentence_transformers": mock_st}),
            patch("control.research.tools.build_embedding_index"),
            patch("control.research.tools.hybrid_search", return_value=[]) as mock_hybrid,
        ):
            result = hybrid_search_with_status("data pipeline tools")
        assert result.retrieval_mode == "semantic_embeddings"
        assert result.semantic_status == "available"
        assert result.embeddings_used is True
        mock_hybrid.assert_called_once()

    def test_reuses_semantic_retrieval_status(self):
        """hybrid_search_with_status() must call semantic_retrieval_status(), not duplicate logic."""
        with (
            patch(
                "control.research.tools.semantic_retrieval_status",
                return_value={"available": False, "status": "unavailable_dependency_missing"},
            ) as mock_st_status,
            patch("control.research.tools._search_with_tfidf") as mock_tfidf,
        ):
            mock_tfidf.return_value = []
            hybrid_search_with_status("test reuse")
        mock_st_status.assert_called_once()

    def test_no_module_level_sentence_transformers_import_after_new_functions(self):
        """Adding status-aware functions must not introduce new top-level ST imports."""
        import control.research.tools as tools_mod

        source = inspect.getsource(tools_mod)
        tree = ast.parse(source)
        top_level_st_imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "sentence_transformers" in node.module:
                    top_level_st_imports.append(ast.unparse(node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "sentence_transformers" in alias.name:
                        top_level_st_imports.append(ast.unparse(node))
        assert top_level_st_imports == []
