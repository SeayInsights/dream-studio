# Dream Studio

[![PR Smoke](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-yellow.svg)](LICENSE)

Dream Studio is a local-first AI orchestration and operational intelligence platform for goal-oriented work. It helps an operator turn goals into route-first milestones, Work Orders, validation evidence, telemetry, dashboard attention, and approval-aware release decisions.

Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP servers, shell tools, and local models are adapter surfaces. They can read and write projected context, but they do not own Dream Studio authority.

## What Dream Studio Provides

- Route-first milestones and Work Orders that continue internally until a real approval, blocker, validation, rollback, or release boundary appears.
- SQLite-backed authority for structured state, telemetry, decisions, artifacts, learning events, shared intelligence, and release gates.
- File-backed reports, handoffs, and audit packets as exports or evidence, not the default source of truth.
- Telemetry emitters and read models for route decisions, hooks, tools, skills, tokens, validations, security findings, workflows, research, decisions, and outcomes.
- A FastAPI and dashboard surface for derived operational intelligence, attention queues, module availability, drilldown entry points, and release readiness.
- Human-in-the-loop gates for live state mutation, database migration, cleanup, deletion, archive execution, push, tag, deploy, and material risk decisions.
- Adapter projections that can generate shared context packets and adapter-specific configuration without making any one AI tool the product identity.
- A Contract Atlas, maturity ledger, sanitized export lifecycle, and docs drift gate that map source changes to impacted contracts, runtime profiles, module boundaries, evidence-backed maturity status, public docs freshness obligations, and public-export leakage checks.
- Installed modular profiles, paused-by-default external project intake, optional Docker profile contracts, and long-run validation closeout that keep local-first operation usable without external mutation or container requirements.

## Current Public Architecture

Dream Studio keeps source, runtime state, and public documentation separate:

| Area | Role | Public repo? |
| --- | --- | --- |
| `core/`, `interfaces/`, `projections/`, `skills/`, `workflows/` | Product source and reusable orchestration logic | Yes |
| `docs/` | Public product, architecture, database, workflow, and operator guidance | Yes |
| `.claude-plugin/`, `.claude/` | Optional Claude Code adapter projection and local integration metadata | Yes, when sanitized |
| `~/.dream-studio/` or `.dream-studio/` runtime state | Operator-local SQLite DB, backups, Work Orders, handoffs, evidence, raw logs, and audit trails | No |
| Generated reports, cutover evidence, dogfood traces, raw telemetry, private decisions | Local evidence or exported packets | No by default |

See [docs/PUBLICATION_BOUNDARY.md](docs/PUBLICATION_BOUNDARY.md) for the publication allowlist and private-boundary policy.

## Quick Start For Local Development

```powershell
git clone https://github.com/SeayInsights/dream-studio.git
cd dream-studio
python -m pytest tests/unit/test_actual_dashboard_telemetry_routes.py -q --tb=line
```

Optional adapter setup is documented in [docs/quickstart.md](docs/quickstart.md). The Claude Code adapter is one supported surface, not the Dream Studio product boundary.

## Runtime State

Dream Studio runtime state belongs in the operator-local state directory, not in Git:

```text
~/.dream-studio/
  state/studio.db
  meta/
  backups/
```

Tests and local validation should use temp or injected database paths when they write. Live installed state and live SQLite should only be mutated by an explicitly approved milestone with backup and rollback evidence.

## Dashboard And Telemetry

The dashboard is a derived operational view. Its API responses should preserve:

- `derived_view: true`
- `primary_authority: false`
- `routing_authority: false`
- source tables and freshness metadata where applicable

Dashboard output is useful for attention and review, but it must not become routing authority.

## Documentation

- [Product Requirements](docs/product/dream-studio-prd.md)
- [Architecture](ARCHITECTURE.md)
- [Database](DATABASE.md)
- [Workflows](WORKFLOWS.md)
- [Operator Guide](docs/operator-guide.md)
- [Documentation Index](docs/README.md)
- [Publication Boundary](docs/PUBLICATION_BOUNDARY.md)
- [Repo Publication Privacy](docs/operations/repo-publication-privacy.md)
- [Installed Platform Productization](docs/operations/installed-platform-productization.md)
- [External Project Validation Pipeline](docs/operations/external-project-validation-pipeline.md)
- [Changelog](CHANGELOG.md)

## Release Boundary

Dream Studio should release through branch and pull request workflow. Direct pushes to `main`, force pushes, bypassing CI, deployment, live cleanup, and history rewrite all require explicit operator approval.

The current release gate expects:

- clean repo status;
- local CI parity validation as the heavy gate;
- CI test checks must use isolated Dream Studio runtime state instead of writing
  the operator-local SQLite authority;
- Contract Atlas documentation drift validation;
- Contract Atlas lifecycle and sanitized export validation;
- required GitHub PR smoke checks passing when Actions are available;
- manual full GitHub CI only when remote parity evidence is explicitly needed;
- no release blockers;
- private/local state excluded from the public repo;
- repo publication readiness validation for tracked files, Git history path
  privacy, README/PRD alignment, and sanitized public exports;
- Apache-2.0 license consistency;
- explicit approval before push, tag, merge, deploy, cleanup, or history rewrite.

GitHub Actions are a lightweight remote confidence layer. Disabled,
unavailable, or unaffordable Actions should not block local development; they
create a remote-confidence gap that requires manual review before merge or
release approval.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Keep changes scoped, evidence-backed, and tested with temp runtime state where writes are required.

## License

Apache-2.0. See [LICENSE](LICENSE).
