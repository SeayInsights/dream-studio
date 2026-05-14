"""Unified decision audit engine."""

from __future__ import annotations
from dataclasses import dataclass

from .coverage_model import DecisionCoverageReport, compute_coverage
from .audit import CoverageGapReport, analyze_gaps
from .integrity import CausalIntegrityReport, validate_causal_integrity


@dataclass
class SystemDecisionAudit:
    """Unified system decision audit report."""

    coverage_report: DecisionCoverageReport
    gap_report: CoverageGapReport
    integrity_report: CausalIntegrityReport
    risk_score: float


def run_full_audit(scan_dirs: list[str] | None = None) -> SystemDecisionAudit:
    """Run complete decision audit across all subsystems.

    Args:
        scan_dirs: Directories to scan (defaults to control/, guardrails/, core/)

    Returns:
        SystemDecisionAudit with complete analysis
    """
    if scan_dirs is None:
        scan_dirs = ["control/", "guardrails/", "core/decisions/", "core/storage/", "core/events/"]

    # Run coverage analysis
    coverage_report = compute_coverage()

    # Run gap analysis
    gap_report = analyze_gaps(scan_dirs)

    # Update coverage report with discovered decision points
    coverage_report.total_behavioral_decision_points = sum(
        stats["total_discovered"] for stats in gap_report.coverage_by_file.values()
    )
    coverage_report.missing_decisions = gap_report.missing_instrumentation

    # Recalculate coverage ratio
    if coverage_report.total_behavioral_decision_points > 0:
        coverage_report.coverage_ratio = (
            coverage_report.instrumented_decisions
            / coverage_report.total_behavioral_decision_points
        )

    # Run integrity validation
    integrity_report = validate_causal_integrity()

    # Calculate risk score
    risk_score = _calculate_risk_score(coverage_report, gap_report, integrity_report)

    return SystemDecisionAudit(
        coverage_report=coverage_report,
        gap_report=gap_report,
        integrity_report=integrity_report,
        risk_score=risk_score,
    )


def _calculate_risk_score(
    coverage: DecisionCoverageReport, gaps: CoverageGapReport, integrity: CausalIntegrityReport
) -> float:
    """Calculate overall system risk score.

    Risk scoring rules:
    - Missing decision coverage = high risk (weight 0.5)
    - Orphan events = medium risk (weight 0.3)
    - Unlinked decisions = medium risk (weight 0.2)

    Returns:
        Risk score (0.0 = no risk, 1.0 = maximum risk)
    """
    # Coverage risk: proportion of missing instrumentation
    coverage_risk = 1.0 - coverage.coverage_ratio

    # Event orphan risk: proportion of orphan events
    total_events = len(integrity.orphan_events) + 100  # Estimate denominator
    event_orphan_risk = len(integrity.orphan_events) / total_events

    # Decision orphan risk: proportion of unlinked decisions
    total_decisions = coverage.instrumented_decisions if coverage.instrumented_decisions > 0 else 1
    decision_orphan_risk = len(coverage.unlinked_decisions) / total_decisions

    # Weighted combination
    risk_score = 0.5 * coverage_risk + 0.3 * event_orphan_risk + 0.2 * decision_orphan_risk

    return min(1.0, max(0.0, risk_score))


def format_audit_report(audit: SystemDecisionAudit) -> str:
    """Format audit report as human-readable text.

    Args:
        audit: SystemDecisionAudit to format

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("DECISION COVERAGE & CAUSAL INTEGRITY AUDIT")
    lines.append("=" * 70)
    lines.append("")

    # Coverage summary
    lines.append("COVERAGE ANALYSIS")
    lines.append("-" * 70)
    lines.append(
        f"Total decision points discovered: {audit.coverage_report.total_behavioral_decision_points}"
    )
    lines.append(f"Instrumented decisions: {audit.coverage_report.instrumented_decisions}")
    lines.append(f"Coverage ratio: {audit.coverage_report.coverage_ratio:.1%}")
    lines.append(f"Missing instrumentation: {len(audit.coverage_report.missing_decisions)} points")
    lines.append("")

    # Top missing decision hotspots
    if audit.coverage_report.missing_decisions:
        lines.append("TOP 10 MISSING DECISION HOTSPOTS")
        lines.append("-" * 70)

        # Group by file
        file_counts = {}
        for point in audit.coverage_report.missing_decisions:
            file_key = point.file.split("\\")[-1]
            if file_key not in file_counts:
                file_counts[file_key] = []
            file_counts[file_key].append(point)

        # Sort by count
        sorted_files = sorted(file_counts.items(), key=lambda x: len(x[1]), reverse=True)[:10]

        for file_name, points in sorted_files:
            lines.append(f"  {file_name}: {len(points)} uncovered points")
            # Show top 3 highest confidence
            top_points = sorted(points, key=lambda p: p.confidence, reverse=True)[:3]
            for point in top_points:
                lines.append(f"    - Line {point.line}: {point.code_snippet[:60]}")
                lines.append(
                    f"      Type: {point.decision_type_guess} (confidence: {point.confidence:.1%})"
                )
        lines.append("")

    # Integrity summary
    lines.append("CAUSAL INTEGRITY")
    lines.append("-" * 70)
    lines.append(f"Orphan events: {len(audit.integrity_report.orphan_events)}")
    lines.append(f"Orphan decisions: {len(audit.integrity_report.orphan_decisions)}")
    lines.append(f"Broken links: {len(audit.integrity_report.broken_links)}")
    lines.append(f"Integrity score: {audit.integrity_report.integrity_score:.1%}")
    lines.append("")

    if audit.integrity_report.orphan_events[:5]:
        lines.append("Sample orphan events:")
        for event in audit.integrity_report.orphan_events[:5]:
            lines.append(f"  - {event}")
        lines.append("")

    # Risk assessment
    lines.append("RISK ASSESSMENT")
    lines.append("-" * 70)
    lines.append(f"Overall risk score: {audit.risk_score:.1%}")

    if audit.risk_score > 0.7:
        risk_level = "HIGH"
    elif audit.risk_score > 0.4:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    lines.append(f"Risk level: {risk_level}")
    lines.append("")

    # Suspicious patterns
    if audit.gap_report.suspicious_unlogged_logic:
        lines.append("SUSPICIOUS UNLOGGED LOGIC")
        lines.append("-" * 70)
        for pattern in audit.gap_report.suspicious_unlogged_logic:
            lines.append(f"  {pattern['file']}: {pattern['pattern']} ({pattern['count']} points)")
            lines.append(f"    Severity: {pattern['severity']}")
        lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)
