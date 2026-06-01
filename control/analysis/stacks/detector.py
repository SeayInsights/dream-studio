"""Multi-signal stack detection for project-intelligence platform.

Combines multiple detection strategies to identify project stack with confidence scoring.
"""

import json
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class StackSignal:
    """A signal indicating a particular stack."""

    name: str  # stack name
    confidence: float  # 0.0-1.0
    source: str  # where the signal came from
    evidence: List[str]  # supporting evidence


@dataclass
class DetectedStack:
    """Result of stack detection."""

    adapter: Optional[str]  # adapter name to use
    confidence: float  # overall confidence
    signals: List[StackSignal]  # all signals detected
    framework: Optional[str]  # framework name
    version: Optional[str]  # framework version if detected
    test_framework: Optional[str] = (
        None  # test framework for coverage parser dispatch (vitest/jest/pytest/mocha)
    )
    database_type: Optional[str] = (
        None  # primary database type for database skill dispatch
        # values: 'sqlite', 'postgres', 'mysql', 'mongodb', 'd1', 'dynamodb', or None
    )


def detect_stack(path: Path) -> DetectedStack:
    """
    Detect project stack using multiple signals.

    Args:
        path: Project root directory

    Returns:
        DetectedStack with adapter name and confidence
    """
    signals = []

    # Signal 1: Try repo_context detection
    try:
        from control.context.repo import _detect_stack

        detected = _detect_stack(path)
        if detected and isinstance(detected, dict):
            stack_name = detected.get("stack") or detected.get("framework")
            if stack_name and isinstance(stack_name, str):
                signals.append(
                    StackSignal(
                        name=stack_name.lower(),
                        confidence=0.7,
                        source="repo_context",
                        evidence=[f"Detected via repo_context: {stack_name}"],
                    )
                )
    except Exception:
        pass  # repo_context not available or failed

    # Signal 2: File-based detection
    signals.extend(_detect_by_files(path))

    # Combine signals into stack result
    result = _combine_signals(signals)

    # Augment with test framework for coverage parser dispatch
    result.test_framework = _detect_test_framework(path)

    # Augment with database type for database skill dispatch
    result.database_type = _detect_database_type(path)

    return result


def _detect_by_files(path: Path) -> List[StackSignal]:
    """Detect stack by checking for key files."""
    signals = []

    # Check for Next.js
    if (path / "next.config.js").exists() or (path / "next.config.ts").exists():
        evidence = []
        if (path / "next.config.js").exists():
            evidence.append("next.config.js exists")
        if (path / "next.config.ts").exists():
            evidence.append("next.config.ts exists")

        signals.append(
            StackSignal(name="nextjs", confidence=0.9, source="file_check", evidence=evidence)
        )

    # Check for Astro
    if (path / "astro.config.mjs").exists() or (path / "astro.config.ts").exists():
        evidence = []
        if (path / "astro.config.mjs").exists():
            evidence.append("astro.config.mjs exists")
        if (path / "astro.config.ts").exists():
            evidence.append("astro.config.ts exists")

        signals.append(
            StackSignal(name="astro", confidence=0.9, source="file_check", evidence=evidence)
        )

    # Check for Python
    python_files = []
    if (path / "pyproject.toml").exists():
        python_files.append("pyproject.toml exists")
    if (path / "requirements.txt").exists():
        python_files.append("requirements.txt exists")
    if (path / "setup.py").exists():
        python_files.append("setup.py exists")

    if python_files:
        signals.append(
            StackSignal(name="python", confidence=0.8, source="file_check", evidence=python_files)
        )

    # Check for generic Node.js (only if no specific framework detected)
    if (path / "package.json").exists():
        has_framework = any(s.name in ("nextjs", "astro") for s in signals)
        if not has_framework:
            signals.append(
                StackSignal(
                    name="node",
                    confidence=0.6,
                    source="file_check",
                    evidence=["package.json exists (no specific framework)"],
                )
            )

    # Check for Go
    if (path / "go.mod").exists():
        signals.append(
            StackSignal(
                name="go",
                confidence=0.95,
                source="file_check",
                evidence=["go.mod exists"],
            )
        )

    # Check for Rust
    if (path / "Cargo.toml").exists():
        signals.append(
            StackSignal(
                name="rust",
                confidence=0.95,
                source="file_check",
                evidence=["Cargo.toml exists"],
            )
        )

    return signals


