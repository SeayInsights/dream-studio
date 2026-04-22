"""
map_compliance.py — Compliance framework mapper for security findings.

Reads scored findings JSON (from score_findings.py) via stdin or --input.
Cross-references each finding against compliance framework mapping YAMLs
to add framework control IDs and identify coverage gaps.

Usage:
    py -3.12 map_compliance.py --client <name> [--input <path>] [--output <path>]
    py -3.12 score_findings.py --client <name> | py -3.12 map_compliance.py --client <name>

Dependencies: PyYAML (stdlib + yaml only)
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[map_compliance] ERROR: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Framework key normalization ───────────────────────────────────────────────
# Maps client profile framework names → yaml filename stems
FRAMEWORK_FILE_MAP = {
    "soc2":        "soc2-mapping.yaml",
    "nist_csf":    "nist-csf-mapping.yaml",
    "owasp_asvs":  "owasp-asvs-mapping.yaml",
    "cwe_top25":   "cwe-top25-mapping.yaml",
    # alternate spellings
    "nist-csf":    "nist-csf-mapping.yaml",
    "owasp-asvs":  "owasp-asvs-mapping.yaml",
    "cwe-top25":   "cwe-top25-mapping.yaml",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def compliance_dir() -> Path:
    """Return path to compliance YAMLs relative to this script."""
    return Path(__file__).parent.parent / "compliance"


def load_client_profile(client: str) -> dict:
    profile_path = Path(os.path.expanduser(f"~/.dream-studio/clients/{client}.yaml"))
    if not profile_path.exists():
        print(
            f"[map_compliance] WARNING: client profile not found at {profile_path}. "
            "Using all available frameworks.",
            file=sys.stderr,
        )
        return {}
    with open(profile_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_framework_mappings(framework_names: list[str]) -> dict[str, dict]:
    """
    Load YAML mapping files for requested frameworks.
    Returns {framework_key: loaded_yaml_dict}
    """
    comp_dir = compliance_dir()
    loaded: dict[str, dict] = {}

    for fw in framework_names:
        fname = FRAMEWORK_FILE_MAP.get(fw)
        if not fname:
            print(f"[map_compliance] WARNING: No mapping file known for framework '{fw}'", file=sys.stderr)
            continue
        fpath = comp_dir / fname
        if not fpath.exists():
            print(f"[map_compliance] WARNING: Mapping file not found: {fpath}", file=sys.stderr)
            continue
        try:
            with open(fpath, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            loaded[fw] = data
            controls = data.get("controls", [])
            print(f"[map_compliance] Loaded {fw} ({len(controls)} controls from {fname})", file=sys.stderr)
        except Exception as exc:
            print(f"[map_compliance] ERROR loading {fpath}: {exc}", file=sys.stderr)

    return loaded


def _rule_pattern_matches(rule_id: str, patterns: list[str]) -> bool:
    """Check if a rule_id matches any of the glob patterns in mapped_rule_patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(rule_id.lower(), pattern.lower()):
            return True
    return False


def _control_display_id(framework_key: str, control_id: str) -> str:
    """Format control ID for display, e.g. 'SOC2-CC6.1', 'NIST-PR.AC-1'."""
    prefix_map = {
        "soc2":       "SOC2",
        "nist_csf":   "NIST",
        "nist-csf":   "NIST",
        "owasp_asvs": "ASVS",
        "owasp-asvs": "ASVS",
        "cwe_top25":  "CWE25",
        "cwe-top25":  "CWE25",
    }
    prefix = prefix_map.get(framework_key, framework_key.upper())
    return f"{prefix}-{control_id}"


def match_finding_to_controls(
    finding: dict,
    framework_mappings: dict[str, dict],
) -> list[str]:
    """
    Given a finding and all loaded framework mappings, return a list of
    matched control display IDs (e.g. ['SOC2-CC6.6', 'NIST-PR.DS-2']).
    """
    finding_cwe = finding.get("cwe", "")
    finding_owasp = finding.get("owasp", "")
    finding_rule_id = finding.get("rule_id", "")
    matched: list[str] = []

    for fw_key, fw_data in framework_mappings.items():
        for control in fw_data.get("controls", []):
            control_id = control.get("control_id", "")
            mapped_cwes = control.get("mapped_cwes", []) or []
            mapped_owasp = control.get("mapped_owasp", []) or []
            mapped_rule_patterns = control.get("mapped_rule_patterns", []) or []

            hit = False
            # CWE match
            if finding_cwe and finding_cwe in mapped_cwes:
                hit = True
            # OWASP category match
            if not hit and finding_owasp and finding_owasp in mapped_owasp:
                hit = True
            # Rule pattern match
            if not hit and finding_rule_id and mapped_rule_patterns:
                if _rule_pattern_matches(finding_rule_id, mapped_rule_patterns):
                    hit = True

            if hit:
                display_id = _control_display_id(fw_key, control_id)
                if display_id not in matched:
                    matched.append(display_id)

    return matched


