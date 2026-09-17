"""Read every findings producer through one shape.

Three adapters, one output. Each is independently fail-soft: a missing DB, an
absent docstore or an unreadable JSONL yields no findings from that source
rather than failing the whole collection, because a partial view is useful and a
crashed view is not. What is NOT acceptable is silently returning nothing and
looking identical to "no findings" — so collect_findings also returns per-source
status, and the renderer shows it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from core.gates.security_verdict import is_security_blocked

from .model import Finding, normalize_severity

# A finding line inside an audit/harden markdown artifact, e.g.
#   - **BLOCKED — secrets in the repo.** ...
#   - **INFO — dashboard renders authority-derived strings.** ...
#   * PASS: no injection in the new DB write
_MD_FINDING_RE = re.compile(
    r"(?im)^\s*[-*]\s*\*{0,2}\s*"
    r"(BLOCKED|CRITICAL|HIGH|MEDIUM|LOW|INFO|PASS|WARN(?:ING)?)\b"
    r"\s*[—\-:]*\s*(.*)$"
)


def _demojibake(text: str) -> str:
    """Undo a UTF-8 -> cp1252 -> UTF-8 double-encoding, when that is lossless.

    Some audit artifacts were written to the docstore through a cp1252 round
    trip, so an em dash is stored as the three characters U+00E2 U+20AC U+201D
    ("a-circumflex, euro, right-double-quote") instead of U+2014. The bytes in
    the docstore are genuinely corrupt; this reader decodes them faithfully and
    therefore renders the corruption.

    Repair is attempted only when re-encoding as cp1252 and decoding as UTF-8
    both succeed. Any text that is NOT double-encoded contains a character
    cp1252 cannot represent (or produces invalid UTF-8) and is returned
    untouched, so correctly-stored text — accented Latin, CJK, emoji — is never
    altered. Verified by codepoint rather than by terminal output, because a
    cp1252 console misrepresents this in both directions.
    """
    if not text:
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("**", "").strip()).strip(" .")


# ---------------------------------------------------------------------------
# Source 1 — security_events rows in the authority DB
# ---------------------------------------------------------------------------


def from_security_events(db_path: Path, project_id: str | None = None) -> list[Finding]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "security_events" not in tables:
            return []
        sql = "SELECT * FROM security_events WHERE event_kind = 'finding.recorded'"
        params: tuple[Any, ...] = ()
        if project_id:
            sql += " AND project_id = ?"
            params = (project_id,)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    out: list[Finding] = []
    for r in rows:
        keys = r.keys()
        sev = normalize_severity(r["severity"] if "severity" in keys else None)
        title = _clean(r["title"] if "title" in keys else "") or "(untitled finding)"
        out.append(
            Finding(
                source="security_event",
                severity=sev,
                title=title,
                ref=str(r["event_id"]),
                detail=_clean(r["body"] if "body" in keys else ""),
                file_path=r["file_path"] if "file_path" in keys else None,
                line=r["line_number"] if "line_number" in keys else None,
                project_id=r["project_id"] if "project_id" in keys else None,
                created_at=r["created_at"] if "created_at" in keys else None,
                blocking=sev in ("critical", "high"),
                extra={
                    k: r[k]
                    for k in ("cwe_id", "owasp_category", "cve_id", "vuln_class", "scanner_type")
                    if k in keys and r[k]
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# Source 2 — audit / harden markdown artifacts in the docstore
# ---------------------------------------------------------------------------


def from_audit_markdown(files_db: Path, project_id: str | None = None) -> list[Finding]:
    conn = sqlite3.connect(f"file:{files_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "ds_files" not in tables:
            return []
        sql = (
            "SELECT name, content, project_id, created_at, version FROM ds_files "
            "WHERE (name LIKE '%security-audit%' OR name LIKE '%harden-results%')"
        )
        params: tuple[Any, ...] = ()
        if project_id:
            sql += " AND project_id = ?"
            params = (project_id,)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    out: list[Finding] = []
    for r in rows:
        content = r["content"]
        if isinstance(content, (bytes, bytearray)):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
        if not content:
            continue
        content = _demojibake(content)

        # The artifact's own blocking verdict, via the same parser the close
        # gates use — one definition, not a second opinion.
        doc_blocked = is_security_blocked(content)

        matched = False
        for label, rest in _MD_FINDING_RE.findall(content):
            matched = True
            sev = normalize_severity(label)
            text = _clean(rest)
            out.append(
                Finding(
                    source="audit_markdown",
                    severity=sev,
                    title=text[:160] or f"{label.upper()} finding",
                    ref=str(r["name"]),
                    detail=text,
                    project_id=r["project_id"],
                    created_at=r["created_at"],
                    blocking=(label.upper() == "BLOCKED"),
                    extra={"artifact": r["name"], "version": r["version"]},
                )
            )

        # An artifact whose prose blocks but whose lines didn't parse must still
        # surface — losing a blocker to a regex miss is the worst outcome here.
        if doc_blocked and not any(f.blocking for f in out if f.ref == r["name"]):
            out.append(
                Finding(
                    source="audit_markdown",
                    severity="critical",
                    title=f"Blocking verdict in {r['name']}",
                    ref=str(r["name"]),
                    detail="Artifact reports a BLOCKED finding marker.",
                    project_id=r["project_id"],
                    created_at=r["created_at"],
                    blocking=True,
                    extra={"artifact": r["name"], "unparsed": not matched},
                )
            )
    return out


# ---------------------------------------------------------------------------
# Source 3 — guardrail fire log (append-only JSONL nothing reads today)
# ---------------------------------------------------------------------------


def from_guard_log(jsonl_path: Path, project_id: str | None = None) -> list[Finding]:
    if not jsonl_path.is_file():
        return []
    out: list[Finding] = []
    with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            if project_id and d.get("project_id") != project_id:
                continue
            sev = normalize_severity(d.get("severity"))
            out.append(
                Finding(
                    source="guard_log",
                    severity=sev,
                    title=_clean(d.get("description") or d.get("rule_id") or "guard fire"),
                    ref=f"{jsonl_path.name}:{lineno}",
                    detail=_clean(d.get("matched_text") or ""),
                    file_path=d.get("target_path") or d.get("file_path"),
                    line=d.get("line_number"),
                    project_id=d.get("project_id"),
                    created_at=d.get("created_at") or d.get("timestamp"),
                    blocking=sev in ("critical", "high"),
                    extra={
                        k: d[k]
                        for k in ("rule_id", "risk_weight", "detection", "source", "status")
                        if d.get(k) is not None
                    },
                )
            )
    return out


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def collect_findings(
    *,
    db_path: Path | None = None,
    files_db: Path | None = None,
    guard_log: Path | None = None,
    project_id: str | None = None,
) -> tuple[list[Finding], list[dict[str, Any]]]:
    """Gather findings from every source.

    Returns (findings, sources) where `sources` records, per producer, whether
    it was read and what it yielded. A source that failed is reported as failed
    rather than silently contributing zero — "no findings" and "could not look"
    must never render identically.
    """
    plan: list[tuple[str, Path | None, Any]] = [
        ("security_event", db_path, from_security_events),
        ("audit_markdown", files_db, from_audit_markdown),
        ("guard_log", guard_log, from_guard_log),
    ]

    findings: list[Finding] = []
    sources: list[dict[str, Any]] = []
    for name, path, reader in plan:
        if path is None:
            sources.append({"source": name, "status": "skipped", "count": 0, "path": None})
            continue
        if not Path(path).exists():
            sources.append({"source": name, "status": "absent", "count": 0, "path": str(path)})
            continue
        try:
            got = reader(Path(path), project_id)
        except Exception as exc:  # noqa: BLE001 — one bad source must not hide the rest
            sources.append(
                {
                    "source": name,
                    "status": "failed",
                    "count": 0,
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue
        findings.extend(got)
        sources.append({"source": name, "status": "ok", "count": len(got), "path": str(path)})

    findings.sort(key=lambda f: f.sort_key())
    return findings, sources


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    """Counts by severity, plus totals — the header numbers."""
    out: dict[str, int] = {}
    total = blocking = 0
    for f in findings:
        out[f.severity] = out.get(f.severity, 0) + 1
        total += 1
        if f.blocking:
            blocking += 1
    out["total"] = total
    out["blocking"] = blocking
    return out
