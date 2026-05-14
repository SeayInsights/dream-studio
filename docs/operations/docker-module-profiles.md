# Dream Studio Docker Module Profiles

Lifecycle status: draft_generated

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

Suggested profile names:

- `security-scanners`
- `agent-workers`
- `workflow-workers`
- `validation-sandboxes`
- `dashboard-api`
- `adapters`

Each profile should bind or configure the approved SQLite path explicitly. No
profile should create a competing authority database by default.

## Fallback Modes

When Docker is unavailable:

- core telemetry writes continue through local SQLite
- module registry marks Docker-backed modules as `enabled=false` or
  `execution_mode=local_unavailable`
- dashboard modules display empty-state behavior
- validation sandboxes fall back to approved local tests

## Boundaries

This document does not start containers, build images, add dependencies, or
enable dashboard/API runtime behavior. Docker profile implementation requires a
separate approved runtime milestone.
