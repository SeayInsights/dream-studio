"""
context_compiler.py — Compile a minimal prompt for a specific skill mode.

CLI:
    py hooks/lib/context_compiler.py --skill=<mode> --pack=<pack> \
        [--repo-context=<path>] [--project-root=.]

Module API:
    from hooks.lib.context_compiler import compile_context
    text = compile_context(skill, pack, repo_context_path=None, project_root=".")

Output is deterministic for identical inputs (enables Claude prompt caching).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Import DocumentStore and deprecation warning - deferred to avoid import errors at module level
_DocumentStore = None
_deprecation = None

def _ensure_imports():
    """Lazy import DocumentStore and deprecation to handle both module and script contexts."""
    global _DocumentStore, _deprecation
    if _DocumentStore is not None:
        return

    try:
        from . import deprecation as _dep  # noqa: PLC0415
        from .document_store import DocumentStore as _DS  # noqa: PLC0415
        _DocumentStore = _DS
        _deprecation = _dep
    except ImportError:
        # When run as script, add hooks dir (parent of lib) to path
        import sys as _sys  # noqa: PLC0415
        _hooks_path = Path(__file__).parent.parent  # hooks dir
        if str(_hooks_path) not in _sys.path:
            _sys.path.insert(0, str(_hooks_path))
        from lib import deprecation as _dep  # type: ignore[import-not-found]  # noqa: PLC0415
        from lib.document_store import DocumentStore as _DS  # type: ignore[import-not-found]  # noqa: PLC0415
        _DocumentStore = _DS
        _deprecation = _dep

# ---------------------------------------------------------------------------
# Section classification
# ---------------------------------------------------------------------------

# Headers whose content we want to keep (case-insensitive substring match)
_KEEP_KEYWORDS = ("steps", "process", "output", "rules", "principles", "anti-patterns")

# Headers whose content we explicitly drop
_DROP_KEYWORDS = (
    "example usage",
    "examples",
    "template",
    "trigger",
    "used by",
    "integration",
    "mode dispatch",
    "shared resources",
)


def _header_label(header: str) -> str:
    """Return the header text stripped of leading '#' and whitespace."""
    return header.lstrip("#").strip()


def _should_keep(header: str) -> bool:
    label = _header_label(header).lower()
    for kw in _DROP_KEYWORDS:
        if kw in label:
            return False
    for kw in _KEEP_KEYWORDS:
        if kw in label:
            return True
    return False


# ---------------------------------------------------------------------------
# Markdown section splitter
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> list[tuple[str, str]]:
    """
    Split markdown text into (header_line, body) tuples.
    Sections start at '## ' (level-2) headers only.
    Content before the first '## ' is collected under header ''.
    """
    sections: list[tuple[str, str]] = []
    current_header = ""
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            sections.append((current_header, "".join(current_lines)))
            current_header = line.rstrip("\n")
            current_lines = []
        else:
            current_lines.append(line)

    sections.append((current_header, "".join(current_lines)))
    return sections


# ---------------------------------------------------------------------------
# SKILL.md extraction
# ---------------------------------------------------------------------------

def _extract_skill_sections(skill_text: str) -> dict[str, str]:
    """
    Return a mapping of canonical section name → body for kept sections.

    Canonical names:
      - "Rules"       ← headers matching Principles or Rules
      - "Process"     ← headers matching Steps or Process
      - "Output Format" ← headers matching Output
      - "Anti-patterns" ← headers matching Anti-patterns
    """
    canonical: dict[str, str] = {}

    for header, body in _split_sections(skill_text):
        if not header:
            continue
        if not _should_keep(header):
            continue

        label = _header_label(header).lower()

        if "anti-patterns" in label:
            key = "Anti-patterns"
        elif "output" in label:
            key = "Output Format"
        elif "process" in label or "steps" in label:
            key = "Process"
        elif "principles" in label or "rules" in label:
            key = "Rules"
        else:
            key = _header_label(header)  # fallback: keep original name

        # Merge if same canonical key appears more than once
        if key in canonical:
            canonical[key] = canonical[key].rstrip("\n") + "\n\n" + body.strip("\n")
        else:
            canonical[key] = body

    return canonical


# ---------------------------------------------------------------------------
# orchestration.md extraction
# ---------------------------------------------------------------------------

def _extract_orchestration_sections(orch_text: str) -> dict[str, str]:
    """
    Return:
      "Model Selection"    — the ## Model Selection section
      "Response Handling"  — the ## Handling agent responses section
    """
    result: dict[str, str] = {}

    for header, body in _split_sections(orch_text):
        if not header:
            continue
        label = _header_label(header).lower()
        if label == "model selection":
            result["Model Selection"] = body
        elif "handling agent responses" in label:
            result["Response Handling"] = body

    return result


# ---------------------------------------------------------------------------
# gotchas.yml parsing (stdlib only — no PyYAML)
# ---------------------------------------------------------------------------

def _parse_gotchas(gotchas_text: str) -> list[dict]:
    """
    Parse gotchas.yml with simple line-by-line logic.
    Returns a list of entry dicts with keys: id, severity, title, avoid (text).

    Structure assumed:
      avoid:
        - id: foo
          severity: high
          title: "..."
          ...other fields...
        - id: bar
          ...
    """
    entries: list[dict] = []
    current: dict | None = None
    in_avoid_block = False

    for raw_line in gotchas_text.splitlines():
        # Detect top-level 'avoid:' block
        if re.match(r"^avoid\s*:", raw_line):
            in_avoid_block = True
            continue

        # Any top-level key (no indentation) other than 'avoid:' ends the block
        if raw_line and raw_line[0].isalpha() and ":" in raw_line:
            if not raw_line.startswith(" ") and not raw_line.startswith("-"):
                in_avoid_block = False
                if current is not None:
                    entries.append(current)
                    current = None
                continue

        if not in_avoid_block:
            continue

        # New entry starts with '  - id:'
        m_id = re.match(r"^\s+-\s+id\s*:\s*(.+)$", raw_line)
        if m_id:
            if current is not None:
                entries.append(current)
            current = {"id": m_id.group(1).strip(), "severity": "", "title": "", "avoid": ""}
            continue

        if current is None:
            continue

        m_sev = re.match(r"^\s+severity\s*:\s*(.+)$", raw_line)
        if m_sev:
            current["severity"] = m_sev.group(1).strip().strip('"').strip("'")
            continue

        m_title = re.match(r"^\s+title\s*:\s*(.+)$", raw_line)
        if m_title:
            current["title"] = m_title.group(1).strip().strip('"').strip("'")
            continue

        # 'fix:' used as the primary "avoid" text (more actionable than 'context')
        m_fix = re.match(r"^\s+fix\s*:\s*(.+)$", raw_line)
        if m_fix:
            current["avoid"] = m_fix.group(1).strip().strip('"').strip("'")
            continue

    if current is not None and in_avoid_block:
        entries.append(current)

    return entries


_HIGH_SEVERITIES = {"critical", "high"}


def _filter_high_gotchas(entries: list[dict]) -> list[dict]:
    filtered = [e for e in entries if e.get("severity", "").lower() in _HIGH_SEVERITIES]
    # Sort deterministically: severity (critical first) then id
    severity_order = {"critical": 0, "high": 1}
    return sorted(
        filtered,
        key=lambda e: (severity_order.get(e["severity"].lower(), 99), e.get("id", ""))
    )


def _format_gotcha_entry(entry: dict) -> str:
    lines = [f"- **[{entry['severity'].upper()}]** {entry['title']}"]
    if entry.get("avoid"):
        lines.append(f"  Fix: {entry['avoid']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core compile function
# ---------------------------------------------------------------------------

def compile_context(
    skill: str,
    pack: str,
    repo_context_path: str | None = None,
    project_root: str = ".",
) -> str:
    """
    Compile a minimal, deterministic context prompt for the given skill/pack.

    Parameters
    ----------
    skill            : mode name, e.g. "build"
    pack             : pack name, e.g. "core"
    repo_context_path: optional path to a JSON repo-context file
    project_root     : root of the dream-studio project (default: current dir)

    Returns
    -------
    Compiled markdown string, ready to feed into a Claude prompt.
    """
    root = Path(project_root).resolve()
    skill_md_path = root / "skills" / pack / "modes" / skill / "SKILL.md"
    gotchas_path = root / "skills" / pack / "modes" / skill / "gotchas.yml"
    orch_path = root / "skills" / "core" / "orchestration.md"

    # ---- 1. Read SKILL.md -------------------------------------------------
    # Try SQLite first, fall back to file system with deprecation warning
    _ensure_imports()
    skill_text = None
    try:
        if _DocumentStore:
            skill_doc = _DocumentStore.get_skill(pack, skill)
            if skill_doc:
                skill_text = skill_doc["content"]
    except Exception:
        pass  # Fall back to file system

    if skill_text is None:
        # Fallback to file system (deprecated)
        if not skill_md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found: {skill_md_path}")
        if _deprecation:
            _deprecation.warn_file_read(
                skill_md_path,
                f"DocumentStore.get_skill('{pack}', '{skill}')"
            )
        skill_text = skill_md_path.read_text(encoding="utf-8")

    skill_sections = _extract_skill_sections(skill_text)

    # ---- 2. Read orchestration.md (optional) ------------------------------
    orch_sections: dict[str, str] = {}
    if orch_path.exists():
        orch_sections = _extract_orchestration_sections(
            orch_path.read_text(encoding="utf-8")
        )

    # ---- 3. Read gotchas.yml (optional) -----------------------------------
    # Load team gotchas first, then skill-specific gotchas
    gotcha_items: list[dict] = []

    # Team gotchas - read from SQLite first
    try:
        if _DocumentStore:
            team_gotcha_docs = _DocumentStore.get_team_gotchas()
            for doc in team_gotcha_docs:
                # Extract parsed gotchas from metadata
                metadata = doc.get("metadata", {})
                parsed = metadata.get("parsed", {})
                avoid_entries = parsed.get("avoid", [])
                if avoid_entries:
                    filtered_team = _filter_high_gotchas(avoid_entries)
                    gotcha_items.extend(filtered_team)
    except Exception:
        # Fallback to legacy team_context module
        try:
            # Import team_context - handle both module and script contexts
            try:
                from . import team_context  # noqa: PLC0415
            except ImportError:
                # When run as script, add hooks/lib to path and import
                import sys as _sys  # noqa: PLC0415
                _lib_path = Path(__file__).parent
                if str(_lib_path) not in _sys.path:
                    _sys.path.insert(0, str(_lib_path))
                import team_context  # type: ignore[import-not-found]  # noqa: PLC0415

            team_gotchas = team_context.load_team_gotchas()
            if team_gotchas:
                if _deprecation:
                    _deprecation.warn_file_read(
                        ".dream-studio/team/gotchas.yml",
                        "DocumentStore.get_team_gotchas()"
                    )
                filtered_team = _filter_high_gotchas(team_gotchas)
                gotcha_items.extend(filtered_team)
        except Exception:
            pass  # Team gotchas are optional, fail gracefully

    # Skill-specific gotchas - read from SQLite first
    skill_gotchas_loaded = False
    try:
        if _DocumentStore:
            skill_gotcha_docs = _DocumentStore.get_skill_gotchas(pack, skill)
            for doc in skill_gotcha_docs:
                # Extract parsed gotchas from metadata
                metadata = doc.get("metadata", {})
                parsed = metadata.get("parsed", {})
                avoid_entries = parsed.get("avoid", [])
                if avoid_entries:
                    gotcha_items.extend(_filter_high_gotchas(avoid_entries))
                    skill_gotchas_loaded = True
    except Exception:
        pass  # Try file fallback

    # Fallback to file system for skill gotchas ONLY if not found in SQLite
    if not skill_gotchas_loaded and gotchas_path.exists():
        if _deprecation:
            _deprecation.warn_file_read(
                gotchas_path,
                f"DocumentStore.get_skill_gotchas('{pack}', '{skill}')"
            )
        raw_gotchas = gotchas_path.read_text(encoding="utf-8")
        all_entries = _parse_gotchas(raw_gotchas)
        gotcha_items.extend(_filter_high_gotchas(all_entries))

    # ---- 4. Read repo-context JSON (optional) -----------------------------
    repo_context_block: str | None = None
    if repo_context_path is not None:
        rc_path = Path(repo_context_path).resolve()
        if rc_path.exists():
            raw_json = rc_path.read_text(encoding="utf-8")
            # Re-serialize with sorted keys for determinism
            repo_context_block = json.dumps(
                json.loads(raw_json), sort_keys=True, indent=2
            )

    # ---- 5. Assemble output -----------------------------------------------
    parts: list[str] = []
    parts.append(f"# {skill} — Compiled Context\n")

    # Project Context (only if provided)
    if repo_context_block is not None:
        parts.append("## Project Context\n")
        parts.append("```json\n" + repo_context_block + "\n```\n")

    # Ordered canonical sections from SKILL.md
    section_order = ["Rules", "Process", "Output Format", "Anti-patterns"]
    for sec_name in section_order:
        if sec_name in skill_sections:
            body = skill_sections[sec_name].strip()
            if body:
                parts.append(f"## {sec_name}\n")
                parts.append(body + "\n")

    # Any extra kept sections not in the standard order (sorted for determinism)
    extra_keys = sorted(k for k in skill_sections if k not in section_order)
    for sec_name in extra_keys:
        body = skill_sections[sec_name].strip()
        if body:
            parts.append(f"## {sec_name}\n")
            parts.append(body + "\n")

    # Model Selection from orchestration.md
    if "Model Selection" in orch_sections:
        body = orch_sections["Model Selection"].strip()
        if body:
            parts.append("## Model Selection\n")
            parts.append(body + "\n")

    # Response Handling from orchestration.md
    if "Response Handling" in orch_sections:
        body = orch_sections["Response Handling"].strip()
        if body:
            parts.append("## Response Handling\n")
            parts.append(body + "\n")

    # Gotchas (high+ severity only)
    if gotcha_items:
        parts.append("## Gotchas\n")
        parts.append(
            "\n".join(_format_gotcha_entry(e) for e in gotcha_items) + "\n"
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile a minimal, cached-friendly prompt for a dream-studio skill mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py hooks/lib/context_compiler.py --skill=build --pack=core
  py hooks/lib/context_compiler.py --skill=debug --pack=quality --project-root=.
  py hooks/lib/context_compiler.py --skill=think --pack=core --repo-context=.planning/repo_context.json
""",
    )
    parser.add_argument("--skill", required=True, help="Skill mode name (e.g. build, debug)")
    parser.add_argument("--pack", required=True, help="Pack name (e.g. core, quality)")
    parser.add_argument(
        "--repo-context",
        default=None,
        metavar="PATH",
        help="Path to a JSON repo-context file to inline as Project Context",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        metavar="DIR",
        help="Root of the dream-studio project (default: current directory)",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        result = compile_context(
            skill=args.skill,
            pack=args.pack,
            repo_context_path=args.repo_context,
            project_root=args.project_root,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Write as UTF-8 regardless of terminal encoding (SKILL.md may contain Unicode)
    sys.stdout.buffer.write(result.encode("utf-8"))


if __name__ == "__main__":
    main()
