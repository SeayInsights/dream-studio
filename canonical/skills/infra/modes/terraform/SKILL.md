## Patterns

- **Remote state with native locking**: S3 with `use_lockfile = true` (AWS, Terraform >= 1.11) or GCS (GCP). DynamoDB locking still works but `dynamodb_table` was deprecated in 1.11 (Feb 2025) in favour of S3-native locking -- don't add one to a new backend. State must be versioned (S3 versioning enabled) for rollback. `encrypt = true` in backend config.
- **for_each over count for mutable collections**: count indexes are positional -- removing an item shifts all higher items, triggering destroy+recreate. for_each keys are stable strings.
- **Module versioning with pessimistic constraint (~>)**: `version = "~> 5.1"` allows any 5.x from 5.1 up -- minor *and* patch bumps (5.2, 5.9) -- but blocks 6.0. Only the three-part form `~> 5.1.0` is patch-only. Run `terraform init -upgrade` deliberately.
- **Import blocks (TF 1.5+)**: declare `import { to = ... id = ... }` in config; import runs as part of apply. TF 1.6+ adds `-generate-config-out=generated.tf` for auto-config generation.
- **Workspaces for env isolation when infra is structurally identical**: use `terraform.workspace` in locals to vary instance types, counts, tags. Separate root modules for structurally different environments.
- **Data sources and remote state outputs for cross-module references**: never hardcode ARNs. Use `data.terraform_remote_state.<name>.outputs.<key>` for resources owned by another root module.
- **Provider version pinning in required_providers**: e.g. `~> 6.0` for the current AWS provider major (v6, GA June 2025). Always read CHANGELOG before crossing a major version boundary.
- **depends_on only for hidden side-effect dependencies**: use sparingly -- it blocks Terraform's parallelism optimizer. Prefer explicit attribute references to express dependencies.

## Anti-Patterns

- **Local state in team environments** -- concurrent applies corrupt state; no locking, no versioning, state contains secrets committed to git.
- **Static cloud credentials in provider blocks** -- end up in config, .terraform lock files, and plan artifacts. Use instance profiles, environment variables, or OIDC.
- **count for sets that change over time** -- reorder or middle-removal triggers destroy+recreate of all higher-indexed resources, including production databases.
- **No version constraints on Terraform or providers** -- `terraform init` installs latest; teammates get different providers; "inconsistent lock file" errors; provider breaking changes deployed silently.
- **One root module for all environments** -- botched dev plan can destroy prod resources; state lock for dev blocks prod changes.
- **Applying without a saved plan file** -- re-run of plan between plan and apply can include out-of-band infra changes not in the reviewed plan.

## Gotchas

- **Interrupted apply corrupts state**: Ctrl+C or CI timeout during apply may leave resources created but unrecorded, or a stale DynamoDB lock. Run `terraform force-unlock <ID>` to release lock; then `terraform plan` to assess drift before next apply.
- **Tainted resources are destroyed on next apply**: partially-created resources are auto-tainted; next plan shows destroy+create. Run `terraform untaint <address>` to un-mark if the resource is actually healthy.
- **Sensitive values are plaintext in state**: `sensitive = true` masks in CLI output but the value is still in the .tfstate JSON. Control access to state bucket via strict IAM; minimize secrets in state by using data sources to read from Secrets Manager at apply time.
- **terraform destroy ordering with deletion-protected resources**: S3 buckets with objects, RDS with deletion_protection, ECR with images will fail mid-destroy. Set `force_destroy = true` or `deletion_protection = false` and apply before destroy.
- **-refresh=false gives stale plan**: skipping refresh misses out-of-band changes; the plan file may not reflect real infra by apply time. Use `-refresh-only` periodically to sync state without changes.
- **Provider major version upgrade requires config migration**: AWS provider v4.0 (Feb 2022) split `aws_s3_bucket` into sub-resources (`aws_s3_bucket_versioning`, `aws_s3_bucket_server_side_encryption_configuration`, ...); v4.9 (Apr 2022) restored the old inline arguments as deprecated fallbacks; v5.0 (May 2023) removed those fallbacks entirely. Bump version constraint, run `terraform init -upgrade`, run `terraform plan` -- address every breaking change before apply.

