"""Gate: a test fixture may not invent a column Dream Studio does not have.

THE DEFECT CLASS. A fixture writes its own ``CREATE TABLE``, so it can describe any schema
at all -- including one production does not have. The test still passes; it just stops
measuring anything real. A fixture asserting on a column production never writes cannot
fail for the right reason, and the divergence also hides errors in the other direction:
on 2026-09-05 a fixture whose ``business_tasks`` predated ``created_at`` was the only
place a real enforcement query raised, and a fail-open handler turned that into "an
authority write happened" for every work order on the machine.

WHAT IS CHECKED, and what deliberately is not.

* Inventing a column FAILS. Extra means the fixture is describing something else.
* Omitting columns is FINE. A minimal fixture is a legitimate, focused thing to write,
  and demanding full parity would turn every schema addition into a sweep of hundreds of
  test files for no gain. The asymmetry is the point.
* Resurrecting a dropped TABLE is out of scope here on purpose -- it is already enforced
  by ``core/gates/test_fixture_resurrection_guard.py``, wired into the blocking pre-push
  tier. Checking it again in a second gate would mean two ledgers to keep in agreement.

THE AUTHORITY IS THE REAL SCHEMA PATH. ``bootstrap_database`` runs the actual migration
chain against a temp file and the answer is read back out of ``sqlite_master``, rather
than parsing the baseline SQL and hoping the parse agrees with production. A gate that
duplicates the schema it checks eventually checks its own copy. Tables absent from a
fresh authority are skipped rather than reported: Dream Studio is a three-store model,
and ``ds_files`` living in ``files.db`` is not a defect in a ``studio.db`` schema.
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CREATE_RE = re.compile(
    r"CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[\"'`\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)[\"'`\]]?\s*\((?P<cols>.*)",
    re.IGNORECASE | re.DOTALL,
)

#: Clause keywords that open a table constraint rather than a column definition.
_CONSTRAINT_WORDS = frozenset({"primary", "foreign", "unique", "check", "constraint", "references"})

#: An exemption must name the exact table.column and state WHY, because a real one exists:
#: a drift-detection test has to build drift, and a schema-coherence fixture has to build
#: incoherence. Those are the subject under test, not a mistake. The reason is mandatory
#: so the exemption stays a decision someone made rather than a quiet hole.
_ALLOW_RE = re.compile(
    r"fixture-schema-parity:\s*allow\s+(?P<table>[A-Za-z_][\w]*)\.(?P<column>[A-Za-z_][\w]*)"
    r"\s*--\s*(?P<reason>\S.*)"
)

#: Shorter than this is not a reason, it is a shrug.
_MIN_REASON_CHARS = 20

#: This gate's own test file, whose fixtures are DDL strings written expressly to be
#: rejected -- including an exemption with a deliberately thin reason. Scanning it reports
#: those on-purpose defects as real ones. Same reason, and same remedy, as
#: ``tests/unit/test_schema_coherence_audit.py`` in ``_SELF_SCAN_EXCLUDE``.
_SELF_SCAN_EXCLUDE = frozenset({"tests/unit/test_fixture_schema_parity_gate.py"})


def canonical_schema() -> dict[str, set[str]]:
    """Table -> column names for a FRESH database, built by the real migration path."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "canonical.db"
        from core.config.sqlite_bootstrap import bootstrap_database

        bootstrap_database(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            ]
            schema: dict[str, set[str]] = {}
            for name in names:
                cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
                schema[name] = {str(col[1]) for col in cols}
            return schema
        finally:
            conn.close()


def _strip_sql_comments(text: str) -> str:
    """Remove `-- ...` comments. Without this, a commented column read as a column named
    `--`, and the words after it as more columns (`so`, `or`, `session`)."""
    return chr(10).join(line.split("--")[0] for line in text.splitlines())


def _split_columns(body: str) -> list[str]:
    """Column/constraint clauses from a CREATE TABLE body, split on top-level commas."""
    depth = 0
    current: list[str] = []
    parts: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break  # the closing paren of the CREATE TABLE itself
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _column_names(body: str) -> set[str]:
    names: set[str] = set()
    for clause in _split_columns(_strip_sql_comments(body)):
        words = clause.split()
        if not words:
            continue
        # `UNIQUE(snapshot_date, kind)` has no space before the paren, so the identifier
        # must be taken up TO the paren -- otherwise the whole call read as a column name.
        first = words[0].split("(")[0]
        if first.lower() in _CONSTRAINT_WORDS or not first:
            continue
        names.add(first.strip("\"'`[]"))
    return names


