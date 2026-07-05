from datetime import UTC
from pathlib import Path
from typing import Any
import re


def build_dependency_graph(path: Path, languages: list) -> dict:
    """Stub — original control.analysis.lib.dependency_graph was removed."""
    return {"cycles": []}


def analyze_complexity(file_path: Path) -> dict:
    """Stub — original control.analysis.lib.complexity was removed."""
    return {"god_functions": []}


from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from emitters.shared.spool_writer import write_envelopes


def audit_architecture(
    path: Path, project_data: dict[str, Any], stack: dict[str, Any]
) -> dict[str, Any]:
    """
    Audit project architecture for violations.

    Args:
        path: Project root
        project_data: Discovery data
        stack: Stack metadata

    Returns:
        {
            "violations": List[Dict],
            "improvements": List[Dict],
            "health_score": float,
            "critical_count": int,
            "high_count": int,
            "medium_count": int,
            "low_count": int
        }
    """
    violations = []
    improvements = []

    languages = project_data.get("languages", [])

    # 1. Check for circular dependencies
    graph_data = build_dependency_graph(path, languages)
    for cycle in graph_data.get("cycles", []):
        violations.append(
            {
                "type": "circular_dependency",
                "severity": "high",
                "files": cycle,
                "description": f"Circular dependency detected: {' -> '.join(cycle)}",
                "impact": "Makes code harder to understand and maintain. Can cause import errors.",
                "fix_recommendation": "Break the cycle by extracting shared code to a separate module.",
                "effort_estimate": "medium",
            }
        )

        improvements.append(
            {
                "type": "break_cycle",
                "priority_score": 0.8,
                "target_files": cycle,
                "current_state": f"Circular dependency: {len(cycle)} files",
                "recommendation": "Extract shared functionality to a new module to break the cycle.",
                "benefit": "Improved code organization and reduced coupling",
                "effort_estimate": "medium",
            }
        )

    # 2. Check for god objects and god functions
    for file_path in path.rglob("*.py"):
        if _should_skip(file_path):
            continue

        rel_path = str(file_path.relative_to(path))

        # Count lines
        try:
            lines = len(
                [
                    l
                    for l in file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if l.strip()
                ]
            )
        except (OSError, UnicodeDecodeError):
            continue

        # God object check (>500 lines)
        if lines > 500:
            violations.append(
                {
                    "type": "god_object",
                    "severity": "medium",
                    "files": [rel_path],
                    "description": f"File is too large: {lines} lines (>500 threshold)",
                    "impact": "Large files are harder to understand and maintain.",
                    "fix_recommendation": "Split into smaller, focused modules.",
                    "effort_estimate": "large",
                }
            )

            improvements.append(
                {
                    "type": "extract_module",
                    "priority_score": 0.7,
                    "target_files": [rel_path],
                    "current_state": f"{lines} lines in single file",
                    "recommendation": "Split into multiple modules by responsibility.",
                    "benefit": "Improved readability and maintainability",
                    "effort_estimate": "large",
                }
            )

        # Analyze complexity to find god functions
        complexity_data = analyze_complexity(file_path)
        god_functions = complexity_data.get("god_functions", [])

        if god_functions:
            violations.append(
                {
                    "type": "god_function",
                    "severity": "low",
                    "files": [rel_path],
                    "description": f"Found {len(god_functions)} god function(s): {', '.join(god_functions[:3])}",
                    "impact": "Large functions are harder to test and maintain.",
                    "fix_recommendation": "Break down large functions into smaller, focused functions.",
                    "effort_estimate": "small",
                }
            )

    # 3. Check for layer violations (test imports prod internals)
    for file_path in path.rglob("test_*.py"):
        if _should_skip(file_path):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            # Check for imports from legacy hook library modules (internal modules)
            if re.search(r"from\s+\w+\.lib\._", content) or re.search(
                r"import\s+\w+\.lib\._", content
            ):
                rel_path = str(file_path.relative_to(path))
                violations.append(
                    {
                        "type": "layer_violation",
                        "severity": "medium",
                        "files": [rel_path],
                        "description": "Test file imports private implementation details (lib._*)",
                        "impact": "Tests become brittle and coupled to internal structure.",
                        "fix_recommendation": "Test public API only, not internal implementation.",
                        "effort_estimate": "small",
                    }
                )
        except (OSError, UnicodeDecodeError):
            pass

    # 4. Check for missing error handling (bare except)
    for file_path in path.rglob("*.py"):
        if _should_skip(file_path):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            bare_excepts = re.findall(r"^\s*except\s*:", content, re.MULTILINE)

            if bare_excepts:
                rel_path = str(file_path.relative_to(path))
                violations.append(
                    {
                        "type": "missing_error_handling",
                        "severity": "low",
                        "files": [rel_path],
                        "lines": [
                            str(i + 1)
                            for i, line in enumerate(content.splitlines())
                            if re.match(r"^\s*except\s*:", line)
                        ],
                        "description": f"Found {len(bare_excepts)} bare except clause(s)",
                        "impact": "Catches all exceptions, including system exits. Makes debugging harder.",
                        "fix_recommendation": "Specify exception types: except ValueError, except Exception, etc.",
                        "effort_estimate": "trivial",
                    }
                )
        except (OSError, UnicodeDecodeError):
            pass

    # Calculate health score
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for violation in violations:
        severity = violation.get("severity", "low")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    health_score = 10 - (
        severity_counts["critical"] * 2
        + severity_counts["high"] * 1
        + severity_counts["medium"] * 0.5
        + severity_counts["low"] * 0.1
    )
    health_score = max(0, min(10, health_score))

    # Store in database
    _store_violations(violations)
    _store_improvements(improvements)

    return {
        "violations": violations,
        "improvements": improvements,
        "health_score": round(health_score, 2),
        "critical_count": severity_counts["critical"],
        "high_count": severity_counts["high"],
        "medium_count": severity_counts["medium"],
        "low_count": severity_counts["low"],
    }


