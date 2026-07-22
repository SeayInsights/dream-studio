"""Test framework, database, web framework, frontend framework, monorepo, and
architecture-framework detectors for stack detection.

WO-GF-CONTROL-INSTALL-split: see detector.py facade docstring.
"""

from __future__ import annotations

import json
from pathlib import Path


def _detect_test_framework(path: Path) -> str | None:
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


def _detect_database_type(path: Path) -> str | None:
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


def _detect_web_framework(path: Path) -> str | None:
    """Detect the primary web/API framework for backend-api skill dispatch."""
    # Check package.json for JS/TS projects
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {}),
            }
            # Next.js already detected in main signals, but check for API routes
            if "next" in all_deps:
                # Check if it actually has API routes
                api_dir = path / "src" / "app" / "api"
                pages_api = path / "pages" / "api"
                if api_dir.exists() or pages_api.exists():
                    return "nextjs-api"
            if "fastify" in all_deps:
                return "fastify"
            if "hono" in all_deps:
                return "hono"
            if "express" in all_deps:
                return "express"
        except (json.JSONDecodeError, OSError):
            pass

    # Check Python project
    for py_config in ["pyproject.toml", "requirements.txt", "setup.py"]:
        config_file = path / py_config
        if config_file.exists():
            try:
                content = config_file.read_text(encoding="utf-8")
                if "fastapi" in content.lower():
                    return "fastapi"
                if "django" in content.lower() and (
                    "rest_framework" in content.lower() or "djangorestframework" in content.lower()
                ):
                    return "django-rest"
                if "flask" in content.lower():
                    return "flask"
            except OSError:
                pass

    # Check Go project
    go_mod = path / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text(encoding="utf-8")
            if "gin-gonic/gin" in content:
                return "gin"
            if "labstack/echo" in content:
                return "echo"
            if "go-chi/chi" in content:
                return "chi"
        except OSError:
            pass

    # Check Rust project
    cargo_toml = path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text(encoding="utf-8")
            if "axum" in content:
                return "axum"
            if "actix-web" in content:
                return "actix"
            if "rocket" in content:
                return "rocket"
        except OSError:
            pass

    return None


def _detect_frontend_framework(path: Path) -> str | None:
    """Detect the primary frontend UI framework for frontend-ux skill dispatch.

    Phase 1: React/Next.js focus. Phase 2 adds Vue/Svelte/Angular.
    """
    # Next.js already detected in main signals; check package.json for React family
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {}),
            }
            # Check in order of specificity
            if "@remix-run/react" in all_deps or "remix" in all_deps:
                return "remix"
            if "next" in all_deps:
                return "nextjs"  # Already in main signals, but set here too
            if "@angular/core" in all_deps:
                return "angular"
            if "svelte" in all_deps:
                return "svelte"
            if "vue" in all_deps:
                return "vue"
            if "react" in all_deps and "react-dom" in all_deps:
                return "react"
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _detect_monorepo_structure(path: Path) -> str | None:
    """Detect monorepo tooling for architecture skill dispatch.

    Returns: 'npm-workspaces', 'pnpm', 'yarn-workspaces', 'cargo', 'gradle', 'lerna', or None.
    """
    # pnpm: pnpm-workspace.yaml
    if (path / "pnpm-workspace.yaml").exists() or (path / "pnpm-workspace.yml").exists():
        return "pnpm"

    # Lerna: lerna.json
    if (path / "lerna.json").exists():
        return "lerna"

    # npm/yarn workspaces: package.json with "workspaces" field
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "workspaces" in content:
                # Distinguish yarn vs npm workspaces by lock file
                if (path / "yarn.lock").exists():
                    return "yarn-workspaces"
                return "npm-workspaces"
        except (json.JSONDecodeError, OSError):
            pass

    # Cargo workspace: Cargo.toml with [workspace] section
    cargo_toml = path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text(encoding="utf-8")
            if "[workspace]" in content:
                return "cargo"
        except OSError:
            pass

    # Gradle multi-project: settings.gradle or settings.gradle.kts with include()
    for settings_file in ["settings.gradle", "settings.gradle.kts"]:
        settings_path = path / settings_file
        if settings_path.exists():
            try:
                content = settings_path.read_text(encoding="utf-8")
                if "include(" in content or 'include "' in content:
                    return "gradle"
            except OSError:
                pass

    return None


def _detect_architecture_framework(path: Path) -> str | None:
    """Detect explicit architecture frameworks for architecture skill calibration.

    Returns: 'nestjs', 'spring', or None.
    NestJS and Spring impose their own layer structures; the skill uses these
    to inform layer_map defaults.
    """
    # NestJS: @nestjs/* in package.json deps + nest-cli.json
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {}),
            }
            if any(dep.startswith("@nestjs/") for dep in all_deps):
                return "nestjs"
        except (json.JSONDecodeError, OSError):
            pass

    # Spring Boot: pom.xml with spring-boot or Gradle with org.springframework.boot
    pom_xml = path / "pom.xml"
    if pom_xml.exists():
        try:
            content = pom_xml.read_text(encoding="utf-8")
            if "spring-boot" in content or "springframework" in content:
                return "spring"
        except OSError:
            pass

    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle_path = path / gradle_file
        if gradle_path.exists():
            try:
                content = gradle_path.read_text(encoding="utf-8")
                if "org.springframework.boot" in content or "spring-boot" in content:
                    return "spring"
            except OSError:
                pass

    return None