def compute_gaps(
    findings: list[dict],
    framework_mappings: dict[str, dict],
) -> list[dict]:
    """
    Identify controls that have mappings (CWE/OWASP/rule) but no findings matched them.
    A control is a 'gap' if it has at least one mapped CWE/OWASP/rule and zero findings hit it.
    Controls with empty mappings (manual-only) are excluded.
    """
    # Build set of display IDs that were matched by at least one finding
    matched_controls: set[str] = set()
    for f in findings:
        for cid in f.get("compliance_controls", []):
            matched_controls.add(cid)

    gaps: list[dict] = []
    for fw_key, fw_data in framework_mappings.items():
        for control in fw_data.get("controls", []):
            control_id = control.get("control_id", "")
            mapped_cwes = control.get("mapped_cwes", []) or []
            mapped_owasp = control.get("mapped_owasp", []) or []
            mapped_rule_patterns = control.get("mapped_rule_patterns", []) or []

            # Skip controls with no automatable mappings
            if not mapped_cwes and not mapped_owasp and not mapped_rule_patterns:
                continue

            display_id = _control_display_id(fw_key, control_id)
            if display_id not in matched_controls:
                title = (
                    control.get("title")
                    or control.get("subcategory")
                    or control.get("name")
                    or control_id
                )
                gaps.append({
                    "framework": fw_key,
                    "control_id": control_id,
                    "display_id": display_id,
                    "title": title,
                    "reason": "no scan rule covers this control or no current findings match it",
                })

    return gaps


def compute_coverage(findings: list[dict], framework_mappings: dict[str, dict]) -> dict[str, int]:
    """Count distinct controls matched per framework."""
    per_fw: dict[str, set] = {fw: set() for fw in framework_mappings}
    for f in findings:
        for cid in f.get("compliance_controls", []):
            # Reverse-map display_id to framework key
            for fw_key in framework_mappings:
                prefix_map = {
                    "soc2": "SOC2", "nist_csf": "NIST", "nist-csf": "NIST",
                    "owasp_asvs": "ASVS", "owasp-asvs": "ASVS",
                    "cwe_top25": "CWE25", "cwe-top25": "CWE25",
                }
                prefix = prefix_map.get(fw_key, fw_key.upper())
                if cid.startswith(f"{prefix}-"):
                    per_fw[fw_key].add(cid)
    return {fw: len(ids) for fw, ids in per_fw.items()}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map scored security findings to compliance framework controls"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. plmarketing-kroger)")
    parser.add_argument("--input", help="Path to scored findings JSON envelope. Default: stdin")
    parser.add_argument("--output", help="Output file path. Default: stdout")
    args = parser.parse_args()

    # ── Load input ────────────────────────────────────────────────────────────
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[map_compliance] ERROR: input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        raw_json = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "[map_compliance] ERROR: No --input specified and stdin is a TTY. "
                "Pipe score_findings.py output or pass --input <path>.",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_json = sys.stdin.read()

    try:
        envelope = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[map_compliance] ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    # Accept either a bare list (from parse_sarif) or a scored envelope
    if isinstance(envelope, list):
        findings = envelope
    elif isinstance(envelope, dict):
        findings = envelope.get("findings", [])
    else:
        print("[map_compliance] ERROR: Expected JSON array or object", file=sys.stderr)
        sys.exit(1)

    print(
        f"[map_compliance] Processing {len(findings)} findings for client: {args.client}",
        file=sys.stderr,
    )

    # ── Load client profile to determine applicable frameworks ────────────────
    profile = load_client_profile(args.client)
    framework_names: list[str] = (
        profile.get("compliance", {}).get("frameworks", [])
        or list(FRAMEWORK_FILE_MAP.keys())[:3]  # fallback: soc2, nist_csf, owasp_asvs
    )
    print(f"[map_compliance] Frameworks: {framework_names}", file=sys.stderr)

    # ── Load compliance mapping YAMLs ─────────────────────────────────────────
    framework_mappings = load_framework_mappings(framework_names)
    if not framework_mappings:
        print("[map_compliance] ERROR: No framework mappings loaded", file=sys.stderr)
        sys.exit(1)

    # ── Map each finding to controls ──────────────────────────────────────────
    mapped_findings: list[dict] = []
    for finding in findings:
        controls = match_finding_to_controls(finding, framework_mappings)
        mapped_findings.append({**finding, "compliance_controls": controls})

    # Summary
    total_mapped = sum(1 for f in mapped_findings if f.get("compliance_controls"))
    print(
        f"[map_compliance] {total_mapped}/{len(mapped_findings)} findings mapped to controls",
        file=sys.stderr,
    )

    # ── Compute gaps ──────────────────────────────────────────────────────────
    gaps = compute_gaps(mapped_findings, framework_mappings)
    print(f"[map_compliance] {len(gaps)} compliance gaps identified", file=sys.stderr)

    # ── Compute coverage ──────────────────────────────────────────────────────
    coverage = compute_coverage(mapped_findings, framework_mappings)

    # ── Build output envelope ─────────────────────────────────────────────────
    # Preserve existing envelope fields, add our new ones
    if isinstance(envelope, dict):
        output = {
            **envelope,
            "client": args.client,
            "findings": mapped_findings,
            "gaps": gaps,
            "coverage": coverage,
        }
    else:
        output = {
            "client": args.client,
            "findings": mapped_findings,
            "gaps": gaps,
            "coverage": coverage,
        }

    output_json = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[map_compliance] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
