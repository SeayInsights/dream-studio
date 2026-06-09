# Dream Studio Agents Reference

Domain-specific subagents registered in Claude Code.

**Source:** `canonical/agents/`  
**Install path:** `~/.claude/agents/`  
**Invocation:** `Agent(subagent_type="<name>", ...)` in skills and workflows

---

## Agent Catalog

### `accessibility-expert`
**When to use:** WCAG 2.2 accessibility audits and remediation on web interfaces.

Capabilities:
- Automated audit (axe-core scanning)
- Manual testing procedures
- WCAG 2.2 Level AA compliance reporting
- Remediation priority framework: Critical → High → Medium → Low
- Keyboard navigation and screen reader verification

Trigger keywords: `accessibility audit:`, `wcag check:`, `a11y review:`, `screen reader:`, `keyboard navigation:`

---

### `data-engineer`
**When to use:** dbt, data warehouse queries, pipeline orchestration, CDC patterns, schema migrations, data quality contracts.

Capabilities:
- dbt model authoring and debugging
- BigQuery, Snowflake, Redshift query optimization
- Airflow DAGs and Dagster assets
- Debezium CDC pattern design
- Schema migrations and data quality contracts

Trigger keywords: `dbt:`, `BigQuery:`, `Snowflake:`, `Redshift:`, `Airflow DAG:`, `Dagster asset:`, `Debezium:`, `CDC:`, `data pipeline:`, `warehouse SQL:`, `data engineering:`

---

### `devops-engineer`
**When to use:** CI/CD pipelines, OIDC auth, Docker builds, release automation, deployment gates.

Capabilities:
- GitHub Actions workflow design
- OIDC cloud authentication setup
- Docker build optimization
- Release automation and branch protection
- Deployment gates

Trigger keywords: `CI/CD pipeline:`, `GitHub Actions workflow:`, `Docker build:`, `release automation:`, `branch protection:`, `deployment gate:`

---

### `idea-validator`
**When to use:** Stress-testing product or feature ideas before committing resources.

Capabilities:
- Fatal flaw hunting
- Assumption inventory mapping
- Market reality check
- Competitive moat analysis
- Go/No-Go verdict with evidence standard

Trigger keywords: `validate idea:`, `stress-test:`, `fatal flaw:`, `product idea:`, `feature idea:`, `go no-go:`, `before committing resources:`

---

### `kubernetes-expert`
**When to use:** Production Kubernetes operations — debugging, resource design, Helm, RBAC.

Capabilities:
- CrashLoopBackOff / OOMKill (exit code 137) / Pending pod diagnosis
- Resource requests/limits and readiness/liveness probes
- Helm chart authoring
- RBAC and NetworkPolicy design
- HPA configuration

Trigger keywords: `k8s cluster issue:`, `workload design:`, `CrashLoopBackOff:`, `OOMKill:`, `Pending pods:`, `resource requests:`, `Helm chart:`, `RBAC:`, `NetworkPolicy:`, `HPA:`

---

### `mobile-developer`
**When to use:** iOS, Android, React Native, or Flutter development.

Capabilities:
- iOS (Swift/SwiftUI) and Android (Kotlin/Compose)
- React Native and Flutter cross-platform
- State management
- Native integrations
- App store submission

Trigger keywords: `iOS:`, `Android:`, `Swift:`, `SwiftUI:`, `Kotlin:`, `Compose:`, `React Native:`, `Flutter:`, `mobile app:`, `store submission:`, `cross-platform:`

---

### `research-analyst`
**When to use:** Market research, competitive analysis, evidence gathering requiring source hierarchy.

Capabilities:
- Source hierarchy (Tier 1 primary / Tier 2 secondary / Tier 3 opinion)
- Triangulation gate (3 independent sources minimum)
- Anti-sycophancy protocol
- Assumption inventory
- Explicit bias identification

Trigger keywords: `market research:`, `competitive analysis:`, `evidence gathering:`, `structured research:`, `source triangulation:`

---

### `technical-writer`
**When to use:** Technical documentation using the Diataxis framework.

Capabilities:
- Diataxis framework (tutorial / how-to / reference / explanation)
- Style rules and prose compression
- PR review with documentation feedback
- Automated linting

Trigger keywords: `technical documentation:`, `docs PR:`, `Diataxis:`, `README:`, `API reference:`, `documentation review:`, `changelog:`

---

### `terraform-architect`
**When to use:** Terraform IaC design, state management, drift detection.

Capabilities:
- Terraform module design
- Remote state management and multi-environment strategy
- Import workflow (TF 1.5+)
- Drift detection
- Provider version management

Trigger keywords: `Terraform:`, `infrastructure design:`, `IaC:`, `state problem:`, `Terraform module:`, `remote state:`, `drift detection:`

---

## Cross-references

- Skills (which invoke these agents): [`docs/reference/skills-index.md`](skills-index.md)
- Workflows (which invoke these agents): [`docs/reference/workflows.md`](workflows.md)
