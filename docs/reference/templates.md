# Dream Studio Templates Reference

Template catalog for skills, workflows, security tooling, and project scaffolding.

---

## Skill Templates

**Source:** `skills/templates/`  
Blueprint files for creating new dream-studio skills.

| Template | Purpose |
|----------|---------|
| `config.yml.template` | Thresholds, model defaults, behavior flags, performance budgets |
| `metadata.yml.template` | Full skill metadata: name, version, pack, status, dependencies, tags, compatibility |
| `pack-router-template.md` | Pack-level `SKILL.md` template for mode dispatch routing |

---

## Workflow Templates

**Source:** `canonical/workflows/`  
25 parameterized YAML workflows. See [`docs/reference/workflows.md`](workflows.md) for the full catalog.

**Workflow YAML structure:**

```yaml
version: "1.0"
on_failure: stop|continue
gates:
  - id: gate-name
    type: pause|approval
nodes:
  - id: node-name
    skill: pack:mode
    model: sonnet|haiku|opus
    context: { ... }
    timeout: 300
    estimated_tokens: 5000
    depends_on: [other-node]
    input: { ... }
    output_compress: true|false
    retry:
      max: 1
    trigger_rule: all_done
```

---

## Work Order Type Templates

**Source:** Migration `049_work_order_type.sql` — `business_work_order_types` table  
10 canonical work order types with pre-defined gate and executor contracts.

| Type | Pre-build gate | Build executor | Post-build gate |
|------|---------------|----------------|----------------|
| `ui_component` | `design_brief_locked` | `fullstack:frontend` | `design_critique` |
| `ui_page` | `design_brief_locked` | `website:page` | `design_critique` |
| `api_endpoint` | `api_contract_exists` | `fullstack:backend` | `security_scan` |
| `authentication` | `api_contract_and_security_review` | `fullstack:backend` | `security_scan` |
| `saas_feature` | `api_contract_exists` | `saas-build` | `security_scan` |
| `data_pipeline` | — | `fullstack:backend` | `security_scan` |
| `game_mechanic` | `spec_approved` | `game-dev` | `game_validate` |
| `deployment` | `all_tests_pass` | `devops-engineer` | `security_scan` |
| `infrastructure` | — | `devops-engineer` | `security_scan` |
| `documentation` | — | `core:build` | — |

---

## Design Brief Template

**Source:** Migration `053_design_brief.sql` — `business_design_briefs` table  
Created per-project, locked before UI work begins.

| Field | Values |
|-------|--------|
| `status` | `draft` → `locked` |
| `design_system` | `tech-minimal`, `editorial-modern`, `brutalist-bold`, `playful-rounded`, `executive-clean` |
| `purpose` | Project purpose |
| `audience` | Target audience |
| `tone` | Communication tone |
| `font_pairing` | Typography selection |
| `brand_tokens` | Color/spacing/radius tokens |

Create: `ds design-brief create <project_id>`  
Lock: `ds design-brief lock <brief_id>`

---

## Security Templates

**Source:** `templates/security/`  
Jinja2 templates for security tool configuration, rendered by `ds-security` pack.

| Category | Templates |
|----------|-----------|
| Binary analysis | `analyze.sh.j2`, `checksec-config.yaml.j2`, `yara-rules.yar.j2` |
| DAST | `nuclei-config.yaml.j2`, `zap-config.yaml.j2` |
| Semgrep rules | `access-control.yaml.j2`, `data-protection.yaml.j2`, `injection.yaml.j2`, `netcompat.yaml.j2`, `secrets.yaml.j2`, `transport.yaml.j2` |
| GitHub Actions | `binary-scan.yml.j2`, `dast-scan.yml.j2`, `security-scan.yml.j2` |
| Compliance mappings | `cwe-top25-mapping.yaml`, `nist-csf-mapping.yaml`, `owasp-asvs-mapping.yaml`, `soc2-mapping.yaml` |
| Mitigations | `auth-fixes.yaml`, `encryption-fixes.yaml`, `injection-fixes.yaml`, `netcompat-fixes.yaml`, `secrets-fixes.yaml` |

---

## Project Standards Template

**Source:** `packs/domains/templates/project-standards/`  
Scaffolded into new projects by `ds-domains:saas-build` and related modes.

| File | Purpose |
|------|---------|
| `.coveragerc` | pytest coverage config |
| `.pre-commit-config.yaml` | Pre-commit hooks configuration |
| `Makefile` | Common project tasks |
| `pyproject.toml` | Package configuration |
| `requirements*.txt` | Dependency pins |
| `git-hooks/audit.py` | Hook audit utilities |
| `git-hooks/models.py` | Hook data models |
| `git-hooks/time_utils.py` | Timestamp utilities |
| `git-hooks/telemetry.py` | Hook telemetry |
| `CONTRIBUTING.md` | Contribution guidelines |
| `SECURITY.md` | Security policy |
| `README.md` | Project README |

---

## Skill Output Templates

**Source:** `canonical/skills/*/templates/`  
Agent prompts and output format blueprints used by skills internally.

| Template | Used by |
|----------|---------|
| `implementer.md` | Implementation agent prompt |
| `reviewer.md` | Code review agent prompt |
| `tdd-loop.md` | TDD loop agent prompt |
| `checkpoint.md` | Milestone checkpoint format |
| `plan-format.md` | Implementation plan output format |
| `findings-report.md` | Audit findings report format |
| `output-format.md` | Generic skill output format |
| `spec-template.md` | Specification document template |
| `design-template.md` | Design document template |
| `deployment-runbook.md` | Deployment runbook template |

---

## Dashboard Template

**Source:** `interfaces/cli/ds_analytics/templates/dashboard.html.j2`  
Jinja2 template for the analytics dashboard UI. Served by `ds dashboard --serve`.

---

## Cross-references

- Work order types and gate contracts: [`docs/reference/schema.md`](schema.md) — `business_work_order_types`
- Workflow execution: [`docs/reference/workflows.md`](workflows.md)
- Security scan: [`docs/reference/guardrails.md`](guardrails.md)
- Gates for work order closure: [`docs/reference/gates.md`](gates.md)
