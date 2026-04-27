# Client Profile Schema

Client profiles live at `~/.dream-studio/clients/{name}.yaml`. This doc defines all fields used by security skills.

---

## Complete Schema

```yaml
# Identity (required by all skills)
client:
  name: string                    # Client/project name (kebab-case)
  github_org: string              # GitHub organization name
  contact_email: string           # Primary contact (optional)

# Data classification (used by: scan, mitigate, comply, netcompat)
data:
  critical: [string]              # Critical data types (e.g., ["pricing", "margins"])
  sensitive: [string]             # Sensitive data types (e.g., ["customer-pii", "vendor-contracts"])
  pii_patterns: [string]          # Regex patterns for PII (e.g., ["SSN:\\s*\\d{3}-\\d{2}-\\d{4}"])
  classification: enum            # Overall level: "public" | "internal" | "confidential" | "restricted"

# Isolation model (used by: scan, mitigate, secure)
isolation:
  model: enum                     # "none" | "single-tenant" | "multi-tenant-shared" | "multi-tenant-isolated"
  tenant_key: string              # Primary tenant identifier field (e.g., "org_id", "workspace_id")
  alternate_keys: [string]        # Secondary identifiers (e.g., ["user_id"])

# Network/proxy (used by: scan, netcompat, dast)
network:
  proxy:
    vendor: enum                  # null | "zscaler" | "cloudflare-gateway" | "squid"
    mode: enum                    # "transparent" | "explicit" | "ssl-inspection"
    cert_pinning_allowed: bool    # Can app pin certificates?
    custom_ca_required: bool      # Does proxy inject custom CA?
    dlp_enabled: bool             # Data loss prevention active?

# Stack info (used by: scan, secure, mitigate)
stack:
  languages: [string]             # Primary languages (e.g., ["python", "typescript"])
  frameworks: [string]            # Frameworks (e.g., ["django", "react", "cloudflare-workers"])
  databases: [string]             # Databases (e.g., ["d1", "postgres"])

# Compliance (used by: comply, mitigate, security-dashboard)
compliance:
  frameworks: [enum]              # ["soc2", "nist-csf", "owasp-asvs", "cwe-top25"]
  audit_date: string              # Next audit date (YYYY-MM-DD)
  evidence_dir: string            # Path for audit evidence exports

# Scan configuration (used by: scan, dast)
scan:
  schedule: string                # Cron expression (e.g., "0 2 * * 1" for weekly Monday 2am)
  priority_repos: [string]        # Repos to scan first (e.g., ["vendor-portal", "api"])
  exclude_repos: [string]         # Repos to skip (e.g., ["archive-*", "poc-*"])
  semgrep_rulesets: [string]      # Community rulesets (e.g., ["p/owasp-top-ten", "p/cwe-top-25"])
  extra_scanners: [enum]          # Additional scanners: ["trivy", "codeql", "zap"]

# DAST-specific (used by: dast)
dast:
  target_urls: [string]           # Base URLs to scan (e.g., ["https://staging.example.com"])
  auth_type: enum                 # "none" | "basic" | "bearer" | "cookie"
  auth_credentials: string        # Path to credentials file (not stored in YAML)
  scan_policy: enum               # "passive" | "active" | "full"
  max_duration_minutes: int       # Timeout for scan (default: 60)
