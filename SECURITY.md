# Security Policy

## Reporting a Vulnerability

To report a security issue in dream-studio, email **dannis.seay@twinrootsllc.com** with the subject line:

```
[dream-studio] Security Report
```

We aim to respond within **30 days**.

## What to Report

- Credential or token exposure in hooks or config files
- Hook injection vulnerabilities (malicious payloads reaching shell execution)
- Skill path traversal (e.g., reading files outside the project directory)
- Dependency CVEs in `requirements.txt` or `requirements-dev.txt`

## What NOT to Report

General bugs and feature requests belong in [GitHub Issues](../../issues), not security reports.

## Scope

This policy covers the dream-studio hook system, skill runner, and any associated scripts. It does not cover Claude Code itself (report those to Anthropic).
