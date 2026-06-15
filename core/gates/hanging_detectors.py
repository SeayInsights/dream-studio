"""Nothing-left-hanging detectors (WO-BLAST-RADIUS-GATE T2).

When a fix's blast radius is bigger than the fix itself, the change set leaves
something dangling that the pr-smoke subset doesn't run — and main goes red
post-merge. These detectors scan a unified git diff for the three classes that
broke main 11 times this milestone:

  (a) detect_stale_removed_symbol_tests — a test still asserts a symbol/string
      that the diff REMOVED and did not re-add (e.g. #347: dashboard HTML ids /
      JS functions deleted, but tests/unit/test_frontend_dashboard_telemetry_surface.py
      still asserted them).

  (b) detect_changed_signature_callers — a function/method SIGNATURE changed in
      the diff, and a file outside the change set still references it (e.g. #353:
      _write_handoff_packet_to_db gained a parameter; the handoff authority test
      still asserted the old call shape).

  (c) detect_unowned_table_writes — the diff adds an INSERT/UPDATE to a table
      that another, unchanged module also writes — an ownership/authority-boundary
      conflict (e.g. #354: TokenConsumptionProjection claimed token_usage_records
      while execution_spine.py still wrote it).

  (d) detect_migration_file_db_duplication — a numbered migration adds a table/
      column while leaving a duplicate definition behind (file+DB drift).

Each detector returns a list of finding dicts:
    {"detector": str, "severity": "block", "path": str, "symbol": str, "message": str}

Detectors are conservative-by-over-inclusion: a signature change can break ANY
reference, so a flagged finding means "review this before merge", not "proven
broken". The merge gate (blast_radius.main) treats findings as blocking.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

Finding = dict[str, Any]

# --- diff parsing -----------------------------------------------------------


def _parse_diff(diff_text: str) -> list[dict[str, Any]]:
    """Parse a unified git diff into per-file {path, added[], removed[]} records."""
    files: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if cur is not None:
                files.append(cur)
            cur = {"path": None, "added": [], "removed": []}
            # Fallback path from the "diff --git a/x b/x" header.
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                cur["path"] = parts[1].strip()
        elif line.startswith("+++ b/"):
            if cur is not None:
                cur["path"] = line[len("+++ b/") :].strip()
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            if cur is not None:
                cur["added"].append(line[1:])
        elif line.startswith("-"):
            if cur is not None:
                cur["removed"].append(line[1:])
    if cur is not None:
        files.append(cur)
    return [f for f in files if f.get("path")]


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _is_test_path(path: str) -> bool:
    p = _normalize(path)
    return p.startswith("tests/") and p.endswith(".py") and Path(p).name.startswith("test_")


_CODE_SUFFIXES = (".py", ".html", ".js", ".ts", ".sql", ".yaml", ".yml")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".dream-studio", "graphify-out"}


def _iter_code_files(repo_root: Path) -> Iterable[tuple[str, str]]:
    """Yield (relative_path, text) for code files under repo_root."""
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in _CODE_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        yield _normalize(str(path.relative_to(repo_root))), text


# --- (a) stale removed-symbol tests -----------------------------------------

_ATTR_RE = re.compile(r'\b(?:id|class|name|data-[\w-]+)\s*=\s*["\']([\w\-]{3,})["\']')
_DEF_RE = re.compile(r"\b(?:def|class|function|const|let|var)\s+([A-Za-z_]\w{2,})")
_QUOTED_RE = re.compile(r"""["']([A-Za-z_][\w\-]{3,})["']""")


def _symbols(lines: Iterable[str]) -> set[str]:
    syms: set[str] = set()
    for ln in lines:
        for rx in (_ATTR_RE, _DEF_RE, _QUOTED_RE):
            syms.update(m.group(1) for m in rx.finditer(ln))
    return syms


def detect_stale_removed_symbol_tests(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    root = Path(repo_root)
    files = _parse_diff(diff_text)
    changed_paths = {_normalize(f["path"]) for f in files}
    removed: set[str] = set()
    added: set[str] = set()
    for f in files:
        removed |= _symbols(f["removed"])
        added |= _symbols(f["added"])
    truly_removed = {s for s in removed if s not in added}
    if not truly_removed:
        return []

    patterns = {s: re.compile(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])") for s in truly_removed}
    findings: list[Finding] = []
    for rel, text in _iter_code_files(root):
        if not _is_test_path(rel) or rel in changed_paths:
            continue
        for sym, pat in patterns.items():
            if pat.search(text):
                findings.append(
                    {
                        "detector": "stale_removed_symbol_test",
                        "severity": "block",
                        "path": rel,
                        "symbol": sym,
                        "message": (
                            f"{rel} still references {sym!r}, which the diff removed and did "
                            f"not re-add. Update or delete the stale test."
                        ),
                    }
                )
    return findings


# --- (b) changed-signature callers ------------------------------------------

_SIG_RE = re.compile(r"\b(?:def|function)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)")


def _param_names(param_str: str) -> tuple[str, ...]:
    names: list[str] = []
    for raw in param_str.split(","):
        tok = raw.strip()
        if not tok or tok in ("self", "cls", "*", "/"):
            continue
        tok = tok.lstrip("*")
        tok = tok.split(":", 1)[0].split("=", 1)[0].strip()
        if tok:
            names.append(tok)
    return tuple(names)


def detect_changed_signature_callers(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    root = Path(repo_root)
    files = _parse_diff(diff_text)
    changed_paths = {_normalize(f["path"]) for f in files}

    changed_sigs: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for f in files:
        old: dict[str, str] = {}
        new: dict[str, str] = {}
        for ln in f["removed"]:
            m = _SIG_RE.search(ln)
            if m:
                old[m.group(1)] = m.group(2)
        for ln in f["added"]:
            m = _SIG_RE.search(ln)
            if m:
                new[m.group(1)] = m.group(2)
        for name in set(old) & set(new):
            if _param_names(old[name]) != _param_names(new[name]):
                changed_sigs[name] = (_param_names(old[name]), _param_names(new[name]))
    if not changed_sigs:
        return []

    ref_res = {name: re.compile(r"(?<![\w.])" + re.escape(name) + r"\b") for name in changed_sigs}
    findings: list[Finding] = []
    for rel, text in _iter_code_files(root):
        if rel in changed_paths:
            continue
        for name, pat in ref_res.items():
            if pat.search(text):
                old_p, new_p = changed_sigs[name]
                findings.append(
                    {
                        "detector": "changed_signature_caller",
                        "severity": "block",
                        "path": rel,
                        "symbol": name,
                        "message": (
                            f"{rel} references {name}(), whose signature changed in this diff "
                            f"({list(old_p)} -> {list(new_p)}) but this file was not updated."
                        ),
                    }
                )
    return findings


# --- (c) unowned / duplicate table writes -----------------------------------

_WRITE_RE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE)\s+([A-Za-z_]\w*)", re.IGNORECASE)


def _table_writers(table: str, repo_root: Path, *, exclude: str) -> list[str]:
    writers: list[str] = []
    table_l = table.lower()
    for rel, text in _iter_code_files(repo_root):
        if rel == exclude or _is_test_path(rel):
            continue
        for m in _WRITE_RE.finditer(text):
            if m.group(1).lower() == table_l:
                writers.append(rel)
                break
    return writers


def detect_unowned_table_writes(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    root = Path(repo_root)
    files = _parse_diff(diff_text)
    findings: list[Finding] = []
    for f in files:
        path = _normalize(f["path"])
        if _is_test_path(path):
            continue
        added_targets = {m.group(1).lower() for ln in f["added"] for m in _WRITE_RE.finditer(ln)}
        removed_targets = {
            m.group(1).lower() for ln in f["removed"] for m in _WRITE_RE.finditer(ln)
        }
        for table in sorted(added_targets - removed_targets):
            other = _table_writers(table, root, exclude=path)
            if other:
                findings.append(
                    {
                        "detector": "unowned_table_write",
                        "severity": "block",
                        "path": path,
                        "symbol": table,
                        "message": (
                            f"{path} adds a write to {table!r}, which is ALSO written by "
                            f"{', '.join(other)}. Resolve table ownership (a derived/projection "
                            f"table must have a single writer) before merge."
                        ),
                    }
                )
    return findings


# --- (d) migration file+DB duplication --------------------------------------

_CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)", re.IGNORECASE)


def detect_migration_file_db_duplication(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    """A migration CREATE TABLE for a table an unchanged migration already creates."""
    root = Path(repo_root)
    files = _parse_diff(diff_text)
    findings: list[Finding] = []
    migrations_dir = root / "core" / "event_store" / "migrations"
    for f in files:
        path = _normalize(f["path"])
        if "migrations/" not in path or not path.endswith(".sql"):
            continue
        created = {m.group(1).lower() for ln in f["added"] for m in _CREATE_RE.finditer(ln)}
        for table in sorted(created):
            if not migrations_dir.is_dir():
                continue
            for mig in migrations_dir.glob("*.sql"):
                rel = _normalize(str(mig.relative_to(root)))
                if rel == path:
                    continue
                try:
                    sql = mig.read_text(encoding="utf-8")
                except OSError:
                    continue
                if any(m.group(1).lower() == table for m in _CREATE_RE.finditer(sql)):
                    findings.append(
                        {
                            "detector": "migration_file_db_duplication",
                            "severity": "block",
                            "path": path,
                            "symbol": table,
                            "message": (
                                f"{path} creates table {table!r}, which {rel} already creates. "
                                f"Duplicate DDL leaves file+DB drift."
                            ),
                        }
                    )
    return findings


def run_all_detectors(diff_text: str, *, repo_root: Path | str = REPO_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for detector in (
        detect_stale_removed_symbol_tests,
        detect_changed_signature_callers,
        detect_unowned_table_writes,
        detect_migration_file_db_duplication,
    ):
        findings.extend(detector(diff_text, repo_root=repo_root))
    return findings
