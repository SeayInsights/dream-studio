"""
export_dataset.py — Power BI-ready CSV exporter for enriched security findings.

Reads fully enriched findings JSON (scored + compliance-mapped + mitigated)
via stdin or --input. Exports Power BI-ready CSVs and a metadata.json.

Usage:
    py -3.12 export_dataset.py --client <name> [--input <path>] [--output-dir <path>]

Default output-dir: ~/.dream-studio/security/datasets/{client}/

Dependencies: PyYAML (stdlib + yaml + csv only)
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

# scan_coverage.py is a sibling of this script (shared with the parse_* scripts).
_ETL_DIR = Path(__file__).resolve().parent
if str(_ETL_DIR) not in sys.path:
    sys.path.insert(0, str(_ETL_DIR))

import scan_coverage  # noqa: E402
from etl_home import home_dir  # noqa: E402

try:
    import yaml
except ImportError:
    print("[export_dataset] ERROR: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Default weights (fallback if client profile not found) ────────────────────
DEFAULT_WEIGHTS = {
    "critical": 10,
    "high": 4,
    "medium": 1,
    "low": 0.25,
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_client_profile(client: str) -> dict:
    profile_path = home_dir() / "clients" / f"{client}.yaml"
    if not profile_path.exists():
        print(
            f"[export_dataset] WARNING: client profile not found at {profile_path}. "
            "Using default weights.",
            file=sys.stderr,
        )
        return {}
    with open(profile_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def compute_org_score(findings: list[dict], weights: dict) -> float:
    """
    Org score = 100 - (sum(finding_count_by_severity × weight) / total_findings), clamped 0-100.
    When there are no findings, score is 100.
    """
    if not findings:
        return 100.0

    total = len(findings)
    penalty_sum = 0.0
    for f in findings:
        sev = f.get("severity", "low")
        w = weights.get(sev, weights.get("low", 0.25))
        penalty_sum += w

    raw_penalty = (penalty_sum / total) * total  # sum of weights
    # Normalize: use a ceiling of total * max_weight to keep scale meaningful
    max_weight = max(weights.values()) if weights else 10
    ceiling = total * max_weight
    penalty_pct = min((raw_penalty / ceiling) * 100, 100) if ceiling > 0 else 0

    score = max(0.0, 100.0 - penalty_pct)
    return round(score, 1)


def _attempt(attempts: dict[str, str] | None, name: str) -> list[str]:
    """The latest attempt's coverage for `name`, as a list to weigh (empty: no attempt known)."""
    return [attempts[name]] if attempts and name in attempts else []


def weakest(values: list[str]) -> str:
    """The weakest of some coverages (partial, then unknown, then complete); `unknown` for none."""
    return scan_coverage.overall({"coverage": v} for v in values)


def _sidecar_coverage(path: Path) -> str | None:
    """The overall coverage a parser's coverage.json states; None when there is none, and
    `unknown` when there is one that cannot be read or states a value outside the vocabulary."""
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("coverage")
    except (OSError, ValueError, AttributeError):
        return "unknown"
    return value if value in (scan_coverage.COMPLETE, scan_coverage.PARTIAL) else "unknown"


#: The names of a target's scan directories: `{date}` for a scan and `{date}-not-scanned` for the
#: record that one did not happen (dast examples.md, Step R2). Nothing else is an attempt.
_ATTEMPT_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})(-not-scanned)?")

#: How many limitations the metadata lists before it counts the rest.
LIMITATIONS_SHOWN = 50


def attempt_key(name: str) -> tuple[str, int] | None:
    """Sort key of a scan directory name, or None when it is not a documented attempt.

    A not-scanned record sorts after a scan of the same day and before the next day's.
    Directory names are not trusted: `latest` or `backup` sorts after every date and used to
    shadow a real record, and `2026-13-45` is not a date.
    """
    match = _ATTEMPT_NAME.fullmatch(name)
    if match is None:
        return None
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return (match.group(1), 1 if match.group(2) else 0)


class ScanState(NamedTuple):
    """What the scan store says. `coverages` are the statements to weigh into the dataset's;
    `attempts` is the latest attempt's coverage by target name (for repos.csv and
    targets.csv); `limitations` say what could not be established."""

    coverages: list[str]
    not_scanned: list[dict]
    limitations: list[str]
    attempts: dict[str, str]


