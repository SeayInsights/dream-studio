---
name: ds-infra
description: 'CI/CD, Kubernetes, and infrastructure as code — pipeline design, cluster operations, Terraform provisioning. Use for: CI/CD pipeline:, k8s cluster issue:, Terraform:'
---

# Infra — CI/CD, Kubernetes, Infrastructure as Code

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| devops | modes/devops/SKILL.md | CI/CD pipeline, GitHub Actions workflow, Docker build, release automation, branch protection, deployment gate |
| kubernetes | modes/kubernetes/SKILL.md | k8s cluster issue, workload design, CrashLoopBackOff, OOMKill, Pending pods, Helm chart, RBAC, NetworkPolicy, HPA |
| terraform | modes/terraform/SKILL.md | Terraform, infrastructure design, IaC, state problem, Terraform module, remote state, drift detection |

Each mode carries a dedicated subagent (`devops-engineer`, `kubernetes-expert`,
`terraform-architect` — see `canonical/agents/coverage.yml`); a caller with
Task-tool access dispatches the subagent directly rather than reading the mode
file inline.

## Shared resources

Reference data directories available to the relevant modes:
- `infra/` — CI/CD, Kubernetes, and Terraform pattern references
- `devops/` — GitHub Actions reference material and patterns

## Split history

Split out of the `domains` pack (`devops`, `kubernetes`, `terraform`) —
pack-split, 2026-09-24. Neither mode's own content, rules, or subagent
changed; only which pack owns them did.
