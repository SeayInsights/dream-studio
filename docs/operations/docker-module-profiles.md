# Dream Studio Docker Module Profiles

Lifecycle status: tested_only

Docker is optional for Dream Studio core. The local-first SQLite authority model
must work without Docker.

## Intended Roles

Docker may support:

- repeatable local/dev execution
- optional module isolation
- security scanner isolation
- worker or adapter isolation
- dashboard/API service profiles when explicitly enabled
- future team/department deployment consistency
- validation sandboxes

## Profile Concepts

Current optional profile contracts:

- `security-scanners`
- `agent-workers`
- `workflow-workers`
- `validation-sandboxes`
- `dashboard-api`
- `adapters`

Each profile should bind or configure the approved SQLite path explicitly. No
profile should create a competing authority database by default.

Each profile declares:

- enabled modules
- required mounts
- explicit SQLite authority path policy
- secrets/config handling
- network exposure
- read/write boundaries
- telemetry emitted
- fallback when Docker is unavailable
- validation requirements
- approval requirements

## Fallback Modes

When Docker is unavailable:

- core telemetry writes continue through local SQLite
- module registry marks Docker-backed modules as `enabled=false` or
  `execution_mode=local_unavailable`
- dashboard modules display empty-state behavior
- validation sandboxes fall back to approved local tests

## Boundaries

This document does not start containers. The static profile tests also do not
start containers, build images, add dependencies, or enable dashboard/API runtime behavior. Docker
execution requires a separate explicit operator approval. Docker must never own
Dream Studio authority, create a competing SQLite database, or become required
for core, analytics-only, security-only, dashboard, shared-intelligence,
adapter-router, or local-first operation unless a future profile explicitly
enables and approves that runtime.

Release-gate validation for Docker profile contracts runs without Docker and
with isolated temporary Dream Studio runtime state. A passing release gate does
not imply container execution, host mounts, network exposure, or access to the
active installed SQLite database.

## SQLite Mount Policy

Container profiles receive an explicit host SQLite authority path when approved.
The default is no host-state mount. Any writable work belongs in container-local
temporary state unless a later approved runtime Work Order scopes a write
boundary. A container-local database may be used only as temporary scratch, not
as Dream Studio authority.

## Validation

The static validation suite checks that every Docker profile is optional,
declares fallback behavior, does not mount host state by default, does not
create an authority database, uses an explicit SQLite authority path, and
forbids host writes by default.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->
