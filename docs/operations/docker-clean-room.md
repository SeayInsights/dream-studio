# Docker Clean-Room Runtime Validation

Phase 8F introduces Docker only as an optional validation harness. It is not a runtime authority, deployment target, packaging decision, dashboard feature, cloud sync layer, adapter profile, or replacement for native local checks.

## What It Proves

The clean-room harness proves that this checkout can run local runtime validation from disposable isolated state:

- read-only runtime preflight
- read-only recovery dry-run
- schema migration replay tests
- runtime reliability tests

The harness uses isolated container state:

```text
HOME=/tmp/dream-studio-user
DREAM_STUDIO_HOME=/tmp/dream-studio-home
```

It does not mount the host `~/.dream-studio` directory and does not copy local runtime DB files into the image.

## What It Does Not Prove

Docker does not prove that the native local runtime DB is compatible with this checkout. Native preflight remains authoritative for the actual local machine state.

The known native condition remains:

- local runtime DB schema version: `36`
- checkout latest migration version: `34`

Docker must not be used to hide or reinterpret that condition. Run native preflight and recovery diagnostics when making local recovery decisions:

```powershell
python interfaces/cli/runtime_preflight.py --json
python interfaces/cli/runtime_recovery.py --dry-run --json
```

## How To Run

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 docker-runtime-check
```

Unix-like shells with GNU make:

```powershell
make docker-runtime-check
```

Both paths build `Dockerfile.runtime-check` and run:

```text
python scripts/docker_runtime_check.py
```

The container command runs:

```text
python interfaces/cli/runtime_preflight.py --json
python interfaces/cli/runtime_recovery.py --dry-run --json
python -m pytest tests/integration/test_schema_migrations.py -q
python -m pytest -m runtime_reliability -q
```

If Docker is unavailable, use the native validation gates and static Docker authority tests instead. Do not claim Docker validation passed unless the Docker command actually ran successfully.

GNU make is not required on Windows. The PowerShell path is the supported Windows equivalent for this validation harness.

## State Isolation Rules

The harness must not:

- mount `~/.dream-studio`
- mount, copy, inspect, migrate, restore, or delete the host `studio.db`
- mount, copy, inspect, migrate, restore, or delete host backup files
- add Docker Compose
- add Postgres, Redis, workers, cloud sync, or dashboard product features
- make Docker required for normal local use

`.dockerignore` excludes local runtime state patterns such as `.dream-studio/`, `studio.db`, and local backup names.

## Future Expansion

Future Docker work should remain phase-scoped:

- Phase 9: dashboard/API/projection boundary harness
- Phase 10: adapter/tool isolation
- Phase 14: packaging candidate
- Phase 15: distribution decision

Each expansion must keep local canonical runtime state authoritative unless a later contract explicitly changes that boundary.
