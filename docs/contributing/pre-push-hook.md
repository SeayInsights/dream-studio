# Pre-Push Hook

The Dream Studio pre-push hook (`hooks/git/pre-push`) runs automatically before
every `git push`. It is installed to `.git/hooks/pre-push` when you run
`ds integrate install claude_code --execute` from the repo root.

## What It Checks

Twenty gates run in order (cheapest first). A failure in any gate blocks the
push. The ones you are most likely to meet:

| Gate | Command | What it catches |
|------|---------|-----------------|
| `format-check` | `py -m black --check .` | Unformatted Python files |
| `lint-check` | `py interfaces/cli/lint_baseline.py check` | New lint findings beyond pinned baseline |
| `skill-sync` | `py -m core.gates.skill_sync_source` | CLI references in the enforcement block (A4/A5 invariant) |
| `test-suite` | `py -m pytest tests/evals -q` | Eval regressions (runtime-scoped: full unit suite takes ~79 min on Windows, too slow for pre-push) |
| `test-list-completeness` | `py -m core.gates.test_list_completeness` | Hardcoded pre-merge test lists naming files that no longer exist |
| `locale-decode` | `py -m core.gates.locale_decode_gate` | `subprocess(..., text=True)` with no `encoding=` — output silently lost to the platform codec |
| `atlas-leak` | `py interfaces/cli/contract_atlas_lifecycle_gate.py` | PRD/contract leakage into unauthorized surfaces |
| `docs-drift` | `py interfaces/cli/contract_docs_drift_gate.py` | Docs/code reference drift |
| `migration-risk` | `py -m core.gates.migration_risk` | Migration-class changes pushed without the matrix-watch acknowledgement |

`canonical/workflows/pre-push.yaml` is the authority for the full list — it also
carries the architectural rule gates (`rule1`–`rule4`, `authority-boundary`),
`pin-tests`, `unit-collect`, `revert-format`, `rubric-immutability`,
`test-fixture-resurrection`, and `leanness`. Each entry has its own
`description` and `fail_hint`; read the manifest rather than this table when a
gate you do not recognise blocks a push.

## If a Gate Blocks Your Push

**format-check:** Run `py -m black .` to auto-fix, then re-push.

**lint-check:** Run `py interfaces/cli/lint_baseline.py check` to see findings.
Fix them, or update the baseline with `py interfaces/cli/lint_baseline.py update`
if they are intentional.

**skill-sync:** The `_ENFORCEMENT_BLOCK` constant in the compiler has regressed
back to CLI references. Restore the function-call form per the A4/A5 invariant.

**test-suite:** Fix the failing eval in `tests/evals/` before re-pushing.

**locale-decode:** Add `encoding="utf-8", errors="replace"` to the subprocess
call the gate names. `text=True` on its own decodes the child's output with the
platform locale codec (cp1252 on Windows), and on an unmapped byte — a `❌` or a
`←` in the output is enough — the reader thread dies, `run()` returns
`returncode=0`, and `stdout` comes back as `None`. The caller is handed success
with no output. If a call is deliberately unguarded (only the gate's own test
should be), mark its line `# locale-decode-gate: intentional — <why>`; the gate
prints every exemption, so it never becomes invisible.

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
