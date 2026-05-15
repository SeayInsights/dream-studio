# Lightweight GitHub CI Strategy

Dream Studio uses local validation as the heavy release gate and GitHub Actions
as a lightweight remote confidence layer. GitHub workflows should protect PRs
without burning a full matrix on every push.

## Workflow Profiles

| Workflow | Trigger | Purpose | Cost posture |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` | pull request, manual | Cheap PR smoke: docs drift, Contract Atlas lifecycle, format, lint baseline, focused release/atlas tests | Required remote confidence |
| `.github/workflows/full-ci.yml` | manual only | Remote run of `python interfaces/cli/ci_gate.py` when an operator wants GitHub-hosted parity evidence | Operator-triggered heavy check |
| `.github/workflows/release-validation.yml` | manual or `v*` tag | Release-candidate evidence; runs the local release gate and release profile tests | Release-only evidence |
| `.github/workflows/validate-skills.yml` | PRs changing `skills/**/*.md` | Path-scoped skill standards validation | Optional/path-scoped |

The required branch-protection check is `pr-smoke`. Full CI and release
validation are not required on every PR by default.

## Local Parity

The local heavy gate remains:

```powershell
python scripts/runtime_state_hash_guard.py --label local_release_gate -- python interfaces/cli/ci_gate.py
```

That gate runs the full test suite, format check, lint baseline, Contract Atlas
docs drift, Contract Atlas lifecycle, and dependency audit. It should be run
before release closure, publication, merge approval, or any operator decision
that needs full confidence.

## Branch And Merge Policy

- Work happens on a branch or PR, not direct-to-main.
- `main` is the default target branch.
- PR smoke must pass unless GitHub Actions is unavailable or disabled.
- A passing local heavy gate is required for release readiness.
- Full GitHub CI can be run manually when the operator wants remote parity
  evidence, but it is not burned on every push.
- Deployment, tag creation, publishing, and merge remain explicit
  operator-approved actions.

If GitHub Actions is disabled, unaffordable, unavailable, or blocked by account
limits, development is not blocked. The release gate should record the remote
confidence gap, rely on local release-gate evidence for continued development,
and require manual operator review before merge/release approval.

## Authority

The CI/CD profile is repo-backed in
`runtime/config/release-gates/dream-studio.json` and mirrored by
`core.release.github_pr_cicd_gate`. Contract Atlas exposes it as
`github_cicd_profile`. Dashboard/API views may show the profile as derived
evidence, but GitHub is not Dream Studio authority.
