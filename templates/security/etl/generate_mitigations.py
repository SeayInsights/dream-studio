"""
generate_mitigations.py — Mitigation template matcher for security findings.

Reads compliance-mapped findings JSON (from map_compliance.py) via stdin or --input.
Matches each finding to a mitigation template and adds fix recommendations.

Usage:
    py -3.12 generate_mitigations.py --client <name> [--input <path>] [--output <path>]
    py -3.12 map_compliance.py --client <name> | py -3.12 generate_mitigations.py --client <name>

Dependencies: PyYAML (stdlib + yaml only)
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[generate_mitigations] ERROR: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Mitigation template files to load ────────────────────────────────────────
MITIGATION_FILES = [
    "injection-fixes.yaml",
    "auth-fixes.yaml",
    "secrets-fixes.yaml",
    "encryption-fixes.yaml",
    "netcompat-fixes.yaml",
]

# ── Generic mitigation fallbacks by OWASP category ───────────────────────────
GENERIC_BY_OWASP = {
    "A01:2021": {
        "title": "Broken Access Control — Enforce Authorization Checks",
        "immediate_fix": "Verify that every endpoint enforces an authorization check before returning or modifying data. Add appropriate access control decorators or middleware.",
        "long_term_fix": "Implement a centralized access control layer (RBAC or ABAC) with default-deny posture. Conduct authorization testing as part of every PR review.",
        "verification_test": "Run automated tests that attempt to access resources as unauthorized users and verify 401/403 responses.",
        "effort_estimate": "2-4h per endpoint",
    },
    "A02:2021": {
        "title": "Cryptographic Failure — Upgrade Cryptography",
        "immediate_fix": "Replace weak or broken cryptographic algorithms with modern equivalents (AES-256-GCM, SHA-256+, RSA-2048+). Ensure all sensitive data is encrypted at rest and in transit.",
        "long_term_fix": "Establish a cryptography policy document; run automated checks via Semgrep crypto rules on every commit; schedule periodic algorithm rotation reviews.",
        "verification_test": "Run Bandit B303/B304/B305 checks and Semgrep crypto ruleset; verify no weak algorithm usage remains.",
        "effort_estimate": "3-6h per instance",
    },
    "A03:2021": {
        "title": "Injection — Use Parameterized Queries and Safe APIs",
        "immediate_fix": "Replace any string concatenation or interpolation in queries/commands with parameterized statements or safe API equivalents.",
        "long_term_fix": "Adopt a query builder or ORM that prevents raw string injection; add injection-detection Semgrep rules to CI pipeline.",
        "verification_test": "Run Semgrep injection ruleset; manually test with SQLMap or equivalent for SQL injection.",
        "effort_estimate": "1-2h per instance",
    },
    "A04:2021": {
        "title": "Insecure Design — Apply Security Design Patterns",
        "immediate_fix": "Review the specific design flaw identified and apply the appropriate security pattern (rate limiting, input size limits, resource quotas).",
        "long_term_fix": "Incorporate threat modeling into the design phase; create security architecture review gates for new features.",
        "verification_test": "Manual security review of affected design component; load test to verify rate limiting is effective.",
        "effort_estimate": "4-8h per design issue",
    },
    "A05:2021": {
        "title": "Security Misconfiguration — Harden Configuration",
        "immediate_fix": "Review and remediate the specific misconfiguration identified. Disable debug mode, remove default credentials, restrict unnecessary permissions.",
        "long_term_fix": "Implement configuration-as-code with security checks; add config validation to CI pipeline; use infrastructure hardening benchmarks (CIS).",
        "verification_test": "Run configuration audit tools (Trivy config scanner, Checkov) against infrastructure definitions.",
        "effort_estimate": "1-3h per configuration",
    },
    "A06:2021": {
        "title": "Vulnerable Component — Upgrade Dependency",
        "immediate_fix": "Upgrade the identified dependency to the patched version specified in the finding. Run your test suite to verify compatibility.",
        "long_term_fix": "Enable automated dependency update PRs (Dependabot, Renovate); add pip-audit/npm-audit to CI as a blocking step; track SBOMs.",
        "verification_test": "Run pip-audit or npm-audit after upgrade; verify the CVE ID is no longer reported.",
        "effort_estimate": "30m-2h per dependency",
    },
    "A07:2021": {
        "title": "Authentication Failure — Strengthen Authentication Controls",
        "immediate_fix": "Implement proper authentication for the affected endpoint. Ensure session tokens are random, unexpired, and invalidated on logout.",
        "long_term_fix": "Adopt a proven authentication library; implement MFA for privileged accounts; use short-lived tokens with refresh flows.",
        "verification_test": "Attempt unauthenticated access to protected endpoints; verify 401 responses with proper WWW-Authenticate headers.",
        "effort_estimate": "2-4h per endpoint",
    },
    "A08:2021": {
        "title": "Software Integrity Failure — Verify Integrity and Avoid Unsafe Deserialization",
        "immediate_fix": "Replace unsafe deserialization (pickle, yaml.load without Loader) with safe alternatives. Verify integrity of software artifacts.",
        "long_term_fix": "Use signed artifacts and verify signatures in CI; replace pickle with JSON/protobuf for data serialization; audit all deserialization entry points.",
        "verification_test": "Run Bandit B301/B302 checks; attempt deserialization of crafted malicious payloads in a test environment.",
        "effort_estimate": "2-4h per serialization point",
    },
    "A09:2021": {
        "title": "Logging Failure — Add Security Event Logging",
        "immediate_fix": "Add structured logging for authentication events, access control decisions, and data access. Ensure logs do not contain sensitive data.",
        "long_term_fix": "Implement centralized SIEM ingestion; define a log retention and alert policy; add log injection prevention.",
        "verification_test": "Perform a test login and verify the event appears in logs with correct fields; confirm no passwords or tokens are logged.",
        "effort_estimate": "2-4h per module",
    },
    "A10:2021": {
        "title": "Server-Side Request Forgery — Validate and Allowlist External URLs",
        "immediate_fix": "Validate all user-controlled URLs against an allowlist of permitted destinations before making outbound requests. Block access to internal network ranges and cloud metadata endpoints.",
        "long_term_fix": "Implement a URL allowlist service with regular review; use a dedicated egress proxy that enforces destination policy; add SSRF detection to DAST scanning.",
        "verification_test": "Attempt to pass internal IP addresses (127.0.0.1, 169.254.169.254) as URL parameters; verify requests are blocked with 400/403.",
        "effort_estimate": "2-4h per URL-accepting endpoint",
    },
}

# ── Generic mitigation fallback by severity ───────────────────────────────────
GENERIC_BY_SEVERITY = {
    "critical": {
        "title": "Critical Security Finding — Immediate Remediation Required",
        "immediate_fix": "This critical finding requires immediate action. Isolate the affected component, assess exploit risk, and apply a patch or compensating control within 24 hours per SLA.",
        "long_term_fix": "Conduct a root cause analysis after immediate remediation. Update security design patterns, add automated detection, and verify fix completeness with penetration testing.",
        "verification_test": "Independent security re-scan after fix; manual verification by a second reviewer; update JIRA/tracking with remediation evidence.",
        "effort_estimate": "4-8h immediate fix + ongoing",
    },
    "high": {
        "title": "High Severity Finding — Remediate Within 7 Days",
        "immediate_fix": "Apply the specific fix for this finding's vulnerability class. Add input validation, access control, or cryptographic controls as appropriate.",
        "long_term_fix": "Backlog a security improvement ticket; add automated detection to CI; document the remediation pattern for similar future issues.",
        "verification_test": "Re-run the scanner after fix; add a regression test case that would have caught this finding.",
        "effort_estimate": "2-4h",
    },
    "medium": {
        "title": "Medium Severity Finding — Remediate Within 30 Days",
        "immediate_fix": "Apply a targeted fix for the identified vulnerability. Prioritize based on business impact and data exposure risk.",
        "long_term_fix": "Include in next sprint security backlog; add to security code review checklist.",
        "verification_test": "Re-run the scanner after fix; verify with a focused security test.",
        "effort_estimate": "1-2h",
    },
    "low": {
        "title": "Low Severity Finding — Remediate Within 90 Days",
        "immediate_fix": "Note the finding and plan remediation in the next maintenance cycle.",
        "long_term_fix": "Include in security debt backlog; address during regular code quality reviews.",
        "verification_test": "Re-run the scanner after fix.",
        "effort_estimate": "30m-1h",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def mitigations_dir() -> Path:
    """Return path to mitigation YAMLs relative to this script."""
    return Path(__file__).parent.parent / "mitigations"


def load_mitigation_templates() -> list[dict]:
    """Load all mitigation template YAML files. Returns flat list of templates."""
    mdir = mitigations_dir()
    templates: list[dict] = []
    for fname in MITIGATION_FILES:
        fpath = mdir / fname
        if not fpath.exists():
            print(f"[generate_mitigations] WARNING: Template file not found: {fpath}", file=sys.stderr)
            continue
        try:
            with open(fpath, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or []
            if isinstance(data, list):
                templates.extend(data)
                print(
                    f"[generate_mitigations] Loaded {len(data)} templates from {fname}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"[generate_mitigations] ERROR loading {fpath}: {exc}", file=sys.stderr)
    return templates


def _match_template(finding: dict, templates: list[dict]) -> dict | None:
    """
    Find best matching mitigation template for a finding.
    Match order: rule_id substring > CWE exact > OWASP category.
    Returns the template dict or None.
    """
    rule_id = finding.get("rule_id", "").lower()
    cwe = finding.get("cwe", "").lower()
    owasp = finding.get("owasp", "").lower()

    # Score each template: higher = better match
    best_score = 0
    best_template = None

    for tmpl in templates:
        raw_pattern = tmpl.get("rule_pattern", "")
        tokens = [t.strip().lower() for t in raw_pattern.split("|") if t.strip()]
        score = 0

        for token in tokens:
            # Direct rule_id match (or substring)
            if token and rule_id and (token in rule_id or rule_id in token):
                score = max(score, 3)
            # CWE match
            if token and cwe and (token == cwe or token == cwe.replace("cwe-", "cwe-")):
                score = max(score, 2)
            # OWASP match
            if token and owasp and token in owasp:
                score = max(score, 1)
            # Template CWE field match
            tmpl_cwe = tmpl.get("cwe", "").lower()
            if tmpl_cwe and cwe and tmpl_cwe == cwe:
                score = max(score, 2)
            # Template OWASP field match
            tmpl_owasp = tmpl.get("owasp_category", "").lower()
            if tmpl_owasp and owasp and tmpl_owasp == owasp:
                score = max(score, 1)

        if score > best_score:
            best_score = score
            best_template = tmpl

    return best_template if best_score > 0 else None


def _apply_template(finding: dict, tmpl: dict) -> dict:
    """Extract mitigation fields from a template and merge into the finding."""
    immediate = tmpl.get("immediate_fix", {})
    if isinstance(immediate, dict):
        immediate_fix = immediate.get("description", "See template for details.")
        code_before = immediate.get("code_before", "")
        code_after = immediate.get("code_after", "")
    else:
        immediate_fix = str(immediate)
        code_before = ""
        code_after = ""

    return {
        **finding,
        "mitigation_title": tmpl.get("title", ""),
        "immediate_fix": immediate_fix,
        "long_term_fix": tmpl.get("long_term_fix", ""),
        "verification_test": tmpl.get("verification_test", ""),
        "effort_estimate": tmpl.get("effort_estimate", ""),
        "code_before": code_before,
        "code_after": code_after,
        "mitigation_source": "template",
    }


def _apply_generic(finding: dict) -> dict:
    """Apply generic mitigation based on OWASP category or severity."""
    owasp = finding.get("owasp", "")
    severity = finding.get("severity", "medium")

    generic = GENERIC_BY_OWASP.get(owasp) or GENERIC_BY_SEVERITY.get(severity, GENERIC_BY_SEVERITY["medium"])

    return {
        **finding,
        "mitigation_title": generic["title"],
        "immediate_fix": generic["immediate_fix"],
        "long_term_fix": generic["long_term_fix"],
        "verification_test": generic["verification_test"],
        "effort_estimate": generic["effort_estimate"],
        "code_before": "",
        "code_after": "",
        "mitigation_source": "generic",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate fix recommendations for compliance-mapped security findings"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. plmarketing-kroger)")
    parser.add_argument("--input", help="Path to compliance-mapped findings JSON. Default: stdin")
    parser.add_argument("--output", help="Output file path. Default: stdout")
    args = parser.parse_args()

    # ── Load input ────────────────────────────────────────────────────────────
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[generate_mitigations] ERROR: input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        raw_json = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "[generate_mitigations] ERROR: No --input specified and stdin is a TTY. "
                "Pipe map_compliance.py output or pass --input <path>.",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_json = sys.stdin.read()

    try:
        envelope = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[generate_mitigations] ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    if isinstance(envelope, list):
        findings = envelope
    elif isinstance(envelope, dict):
        findings = envelope.get("findings", [])
    else:
        print("[generate_mitigations] ERROR: Expected JSON array or object", file=sys.stderr)
        sys.exit(1)

    print(
        f"[generate_mitigations] Processing {len(findings)} findings for client: {args.client}",
        file=sys.stderr,
    )

    # ── Load mitigation templates ─────────────────────────────────────────────
    templates = load_mitigation_templates()
    print(f"[generate_mitigations] Total templates loaded: {len(templates)}", file=sys.stderr)

    # ── Match each finding to a template ─────────────────────────────────────
    mitigated_findings: list[dict] = []
    template_hits = 0
    generic_hits = 0

    for finding in findings:
        tmpl = _match_template(finding, templates)
        if tmpl:
            mitigated = _apply_template(finding, tmpl)
            template_hits += 1
        else:
            mitigated = _apply_generic(finding)
            generic_hits += 1
        mitigated_findings.append(mitigated)

    print(
        f"[generate_mitigations] Template matches: {template_hits}, "
        f"Generic fallback: {generic_hits}",
        file=sys.stderr,
    )

    # ── Build output envelope ─────────────────────────────────────────────────
    if isinstance(envelope, dict):
        output = {
            **envelope,
            "client": args.client,
            "findings": mitigated_findings,
        }
    else:
        output = {
            "client": args.client,
            "findings": mitigated_findings,
        }

    output_json = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[generate_mitigations] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
