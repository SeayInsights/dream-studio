"""Multi-signal stack detection for project-intelligence platform.

Combines multiple detection strategies to identify project stack with confidence scoring.
"""

import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class StackSignal:
    """A signal indicating a particular stack."""

    name: str  # stack name
    confidence: float  # 0.0-1.0
    source: str  # where the signal came from
    evidence: list[str]  # supporting evidence


@dataclass
class DetectedStack:
    """Result of stack detection."""

    adapter: str | None  # adapter name to use
    confidence: float  # overall confidence
    signals: list[StackSignal]  # all signals detected
    framework: str | None  # framework name
    version: str | None  # framework version if detected
    test_framework: str | None = (
        None  # test framework for coverage parser dispatch (vitest/jest/pytest/mocha)
    )
    database_type: str | None = (
        None  # primary database type for database skill dispatch
        # values: 'sqlite', 'postgres', 'mysql', 'mongodb', 'd1', 'dynamodb', or None
    )
    web_framework: str | None = (
        None  # primary web/API framework for backend-api skill dispatch
        # values: 'fastapi', 'flask', 'django-rest', 'express', 'fastify', 'hono',
        #         'nextjs-api', 'gin', 'echo', 'chi', 'axum', 'actix', 'rocket', or None
    )
    frontend_framework: str | None = (
        None  # primary frontend UI framework for frontend-ux skill dispatch
        # values: 'nextjs', 'react', 'remix', 'vue', 'svelte', 'angular', or None
    )
    monorepo_type: str | None = (
        None  # monorepo tooling for architecture skill dispatch
        # values: 'npm-workspaces', 'pnpm', 'yarn-workspaces', 'cargo', 'gradle', 'lerna', or None
    )
    architecture_framework: str | None = (
        None  # explicit architecture framework for architecture skill calibration
        # values: 'nestjs', 'spring', or None
    )
    has_dockerfile: bool = False  # ops skill: Dockerfile present → ops-012 applies
    has_docker_compose: bool = False  # ops skill: docker-compose present → ops-013 resource check
    has_k8s_manifest: bool = False  # ops skill: k8s YAML present → ops-013 applies
    is_service: bool = False  # ops skill: True for web services; False for CLI tools and libraries
    deployment_type: str | None = (
        None  # ops skill deployment context
        # values: 'container', 'serverless', 'cli', or None
    )
    has_pii_schema: bool = False  # db-compliance skill: PII-suggestive columns detected in schema
    has_privacy_policy: bool = False  # db-compliance skill: privacy policy doc present in repo
    compliance_hints: list | None = None  # db-compliance skill: detected compliance signals
    # values: ['gdpr', 'hipaa', 'ccpa', 'coppa'] or [] or None
    service_type: str | None = (
        None  # pre-launch skill: service type for rule calibration
        # values: 'consumer', 'developer-tool', 'internal-service', 'library', or None
    )
    has_changelog: bool = False  # pre-launch skill: CHANGELOG.md or CHANGES.md present
    has_runbook: bool = False  # pre-launch skill: deployment runbook present
    changelog_convention: str | None = (
        None  # pre-launch skill: detected changelog format
        # values: 'keep-a-changelog', 'conventional', 'custom', or None
    )
    release_tooling: str | None = (
        None  # pre-launch skill: release automation detected
        # values: 'semantic-release', 'standard-version', 'release-it', 'manual', or None
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

    # Augment with web framework for backend-api skill dispatch
    result.web_framework = _detect_web_framework(path)

    # Augment with frontend framework for frontend-ux skill dispatch
    result.frontend_framework = _detect_frontend_framework(path)

    # Augment with monorepo type and architecture framework for architecture skill dispatch
    result.monorepo_type = _detect_monorepo_structure(path)
    result.architecture_framework = _detect_architecture_framework(path)

    # Augment with ops deployment context for ops skill dispatch
    ops_context = _detect_ops_context(path)
    result.has_dockerfile = ops_context["has_dockerfile"]
    result.has_docker_compose = ops_context["has_docker_compose"]
    result.has_k8s_manifest = ops_context["has_k8s_manifest"]
    result.is_service = ops_context["is_service"]
    result.deployment_type = ops_context["deployment_type"]

    # Augment with compliance context for database-compliance skill dispatch
    compliance_context = _detect_compliance_context(path)
    result.has_pii_schema = compliance_context["has_pii_schema"]
    result.has_privacy_policy = compliance_context["has_privacy_policy"]
    result.compliance_hints = compliance_context["compliance_hints"]

    # Augment with release context for pre-launch skill dispatch
    release_context = _detect_release_context(path)
    result.service_type = release_context["service_type"]
    result.has_changelog = release_context["has_changelog"]
    result.has_runbook = release_context["has_runbook"]
    result.changelog_convention = release_context["changelog_convention"]
    result.release_tooling = release_context["release_tooling"]

    return result


def _detect_by_files(path: Path) -> list[StackSignal]:
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


def _detect_ops_context(path: Path) -> dict:
    """Detect operational deployment context for ops skill dispatch.

    Returns dict with keys: has_dockerfile, has_docker_compose, has_k8s_manifest,
    is_service, deployment_type.
    """
    has_dockerfile = (path / "Dockerfile").exists() or any(path.glob("Dockerfile.*"))
    has_docker_compose = (path / "docker-compose.yml").exists() or (
        path / "docker-compose.yaml"
    ).exists()

    # k8s: look for YAML files with apiVersion: apps/v1 pattern
    has_k8s_manifest = False
    for k8s_dir in ["k8s", "kubernetes", "deploy", "infra"]:
        if (path / k8s_dir).exists():
            has_k8s_manifest = True
            break
    if not has_k8s_manifest:
        for yaml_file in list(path.glob("*.yaml")) + list(path.glob("*.yml")):
            try:
                content = yaml_file.read_text(encoding="utf-8", errors="ignore")
                if "apiVersion: apps/v1" in content or "kind: Deployment" in content:
                    has_k8s_manifest = True
                    break
            except OSError:
                pass

    # Service heuristic: has web_framework OR has_dockerfile
    # CLI heuristic: has no web_framework AND no Dockerfile AND has CLI entrypoint markers
    is_service = has_dockerfile
    # Refine: if pyproject.toml or setup.py without web framework, likely library/CLI
    for py_config in ["pyproject.toml", "setup.py"]:
        config_path = path / py_config
        if config_path.exists():
            try:
                content = config_path.read_text(encoding="utf-8", errors="ignore")
                if any(fw in content.lower() for fw in ["fastapi", "flask", "django", "starlette"]):
                    is_service = True
                    break
            except OSError:
                pass

    # Serverless: Cloudflare Workers / Vercel / AWS Lambda markers
    is_serverless = (
        (path / "wrangler.toml").exists()
        or (path / "wrangler.jsonc").exists()
        or (path / "vercel.json").exists()
        or (path / "serverless.yml").exists()
    )

    if is_serverless:
        deployment_type = "serverless"
    elif has_dockerfile:
        deployment_type = "container"
    elif not is_service:
        deployment_type = "cli"
    else:
        deployment_type = None

    return {
        "has_dockerfile": has_dockerfile,
        "has_docker_compose": has_docker_compose,
        "has_k8s_manifest": has_k8s_manifest,
        "is_service": is_service,
        "deployment_type": deployment_type,
    }


def _detect_compliance_context(path: Path) -> dict:
    """Detect compliance-relevant context for database-compliance skill dispatch.

    Returns dict with keys: has_pii_schema, has_privacy_policy, compliance_hints.
    """
    # PII schema: scan SQL migration files for PII-suggestive column names
    pii_signals = [
        "email",
        "phone",
        "name",
        "ssn",
        "dob",
        "date_of_birth",
        "address",
        "credit_card",
        "passport",
        "national_id",
        "medical_record",
        "biometric",
        "ip_address",
    ]
    has_pii_schema = False
    for sql_file in list(path.glob("**/migrations/*.sql")) + list(path.glob("**/*.sql")):
        if "node_modules" in str(sql_file) or ".venv" in str(sql_file):
            continue
        try:
            content = sql_file.read_text(encoding="utf-8", errors="ignore").lower()
            if any(sig in content for sig in pii_signals):
                has_pii_schema = True
                break
        except OSError:
            pass

    # Also check TypeScript/JS schema files (Prisma, Drizzle, TypeORM)
    if not has_pii_schema:
        for ts_file in list(path.glob("**/*.prisma")) + list(path.glob("**/schema.ts")):
            if "node_modules" in str(ts_file):
                continue
            try:
                content = ts_file.read_text(encoding="utf-8", errors="ignore").lower()
                if any(sig in content for sig in pii_signals):
                    has_pii_schema = True
                    break
            except OSError:
                pass

    # Privacy policy document
    has_privacy_policy = any(
        [
            (path / "PRIVACY.md").exists(),
            (path / "PRIVACY_POLICY.md").exists(),
            (path / "privacy-policy.md").exists(),
            (path / "docs" / "privacy.md").exists(),
            (path / "docs" / "privacy-policy.md").exists(),
            (path / "legal").is_dir(),
        ]
    )

    # Compliance hints from code, config, or package files
    hints: list = []
    hint_files = list(path.glob("*.toml")) + list(path.glob("*.json")) + list(path.glob("*.md"))
    for hf in hint_files[:20]:  # cap scan to avoid very large repos
        if "node_modules" in str(hf) or ".venv" in str(hf):
            continue
        try:
            content = hf.read_text(encoding="utf-8", errors="ignore").lower()
            if "gdpr" in content and "gdpr" not in hints:
                hints.append("gdpr")
            if "hipaa" in content and "hipaa" not in hints:
                hints.append("hipaa")
            if "ccpa" in content and "ccpa" not in hints:
                hints.append("ccpa")
            if "coppa" in content and "coppa" not in hints:
                hints.append("coppa")
        except OSError:
            pass

    return {
        "has_pii_schema": has_pii_schema,
        "has_privacy_policy": has_privacy_policy,
        "compliance_hints": hints,
    }


def _detect_release_context(path: Path) -> dict:
    """Detect release management context for pre-launch skill dispatch.

    Returns dict with keys: service_type, has_changelog, has_runbook,
    changelog_convention, release_tooling.
    """
    # has_changelog: common changelog file names
    changelog_names = ["CHANGELOG.md", "CHANGES.md", "HISTORY.md", "CHANGELOG.rst"]
    has_changelog = any((path / name).exists() for name in changelog_names)

    # changelog_convention: detect Keep a Changelog vs conventional commits
    changelog_convention = None
    for name in changelog_names:
        clog = path / name
        if clog.exists():
            try:
                content = clog.read_text(encoding="utf-8", errors="ignore")[:2000]
                if "## [Unreleased]" in content or "## [" in content:
                    changelog_convention = "keep-a-changelog"
                elif "### feat" in content or "### fix" in content or "### chore" in content:
                    changelog_convention = "conventional"
                else:
                    changelog_convention = "custom"
            except OSError:
                pass
            break

    # has_runbook: deployment/runbook documentation
    runbook_paths = [
        "RUNBOOK.md",
        "DEPLOYMENT.md",
        "docs/runbook.md",
        "docs/deployment.md",
        "docs/operations/deployment.md",
    ]
    has_runbook = any((path / p).exists() for p in runbook_paths)

    # release_tooling: detect automated release tools
    release_tooling = None
    for config_name in [".releaserc.json", ".releaserc.yaml", ".releaserc.yml"]:
        if (path / config_name).exists():
            release_tooling = "semantic-release"
            break
    if release_tooling is None:
        pkg_json = path / "package.json"
        if pkg_json.exists():
            try:
                content = pkg_json.read_text(encoding="utf-8", errors="ignore")
                if "@semantic-release" in content or '"semantic-release"' in content:
                    release_tooling = "semantic-release"
                elif "standard-version" in content:
                    release_tooling = "standard-version"
                elif "release-it" in content:
                    release_tooling = "release-it"
            except OSError:
                pass
    if release_tooling is None and (has_changelog or has_runbook):
        release_tooling = "manual"

    # service_type inference
    # consumer: has PII schema + auth patterns + public-facing web UI
    # developer-tool: has CLI entry points + no public user accounts
    # internal-service: has API but no public consumer surface
    # library: pure code artifact
    service_type = _infer_service_type(path)

    return {
        "service_type": service_type,
        "has_changelog": has_changelog,
        "has_runbook": has_runbook,
        "changelog_convention": changelog_convention,
        "release_tooling": release_tooling,
    }


def _infer_service_type(path: Path) -> str | None:
    """Infer service type for pre-launch rule calibration.

    Inference priority:
    1. Explicit override in pre_launch_config.yml
    2. Library signals (no main service entry, pure code package)
    3. Developer-tool signals (CLI + no public consumer UI)
    4. Consumer signals (user accounts + PII + public web)
    5. Internal-service (API but no public consumer surface)
    """
    # 1. Check project-level override
    for config_name in ["pre_launch_config.yml", "pre_launch_config.yaml"]:
        config_path = path / config_name
        if config_path.exists():
            try:
                content = config_path.read_text(encoding="utf-8", errors="ignore")
                for st in ["consumer", "developer-tool", "internal-service", "library"]:
                    if f"service_type: {st}" in content:
                        return st
            except OSError:
                pass

    # 2. Library signals: setup.py/pyproject + no main app + no web framework
    is_library = False
    for lib_signal in ["setup.py", "setup.cfg"]:
        if (path / lib_signal).exists():
            is_library = True
    if (path / "pyproject.toml").exists():
        try:
            content = (path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
            if "[tool.poetry]" in content or "[project]" in content:
                if "fastapi" not in content.lower() and "flask" not in content.lower():
                    is_library = True
        except OSError:
            pass

    # 3. Developer-tool signals: has CLI entry point, no public UI
    has_cli = False
    for cli_signal in ["interfaces/cli", "cmd/", "bin/", "src/cli"]:
        if (path / cli_signal).exists():
            has_cli = True
    if (path / "pyproject.toml").exists():
        try:
            content = (path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
            if "scripts" in content.lower() or "console_scripts" in content.lower():
                has_cli = True
        except OSError:
            pass

    # Check for public-facing web UI (consumer signal)
    has_web_ui = any(
        [
            (path / "src" / "app").exists(),
            (path / "src" / "pages").exists(),
            (path / "pages").exists(),
            (path / "app").exists() and (path / "app" / "page.tsx").exists(),
            (path / "next.config.js").exists(),
            (path / "next.config.ts").exists(),
        ]
    )

    # Check for PII/user data signals (consumer signal)
    pii_signals = ["email", "phone", "users", "contacts", "guests", "customers"]
    has_user_data = False
    for sql_file in list(path.glob("**/migrations/*.sql"))[:10]:
        try:
            content = sql_file.read_text(encoding="utf-8", errors="ignore").lower()
            if any(sig in content for sig in pii_signals):
                has_user_data = True
                break
        except OSError:
            pass

    # Decide
    if is_library and not has_web_ui and not has_user_data:
        return "library"
    if has_cli and not has_web_ui and not has_user_data:
        return "developer-tool"
    if has_web_ui or has_user_data:
        return "consumer"
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
        # Python project with no strong consumer signals → developer-tool default
        return "developer-tool"
    return "internal-service"


def _combine_signals(signals: list[StackSignal]) -> DetectedStack:
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
