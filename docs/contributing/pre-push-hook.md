# Pre-Push Hook

The Dream Studio pre-push hook (`hooks/git/pre-push`) runs automatically before
every `git push`. It is installed to `.git/hooks/pre-push` when you run
`ds integrate install claude_code --execute` from the repo root.

## What It Checks

Six gates run in order (cheapest first). A failure in any gate blocks the push.

| Gate | Command | What it catches |
|------|---------|-----------------|
| `format-check` | `py -m black --check .` | Unformatted Python files |
| `lint-check` | `py interfaces/cli/lint_baseline.py check` | New lint findings beyond pinned baseline |
| `skill-sync` | `py -m core.gates.skill_sync_source` | CLI references in the enforcement block (A4/A5 invariant) |
| `test-suite` | `py -m pytest tests/evals -q` | Eval regressions (runtime-scoped: full unit suite takes ~79 min on Windows, too slow for pre-push) |
| `atlas-leak` | `py interfaces/cli/contract_atlas_lifecycle_gate.py` | PRD/contract leakage into unauthorized surfaces |
| `docs-drift` | `py interfaces/cli/contract_docs_drift_gate.py` | Docs/code reference drift |

The full workflow definition is in `canonical/workflows/pre-push.yaml`.

## If a Gate Blocks Your Push

**format-check:** Run `py -m black .` to auto-fix, then re-push.

**lint-check:** Run `py interfaces/cli/lint_baseline.py check` to see findings.
Fix them, or update the baseline with `py interfaces/cli/lint_baseline.py update`
if they are intentional.

**skill-sync:** The `_ENFORCEMENT_BLOCK` constant in the compiler has regressed
back to CLI references. Restore the function-call form per the A4/A5 invariant.

**test-suite:** Fix the failing eval in `tests/evals/` before re-pushing.

**atlas-leak:** Check `docs/contracts/` for unauthorized surface references.
See the contract-atlas docs for resolution steps.

**docs-drift:** Run `py interfaces/cli/contract_docs_drift_gate.py` to see which
doc references have drifted. Update docs or the drift baseline as appropriate.

## Bypass the Hook (Single Push)

```bash
git push --no-verify
```

Use this only in emergencies. Document why in your PR description and fix
the underlying gate failure in the next commit.

## Disable the Hook Permanently

Add `skip_hook_install` to `~/.dream-studio/config.json`:

```json
{
  "skip_hook_install": true
}
```

Then re-run the installer to remove the hook:

```powershell
ds integrate install claude_code --execute
```

The installer will print a confirmation that hook installation was skipped.
To re-enable, remove the key and run the installer again.