def _sql_literals(path: Path) -> list[str]:
    """Every string constant in the file. DDL is assembled from these.

    Read via the AST rather than a line regex so that a CREATE TABLE spanning several
    implicitly concatenated literals is seen whole -- which is how nearly all of them are
    written in this suite.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "CREATE" in node.value
    ]


def _exemptions(text: str) -> tuple[set[str], list[dict]]:
    """Declared `table.column` exemptions, plus complaints about unusable ones.

    An exemption whose reason is missing or perfunctory is itself reported. Otherwise the
    escape hatch would quietly become the norm -- which is how a rule turns back into
    prose.
    """
    allowed: set[str] = set()
    problems: list[dict] = []
    for match in _ALLOW_RE.finditer(text):
        reason = match.group("reason").strip()
        key = f"{match.group('table')}.{match.group('column')}"
        if len(reason) < _MIN_REASON_CHARS:
            problems.append({"key": key, "reason": reason})
            continue
        allowed.add(key)
    return allowed, problems


def _offenders_in(path: Path, schema: dict[str, set[str]], repo_root: Path) -> list[dict]:
    try:
        rel = str(path.relative_to(repo_root))
    except ValueError:
        rel = str(path)
    rel = rel.replace(chr(92), "/")
    if rel in _SELF_SCAN_EXCLUDE:
        return []

    try:
        allowed, thin = _exemptions(path.read_text(encoding="utf-8"))
    except OSError:
        return []

    offenders: list[dict] = [
        {
            "path": rel,
            "table": problem["key"].split(".")[0],
            "columns": [problem["key"].split(".")[1]],
            "message": (
                f"The exemption for {problem['key']} states no usable reason"
                f" ({problem['reason']!r}). An exemption exists for cases like a"
                " drift-detection fixture that must build drift; say which one this is,"
                f" in at least {_MIN_REASON_CHARS} characters, or fix the column."
            ),
        }
        for problem in thin
    ]
    for literal in _sql_literals(path):
        for match in _CREATE_RE.finditer(literal):
            name = match.group("name")
            if name.startswith("sqlite_"):
                continue
            if name not in schema:
                # Not an authority table: another store (files.db, events.db) or scratch
                # scaffolding. A dropped table reappearing here is the resurrection
                # guard's job, not this one's.
                continue
            invented = sorted(
                col
                for col in _column_names(match.group("cols")) - schema[name]
                if f"{name}.{col}" not in allowed
            )
            if invented:
                offenders.append(
                    {
                        "path": rel,
                        "table": name,
                        "columns": invented,
                        "message": (
                            f"Fixture gives {name!r} column(s) {invented} that a fresh"
                            " database does not have. A test asserting on a column"
                            " production never writes cannot fail for the right reason."
                            " Omitting columns is fine; inventing them is not."
                        ),
                    }
                )
    return offenders


def _iter_tests(repo_root: Path) -> list[Path]:
    base = repo_root / "tests"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts]


def run(repo_root: Path = REPO_ROOT, schema: dict[str, set[str]] | None = None) -> dict:
    """Scan repo_root/tests against schema (default: a freshly bootstrapped database)."""
    schema = canonical_schema() if schema is None else schema
    offenders: list[dict] = []
    files = _iter_tests(repo_root)
    for path in files:
        offenders.extend(_offenders_in(path, schema, repo_root))
    return {
        "status": "fail" if offenders else "pass",
        "files_scanned": len(files),
        "canonical_tables": len(schema),
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nfixture-schema-parity: FAILED - {len(result['offenders'])} fixture(s)"
            " describe a schema Dream Studio does not have.",
            file=sys.stderr,
        )
        return 1
    print(
        f"fixture-schema-parity: OK - {result['files_scanned']} test file(s) checked against"
        f" {result['canonical_tables']} canonical tables."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
