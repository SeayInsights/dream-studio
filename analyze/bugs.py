from pathlib import Path
from typing import Dict, Any, List
import re

def analyze_bugs(path: Path, project_data: Dict[str, Any], stack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze code for common bug patterns.

    Detected patterns:
    - bare_except: catches all exceptions (type: logic_error)
    - hardcoded_secret: API keys, passwords in code (type: security_flaw)
    - sql_injection: f-strings in SQL queries (type: security_flaw)
    - unused_import: imports never used (type: resource_leak)
    - technical_debt_todo/fixme/hack: technical debt markers (type: logic_error)

    Note: "type" field maps to pi_bugs schema constraints (logic_error, security_flaw, resource_leak, etc.)
          "pattern" field stores the specific pattern detected (bare_except, sql_injection, etc.)

    Returns:
        {
            "bugs": List[Dict],
            "critical_count": int,
            "high_count": int,
            "medium_count": int,
            "low_count": int
        }
    """
    bugs = []

    for file_path in path.rglob("*.py"):
        if _should_skip(file_path):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            rel_path = str(file_path.relative_to(path))

            # 1. Bare except
            for i, line in enumerate(lines):
                if re.match(r'^\s*except\s*:', line):
                    bugs.append({
                        "type": "logic_error",
                        "pattern": "bare_except",
                        "category": "correctness",
                        "severity": "high",
                        "file": rel_path,
                        "line": i + 1,
                        "issue": "Bare except clause",
                        "description": "Catches all exceptions including SystemExit and KeyboardInterrupt",
                        "proof": line.strip(),
                        "impact": "May hide critical errors and make debugging difficult",
                        "fix_recommendation": "Use specific exception types: except ValueError, except Exception",
                        "effort_estimate": "trivial",
                        "likelihood": 0.7,
                        "risk_score": 0.7 * 0.8  # high severity = 0.8
                    })

            # 2. Hardcoded secrets
            secret_patterns = [
                (r'(api[_-]?key|apikey)\s*=\s*["\']([a-zA-Z0-9]{20,})["\']', "API key"),
                (r'(password|passwd|pwd)\s*=\s*["\']([^"\']{8,})["\']', "password"),
                (r'(secret|token)\s*=\s*["\']([a-zA-Z0-9]{20,})["\']', "secret/token"),
            ]

            for i, line in enumerate(lines):
                for pattern, secret_type in secret_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        bugs.append({
                            "type": "security_flaw",
                            "pattern": "hardcoded_secret",
                            "category": "security",
                            "severity": "critical",
                            "file": rel_path,
                            "line": i + 1,
                            "issue": f"Hardcoded {secret_type}",
                            "description": f"Found hardcoded {secret_type} in source code",
                            "proof": line.strip()[:100],
                            "impact": "Security vulnerability: credentials exposed in version control",
                            "fix_recommendation": "Move to environment variables or secret management system",
                            "effort_estimate": "small",
                            "likelihood": 1.0,
                            "risk_score": 1.0 * 1.0  # critical = 1.0
                        })

            # 3. SQL injection (f-string in SQL)
            sql_patterns = [r'f["\'].*SELECT.*{', r'f["\'].*INSERT.*{', r'f["\'].*UPDATE.*{', r'f["\'].*DELETE.*{']
            for i, line in enumerate(lines):
                for pattern in sql_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        bugs.append({
                            "type": "security_flaw",
                            "pattern": "sql_injection",
                            "category": "security",
                            "severity": "critical",
                            "file": rel_path,
                            "line": i + 1,
                            "issue": "Potential SQL injection",
                            "description": "SQL query uses f-string with variable interpolation",
                            "proof": line.strip()[:100],
                            "impact": "SQL injection vulnerability: attacker can execute arbitrary SQL",
                            "fix_recommendation": "Use parameterized queries with ? placeholders",
                            "effort_estimate": "small",
                            "likelihood": 0.8,
                            "risk_score": 0.8 * 1.0
                        })

            # 4. Unused imports (simplified: import on its own line, never referenced)
            import_pattern = r'^import\s+([a-zA-Z0-9_\.]+)'
            from_pattern = r'^from\s+[a-zA-Z0-9_\.]+\s+import\s+([a-zA-Z0-9_]+)'

            imports = {}
            for i, line in enumerate(lines):
                match = re.match(import_pattern, line.strip())
                if match:
                    module = match.group(1).split('.')[-1]
                    imports[module] = i + 1

                match = re.match(from_pattern, line.strip())
                if match:
                    name = match.group(1)
                    imports[name] = i + 1

            for module, line_num in imports.items():
                # Check if module is used elsewhere
                usage_count = sum(1 for line in lines if module in line) - 1  # Subtract the import itself
                if usage_count == 0:
                    bugs.append({
                        "type": "resource_leak",
                        "pattern": "unused_import",
                        "category": "performance",
                        "severity": "low",
                        "file": rel_path,
                        "line": line_num,
                        "issue": f"Unused import: {module}",
                        "description": f"Module '{module}' is imported but never used",
                        "proof": f"import {module}",
                        "impact": "Unnecessary memory usage and slower startup",
                        "fix_recommendation": "Remove unused import",
                        "effort_estimate": "trivial",
                        "likelihood": 0.3,
                        "risk_score": 0.3 * 0.2  # low severity = 0.2
                    })

            # 5. TODO/FIXME/HACK comments
            debt_patterns = [(r'\bTODO\b', "TODO"), (r'\bFIXME\b', "FIXME"), (r'\bHACK\b', "HACK")]
            for i, line in enumerate(lines):
                for pattern, marker_type in debt_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        bugs.append({
                            "type": "logic_error",
                            "pattern": f"technical_debt_{marker_type.lower()}",
                            "category": "reliability",
                            "severity": "low",
                            "file": rel_path,
                            "line": i + 1,
                            "issue": f"{marker_type} marker found",
                            "description": f"Technical debt marker: {marker_type}",
                            "proof": line.strip()[:100],
                            "impact": "Indicates incomplete or temporary solution",
                            "fix_recommendation": "Address the TODO/FIXME or remove if no longer relevant",
                            "effort_estimate": None,
                            "likelihood": 0.5,
                            "risk_score": 0.5 * 0.2
                        })

        except Exception:
            pass

    # Count by severity
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for bug in bugs:
        severity = bug.get("severity", "low")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    # Store in database
    _store_bugs(bugs)

    return {
        "bugs": bugs,
        "critical_count": severity_counts["critical"],
        "high_count": severity_counts["high"],
        "medium_count": severity_counts["medium"],
        "low_count": severity_counts["low"]
    }

def _should_skip(file_path: Path) -> bool:
    """Skip test files, generated files."""
    skip_patterns = ["__pycache__", "node_modules", ".venv", "venv", "dist/", "build/", ".next", "migrations/"]
    return any(pattern in str(file_path) for pattern in skip_patterns)

def _store_bugs(bugs: List[Dict]) -> None:
    """Store bugs in pi_bugs table."""
    try:
        import sys
        from pathlib import Path as SysPath
        sys.path.insert(0, str(SysPath(__file__).resolve().parents[1] / "hooks"))

        from lib.studio_db import _connect
        from datetime import datetime, timezone

        conn = _connect()
        for bug in bugs:
            # Create unique ID from file + line + pattern
            file_path = bug.get("file", "")
            line_num = bug.get("line", 0)
            pattern = bug.get("pattern", bug.get("type", ""))
            bug_id = f"bug-{abs(hash(f'{file_path}:{line_num}:{pattern}'))}"
            conn.execute("""
                INSERT OR REPLACE INTO pi_bugs (
                    bug_id, project_id, bug_type, category, severity,
                    file, line, issue, description, proof,
                    impact, fix_recommendation, effort_estimate,
                    likelihood, risk_score, status, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bug_id,
                "dream-studio",
                bug.get("type"),
                bug.get("category"),
                bug.get("severity"),
                bug.get("file"),
                bug.get("line"),
                bug.get("issue"),
                bug.get("description"),
                bug.get("proof"),
                bug.get("impact"),
                bug.get("fix_recommendation"),
                bug.get("effort_estimate"),
                bug.get("likelihood"),
                bug.get("risk_score"),
                "open",
                datetime.now(timezone.utc).isoformat()
            ))
        conn.commit()
    except Exception as e:
        # Silent fail but print to stderr for debugging
        import sys
        print(f"Warning: Failed to store bugs in database: {e}", file=sys.stderr)
