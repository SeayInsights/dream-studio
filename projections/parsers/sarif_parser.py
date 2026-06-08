"""SARIF file parser for security findings.

Parses SARIF 2.1.0 format files from security scanning tools (Semgrep, Bandit, Trivy, etc.)
and writes findings to the security_events spine via record_finding() (AD-6 / WO-Y).

Usage:
    from projections.parsers.sarif_parser import parse_sarif_file

    count = parse_sarif_file('/path/to/scan-results.sarif')
    print(f"Imported {count} findings")

SARIF format reference: https://docs.oasis-open.org/sarif/sarif/v2.1.0/
"""

from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.findings.mutations import record_finding as _record_finding  # noqa: E402

logger = logging.getLogger(__name__)

# SARIF severity mapping to sec_sarif_findings severity levels
# sec_sarif_findings.severity constraint: ('critical', 'high', 'medium', 'low', 'info')
SARIF_TO_FINDING_SEVERITY = {
    "error": "high",  # SARIF 'error' → finding 'high'
    "warning": "medium",  # SARIF 'warning' → finding 'medium'
    "note": "low",  # SARIF 'note' → finding 'low'
    "none": "info",  # SARIF 'none' → finding 'info'
}

# Finding severity to activity_log severity mapping
# activity_log.severity constraint: ('info', 'warning', 'error', 'critical')
FINDING_TO_ACTIVITY_SEVERITY = {
    "critical": "critical",
    "high": "error",
    "medium": "warning",
    "low": "info",
    "info": "info",
}

# Severity to activity_log status mapping
# critical/high → 'failed' (needs attention)
# medium → 'in_progress' (should review)
# low/info → 'completed' (noted but not blocking)
SEVERITY_TO_STATUS = {
    "critical": "failed",
    "high": "failed",
    "medium": "in_progress",
    "low": "completed",
    "info": "completed",
}


def _extract_cwe_ids(result: dict) -> Optional[str]:
    """Extract CWE IDs from SARIF result object.

    SARIF can store CWE IDs in multiple locations:
    - result.properties.tags (e.g., ["CWE-79", "OWASP-A03"])
    - result.taxa (references to taxonomies)
    - result.properties (custom properties)

    Args:
        result: SARIF result object

    Returns:
        JSON string of CWE IDs (e.g., '["CWE-79", "CWE-89"]') or None
    """
    cwe_ids = []

    # Check properties.tags for CWE IDs
    if "properties" in result and "tags" in result["properties"]:
        tags = result["properties"]["tags"]
        if isinstance(tags, list):
            cwe_ids.extend([tag for tag in tags if tag.startswith("CWE-")])

    # Check taxa references (SARIF 2.1.0 taxonomies)
    if "taxa" in result:
        taxa = result["taxa"]
        if isinstance(taxa, list):
            for taxon in taxa:
                if isinstance(taxon, dict) and "id" in taxon:
                    taxon_id = taxon["id"]
                    if taxon_id.startswith("CWE-"):
                        cwe_ids.append(taxon_id)

    return json.dumps(cwe_ids) if cwe_ids else None


def _extract_cvss_score(result: dict) -> Optional[float]:
    """Extract CVSS score from SARIF result properties.

    Args:
        result: SARIF result object

    Returns:
        CVSS score (0.0-10.0) or None
    """
    if "properties" in result:
        props = result["properties"]
        # Common property names for CVSS
        for key in ["cvss", "cvssScore", "cvss_score", "score"]:
            if key in props:
                try:
                    return float(props[key])
                except (ValueError, TypeError):
                    continue
    return None


def _normalize_severity(sarif_level: str) -> str:
    """Map SARIF severity level to finding severity.

    Args:
        sarif_level: SARIF level ('error', 'warning', 'note', 'none')

    Returns:
        Finding severity ('critical', 'high', 'medium', 'low', 'info')
    """
    return SARIF_TO_FINDING_SEVERITY.get(sarif_level.lower(), "medium")


def _check_duplicate(rule_id: str, file_path: str, line_number: Optional[int]) -> bool:
    """Check if a finding already exists in security_events.

    Deduplication logic: same rule_id + file_path + line_number = duplicate.
    Reads from the security_events spine (vuln_class stores rule_id for SARIF findings).
    """
    try:
        from core.config.database import get_connection

        with get_connection(read_only=True) as conn:
            if line_number is not None:
                row = conn.execute(
                    "SELECT 1 FROM security_events"
                    " WHERE event_kind = 'finding.recorded'"
                    "   AND vuln_class = ? AND file_path = ? AND line_number = ? LIMIT 1",
                    (rule_id, file_path, line_number),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM security_events"
                    " WHERE event_kind = 'finding.recorded'"
                    "   AND vuln_class = ? AND file_path = ? AND line_number IS NULL LIMIT 1",
                    (rule_id, file_path),
                ).fetchone()
            return row is not None
    except Exception:
        return False  # Fail-open: if check errors, allow the insert attempt.


