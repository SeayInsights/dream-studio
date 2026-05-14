# Dream Studio Database

Dream Studio uses local SQLite as structured operational authority where safe. The database stores runtime state, telemetry, read-model inputs, Work Orders, route decisions, artifacts, learning events, shared intelligence records, and release evidence.

The operator-local database is runtime state and must not be committed.

```text
~/.dream-studio/state/studio.db
```

Tests and validation should use temp or injected database paths for writes.

## Current Public Schema Direction

- Repo-backed migrations live under `core/event_store/migrations/`.
- Runtime bootstrap lives under `core/config/sqlite_bootstrap.py`.
- Canonical path resolution lives under `core/config/database.py`.
- Telemetry read models live under `core/telemetry/read_models.py`.
- Shared-intelligence authority lives under `core/shared_intelligence/`.

## Authority Rules

- Additive migrations are preferred.
- Live migrations require explicit approval, backup evidence, and rollback instructions.
- Dashboard/API responses are derived views.
- Database cleanup, retention deletion, compaction, and destructive migration require separate future approval.
- Local DB files, WAL/SHM files, backups, dumps, and raw telemetry stay out of Git.

See [docs/DATABASE.md](docs/DATABASE.md) for more detail.
