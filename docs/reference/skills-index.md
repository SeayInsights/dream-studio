# Dream Studio Skills Index

Complete reference for all packs, modes, and routing triggers.

**Source of truth:** `packs.yaml`, `canonical/skills/`  
**Install path:** `~/.claude/skills/`  
**Invocation:** `Skill(skill="ds-<pack>", args="<mode>")` or `ds skill invoke <pack>:<mode>`

---

## Pack × Mode Matrix

| Pack | Skill ID | Modes | Mode Count |
|------|----------|-------|-----------|
| **core** | `ds-core` | think, plan, build, review, verify, ship, handoff, recap, explain | 9 |
| **quality** | `ds-quality` | debug, polish, harden, pr-security-scan, structure-audit, learn, coach, audit, security, accessibility, database, code-quality, testing, types-deps, backend-api, frontend-ux, architecture, ops, database-compliance, pre-launch | 20 |
| **analyze** | `ds-analyze` | multi, domain-re, repo, intelligence, research, idea-validation | 6 |
| **domains** | `ds-domains` | game-dev, saas-build, mcp-build, dashboard-dev, client-work, design, fullstack, website, devops, kubernetes, technical-writing, terraform, mobile, data-engineering | 14 |
| **workflow** | `ds-workflow` | _(orchestration infrastructure — no discrete modes)_ | — |
| **security** | `ds-security` | scan, dast, binary-scan, mitigate, comply, netcompat, dashboard, review | 8 |
| **ds-project** | `ds-project` | scope, resume, brief, manage | 4 |
| **ds-workorder** | `ds-workorder` | start, execute, close, block, status | 5 |
| **ds-milestone** | `ds-milestone` | status, close | 2 |
| **ds-website** | `ds-website` | discover, direction, page, prototype, animate, brand, cip, critique, deck | 9 |
| **ds-fullstack** | `ds-fullstack` | frontend, backend, integrate, secure | 4 |
| **ds-setup** | `ds-setup` | wizard, status, jit | 3 |

**Total: 12 packs, 84 modes**

---

## Routing Trigger Table

Triggers appear in user messages to auto-route to the correct pack and mode.

### Build Lifecycle — `ds-core`

| Trigger keywords | Mode |
|-----------------|------|
| `think:`, `spec:`, `shape ux:`, `design brief:`, `research:` | think |
| `plan:`, `/plan:` | plan |
| `build:`, `execute plan:` | build |
| `review:`, `review code:`, `review PR:` | review |
| `verify:`, `prove it:` | verify |
| `ship:`, `pre-deploy:`, `deploy:` | ship |
| `handoff:` | handoff |
| `recap:`, `session recap:` | recap |
| `explain:`, `how does:`, `walk me through:`, `what is this doing:`, `why does:` | explain |

### Code Quality — `ds-quality`

| Trigger keywords | Mode |
|-----------------|------|
| `debug:`, `diagnose:` | debug |
| `polish:` | polish |
| `harden:` | harden |
| `pr-security-scan:` | pr-security-scan |
| `structure-audit:` | structure-audit |
| `learn:` | learn |
| `coach:` | coach |
| `audit:` | audit |
| `security audit:`, `check security:`, `check codebase security:`, `enforce security:` | security |
| `accessibility audit:`, `wcag check:`, `a11y review:`, `screen reader:`, `keyboard navigation:` | accessibility |
| `database audit:`, `check schema:`, `check migrations:`, `db audit:`, `generate migration:`, `design schema:` | database |
| `code-quality audit:`, `cq audit:`, `check code quality:` | code-quality |
| `testing audit:`, `check tests:`, `test audit:`, `generate tests:`, `write tests:` | testing |
| `types audit:`, `deps audit:`, `dependency audit:`, `type safety:`, `annotation coverage:` | types-deps |
| `backend-api:` | backend-api |
| `frontend-ux:` | frontend-ux |
| `architecture:` | architecture |
| `ops:` | ops |
| `database-compliance:` | database-compliance |
| `pre-launch:` | pre-launch |

### Analysis Engine — `ds-analyze`

| Trigger keywords | Mode |
|-----------------|------|
| `multi:` | multi |
| `domain-re:` | domain-re |
| `repo:` | repo |
| `analyze project:`, `project intelligence:`, `scan codebase:` | intelligence |
| `market research:`, `competitive analysis:`, `evidence gathering:`, `structured research:` | research |
| `validate idea:`, `stress-test:`, `fatal flaw:`, `product idea:`, `feature idea:`, `go no-go:` | idea-validation |

### Domain Builders — `ds-domains`

