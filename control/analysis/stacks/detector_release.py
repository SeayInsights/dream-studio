"""Ops, compliance, and release-context detectors for stack detection.

WO-GF-CONTROL-INSTALL-split: see detector.py facade docstring.
"""

from __future__ import annotations

from pathlib import Path


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
