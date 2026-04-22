"""
score_findings.py — Security finding scorer and repo aggregator.

Reads normalized findings JSON (from parse_sarif.py) via stdin or --input,
applies CVSS estimates, business impact scoring, and per-repo aggregation.

Usage:
    py -3.12 score_findings.py --client <name> [--input <path>] [--output <path>]
    py -3.12 parse_sarif.py --sample --client <name> | py -3.12 score_findings.py --client <name>

Dependencies: PyYAML (stdlib + yaml only)
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[score_findings] ERROR: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── CVSS estimate table ────────────────────────────────────────────────────────
CVSS_BY_SEVERITY = {
    "critical": 9.5,
    "high": 7.5,
    "medium": 4.5,
    "low": 2.0,
    "info": 0.5,
}

# ── Default severity weights (used when client profile lacks them) ─────────────
DEFAULT_WEIGHTS = {
    "critical": 10,
    "high": 4,
    "medium": 1,
    "low": 0.25,
    "secrets_exposed": 15,
    "isolation_failures": 20,
    "netcompat_failures": 5,
}


# ── Client profile loader ─────────────────────────────────────────────────────

def load_client_profile(client: str) -> dict:
    profile_path = Path(os.path.expanduser(f"~/.dream-studio/clients/{client}.yaml"))
    if not profile_path.exists():
        print(
            f"[score_findings] WARNING: client profile not found at {profile_path}. "
            "Using default weights and no business impact terms.",
            file=sys.stderr,
        )
        return {}
    with open(profile_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ── Business impact classifier ────────────────────────────────────────────────

def classify_business_impact(finding: dict, data_config: dict) -> tuple[int, str]:
    """
    Returns (score 0-10, reason string).
    Checks finding message + file path against data classification terms.
    """
    text = (finding.get("message", "") + " " + finding.get("file", "")).lower()

    critical_terms = [t.lower() for t in data_config.get("critical", [])]
    sensitive_terms = [t.lower() for t in data_config.get("sensitive", [])]
    internal_terms = [t.lower() for t in data_config.get("internal", [])]

    for term in critical_terms:
        if term in text:
            return 10, f"involves critical data term: {term}"

    for term in sensitive_terms:
        if term in text:
            return 6, f"involves sensitive data term: {term}"

    for term in internal_terms:
        if term in text:
            return 3, f"involves internal data term: {term}"

    # Fallback: severity-based minimum impact for secrets/critical findings
    if finding.get("severity") == "critical":
        return 5, "critical severity finding with no specific data classification match"
    if finding.get("severity") == "high":
        return 2, "high severity finding"

    return 1, "no specific data classification match"


# ── Risk score per finding ────────────────────────────────────────────────────

def score_finding(finding: dict, data_config: dict) -> dict:
    severity = finding.get("severity", "low")
    cvss = CVSS_BY_SEVERITY.get(severity, 2.0)

    business_impact, reason = classify_business_impact(finding, data_config)

    # Risk score = CVSS × business_impact_multiplier
    # multiplier = 1.0 + business_impact/10  → range [1.0, 2.0]
    multiplier = 1.0 + business_impact / 10.0
    risk_score = round(cvss * multiplier, 2)

    return {
        **finding,
        "cvss": cvss,
        "business_impact": business_impact,
        "business_impact_reason": reason,
        "risk_score": risk_score,
    }


# ── Per-repo aggregation ──────────────────────────────────────────────────────

def aggregate_repos(scored_findings: list[dict], weights: dict) -> dict:
    """
    Returns dict of {repo: score_0_to_100} where 100 = no risk.
    Formula: raw_score = sum(risk_score * severity_weight)
    Then normalize: repo_score = max(0, 100 - normalized_raw)
    """
    repos: dict[str, list[dict]] = {}
    for f in scored_findings:
        repo = f.get("repo", "unknown")
        repos.setdefault(repo, []).append(f)

    repo_scores: dict[str, dict] = {}
    for repo, findings in repos.items():
        raw_score = 0.0
        for f in findings:
            sev = f.get("severity", "low")
            weight = weights.get(sev, weights.get("low", 0.25))
            raw_score += f.get("risk_score", 0) * weight

        # Normalize: scale raw_score to a penalty out of 100.
        # Heuristic ceiling: a repo with 5 critical+high findings at max impact = ~500
        # We use a soft ceiling of 300 to keep the scale meaningful.
        CEILING = 300.0
        penalty = min(raw_score / CEILING * 100, 100)
        repo_score = round(max(0, 100 - penalty), 1)

        repo_scores[repo] = {
            "score": repo_score,
            "finding_count": len(findings),
            "raw_risk_total": round(raw_score, 2),
        }

    return repo_scores


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score normalized security findings with CVSS + business impact"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. plmarketing-kroger)")
    parser.add_argument(
        "--input",
        help="Path to normalized findings JSON. Default: stdin",
    )
    parser.add_argument("--output", help="Output file path. Default: stdout")
    args = parser.parse_args()

    # Load findings
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[score_findings] ERROR: input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        raw_json = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "[score_findings] ERROR: No --input specified and stdin is a TTY. "
                "Pipe parse_sarif.py output or pass --input <path>.",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_json = sys.stdin.read()

    try:
        findings = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[score_findings] ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(findings, list):
        print("[score_findings] ERROR: Expected a JSON array of findings", file=sys.stderr)
        sys.exit(1)

    print(f"[score_findings] Scoring {len(findings)} findings for client: {args.client}", file=sys.stderr)

    # Load client profile
    profile = load_client_profile(args.client)
    weights = (
        profile.get("dashboard", {}).get("org_score", {}).get("weights", DEFAULT_WEIGHTS)
    )
    data_config = profile.get("data", {})

    # Score each finding
    scored = [score_finding(f, data_config) for f in findings]

    # Aggregate per repo
    repo_scores = aggregate_repos(scored, weights)

    # Build output envelope
    output = {
        "client": args.client,
        "total_findings": len(scored),
        "repo_scores": repo_scores,
        "findings": scored,
    }

    # Summary to stderr
    print("[score_findings] Per-repo scores:", file=sys.stderr)
    for repo, info in repo_scores.items():
        print(
            f"  {repo}: {info['score']}/100  "
            f"({info['finding_count']} findings, raw_risk={info['raw_risk_total']})",
            file=sys.stderr,
        )

    output_json = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[score_findings] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
