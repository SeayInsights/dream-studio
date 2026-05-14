# Windows Development Commands

Dream Studio keeps the `Makefile` for Unix-like environments. On Windows, make is not required for normal development or Phase 8 validation. Use the PowerShell command surface instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 <target>
```

## Core Targets

| Target | PowerShell | Makefile equivalent |
| --- | --- | --- |
| Install dev dependencies | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 install-dev` | `make install-dev` |
| Test | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test` | `make test` |
| Guarded test | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test-guarded` | none |
| Lint | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 lint` | `make lint` |
| Format | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 fmt` | `make fmt` |
| Security audit | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 security` | `make security` |
| Runtime reliability | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 runtime-check` | `make runtime-check` |
| Guarded runtime verification | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify-guarded` | none |
| Product readiness baseline | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 product-readiness` | none |
| Docker clean-room check | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 docker-runtime-check` | `make docker-runtime-check` |
| Setup check | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 setup-check` | `make setup-check` |
| Dashboard check | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 dashboard-check` | `make dashboard-check` |

## Additional Windows Targets

These targets are Windows-native aliases for common development operations:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 typecheck
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 run-api
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 run-ui
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 clean
```

- `verify` runs the focused runtime gates: schema migrations, runtime reliability, and hook runtime reliability.
- `verify-guarded` runs the same focused runtime gates under `scripts/runtime_state_hash_guard.py`.
- `test-guarded` runs the full test target under `scripts/runtime_state_hash_guard.py`.
- `lint` runs Black in check mode and compares flake8 output to the committed lint baseline. Existing baseline debt is reported but does not block unless it increases.
- `product-readiness` runs the narrow static Phase 15 readiness baseline guardrails. It does not replace hash-guarded `verify` or `test`.
- `typecheck` runs `pyright` when available, or `npx pyright` when Node tooling is available. If neither is installed, the command fails with an explicit setup message.
- `run-api` starts `projections.api.main:app` through `uvicorn`.
- `run-ui` launches the dashboard through `interfaces/cli/ds_dashboard.py`.
- `clean` removes local Python and test cache artifacts inside the repository only.

Guarded targets are optional validation ergonomics. They fail if the native local
runtime DB or local backup files change during validation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify-guarded
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test-guarded
```

Use guarded targets when validating local runtime hardening or when the native DB
has known version skew. They do not repair, restore, downgrade, or migrate local
runtime state.

## Docker Clean-Room Validation

On Windows, run the Docker clean-room harness without make:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 docker-runtime-check
```

This performs the same build and run steps as the Makefile target:

```powershell
docker build -f Dockerfile.runtime-check -t dream-studio-runtime-check .
docker run --rm --network none -e HOME=/tmp/dream-studio-user -e DREAM_STUDIO_HOME=/tmp/dream-studio-home dream-studio-runtime-check
```

The container command still uses isolated state only. It must not mount the host `.dream-studio` directory or the native runtime DB.

## Translation Notes

No Makefile target currently requires GNU make semantics that cannot be represented in PowerShell.

Targets that start long-running processes, such as `run-api`, `run-ui`, and `dashboard`, remain foreground commands. Stop them with `Ctrl+C`.
