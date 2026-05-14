"""Decision instrumentation gap analysis."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

from core.event_store.studio_db import _connect
from .discovery import DiscoveredDecisionPoint, discover_decision_points
from .schema import Decision


@dataclass
class CoverageGapReport:
    """Report of instrumentation gaps."""

    missing_instrumentation: List[DiscoveredDecisionPoint]
    over_instrumentation: List[Decision]
    suspicious_unlogged_logic: List[dict]
    coverage_by_file: dict


def analyze_gaps(scan_dirs: List[str]) -> CoverageGapReport:
    """Analyze gaps between discovered decision points and emitted decisions.

    Args:
        scan_dirs: Directories to scan for decision points

    Returns:
        CoverageGapReport with identified gaps
    """
    # Discover potential decision points via AST
    discovered = discover_decision_points(scan_dirs)

    # Get emitted decisions from database
    with _connect() as conn:
        emitted_rows = conn.execute("""SELECT decision_id, decision_type, source_subsystem, context
               FROM decision_log""").fetchall()

    # Build coverage map by file
    coverage_by_file = {}
    for point in discovered:
        file_key = point.file
        if file_key not in coverage_by_file:
            coverage_by_file[file_key] = {
                "total_discovered": 0,
                "likely_covered": 0,
                "high_confidence_uncovered": 0,
            }
        coverage_by_file[file_key]["total_discovered"] += 1

    # Check which discovered points are likely covered
    missing = []
    for point in discovered:
        # Heuristic: a point is covered if there's a decision emission
        # in the same file or subsystem with matching semantic category
        is_covered = _is_likely_covered(point, emitted_rows)

        if not is_covered:
            if point.confidence > 0.6:
                coverage_by_file[point.file]["high_confidence_uncovered"] += 1
            missing.append(point)
        else:
            coverage_by_file[point.file]["likely_covered"] += 1

    # Identify over-instrumentation (decisions with no real impact)
    # Heuristic: decisions with very low confidence or no linked events
    over_instrumented = []  # Placeholder for now

    # Identify suspicious unlogged logic
    suspicious = _find_suspicious_patterns(discovered, emitted_rows)

    return CoverageGapReport(
        missing_instrumentation=missing,
        over_instrumentation=over_instrumented,
        suspicious_unlogged_logic=suspicious,
        coverage_by_file=coverage_by_file,
    )


def _is_likely_covered(point: DiscoveredDecisionPoint, emitted_decisions: List[tuple]) -> bool:
    """Heuristic check if a decision point is covered.

    Args:
        point: Discovered decision point
        emitted_decisions: List of (decision_id, type, subsystem, context) tuples

    Returns:
        True if likely covered by instrumentation
    """
    # Extract file path for matching
    file_name = point.file.split("\\")[-1].replace(".py", "")

    for decision in emitted_decisions:
        decision_type = decision[1]
        subsystem = decision[2]

        # Match by semantic category
        if point.decision_type_guess in decision_type:
            return True

        # Match by subsystem (file name alignment)
        if file_name in subsystem:
            # Check if types are compatible
            if _types_compatible(point.decision_type_guess, decision_type):
                return True

    return False


def _types_compatible(guess: str, actual: str) -> bool:
    """Check if guessed type is compatible with actual decision type."""
    compat_map = {
        "trust_score": ["trust_score"],
        "ttl_assignment": ["ttl"],
        "unlock_pattern": ["unlock"],
        "guardrail_policy": ["guardrail"],
        "routing": ["route", "dispatch"],
        "threshold_check": ["trust", "ttl", "score"],
        "policy_check": ["policy", "guardrail"],
        "return_selection": ["trust", "ttl", "unlock"],
        "fallback_default": ["ttl", "trust"],
    }

    if guess not in compat_map:
        return False

    for pattern in compat_map[guess]:
        if pattern in actual:
            return True

    return False


def _find_suspicious_patterns(
    discovered: List[DiscoveredDecisionPoint], emitted_decisions: List[tuple]
) -> List[dict]:
    """Find suspicious patterns in uncovered logic.

    Args:
        discovered: All discovered decision points
        emitted_decisions: All emitted decisions

    Returns:
        List of suspicious patterns (file, pattern type, count)
    """
    suspicious = []

    # Group by file
    file_groups = {}
    for point in discovered:
        if point.file not in file_groups:
            file_groups[point.file] = []
        file_groups[point.file].append(point)

    # Check for files with many uncovered high-confidence points
    for file_path, points in file_groups.items():
        high_conf_points = [p for p in points if p.confidence > 0.7]
        if len(high_conf_points) >= 3:
            # Check if ANY decisions are emitted from this file
            file_name = file_path.split("\\")[-1].replace(".py", "")
            has_coverage = any(file_name in d[2] for d in emitted_decisions)

            if not has_coverage:
                suspicious.append(
                    {
                        "file": file_path,
                        "pattern": "no_instrumentation",
                        "count": len(high_conf_points),
                        "severity": "high",
                    }
                )

    return suspicious
