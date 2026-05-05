"""Tests for Context7 progressive context loader."""
import sys
from pathlib import Path
import tempfile

# Add hooks/lib to path
HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
sys.path.insert(0, str(HOOKS_LIB))

from context.context7_manager import Context7Manager


def test_init_default_token_budget():
    """Test Context7Manager initializes with default token budget."""
    manager = Context7Manager()
    assert manager.max_tokens == 150000


def test_init_custom_token_budget():
    """Test Context7Manager with custom token budget."""
    manager = Context7Manager(max_tokens=100000)
    assert manager.max_tokens == 100000


def test_load_small_codebase():
    """Test loading a small test codebase."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)

        # Create test files
        (test_dir / "file1.py").write_text("def hello(): pass")
        (test_dir / "file2.py").write_text("def world(): pass")

        manager = Context7Manager(max_tokens=10000)
        result = manager.load_codebase(test_dir, "hello world")

        assert "skeleton" in result
        assert "details" in result
        assert "tokens_used" in result
        assert "coverage" in result
        assert result["tokens_used"] > 0


def test_token_estimation():
    """Test token estimation is reasonable."""
    manager = Context7Manager()
    content = "x" * 400  # ~100 tokens
    estimated = manager._estimate_tokens(content)
    assert 80 < estimated < 120  # Should be ~100


def test_ignores_common_directories():
    """Test that common ignore directories are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)

        # Create files in ignored directories
        (test_dir / "node_modules").mkdir()
        (test_dir / "node_modules" / "test.js").write_text("ignored")

        (test_dir / ".venv").mkdir()
        (test_dir / ".venv" / "test.py").write_text("ignored")

        # Create valid file
        (test_dir / "valid.py").write_text("def test(): pass")

        manager = Context7Manager()
        result = manager.load_codebase(test_dir, "test")

        # Should only load valid.py, not ignored files
        assert result["tokens_used"] < 1000


def test_coverage_metric():
    """Test that coverage is between 0 and 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)

        # Create multiple files
        for i in range(5):
            (test_dir / f"file{i}.py").write_text(f"def func{i}(): pass")

        manager = Context7Manager(max_tokens=500)  # Very small budget
        result = manager.load_codebase(test_dir, "func")

        assert 0.0 <= result["coverage"] <= 1.0
