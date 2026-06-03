"""Security build mode — static enforcement on generated Python code.

Implements patterns documented in:
  canonical/skills/quality/modes/security/build/SKILL.md

6 static patterns applied synchronously. No LLM. No DB. No subprocess.
Returns in < 200ms for typical generated function.
"""

from __future__ import annotations

import re
from typing import Any

TIER_T1 = "T1"
TIER_T2 = "T2"
TIER_T3 = "T3"

# Credential-suggestive variable name suffixes
_CRED_SUFFIXES = (
    "_key", "_secret", "_password", "_token", "_credential",
    "_api_key", "_auth_token", "_private_key",
)
_CRED_EXACT = {
    "API_KEY", "SECRET", "SECRET_KEY", "PASSWORD", "TOKEN",
    "AUTH_TOKEN", "PRIVATE_KEY", "ACCESS_KEY", "ACCESS_TOKEN",
}
# Known leaked credential prefixes in string literals
_LEAKED_PREFIXES = ("sk-", "ghp_", "AKIA", "xoxb-", "xoxp-", "-----BEGIN")

# PII-suggestive variable names for logging check
_PII_NAMES = ("email", "password", "ssn", "dob", "phone", "credit_card", "token",
              "full_name", "birth", "national_id", "passport")

# SQL keywords that indicate injection risk in formatted strings
_SQL_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "FROM",
                 "DROP", "EXEC", "UNION", "JOIN")