| Trigger keywords | Mode |
|-----------------|------|
| `game-dev:` | game-dev |
| `saas-build:` | saas-build |
| `mcp-build:` | mcp-build |
| `dashboard-dev:` | dashboard-dev |
| `intake:`, `sow:`, `proposal:`, `build report:`, `review powerbi:`, `optimize dax:`, `build flow:`, `build app:`, `client handoff:`, `document:` | client-work |
| `design:` | design |
| `fullstack:`, `build fullstack:`, `fullstack frontend:`, `fullstack backend:`, `full-stack:`, `full stack:` | fullstack |
| `website:`, `build website:`, `landing page:`, `build page:`, `prototype app:`, `pitch deck:`, `animate:`, `build site:` | website |
| `CI/CD pipeline:`, `GitHub Actions workflow:`, `Docker build:`, `release automation:`, `branch protection:`, `deployment gate:` | devops |
| `k8s cluster issue:`, `workload design:`, `CrashLoopBackOff:`, `OOMKill:`, `Pending pods:`, `resource requests:`, `Helm chart:`, `RBAC:`, `NetworkPolicy:`, `HPA:` | kubernetes |
| `technical documentation:`, `docs PR:`, `Diataxis:`, `README:`, `API reference:`, `documentation review:`, `changelog:` | technical-writing |
| `Terraform:`, `infrastructure design:`, `IaC:`, `state problem:`, `Terraform module:`, `remote state:`, `drift detection:` | terraform |
| `iOS:`, `Android:`, `Swift:`, `SwiftUI:`, `Kotlin:`, `Compose:`, `React Native:`, `Flutter:`, `mobile app:`, `store submission:` | mobile |
| `dbt:`, `BigQuery:`, `Snowflake:`, `Redshift:`, `Airflow DAG:`, `Dagster asset:`, `Debezium:`, `CDC:`, `data pipeline:`, `warehouse SQL:`, `data engineering:` | data-engineering |

### Workflow Orchestration — `ds-workflow`

| Trigger keywords | Mode |
|-----------------|------|
| `workflow:`, `run workflow:`, `idea-to-pr:`, `studio-onboard:`, `feature-research:`, `start workflow:`, `execute work orders:`, `run the clean-state loop:` | _(route to workflow runner)_ |

### Security Analysis — `ds-security`

| Trigger keywords | Mode |
|-----------------|------|
| `scan:` | scan |
| `dast:` | dast |
| `binary-scan:` | binary-scan |
| `mitigate:` | mitigate |
| `comply:` | comply |
| `netcompat:` | netcompat |
| `dashboard:` | dashboard |
| `review:` | review |

### Project Lifecycle — `ds-project`

| Trigger keywords | Mode |
|-----------------|------|
| `scope project:`, `ds project scope:`, `create prd:` | scope |
| `resume:`, `continue:`, `what's next:`, `where was I:`, `what am I working on:`, `start building:` | resume |
| `design brief:`, `fill brief:`, `brief:`, `lock brief:` | brief |
| `list projects:`, `switch project:`, `archive project:`, `delete project:` | manage |

### Work Order Lifecycle — `ds-workorder`

| Trigger keywords | Mode |
|-----------------|------|
| `start work order:`, `begin work order:` | start |
| `mark task done:`, `task done:`, `complete task:` | execute |
| `close work order:`, `finish work order:` | close |
| `block:`, `blocked by:` | block |
| `work order status:`, `show tasks:` | status |

### Milestone Lifecycle — `ds-milestone`

| Trigger keywords | Mode |
|-----------------|------|
| `milestone status:`, `milestone progress:` | status |
| `close milestone:`, `milestone done:` | close |

### Website Builder — `ds-website`

| Trigger keywords | Mode |
|-----------------|------|
| `discover:` | discover |
| `direction:` | direction |
| `page:` | page |
| `prototype:` | prototype |
| `animate:` | animate |
| `brand:` | brand |
| `cip:` | cip |
| `critique:` | critique |
| `deck:` | deck |

### Fullstack Builder — `ds-fullstack`

| Trigger keywords | Mode |
|-----------------|------|
| `frontend:` | frontend |
| `backend:` | backend |
| `integrate:` | integrate |
| `secure:` | secure |

### Setup — `ds-setup`

| Trigger keywords | Mode |
|-----------------|------|
| `wizard:` | wizard |
| `status:` | status |
| `jit:` | jit |

---

## Routing Fallback

If no trigger keyword matches, route to `ds-quality` with arg `coach`. Coach classifies the intent, maps it to the nearest pack and mode, and explains confidence + alternatives.

---

## Cross-references

- Skill API contract: [`docs/reference/skill-api-map.md`](skill-api-map.md)
- Layer map: [`docs/reference/layer-map.md`](layer-map.md)
- Agents: [`docs/reference/agents.md`](agents.md)
- Hooks: [`docs/reference/hooks.md`](hooks.md)
