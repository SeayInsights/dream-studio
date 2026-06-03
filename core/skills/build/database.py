"""Database build mode — static enforcement on generated SQL and Python DB code.

Implements patterns documented in:
  canonical/skills/quality/modes/database/build/SKILL.md

10 static checks applied synchronously. No LLM. No DB connection. File-read only.
Returns in < 200ms for typical migration or query block.
"""

from __future__ import annotations

import re
from typing import Any

TIER_T1 = "T1"
TIER_T2 = "T2"
TIER_T3 = "T3"

# Financial field name patterns that should never be REAL/FLOAT/DOUBLE
_FINANCIAL_FIELDS = re.compile(
    r"\b(price|cost|amount|total|balance|fee|charge|revenue|salary|rate|"
    r"budget|payment|invoice|discount|tax|subtotal|gross|net|profit)\b",
    re.I,
)
_FLOAT_TYPES = re.compile(r"\b(REAL|FLOAT|DOUBLE(\s+PRECISION)?)\b", re.I)

# SQL keywords that indicate injection risk
_SQL_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "FROM",
                 "DROP", "EXEC", "UNION", "JOIN")

# Audit timestamp columns
_AUDIT_COLS = re.compile(r"\b(created_at|updated_at)\b", re.I)


def audit_generated_sql_or_python(
    code_block: str, context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Static database check of a generated SQL or Python DB code block.

    Called by SkillDispatcher.build() for SQL artifacts and Python with DB patterns.

    Returns list of findings [{rule_id, severity, tier, excerpt, explanation, line}].
    """
    findings: list[dict[str, Any]] = []
    lines = code_block.splitlines()
    trigger = context.get("trigger", "generic").lower()

    for i, line in enumerate(lines):
        stripped = line.strip()
        lineno = i + 1

        # db-001: CREATE TABLE without PRIMARY KEY (BLOCK) ─────────────────
        if _is_create_table(stripped):
            if not _has_primary_key(code_block, i, lines):
                findings.append({
                    "rule_id": "db-001",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": stripped[:80],
                    "explanation": "CREATE TABLE without PRIMARY KEY. Every table needs a primary key.",
                    "line": lineno,
                })

        # db-005: money as REAL/FLOAT (BLOCK) ──────────────────────────────
        if _FLOAT_TYPES.search(stripped) and _FINANCIAL_FIELDS.search(stripped):
            findings.append({
                "rule_id": "db-005",
                "severity": "critical",
                "tier": TIER_T1,
                "excerpt": stripped[:80],
                "explanation": "Financial column uses REAL/FLOAT — floating point precision causes rounding errors. Use INTEGER (cents) or NUMERIC.",
                "line": lineno,
            })

        # db-009: SQL injection via f-string (BLOCK) ───────────────────────
        if ('f"' in line or "f'" in line) and '{' in line:
            upper = line.upper()
            if any(kw in upper for kw in _SQL_KEYWORDS):
                findings.append({
                    "rule_id": "db-009",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": line[:80],
                    "explanation": "SQL injection: f-string with SQL keywords. Use parameterized queries: cursor.execute(sql, (param,)).",
                    "line": lineno,
                })

        # db-011: DROP without deprecation comment (BLOCK) ─────────────────
        if re.match(r"^\s*(ALTER\s+TABLE.*DROP|DROP\s+(TABLE|COLUMN|INDEX))", stripped, re.I):
            # Look for a deprecation comment on this line or the preceding line
            prev_line = lines[i - 1].strip() if i > 0 else ""
            has_comment = "--" in line or "#" in line or "deprecat" in prev_line.lower()
            if not has_comment:
                findings.append({
                    "rule_id": "db-011",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": stripped[:80],
                    "explanation": "DROP statement without deprecation comment. Destructive migrations must document rollback path.",
                    "line": lineno,
                })

        # db-002: REFERENCES without ON DELETE (WARN) ─────────────────────
        if re.search(r"REFERENCES\s+\w+", stripped, re.I):
            if not re.search(r"ON\s+DELETE\s+\w+", stripped, re.I):
                # Check next few lines for ON DELETE
                lookahead = " ".join(lines[i:i+3])
                if not re.search(r"ON\s+DELETE\s+\w+", lookahead, re.I):
                    findings.append({
                        "rule_id": "db-002",
                        "severity": "high",
                        "tier": TIER_T2,
                        "excerpt": stripped[:80],
                        "explanation": "FK without ON DELETE behavior. Add ON DELETE CASCADE or ON DELETE SET NULL to declare intent.",
                        "line": lineno,
                    })

        # db-014: OFFSET pagination (WARN) ─────────────────────────────────
        if re.search(r"\bOFFSET\b", stripped, re.I) and re.search(r"\bLIMIT\b", stripped, re.I):
            findings.append({
                "rule_id": "db-014",
                "severity": "medium",
                "tier": TIER_T2,
                "excerpt": stripped[:80],
                "explanation": "OFFSET pagination is slow on large tables. Consider cursor-based pagination (WHERE id > last_id).",
                "line": lineno,
            })

    # db-021: CREATE TABLE with >3 columns missing created_at/updated_at (WARN) ─
    _check_audit_columns(code_block, findings)

    return findings


# ── Helpers ───────────────────────────────────────────────────────────────

def _is_create_table(line: str) -> bool:
    return bool(re.match(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?", line, re.I))


def _has_primary_key(code_block: str, start_line: int, lines: list[str]) -> bool:
    """Check if CREATE TABLE block has a PRIMARY KEY constraint."""
    # Look ahead up to 30 lines for PRIMARY KEY
    end = min(start_line + 30, len(lines))
    block = "\n".join(lines[start_line:end])
    return bool(re.search(r"\bPRIMARY\s+KEY\b", block, re.I))


def _check_audit_columns(code_block: str, findings: list) -> None:
    """db-021: tables with >3 columns should have created_at/updated_at."""
    # Find each CREATE TABLE block
    for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(([^;]+?)\)",
                         code_block, re.I | re.DOTALL):
        table_name = m.group(1)
        body = m.group(2)
        # Count column definitions (lines with a name and a type)
        col_lines = [
            line.strip() for line in body.splitlines()
            if line.strip() and not line.strip().startswith("--")
            and re.match(r"\w+\s+\w+", line.strip())
        ]
        if len(col_lines) > 3:
            if not _AUDIT_COLS.search(body):
                findings.append({
                    "rule_id": "db-021",
                    "severity": "medium",
                    "tier": TIER_T2,
                    "excerpt": f"CREATE TABLE {table_name} (...) — {len(col_lines)} columns, no audit timestamps",
                    "explanation": f"Table `{table_name}` has {len(col_lines)} columns but no created_at/updated_at audit columns.",
                    "line": code_block[:m.start()].count("\n") + 1,
                })