def _bounded(limitations: list[str]) -> list[str]:
    if len(limitations) <= LIMITATIONS_SHOWN:
        return limitations
    cut = len(limitations) - LIMITATIONS_SHOWN
    return limitations[:LIMITATIONS_SHOWN] + [f"... and {cut} more"]


def scan_state(scans_dir: Path) -> ScanState:
    """What the scan store says about the LATEST attempt on each target.

    The layout is scans/{client}/{target}/{date}[-not-scanned]/ (see attempt_key). The newest
    recognised directory of a target decides. A not-scanned record is partial and listed with
    its reason. Otherwise the parser's coverage.json beside the scan states the coverage, and
    when the attempt cannot say (a scan-meta.json that cannot be read, a directory with neither
    file, a scan-meta.json with no coverage.json) it is `unknown`: an unreadable or evidence-less
    latest attempt is never complete and never ignored. A directory that is not a documented
    attempt is named in the limitations and decides nothing. A store that is absent or holds no
    target is `unknown` too: nothing says what was scanned.
    """
    coverages: list[str] = []
    not_scanned: list[dict] = []
    limitations: list[str] = []
    attempts: dict[str, str] = {}
    if not scans_dir.is_dir():
        coverages.append(scan_coverage.UNKNOWN)
        limitations.append(f"scan store not found: {scans_dir}; what was scanned is not known")
        return ScanState(coverages, not_scanned, _bounded(limitations), attempts)
    targets = sorted(p for p in scans_dir.iterdir() if p.is_dir())
    if not targets:
        coverages.append(scan_coverage.UNKNOWN)
        limitations.append(
            f"scan store {scans_dir} has no target directories; what was scanned is not known"
        )
        return ScanState(coverages, not_scanned, _bounded(limitations), attempts)

    for target in targets:
        recognised: list[tuple[tuple[str, int], Path]] = []
        for directory in sorted(p for p in target.iterdir() if p.is_dir()):
            key = attempt_key(directory.name)
            if key is None:
                limitations.append(f"unrecognised scan directory {target.name}/{directory.name}")
            else:
                recognised.append((key, directory))
        if not recognised:
            coverages.append(scan_coverage.UNKNOWN)
            attempts[target.name] = scan_coverage.UNKNOWN
            limitations.append(
                f"{target.name}: no recognised scan directory (names are {{date}} or "
                "{date}-not-scanned)"
            )
            continue
        newest = max(recognised)[1]
        meta_path = newest / scan_coverage.META_NAME
        sidecar_path = newest / "coverage.json"
        meta = scan_coverage.load_meta(meta_path)
        label = f"{target.name}: the latest attempt ({newest.name})"
        if meta_path.is_file() and meta is None:
            state = scan_coverage.UNKNOWN
            limitations.append(f"{label} has an unreadable scan-meta.json")
        elif scan_coverage.is_not_scanned(meta):
            reason = meta.get("reason")
            not_scanned.append(
                {
                    "target": target.name,
                    "date": newest.name,
                    "reason": scan_coverage.short(reason) if isinstance(reason, str) else "",
                    "url": meta.get("url") if isinstance(meta.get("url"), str) else "",
                }
            )
            state = scan_coverage.PARTIAL
        else:
            sidecar = _sidecar_coverage(sidecar_path)
            if sidecar is not None:
                state = sidecar
                if sidecar == scan_coverage.UNKNOWN:
                    limitations.append(f"{label} has a coverage.json that states no coverage")
            elif meta is not None:
                state = scan_coverage.UNKNOWN
                limitations.append(
                    f"{label} has a scan-meta.json but no coverage.json (run the parser with "
                    "--coverage-output)"
                )
            else:
                state = scan_coverage.UNKNOWN
                limitations.append(
                    f"{label} has no scan-meta.json or coverage.json, so what it did is not known"
                )
        coverages.append(state)
        attempts[target.name] = state
    return ScanState(coverages, not_scanned, _bounded(limitations), attempts)