def parse_sarif_file(file_path: str) -> int:
    """Parse a SARIF file and import findings into the database.

    Supports SARIF 2.1.0 schema. Extracts:
    - Tool name
    - Rule ID and severity
    - File path and line number
    - CWE IDs and CVSS scores
    - Finding message

    For each finding:
    1. Check for duplicates (skip if exists)
    2. Emit canonical SECURITY_FINDING_RECORDED event via spool
    3. Insert into sec_sarif_findings

    Args:
        file_path: Path to SARIF JSON file

    Returns:
        Count of findings imported (excludes duplicates and parse errors)

    Raises:
        FileNotFoundError: If SARIF file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    sarif_path = Path(file_path)

    if not sarif_path.exists():
        logger.error(f"SARIF file not found: {file_path}")
        raise FileNotFoundError(f"SARIF file not found: {file_path}")

    try:
        with open(sarif_path, "r", encoding="utf-8") as f:
            sarif_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in SARIF file {file_path}: {e}")
        raise

    # Validate SARIF structure
    if "runs" not in sarif_data:
        logger.error(f"Invalid SARIF: missing 'runs' array in {file_path}")
        return 0

    imported_count = 0
    skipped_duplicates = 0
    skipped_malformed = 0

    for run_idx, run in enumerate(sarif_data["runs"]):
        # Extract tool name
        tool_name = "unknown"
        if "tool" in run and "driver" in run["tool"]:
            driver = run["tool"]["driver"]
            tool_name = driver.get("name", "unknown")

        # Process results
        results = run.get("results", [])

        for result_idx, result in enumerate(results):
            try:
                # Extract required fields
                rule_id = result.get("ruleId")
                if not rule_id:
                    logger.warning(f"Skipping result {result_idx} in run {run_idx}: missing ruleId")
                    skipped_malformed += 1
                    continue

                message_obj = result.get("message", {})
                message = message_obj.get("text", "No message provided")

                # Extract location (file path and line number)
                locations = result.get("locations", [])
                if not locations:
                    logger.warning(f"Skipping result {result_idx}: no locations")
                    skipped_malformed += 1
                    continue

                first_location = locations[0]
                physical_location = first_location.get("physicalLocation", {})
                artifact_location = physical_location.get("artifactLocation", {})
                file_path = artifact_location.get("uri", "unknown")

                region = physical_location.get("region", {})
                line_number = region.get("startLine")

                # Extract severity
                sarif_level = result.get("level", "warning")
                finding_severity = _normalize_severity(sarif_level)

                # Extract optional fields
                cwe_ids_raw = _extract_cwe_ids(result)
                cwe_id = None
                if cwe_ids_raw:
                    import json as _json

                    cwe_list = _json.loads(cwe_ids_raw)
                    cwe_id = cwe_list[0] if cwe_list else None

                # Dedup check against security_events spine
                if _check_duplicate(rule_id, file_path, line_number):
                    logger.debug(
                        f"Skipping duplicate finding: {rule_id} in {file_path}:{line_number or '?'}"
                    )
                    skipped_duplicates += 1
                    continue

                # Write to security_events spine via record_finding() (AD-6)
                _record_finding(
                    severity=finding_severity,
                    title=message,
                    file_path=file_path,
                    line_number=line_number,
                    scanner_type=tool_name,
                    cwe_id=cwe_id,
                    vuln_class=rule_id,  # rule_id stored in vuln_class for dedup
                )

                imported_count += 1

            except Exception as e:
                logger.error(f"Error parsing result {result_idx} in run {run_idx}: {e}")
                skipped_malformed += 1
                continue

    logger.info(
        f"SARIF import complete: {imported_count} imported, "
        f"{skipped_duplicates} duplicates, {skipped_malformed} malformed"
    )

    return imported_count


if __name__ == "__main__":
    # CLI usage for testing
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Parse SARIF security findings")
    parser.add_argument("sarif_file", help="Path to SARIF JSON file")

    args = parser.parse_args()

    try:
        count = parse_sarif_file(args.sarif_file)
        print(f"[OK] Imported {count} findings")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
