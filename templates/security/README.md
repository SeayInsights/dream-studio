# Security Templates Registry

Templates used by dream-studio security skills. All Jinja2 templates (`.j2`) are rendered with client-specific values before use.

## Directory Layout

```
templates/security/
├── binary/                  # Binary analysis templates
│   ├── analyze.sh.j2        # Shell script for binary analysis
│   ├── checksec-config.yaml.j2
│   └── yara-rules.yar.j2
├── compliance/              # Compliance framework mappings
│   ├── cwe-top25-mapping.yaml
│   ├── nist-csf-mapping.yaml
│   ├── owasp-asvs-mapping.yaml
│   └── soc2-mapping.yaml
├── dast/                    # Dynamic analysis templates
│   ├── nuclei-config.yaml.j2
│   └── zap-config.yaml.j2
├── etl/                     # Python ETL scripts (pipeline stage processors)
│   ├── analyze_netcompat.py
│   ├── export_dataset.py
│   ├── generate_mitigations.py
│   ├── map_compliance.py
│   ├── parse_binary.py
│   ├── parse_dast.py
│   ├── parse_sarif.py
│   └── score_findings.py
├── github-actions/          # CI/CD workflow templates
│   ├── binary-scan.yml.j2
│   ├── dast-scan.yml.j2
│   └── security-scan.yml.j2
├── mitigations/             # Fix templates indexed by CWE/OWASP category
│   ├── auth-fixes.yaml
│   ├── encryption-fixes.yaml
│   ├── injection-fixes.yaml
│   ├── netcompat-fixes.yaml
│   └── secrets-fixes.yaml
├── powerbi/                 # Power BI dashboard spec
│   └── dashboard-spec.md
└── semgrep-rules/           # Static analysis rule templates
    ├── access-control.yaml.j2
    ├── data-protection.yaml.j2
    ├── injection.yaml.j2
    ├── netcompat.yaml.j2
    ├── secrets.yaml.j2
    └── transport.yaml.j2
```

## Skills That Use These Templates

| Skill | Templates Used |
|-------|---------------|
| `binary-scan` | `binary/`, `github-actions/binary-scan.yml.j2`, `etl/parse_binary.py` |
| `dast` | `dast/`, `github-actions/dast-scan.yml.j2`, `etl/parse_dast.py` |
| `scan` | `semgrep-rules/`, `github-actions/security-scan.yml.j2`, `etl/parse_sarif.py` |
| `mitigate` | `mitigations/`, `etl/generate_mitigations.py` |
| `comply` | `compliance/`, `etl/map_compliance.py` |
| `netcompat` | `semgrep-rules/netcompat.yaml.j2`, `etl/analyze_netcompat.py` |
| `security-dashboard` | `powerbi/dashboard-spec.md`, `etl/` (full pipeline) |

## Usage Pattern

```bash
# Render a Jinja2 template with client config
py -3.12 templates/security/etl/parse_sarif.py --client {client} --scans-dir {scan_dir}
```

ETL scripts expect `~/.dream-studio/clients/{client}/` to exist with scan outputs.