def safe_str(value) -> str:
    """Convert any value to a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def write_csv(filepath: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Write a list of dicts to a CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Ensure all fields are present and string-safe
            safe_row = {k: safe_str(row.get(k, "")) for k in fieldnames}
            writer.writerow(safe_row)
    print(f"[export_dataset] Wrote {len(rows)} rows → {filepath}", file=sys.stderr)


# ── CSV generators ────────────────────────────────────────────────────────────


#: A spreadsheet cell holds 32,767 characters, and Excel and Power BI cut a longer one: a scan
#: with thousands of limitations reached ~600 KB. Leave room for the closing marker.
CELL_LIMIT = 32_000


def limitations_cell(limitations: list[str]) -> str:
    """`limitations` as one JSON-string cell that fits a spreadsheet cell.

    A list that fits is exported whole. A longer one keeps its first entries (the most
    specific ones come first: skipped steps and refusals before notes) and ends with an
    explicit marker saying how many were left out, so the cut is never silent and the cell
    is still a valid JSON list.
    """
    whole = json.dumps(limitations, ensure_ascii=False)
    if len(whole) <= CELL_LIMIT:
        return whole
    kept: list[str] = []
    size = 2  # the brackets

    def marker(omitted: int) -> str:
        return f"... {omitted} more limitation(s) omitted: the cell limit of a spreadsheet"

    for item in limitations:
        piece = len(json.dumps(item, ensure_ascii=False)) + 2  # the comma and the space
        if size + piece + len(json.dumps(marker(len(limitations)))) + 2 > CELL_LIMIT:
            break
        kept.append(item)
        size += piece
    return json.dumps([*kept, marker(len(limitations) - len(kept))], ensure_ascii=False)


def build_findings_csv(findings: list[dict]) -> list[dict]:
    rows = []
    for f in findings:
        coverage, limitations = scan_coverage.finding_coverage(f)
        rows.append(
            {
                "id": f.get("id", ""),
                "repo": f.get("repo", ""),
                "file": f.get("file", ""),
                "line": f.get("line", ""),
                "rule_id": f.get("rule_id", ""),
                "severity": f.get("severity", ""),
                "cvss": f.get("cvss", ""),
                "business_impact": f.get("business_impact", ""),
                "risk_score": f.get("risk_score", ""),
                "owasp": f.get("owasp", ""),
                "cwe": f.get("cwe", ""),
                "status": f.get("status", "open"),
                "age_days": f.get("age_days", "0"),
                "scanner": f.get("scanner", ""),
                "message": f.get("message", ""),
                "compliance_controls": safe_str(f.get("compliance_controls", [])),
                "target_type": f.get("target_type", "repo"),
                "target_name": f.get("target_name", ""),
                "url": f.get("url", ""),
                "http_method": f.get("http_method", ""),
                "binary_hash": f.get("binary_hash", ""),
                # How much of the scan this finding's result covers. Unknown stays unknown
                # (see scan_coverage.finding_coverage); limitations is one JSON string cell.
                "coverage": coverage,
                "limitations": limitations_cell(limitations),
            }
        )
    return rows


FINDINGS_FIELDS = [
    "id",
    "repo",
    "file",
    "line",
    "rule_id",
    "severity",
    "cvss",
    "business_impact",
    "risk_score",
    "owasp",
    "cwe",
    "status",
    "age_days",
    "scanner",
    "message",
    "compliance_controls",
    "target_type",
    "target_name",
    "url",
    "http_method",
    "binary_hash",
    "coverage",
    "limitations",
]


def build_mitigations_csv(findings: list[dict]) -> list[dict]:
    rows = []
    for f in findings:
        rows.append(
            {
                "finding_id": f.get("id", ""),
                "rule_id": f.get("rule_id", ""),
                "title": f.get("mitigation_title", ""),
                "immediate_fix": f.get("immediate_fix", ""),
                "long_term_fix": f.get("long_term_fix", ""),
                "verification_test": f.get("verification_test", ""),
                "effort_estimate": f.get("effort_estimate", ""),
                "code_before": f.get("code_before", ""),
                "code_after": f.get("code_after", ""),
            }
        )
    return rows


MITIGATIONS_FIELDS = [
    "finding_id",
    "rule_id",
    "title",
    "immediate_fix",
    "long_term_fix",
    "verification_test",
    "effort_estimate",
    "code_before",
    "code_after",
]


def build_compliance_csv(
    findings: list[dict],
    gaps: list[dict],
) -> list[dict]:
    """
    Build compliance.csv from matched controls and gap controls.
    finding_count = number of findings that matched this control.
    """
    # Count findings per control display_id
    control_finding_counts: dict[str, int] = {}
    control_meta: dict[str, dict] = {}

    for f in findings:
        controls = f.get("compliance_controls", []) or []
        for ctrl in controls:
            control_finding_counts[ctrl] = control_finding_counts.get(ctrl, 0) + 1
            if ctrl not in control_meta:
                # Parse framework and control_id from display_id (e.g. "SOC2-CC6.1")
                parts = ctrl.split("-", 1)
                framework = parts[0] if parts else ctrl
                control_id = parts[1] if len(parts) > 1 else ctrl
                control_meta[ctrl] = {
                    "framework": framework,
                    "control_id": control_id,
                    "title": "",  # title not readily available here
                    "covered_by_scan": "yes",
                    "gap_status": "covered",
                }

    rows = []
    # Covered controls
    for display_id, count in control_finding_counts.items():
        meta = control_meta.get(display_id, {})
        rows.append(
            {
                "framework": meta.get("framework", ""),
                "control_id": display_id,
                "title": meta.get("title", ""),
                "covered_by_scan": "yes",
                "finding_count": count,
                "gap_status": "covered",
            }
        )

    # Gap controls
    for gap in gaps:
        rows.append(
            {
                "framework": gap.get("framework", ""),
                "control_id": gap.get("display_id", gap.get("control_id", "")),
                "title": gap.get("title", ""),
                "covered_by_scan": "partial",
                "finding_count": 0,
                "gap_status": "gap",
            }
        )

    return rows


COMPLIANCE_FIELDS = [
    "framework",
    "control_id",
    "title",
    "covered_by_scan",
    "finding_count",
    "gap_status",
]


def build_repos_csv(
    findings: list[dict], repo_scores: dict, attempts: dict[str, str] | None = None
) -> list[dict]:
    """Aggregate per-repo statistics."""
    repos: dict[str, dict] = {}
    coverages: dict[str, list[str]] = {}
    today = date.today().isoformat()

    for f in findings:
        repo = f.get("repo", "unknown")
        if repo not in repos:
            repos[repo] = {
                "name": repo,
                "language": "",
                "last_scan": today,
                "risk_score": 0.0,
                "finding_count": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
            }
        r = repos[repo]
        coverages.setdefault(repo, []).append(scan_coverage.finding_coverage(f)[0])
        r["finding_count"] += 1
        sev = f.get("severity", "low")
        if sev == "critical":
            r["critical_count"] += 1
        elif sev == "high":
            r["high_count"] += 1
        elif sev == "medium":
            r["medium_count"] += 1
        else:
            r["low_count"] += 1

    # Apply risk scores from score_findings output
    for repo, score_info in (repo_scores or {}).items():
        if repo in repos:
            if isinstance(score_info, dict):
                repos[repo]["risk_score"] = score_info.get("score", 0.0)
            else:
                repos[repo]["risk_score"] = score_info

    for repo, row in repos.items():
        # A name's coverage is its findings' AND its latest attempt's: a webapp whose latest
        # attempt scanned nothing is not complete because an older scan's findings were.
        row["coverage"] = weakest(coverages.get(repo, []) + _attempt(attempts, repo))
    return list(repos.values())


REPOS_FIELDS = [
    "name",
    "language",
    "last_scan",
    "risk_score",
    "finding_count",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
    "coverage",
]


TARGETS_FIELDS = [
    "name",
    "target_type",
    "url",
    "platform",
    "last_scan",
    "risk_score",
    "finding_count",
    "coverage",
]


def build_targets_csv(
    findings: list[dict],
    repo_scores: dict,
    not_scanned: list[dict] | None = None,
    attempts: dict[str, str] | None = None,
) -> list[dict]:
    targets: dict[str, dict] = {}
    coverages: dict[str, list[str]] = {}
    today = date.today().isoformat()

    for f in findings:
        target_type = f.get("target_type", "repo")
        target_name = f.get("target_name", "") or f.get("repo", "unknown")
        if target_name not in targets:
            targets[target_name] = {
                "name": target_name,
                "target_type": target_type,
                "url": f.get("url", ""),
                "platform": "",
                "last_scan": today,
                "risk_score": 0.0,
                "finding_count": 0,
            }
        targets[target_name]["finding_count"] += 1
        coverages.setdefault(target_name, []).append(scan_coverage.finding_coverage(f)[0])

    for target, score_info in (repo_scores or {}).items():
        if target in targets:
            if isinstance(score_info, dict):
                targets[target]["risk_score"] = score_info.get("score", 0.0)
            else:
                targets[target]["risk_score"] = score_info

    for target, row in targets.items():
        row["coverage"] = weakest(coverages.get(target, []) + _attempt(attempts, target))
    # A target the run never scanned has no finding to carry it into this table; without a
    # row it would be absent, which reads as "nothing to report".
    for entry in not_scanned or []:
        name = entry["target"]
        if name in targets:
            targets[name]["coverage"] = "partial"
            continue
        targets[name] = {
            "name": name,
            "target_type": "webapp",
            "url": entry.get("url", ""),
            "platform": "",
            "last_scan": "",
            "risk_score": 0.0,
            "finding_count": 0,
            "coverage": "partial",
        }

    return list(targets.values())


def build_trends_row(
    findings: list[dict],
    org_score: float,
    existing_trends_path: Path,
) -> list[dict]:
    """
    Build trends.csv. Single row for current scan.
    If the file already exists, append the new row.
    """
    today = date.today().isoformat()
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        if sev in severity_counts:
            severity_counts[sev] += 1

    new_row = {
        "date": today,
        "total_findings": len(findings),
        "critical": severity_counts["critical"],
        "high": severity_counts["high"],
        "medium": severity_counts["medium"],
        "low": severity_counts["low"],
        "org_score": org_score,
        "resolved_count": 0,
    }

    # Read existing trends if file exists
    existing_rows: list[dict] = []
    if existing_trends_path.exists():
        try:
            with open(existing_trends_path, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                existing_rows = list(reader)
        except Exception as exc:
            print(
                f"[export_dataset] WARNING: Could not read existing trends: {exc}", file=sys.stderr
            )

    # Replace row for today or append
    updated = [r for r in existing_rows if r.get("date") != today]
    updated.append(new_row)
    return updated


TRENDS_FIELDS = [
    "date",
    "total_findings",
    "critical",
    "high",
    "medium",
    "low",
    "org_score",
    "resolved_count",
]


def build_metadata(
    client_profile: dict,
    findings: list[dict],
    org_score: float,
    scan_coverages: list[str] | None = None,
    not_scanned: list[dict] | None = None,
    limitations: list[str] | None = None,
) -> dict:
    client_info = client_profile.get("client", {})
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    repos: set[str] = set()
    for f in findings:
        sev = f.get("severity", "low")
        if sev in severity_counts:
            severity_counts[sev] += 1
        target_name = f.get("target_name", "") or f.get("repo", "unknown")
        repos.add(target_name)

    frameworks = client_profile.get("compliance", {}).get("frameworks", [])

    return {
        # The weakest coverage among the exported findings AND the scan store's latest
        # attempt per target (coverage.json sidecars, not-scanned records): partial beats
        # unknown beats complete. With neither findings nor a sidecar it is unknown.
        "coverage": weakest(
            [scan_coverage.finding_coverage(f)[0] for f in findings] + list(scan_coverages or [])
        ),
        # What could not be established about the scan store (unreadable or evidence-less
        # latest attempts, unrecognised directories, an absent store).
        "limitations": list(limitations or []),
        # Targets whose latest attempt scanned nothing: absent from every finding.
        "not_scanned_targets": [
            {k: v for k, v in entry.items() if k != "url"} for entry in (not_scanned or [])
        ],
        "client_name": client_info.get("name", "Unknown"),
        "enterprise": client_info.get("enterprise", ""),
        "scan_date": date.today().isoformat(),
        "total_repos": len(repos),
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "org_score": org_score,
        "frameworks": frameworks,
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export enriched security findings to Power BI-ready CSVs"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. acme-corp)")
    parser.add_argument("--input", help="Path to enriched findings JSON. Default: stdin")
    parser.add_argument(
        "--scans-dir",
        help="Scan store to read the latest attempt per target from (coverage.json sidecars, "
        "not-scanned records). Default: ~/.dream-studio/security/scans/{client}/",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory. Default: ~/.dream-studio/security/datasets/{client}/",
    )
    args = parser.parse_args()

    if args.scans_dir:
        # An explicit scan store that is not there is a typo, not "no information": say so
        # before anything is written, or every unscanned target is hidden by it.
        explicit = Path(args.scans_dir)
        if not explicit.exists():
            print(f"[export_dataset] ERROR: --scans-dir {explicit} does not exist", file=sys.stderr)
            sys.exit(1)
        if not explicit.is_dir():
            print(
                f"[export_dataset] ERROR: --scans-dir {explicit} is not a directory",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── Load input ────────────────────────────────────────────────────────────
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[export_dataset] ERROR: input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        raw_json = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "[export_dataset] ERROR: No --input specified and stdin is a TTY. "
                "Pipe generate_mitigations.py output or pass --input <path>.",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_json = sys.stdin.read()

    try:
        envelope = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[export_dataset] ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    if isinstance(envelope, list):
        findings = envelope
        gaps: list[dict] = []
        repo_scores: dict = {}
    elif isinstance(envelope, dict):
        findings = envelope.get("findings", [])
        gaps = envelope.get("gaps", [])
        repo_scores = envelope.get("repo_scores", {})
    else:
        print("[export_dataset] ERROR: Expected JSON array or object", file=sys.stderr)
        sys.exit(1)

    print(
        f"[export_dataset] Exporting {len(findings)} findings for client: {args.client}",
        file=sys.stderr,
    )

    # ── Output directory ──────────────────────────────────────────────────────
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else home_dir() / "security" / "datasets" / args.client
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[export_dataset] Output directory: {output_dir}", file=sys.stderr)

    # ── Load client profile ───────────────────────────────────────────────────
    client_profile = load_client_profile(args.client)
    weights = (
        client_profile.get("dashboard", {}).get("org_score", {}).get("weights", DEFAULT_WEIGHTS)
    )

    # ── Compute org score ─────────────────────────────────────────────────────
    org_score = compute_org_score(findings, weights)
    print(f"[export_dataset] Org score: {org_score}", file=sys.stderr)

    # ── What the scan store says about the latest attempt per target ─────────────────
    scans_dir = (
        Path(args.scans_dir) if args.scans_dir else home_dir() / "security" / "scans" / args.client
    )
    state = scan_state(scans_dir)
    scan_coverages, not_scanned = state.coverages, state.not_scanned
    for limitation in state.limitations:
        print(f"[export_dataset] {limitation}", file=sys.stderr)
    for entry in not_scanned:
        print(
            f"[export_dataset] target {entry['target']} was not scanned "
            f"({entry['date']}): {entry['reason']}",
            file=sys.stderr,
        )

    # ── Write findings.csv ────────────────────────────────────────────────────
    findings_rows = build_findings_csv(findings)
    write_csv(output_dir / "findings.csv", findings_rows, FINDINGS_FIELDS)

    # ── Write mitigations.csv ─────────────────────────────────────────────────
    mitigations_rows = build_mitigations_csv(findings)
    write_csv(output_dir / "mitigations.csv", mitigations_rows, MITIGATIONS_FIELDS)

    # ── Write compliance.csv ──────────────────────────────────────────────────
    compliance_rows = build_compliance_csv(findings, gaps)
    write_csv(output_dir / "compliance.csv", compliance_rows, COMPLIANCE_FIELDS)

    # ── Write repos.csv ───────────────────────────────────────────────────────
    repos_rows = build_repos_csv(findings, repo_scores, state.attempts)
    write_csv(output_dir / "repos.csv", repos_rows, REPOS_FIELDS)

    # ── Write targets.csv (all target types) ─────────────────────────────
    targets_rows = build_targets_csv(findings, repo_scores, not_scanned, state.attempts)
    write_csv(output_dir / "targets.csv", targets_rows, TARGETS_FIELDS)

    # ── Write trends.csv (append if exists) ───────────────────────────────────
    trends_path = output_dir / "trends.csv"
    trends_rows = build_trends_row(findings, org_score, trends_path)
    write_csv(trends_path, trends_rows, TRENDS_FIELDS)

    # ── Write metadata.json ───────────────────────────────────────────────────
    metadata = build_metadata(
        client_profile, findings, org_score, scan_coverages, not_scanned, state.limitations
    )
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[export_dataset] Wrote metadata.json → {metadata_path}", file=sys.stderr)

    # ── Check for existing netcompat.csv (passthrough) ────────────────────────
    netcompat_path = output_dir / "netcompat.csv"
    if netcompat_path.exists():
        print(
            f"[export_dataset] netcompat.csv already exists at {netcompat_path} — preserved",
            file=sys.stderr,
        )
    else:
        print(
            "[export_dataset] netcompat.csv not found — skipping (run analyze_netcompat.py to generate)",
            file=sys.stderr,
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(
        f"[export_dataset] Done. Files written to {output_dir}:\n"
        f"  findings.csv ({len(findings_rows)} rows)\n"
        f"  mitigations.csv ({len(mitigations_rows)} rows)\n"
        f"  compliance.csv ({len(compliance_rows)} rows)\n"
        f"  repos.csv ({len(repos_rows)} rows)\n"
        f"  targets.csv ({len(targets_rows)} rows)\n"
        f"  trends.csv ({len(trends_rows)} rows)\n"
        f"  metadata.json (org_score={org_score})",
        file=sys.stderr,
    )

    # Emit metadata to stdout so pipeline callers can inspect it
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