## Commands

```bash
# Initialize with backend (first time or after config change)
terraform init -backend-config=backend-prod.hcl

# Upgrade providers to latest allowed by constraints
terraform init -upgrade

# Plan and save to file (required for safe apply)
terraform plan -out=tfplan.binary

# Apply saved plan only (no re-plan)
terraform apply tfplan.binary

# Show human-readable saved plan
terraform show tfplan.binary

# Format all .tf files in place
terraform fmt -recursive

# Validate config without API calls
terraform validate

# Workspace operations
terraform workspace list
terraform workspace new staging
terraform workspace select production

# Import existing resource (TF 1.5+ import block approach)
# Add import block to config, then:
terraform plan   # shows import + diff
terraform apply  # executes import

# CLI import (pre-1.5 or one-off)
terraform import aws_s3_bucket.my_bucket my-existing-bucket

# Detect drift -- refresh state without changes
terraform plan -refresh-only

# Release a stuck state lock
terraform force-unlock <LOCK_ID>

# Remove a resource from state without destroying it (decommission TF management)
terraform state rm aws_s3_bucket.old_bucket

# Move resource address in state (after rename or module restructure)
terraform state mv aws_instance.server module.compute.aws_instance.server

# List all resources in state
terraform state list

# Show specific resource state
terraform state show aws_eks_cluster.main

# Force replacement via a reviewable plan (preferred since TF 0.15.2)
terraform apply -replace="aws_instance.flaky_server"

# Taint a resource (DEPRECATED -- mutates state with no reviewable plan; prefer -replace above)
terraform taint aws_instance.flaky_server

# Remove taint
terraform untaint aws_instance.flaky_server

# Generate config for imported resources (TF 1.6+)
terraform plan -generate-config-out=generated.tf
```

## Version Notes

- **Terraform 1.5 (2023)**: import blocks (config-driven import) -- no more imperative CLI import as first step.
- **Terraform 1.6 (2023)**: `-generate-config-out` for auto-generating config from imported resources.
- **Terraform 1.7 (2024)**: `removed` blocks for cleanly removing resources from state without a destroy.
- **Terraform 1.8 (2024)**: provider functions available in expressions (e.g., AWS provider functions for ARN parsing).
- **Terraform 1.9 (Jun 2024)**: variable `validation` can reference other objects; `templatestring` function.
- **Terraform 1.10 (Nov 2024)**: ephemeral values/resources (secrets that never land in state); experimental S3-native locking (`use_lockfile`).
- **Terraform 1.11 (Feb 2025)**: `use_lockfile` GA; `dynamodb_table`/`dynamodb_endpoint` deprecated on the S3 backend.
- **Terraform 1.12 (May 2025)**: import blocks can target a provider-defined `identity`; OCI Object Storage backend.
- **Terraform 1.13-1.16 (2025-2026)**: Stacks CLI hardening; List Resources (`terraform query`) and `action` blocks. Current stable is 1.16.x (Sep 2026).
- **AWS provider v4.0 (Feb 2022)**: major breaking change -- `aws_s3_bucket` split into `aws_s3_bucket_versioning`, `aws_s3_bucket_server_side_encryption_configuration`, etc. **v4.9 (Apr 2022)** restored the old inline arguments as deprecated fallbacks; **v5.0 (May 2023)** removed them. Current AWS provider major is **v6** (GA June 2025).
- **Kubernetes provider**: `kubernetes_manifest` has supported server-side apply and `field_manager` since it went GA in Oct 2021 -- don't gate on v2.25. Current major is **v3** (GA Dec 2025).
- **OpenTofu**: open-source fork diverging at Terraform 1.6 (Jan 2024); compatible with most TF 1.x configs and state, and has since added its own features (e.g. state encryption). Current stable is 1.12.x (Aug 2026).
