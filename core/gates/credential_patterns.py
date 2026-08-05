"""Single source of truth for credential-detection patterns (WO ed3aa5db).

Three surfaces detect leaked credentials, and each used to hardcode its own regexes /
prefixes, drifting apart in coverage and strictness:

  * ``core/gates/secret_scan.py``            — the fail-closed CI secret-scan gate (tree +
    git history). The strictest and most complete set — the authoritative one.
  * ``core/release/repo_publication_readiness.py`` — the pre-publication content scan.
    It carried a looser 4-rule subset, so it MISSED Slack/Google/Stripe/GitHub-PAT/
    aws-secret leaks and over-matched short non-secrets.
  * ``core/skills/build/security.py``        — the fast static linter for LLM-generated
    Python. A deliberately-loose *prefix* heuristic (a different modality): flag a literal
    that merely starts with a known credential prefix, even short/partial ones.

This module holds the patterns once so the three cannot drift:

  ``CREDENTIAL_PATTERNS``  — the structured, high-confidence regexes for content scanning
                             (secret_scan + repo_publication_readiness).
  ``CREDENTIAL_PREFIXES``  — the literal prefixes those families start with, for the fast
                             prefix heuristic (security.py). A superset of the prefixes
                             security.py previously hardcoded — coverage only grows.
  ``SCANNER_EXCLUDED_PATH_SUBSTRINGS`` — the shared scan-exclusion policy: paths that
                             legitimately contain credential *patterns/fixtures* (this
                             module, the scanners, their tests, semgrep rules, security
                             templates) rather than real credentials.

Design note (strictness): the structured patterns are the STRICT, comprehensive set. Real
credentials all exceed these prefix+length thresholds, so unifying the looser publication
scan onto them only adds secret TYPES and removes false positives — it never lowers real
coverage.
"""

from __future__ import annotations

import re

# High-confidence, structurally self-verifying credential formats. Each is specific enough
# (fixed prefix + charset + length) that a match is a real credential shape, not noise.
CREDENTIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}\b"),
    "github_pat": re.compile(r"\bgithub_pat_[0-9A-Za-z_]{82}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,72}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "stripe_secret_key": re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{24,}\b"),
    "openai_api_key": re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z_\-]{32,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "aws_secret_access_key": re.compile(
        r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([0-9A-Za-z/+]{40})['\"]?"
    ),
}

# Literal prefixes the families above begin with — for the fast prefix heuristic that lints
# LLM-generated code (core/skills/build/security.py), where even a short/partial literal is
# worth flagging. Superset of security.py's former hardcoded list; coverage only grows.
CREDENTIAL_PREFIXES: tuple[str, ...] = (
    "sk-",
    "sk_live_",
    "rk_live_",
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "AKIA",
    "ASIA",
    "xoxb-",
    "xoxa-",
    "xoxp-",
    "xoxr-",
    "xoxs-",
    "AIza",
    "-----BEGIN",
)

# Paths that legitimately contain credential *patterns* (rule definitions, the scanners,
# their tests, semgrep rules, security templates) rather than real credentials — shared by
# every scanner so a pattern-definition file is never mistaken for a leak, and the two
# content scanners cannot drift on WHAT they skip.
SCANNER_EXCLUDED_PATH_SUBSTRINGS: tuple[str, ...] = (
    "semgrep-rules",
    "core/gates/credential_patterns.py",
    "core/gates/secret_scan.py",
    "test_secret_scan",
    "test_security_baseline",
    "test_credential_patterns",
    "templates/security",
)