def _detect_test_framework(path: Path) -> Optional[str]:
    """
    Detect test framework for coverage parser dispatch (tst-001 and tst-010).

    Checks package.json devDependencies/dependencies for vitest/jest/mocha,
    and pyproject.toml / pytest.ini for pytest.

    Returns the test framework name string, or None if not detected.
    Priority: vitest > jest > mocha > pytest (JS/TS takes precedence when both present).
    """
    # Check package.json for JS/TS test frameworks
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with pkg_json.open(encoding="utf-8") as fh:
                pkg = json.load(fh)
            all_deps: dict = {}
            all_deps.update(pkg.get("dependencies", {}))
            all_deps.update(pkg.get("devDependencies", {}))
            if "vitest" in all_deps:
                return "vitest"
            if "jest" in all_deps or "@jest/core" in all_deps:
                return "jest"
            if "mocha" in all_deps:
                return "mocha"
        except Exception:
            pass  # malformed package.json — fall through

    # Check for Python test frameworks
    if (path / "pyproject.toml").exists() or (path / "pytest.ini").exists():
        return "pytest"

    # Check for Go (go test is built-in to the toolchain)
    if (path / "go.mod").exists():
        return "go"

    # Check for Rust (cargo test is built-in to the toolchain)
    if (path / "Cargo.toml").exists():
        return "cargo"

    return None


def _detect_database_type(path: Path) -> Optional[str]:
    """Detect database type for database skill dispatch.

    Returns the primary database type: 'sqlite', 'postgres', 'mysql',
    'mongodb', 'd1', 'dynamodb', or None if not detected.
    """
    # Check package.json for JS/TS projects
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {}),
            }
            if "@cloudflare/workers-types" in all_deps or "wrangler" in all_deps:
                # Check wrangler config for D1 binding
                for wrangler_file in ["wrangler.toml", "wrangler.jsonc", "wrangler.json"]:
                    if (path / wrangler_file).exists():
                        wrangler_text = (path / wrangler_file).read_text(encoding="utf-8")
                        if "d1_databases" in wrangler_text or "D1Database" in wrangler_text:
                            return "d1"
            if any(
                dep in all_deps
                for dep in ["pg", "postgres", "@neondatabase/serverless", "postgresql"]
            ):
                return "postgres"
            if any(dep in all_deps for dep in ["mysql", "mysql2", "mariadb"]):
                return "mysql"
            if any(
                dep in all_deps
                for dep in ["mongoose", "mongodb", "@mongodb/mongodb-client-encryption"]
            ):
                return "mongodb"
            if "@aws-sdk/client-dynamodb" in all_deps or "dynamodb" in all_deps:
                return "dynamodb"
        except (json.JSONDecodeError, OSError):
            pass

    # Check Python project
    for py_config in ["pyproject.toml", "requirements.txt", "setup.py"]:
        config_file = path / py_config
        if config_file.exists():
            try:
                content = config_file.read_text(encoding="utf-8")
                if "psycopg2" in content or "asyncpg" in content or "pg8000" in content:
                    return "postgres"
                if "pymysql" in content or "mysql-connector" in content or "aiomysql" in content:
                    return "mysql"
                if "pymongo" in content or "motor" in content:
                    return "mongodb"
                if "sqlite" in content.lower():
                    return "sqlite"
            except OSError:
                pass

    # Fallback: check for sqlite3 import pattern or .db files
    for db_file in path.glob("**/*.db"):
        if "node_modules" not in str(db_file) and ".planning" not in str(db_file):
            return "sqlite"

    # Check Go project
    go_mod = path / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text(encoding="utf-8")
            if "pgx" in content or "lib/pq" in content or "go-pg" in content:
                return "postgres"
            if "go-sql-driver/mysql" in content:
                return "mysql"
            if "mongo-driver" in content:
                return "mongodb"
            if "mattn/go-sqlite3" in content or "modernc.org/sqlite" in content:
                return "sqlite"
        except OSError:
            pass

    # Check Rust project
    cargo_toml = path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text(encoding="utf-8")
            if "sqlx" in content and "postgres" in content:
                return "postgres"
            if "sqlx" in content and "sqlite" in content:
                return "sqlite"
            if "diesel" in content:
                # diesel defaults to postgres if not specified
                return "postgres"
            if "mongodb" in content:
                return "mongodb"
        except OSError:
            pass

    return None


def _combine_signals(signals: List[StackSignal]) -> DetectedStack:
    """Combine signals and select best match."""
    if not signals:
        return DetectedStack(adapter=None, confidence=0.0, signals=[], framework=None, version=None)

    # Group by stack name, take max confidence
    stack_scores = {}
    for signal in signals:
        if signal.name not in stack_scores:
            stack_scores[signal.name] = signal.confidence
        else:
            # Multiple signals boost confidence (20% of signal confidence added)
            stack_scores[signal.name] = min(
                1.0, stack_scores[signal.name] + signal.confidence * 0.2
            )

    # Best match
    best_name = max(stack_scores.keys(), key=lambda k: stack_scores[k])
    best_confidence = stack_scores[best_name]

    # Framework name mapping
    framework_names = {
        "nextjs": "Next.js",
        "astro": "Astro",
        "python": "Python",
        "node": "Node.js",
        "go": "Go",
        "rust": "Rust",
    }

    return DetectedStack(
        adapter=best_name,
        confidence=best_confidence,
        signals=signals,
        framework=framework_names.get(best_name, best_name.title()),
        version=None,  # Version detection in Wave 3
    )