def _should_skip(file_path: Path) -> bool:
    """Skip test files, generated files, migrations."""
    skip_patterns = ["__pycache__", "node_modules", ".venv", "venv", "dist/", "build/", ".next"]
    return any(pattern in str(file_path) for pattern in skip_patterns)


def _store_violations(violations: list[dict]) -> None:
    """Store violations in pi_violations table."""
    if not violations:
        return

    try:
        import sys
        from pathlib import Path as SysPath

        sys.path.insert(0, str(SysPath(__file__).resolve().parents[1] / "hooks"))

        from core.config.database import transaction
        import json
        from datetime import datetime

        # Map specific violation types to schema categories
        TYPE_MAP = {
            "circular_dependency": "architecture",
            "god_object": "architecture",
            "god_function": "architecture",
            "layer_violation": "architecture",
            "missing_error_handling": "style",
        }

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.AUDIT_VIOLATIONS_CLEARED.value,
                    session_id=None,
                    payload={
                        "project_id": "dream-studio",
                        "violation_count": len(violations),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        with transaction() as conn:
            # Clear existing violations for this project to avoid duplicates
            conn.execute("DELETE FROM pi_violations WHERE project_id = 'dream-studio'")

            for v in violations:
                specific_type = v.get("type")
                schema_type = TYPE_MAP.get(specific_type, "architecture")

                # Include specific type in description
                description = f"[{specific_type}] {v.get('description', '')}"
                violation_id = f"viol-{abs(hash(str(v)))}"

                # Slice 3: Emit event via spool pipeline
                write_envelopes(
                    [
                        CanonicalEventEnvelope(
                            event_type=CanonicalEventType.AUDIT_VIOLATION_FOUND.value,
                            session_id=None,
                            payload={
                                "violation_id": violation_id,
                                "project_id": "dream-studio",
                                "violation_type": schema_type,
                                "specific_type": specific_type,
                                "severity": v.get("severity"),
                                "files": v.get("files", []),
                                "description": description,
                                "impact": v.get("impact"),
                            },
                            severity=v.get("severity", "low"),
                            confidence="unavailable",
                            project_id=None,
                        )
                    ]
                )

                conn.execute(
                    """
                    INSERT INTO pi_violations (
                        violation_id, project_id, violation_type, severity,
                        files, lines, description, impact, fix_recommendation,
                        effort_estimate, status, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        violation_id,
                        "dream-studio",
                        schema_type,
                        v.get("severity"),
                        json.dumps(v.get("files", [])),
                        json.dumps(v.get("lines", [])),
                        description,
                        v.get("impact"),
                        v.get("fix_recommendation"),
                        v.get("effort_estimate"),
                        "open",
                        datetime.now(UTC).isoformat(),
                    ),
                )
    except Exception as e:
        import traceback

        traceback.print_exc()  # Debug: show errors during development


def _store_improvements(improvements: list[dict]) -> None:
    """Store improvements in pi_improvements table."""
    if not improvements:
        return

    try:
        import sys
        from pathlib import Path as SysPath

        sys.path.insert(0, str(SysPath(__file__).resolve().parents[1] / "hooks"))

        from core.config.database import transaction
        import json
        from datetime import datetime

        # Map specific improvement types to schema categories
        TYPE_MAP = {
            "extract_module": "refactor",
            "break_cycle": "refactor",
            "add_tests": "test_coverage",
        }

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.AUDIT_IMPROVEMENTS_CLEARED.value,
                    session_id=None,
                    payload={
                        "project_id": "dream-studio",
                        "improvement_count": len(improvements),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        with transaction() as conn:
            # Clear existing improvements for this project to avoid duplicates
            conn.execute("DELETE FROM pi_improvements WHERE project_id = 'dream-studio'")

            for imp in improvements:
                specific_type = imp.get("type")
                schema_type = TYPE_MAP.get(specific_type, "refactor")

                # Include specific type in recommendation
                recommendation = f"[{specific_type}] {imp.get('recommendation', '')}"
                improvement_id = f"imp-{abs(hash(str(imp)))}"

                # Slice 3: Emit event via spool pipeline
                write_envelopes(
                    [
                        CanonicalEventEnvelope(
                            event_type=CanonicalEventType.AUDIT_IMPROVEMENT_FOUND.value,
                            session_id=None,
                            payload={
                                "improvement_id": improvement_id,
                                "project_id": "dream-studio",
                                "improvement_type": schema_type,
                                "specific_type": specific_type,
                                "priority_score": imp.get("priority_score"),
                                "target_files": imp.get("target_files", []),
                                "recommendation": recommendation,
                                "benefit": imp.get("benefit"),
                            },
                            confidence="unavailable",
                            project_id=None,
                        )
                    ]
                )

                conn.execute(
                    """
                    INSERT INTO pi_improvements (
                        improvement_id, project_id, improvement_type,
                        priority_score, target_files, current_state,
                        recommendation, benefit, effort_estimate,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        improvement_id,
                        "dream-studio",
                        schema_type,
                        imp.get("priority_score"),
                        json.dumps(imp.get("target_files", [])),
                        imp.get("current_state"),
                        recommendation,
                        imp.get("benefit"),
                        imp.get("effort_estimate"),
                        "proposed",
                        datetime.now(UTC).isoformat(),
                    ),
                )
    except Exception as e:
        import traceback

        traceback.print_exc()  # Debug: show errors during development