def audit_generated_python(code_block: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Static security check of a generated Python code block.

    Called by SkillDispatcher.build() for Python artifacts.

    Returns list of findings [{rule_id, severity, tier, excerpt, explanation, line}].
    Empty list = clean.
    """
    findings: list[dict[str, Any]] = []
    lines = code_block.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()
        lineno = i + 1

        # sec-001: hardcoded credentials ──────────────────────────────────
        _check_hardcoded_cred(stripped, lineno, findings)

        # sec-002: SQL injection via f-string / %-format ──────────────────
        _check_sql_injection(stripped, lineno, findings)

        # sec-005: weak password hashing ──────────────────────────────────
        _check_weak_password_hash(stripped, lineno, findings)

        # sec-021: weak crypto algorithms ─────────────────────────────────
        _check_weak_crypto(stripped, lineno, findings)

        # sec-007: insecure cookie flags ──────────────────────────────────
        _check_insecure_cookie(stripped, lineno, findings)

        # sec-013: PII in log statements ──────────────────────────────────
        _check_pii_in_logs(stripped, lineno, findings)

    return findings


# ── Checkers ──────────────────────────────────────────────────────────────

def _check_hardcoded_cred(line: str, lineno: int, findings: list) -> None:
    """sec-001: detect hardcoded credential string literals."""
    # Pattern: VARNAME = "literal" where VARNAME suggests a credential
    m = re.match(r'^(\w+)\s*=\s*["\'](.+)["\']', line)
    if not m:
        return
    varname, value = m.group(1), m.group(2)
    if len(value) < 4:
        return  # too short to be a credential
    # Check for known leaked prefixes in value
    for prefix in _LEAKED_PREFIXES:
        if value.startswith(prefix):
            findings.append({
                "rule_id": "sec-001",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": f"{varname} = \"{value[:8]}...\"",
                "explanation": f"Hardcoded credential: `{varname}` contains a string matching known API key pattern `{prefix}...`",
                "line": lineno,
            })
            return
    # Check for credential-suggestive variable names with non-trivial values
    varname_lower = varname.lower()
    if varname in _CRED_EXACT or any(varname_lower.endswith(suf) for suf in _CRED_SUFFIXES):
        # Only flag if value looks like a real credential (not a placeholder)
        if not re.match(r'^(your[-_]|<|{|\[|TODO|CHANGEME|XXX|placeholder)', value, re.I):
            findings.append({
                "rule_id": "sec-001",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": f"{varname} = \"{value[:8]}...\"",
                "explanation": f"Hardcoded credential: `{varname}` assigned a string literal. Use os.environ.get('{varname}') instead.",
                "line": lineno,
            })


def _check_sql_injection(line: str, lineno: int, findings: list) -> None:
    """sec-002: detect SQL injection via f-string or % formatting."""
    # Check for f-string with SQL keyword + variable interpolation
    if ('f"' in line or "f'" in line) and '{' in line:
        upper_line = line.upper()
        if any(kw in upper_line for kw in _SQL_KEYWORDS):
            findings.append({
                "rule_id": "sec-002",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": line[:80],
                "explanation": "SQL injection risk: f-string with SQL keywords interpolates variables. Use parameterized queries.",
                "line": lineno,
            })
            return
    # Check for %-format with SQL keyword
    if ' % ' in line or '.format(' in line:
        upper_line = line.upper()
        if any(kw in upper_line for kw in _SQL_KEYWORDS):
            findings.append({
                "rule_id": "sec-002",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": line[:80],
                "explanation": "SQL injection risk: string formatting with SQL keywords. Use parameterized queries.",
                "line": lineno,
            })


def _check_weak_password_hash(line: str, lineno: int, findings: list) -> None:
    """sec-005: detect password hashed with weak algorithm."""
    # Check for password variable passed to weak hash
    if re.search(r"(password|passwd|pwd)\b", line, re.I):
        if re.search(r"(md5|sha1|sha256)\s*\(", line, re.I):
            findings.append({
                "rule_id": "sec-005",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": line.strip(),
                "explanation": "Weak password hashing: MD5/SHA1/SHA256 are cryptographically weak for passwords. Use bcrypt, argon2, or scrypt.",
                "line": lineno,
            })


def _check_weak_crypto(line: str, lineno: int, findings: list) -> None:
    """sec-021: detect use of weak cryptographic algorithms."""
    weak_patterns = [
        (r"hashlib\.md5\s*\(", "MD5 is cryptographically broken"),
        (r"hashlib\.sha1\s*\(", "SHA1 is cryptographically broken"),
        (r"\bDES\b", "DES is a weak cipher"),
        (r"ECB\b", "ECB mode is insecure (no IV, reveals patterns)"),
        (r"\bRC4\b", "RC4 is a broken stream cipher"),
        (r"random\.(random|randint|choice|randrange)\s*\(", "random module is not cryptographically secure; use secrets module"),
    ]
    for pattern, explanation in weak_patterns:
        if re.search(pattern, line, re.I):
            findings.append({
                "rule_id": "sec-021",
                "severity": "high",
                "tier": TIER_T1,
                "excerpt": line.strip(),
                "explanation": f"Weak crypto: {explanation}",
                "line": lineno,
            })
            break  # one finding per line


def _check_insecure_cookie(line: str, lineno: int, findings: list) -> None:
    """sec-007: detect set_cookie without secure and httponly flags."""
    if "set_cookie" in line.lower():
        has_secure = re.search(r"secure\s*=\s*True", line, re.I)
        has_httponly = re.search(r"httponly\s*=\s*True", line, re.I)
        if not (has_secure and has_httponly):
            missing = []
            if not has_secure:
                missing.append("secure=True")
            if not has_httponly:
                missing.append("httponly=True")
            findings.append({
                "rule_id": "sec-007",
                "severity": "high",
                "tier": TIER_T1,
                "excerpt": line.strip(),
                "explanation": f"Insecure cookie: missing {' and '.join(missing)}. Session cookies need both flags.",
                "line": lineno,
            })


def _check_pii_in_logs(line: str, lineno: int, findings: list) -> None:
    """sec-013: detect PII variable names in logging/print calls."""
    # Check if this is a logging or print call
    is_log_call = re.search(r"(logging\.|log\.|logger\.|print\s*\()", line, re.I)
    if not is_log_call:
        return
    # Check for PII-suggestive variable names in the call
    for pii in _PII_NAMES:
        if re.search(r"\b" + pii + r"\b", line, re.I):
            findings.append({
                "rule_id": "sec-013",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": line.strip(),
                "explanation": f"PII in log: `{pii}` variable passed to a log/print call. Log an opaque ID instead.",
                "line": lineno,
            })
            return  # one finding per line
