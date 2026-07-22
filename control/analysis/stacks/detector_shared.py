"""Shared dataclasses for stack detection.

WO-GF-CONTROL-INSTALL-split: implementation moved to detector_{shared,signals,
dispatch,release,core}.py; control/analysis/stacks/detector.py re-exports the
public+private surface so existing `from control.analysis.stacks.detector import X`
callers are unchanged.
"""

from __future__ import annotations

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
