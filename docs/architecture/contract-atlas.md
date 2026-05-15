# Contract Atlas

Lifecycle status: foundation_active

The Contract Atlas is Dream Studio's private-by-default map of its own system
contracts. It explains what each layer, module, interface, runtime profile, and
adapter projection is allowed to own, what it can only derive, and which docs
must be refreshed when meaningful source changes occur.

## Authority Boundary

The Contract Atlas is a derived view. It does not create routing authority,
database authority, cleanup authority, adapter execution authority, or release
approval.

Current implementation:

- `core/shared_intelligence/contract_atlas.py` builds the atlas read model.
- `core/shared_intelligence/contract_registry.py` defines the contract domains
  and changed-file-to-docs impact mapping.
- `/api/shared-intelligence/contract-atlas` exposes the atlas for local
  dashboard and tooling consumption.
- If no `project_id` is supplied, the Contract Atlas defaults to the local
  Dream Studio project scope (`dream-studio`) so adapter projection staleness is
  compared against the same generated project-scoped files used by the active
  clean checkout. Callers can still pass an explicit `project_id` for scoped
  inspection.
- `interfaces/cli/contract_docs_drift_gate.py` blocks release closure when
  impacted contracts or docs are stale.

## Registry Foundation

The registry currently tracks these release-blocking domains:

- Contract Atlas
- Shared intelligence and adapter projections
- SQLite schema and authority
- Installed adapter runtime and global router
- Dashboard runtime and read models
- Workflow and hook runtime
- Security-by-default lifecycle gate
- Release gate and publication boundary

Each domain declares:

- source patterns;
- contract refs;
- documentation refs;
- required docs that must be refreshed with meaningful source changes;
- public/private export boundary;
- freshness policy.

## Maturity Ledger

The atlas includes a current maturity ledger for major Dream Studio areas. Each
area is classified as one of:

- `hardened`
- `runtime_validated`
- `tested_only`
- `designed_not_proven`
- `stale`
- `blocked`
- `not_started`
- `manual_review_required`

Every ledger row must include evidence refs, validation refs, owner/source,
known gaps, next action, whether it can be claimed publicly, and whether it can
be used operationally. This prevents Dream Studio from claiming live Claude,
Codex, Docker, external-project, or release behavior that is only designed or
tested in isolation.

The installed runtime model and module profiles are now first-class atlas
sections. They declare the source/state split, global command surface,
adapter-router read model, and per-profile dependency expectations so installed
Dream Studio behavior is visible without making the atlas an installer,
mutator, or live-state authority.

The security lifecycle gate is also a first-class atlas section. It maps the
47 enterprise security controls to the security review catalog, security skill,
project health, and release readiness while preserving the non-execution
boundary.

## Drift Gate

The drift gate checks changed files against the registry. If source changes
impact a domain, the required contract or docs refs for that domain must be in
the same change set. This keeps Dream Studio from closing work that changed
code, schema, dashboard routes, workflows, hooks, adapters, or release behavior
while leaving the matching public docs stale.

The gate distinguishes:

- docs update required;
- docs reviewed and no change needed;
- PRD update required;
- README update required;
- Contract Atlas update required;
- publication boundary review required;
- private artifact risk detected.

The gate is intentionally scoped. It does not rewrite every doc blindly and it
does not require PRD updates for implementation details that do not change
product authority.

## Export Boundary

The private atlas may include local repo paths and local surface status. Public
exports must be sanitized and must not include private runtime state, local
evidence paths, secrets, raw telemetry, backups, or operator-local config
contents.

## Visual Layer

The current milestone establishes the foundation and release gate. A later
visual Contract Atlas dashboard can render the same registry, graph, scorecard,
and boundary report without inventing new dependency data.
