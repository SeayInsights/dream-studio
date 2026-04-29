---
name: devops-engineer
description: GitHub Actions CI/CD pipeline design, OIDC cloud auth setup, release automation, Docker build optimization, branch protection, and deployment gates. Invoke for any CI/CD pipeline, GitHub Actions workflow, or Docker build question.
---

## Patterns

- **Reusable workflows (workflow_call)**: extract shared CI logic into a central repo; callers pass inputs and secrets. Single change propagates to all consumers.
- **OIDC federation for cloud auth**: request short-lived tokens via GitHub OIDC provider to AWS/GCP/Azure. No static credentials in secrets. Token expires with the workflow run.
- **SHA-pin all third-party actions**: tags are mutable; pin to full commit SHA and use Dependabot `package-ecosystem: github-actions` to auto-update.
- **Explicit permissions block per workflow and per job**: declare minimal set (`contents: read`, `id-token: write` for OIDC). Never rely on default repo-level GITHUB_TOKEN scope.
- **Concurrency groups on deploy workflows**: `group: deploy-${{ github.ref }}` serializes deploys per branch; `cancel-in-progress: true` for PR previews, `false` for production queuing.
- **Environment protection rules**: production environment requires human approval before deploy job proceeds. Gate via Settings -> Environments -> Required reviewers.
- **Matrix builds with fail-fast: false**: test across OS/version combinations in parallel; one failure does not cancel other matrix cells.
- **Docker multi-stage + BuildKit cache mounts**: `RUN --mount=type=cache,target=/root/.npm` speeds dep installs; multi-stage keeps final image small.
- **Artifact caching keyed on lockfile hash**: `${{ hashFiles('**/package-lock.json') }}` busts cache on dependency changes; restore-keys provide fallback partial cache.

## Anti-Patterns

- **Long-lived AWS access keys as GitHub secrets** -- static credentials never expire; a log leak grants persistent access. Use OIDC.
- **Pinning to branch or tag (uses: actions/foo@v4)** -- mutable refs allow supply-chain injection. Use full SHA.
- **Echo or print secrets in run steps** -- masking is bypassable via base64/transform. Pass secrets as env vars, never as inline command args.
- **No timeout-minutes on jobs** -- hung process consumes runner for 6 hours (GitHub default maximum). Set timeout on every job.
- **pull_request_target with untrusted fork code** -- runs with write perms and secrets; a malicious fork PR can exfiltrate all secrets. Never checkout fork code in pull_request_target without review gates.

## Gotchas

- **GITHUB_TOKEN cannot trigger downstream workflows**: a commit pushed by GITHUB_TOKEN does not start CI on that commit. Use a GitHub App token or PAT when CI must run on an automated commit.
- **Fork PRs have no secrets**: `pull_request` from a fork gets a read-only GITHUB_TOKEN and empty secret values -- by design. Gate deployment jobs on a maintainer-added label or use Environments.
- **Concurrent deploys race on shared infra**: two merges in quick succession both trigger deploy, last-write-wins on S3 or leaves partial state. Add `concurrency` group.
- **Cache poisoning via untrusted PRs**: if fork PRs can write to a shared cache key, they can inject malicious node_modules into trusted workflow runs. Scope keys or restrict cache writes to main.
- **Artifact retention and size limits**: default 90-day retention, 500MB public / 2GB private per run. Upload silently truncates on older action versions; actions/upload-artifact v4 fails loudly.

## Commands

```bash
# List open PRs before starting work
gh pr list --state open

# Check PR state before pushing to a branch
gh pr view <branch-name> --json state,title,url

# Create a PR with template body
gh pr create --title "feat: description" --body "$(cat .github/PULL_REQUEST_TEMPLATE.md)"

# View workflow run status
gh run list --limit 10
gh run view <run-id> --log

# Re-run failed jobs only
gh run rerun <run-id> --failed

# Watch a workflow run in real time
gh run watch <run-id>

# Trigger workflow manually (workflow_dispatch)
gh workflow run deploy.yml --ref main -f environment=staging

# Set a repository secret
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::123456789012:role/github-actions"

# List environments
gh api repos/{owner}/{repo}/environments

# Build Docker image with BuildKit and inline cache
DOCKER_BUILDKIT=1 docker build \
  --cache-from type=registry,ref=ghcr.io/myorg/myapp:cache \
  --cache-to type=registry,ref=ghcr.io/myorg/myapp:cache,mode=max \
  -t ghcr.io/myorg/myapp:latest .

# Multi-platform build and push
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \
  -t ghcr.io/myorg/myapp:1.2.3 .

# Create a release with auto-generated notes
gh release create v1.2.3 --generate-notes --latest

# Check branch protection rules
gh api repos/{owner}/{repo}/branches/main/protection
```

## Version Notes

- **GitHub Actions (2024+)**: `actions/upload-artifact` v4 and `actions/download-artifact` v4 are the current major; v3 is deprecated as of November 2024.
- **actions/checkout v4**: uses Node 20 runtime; v3 (Node 16) is deprecated.
- **OIDC with AWS**: requires `aws-actions/configure-aws-credentials` v4+ for the latest STS session tags support.
- **Docker BuildKit**: enabled by default in Docker 23.0+; no need to set `DOCKER_BUILDKIT=1` explicitly on current Docker Desktop.
- **GitHub cache v4**: storage limit is 10GB per repo; evicts LRU when over limit. Cache entries not accessed in 7 days are evicted regardless of size.
- **Concurrency cancel-in-progress**: added in GitHub Actions 2022; `group` can reference any expression including `github.ref`, `github.workflow`, `github.head_ref`.
