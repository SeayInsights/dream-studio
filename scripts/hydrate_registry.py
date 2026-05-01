"""Hydrate SQLite registry tables from the dream-studio file structure.

Usage:
    py scripts/hydrate_registry.py [--verbose] [--dry-run]

Scans skills/*/modes/*/SKILL.md, skills/workflow/SKILL.md, sibling gotchas.yml
files, and workflows/*.yaml — then populates the reg_* tables in studio.db.
Always does a full clear-and-replace (not incremental).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# ── Path bootstrap ───────────────────────────────────────────────────────────
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "hooks"))

from lib.studio_db import (  # noqa: E402
    clear_registry,
    upsert_gotcha,
    upsert_skill,
    upsert_skill_dep,
    upsert_workflow,
)

# ── YAML helpers (no third-party dependency) ─────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ---...--- YAML frontmatter from body. Return (fm_dict, body)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    return _parse_simple_yaml(fm_block), body


def _parse_simple_yaml(block: str) -> dict[str, Any]:
    """
    Parse a restricted subset of YAML sufficient for config.yml metadata:
      - scalar key: value  (strings, unquoted or quoted)
      - block sequences:
            key:
              - item
      - nested mapping under chain_suggests / triggers handled via _parse_chain
    """
    result: dict[str, Any] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip blank and comment lines
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        # Top-level key: value
        m = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if not m:
            i += 1
            continue

        key, val = m.group(1), m.group(2).strip()

        if val == "" or val == "|" or val == ">":
            # Block value — collect indented lines
            indent_val: list[str] = []
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if next_line.strip() == "" or next_line.startswith(" ") or next_line.startswith("\t"):
                    indent_val.append(next_line.strip())
                    i += 1
                else:
                    break
            # Detect list vs nested block
            if indent_val and indent_val[0].startswith("- "):
                result[key] = _parse_block_list(indent_val)
            else:
                result[key] = " ".join(s for s in indent_val if s)
        else:
            # Inline scalar
            result[key] = _strip_quotes(val)
            i += 1

    return result


def _parse_block_list(items: list[str]) -> list[Any]:
    """Convert a list of '- ...' strings into Python objects (dicts or strings)."""
    result = []
    current: dict[str, str] | None = None

    for raw in items:
        if not raw:
            continue
        if raw.startswith("- "):
            if current is not None:
                result.append(current)
            tail = raw[2:].strip()
            if ":" in tail:
                k, v = tail.split(":", 1)
                current = {k.strip(): _strip_quotes(v.strip())}
            else:
                result.append(_strip_quotes(tail))
                current = None
        elif raw.startswith("  ") or re.match(r"^\w+:", raw):
            # Continuation of current mapping item
            if current is None:
                current = {}
            m2 = re.match(r"^\s*(\w[\w_-]*):\s*(.*)", raw)
            if m2:
                current[m2.group(1)] = _strip_quotes(m2.group(2).strip())

    if current is not None:
        result.append(current)

    return result


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


# ── gotchas.yml parser ───────────────────────────────────────────────────────

_ENTRY_SECTIONS = {"avoid", "best_practices", "edge_cases", "limitations", "deprecated"}

# Default severity per section
_SECTION_SEVERITY: dict[str, str] = {
    "avoid": "high",
    "best_practices": "low",
    "edge_cases": "medium",
    "limitations": "low",
    "deprecated": "low",
}


def _parse_gotchas_yml(path: Path) -> list[dict[str, str]]:
    """
    Parse a gotchas.yml file into a list of entry dicts.
    Handles the structure used across dream-studio (line-by-line, no PyYAML).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[dict[str, str]] = []

    current_section = "avoid"
    current: dict[str, str] | None = None
    in_multiline: str | None = None  # key being collected as block scalar
    multiline_buf: list[str] = []

    def _flush_entry() -> None:
        nonlocal current
        if current and current.get("id") and current.get("title"):
            if "severity" not in current:
                current["severity"] = _SECTION_SEVERITY.get(current_section, "medium")
            entries.append(current)
        current = None

    def _flush_multiline() -> None:
        nonlocal in_multiline, multiline_buf
        if in_multiline and current is not None:
            current[in_multiline] = " ".join(l.strip() for l in multiline_buf if l.strip())
        in_multiline = None
        multiline_buf = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # Section header (top-level key like "avoid:", "best_practices:", etc.)
        section_m = re.match(r"^(\w+):\s*(\[\])?$", line)
        if section_m and section_m.group(1) in _ENTRY_SECTIONS:
            _flush_multiline()
            _flush_entry()
            current_section = section_m.group(1)
            continue

        # Skip version / comments / blank
        if not line.strip() or line.strip().startswith("#") or re.match(r"^version:", line):
            if in_multiline is not None:
                _flush_multiline()
            continue

        # Detect indentation level
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Continuation of a block scalar (context/fix text)
        if in_multiline is not None:
            if indent >= 6 or stripped.startswith('"') or not re.match(r"^\w[\w_-]*:", stripped):
                multiline_buf.append(stripped)
                continue
            else:
                _flush_multiline()

        # New list item entry: "  - id: ..."
        new_entry_m = re.match(r"^\s*-\s+id:\s*(.+)", line)
        if new_entry_m:
            _flush_entry()
            current = {"id": _strip_quotes(new_entry_m.group(1).strip())}
            continue

        # List continuation "  - ..." that's NOT an id (probably a bare list item)
        bare_list_m = re.match(r"^\s+-\s+(.+)", line)
        if bare_list_m and current is None:
            # Bare list entry without id — skip (e.g. deprecated: [])
            continue

        # Key: value inside an entry (indent >= 2)
        if current is not None and indent >= 2:
            kv_m = re.match(r"^\s+(\w[\w_-]*):\s*(.*)", line)
            if kv_m:
                k = kv_m.group(1)
                v = kv_m.group(2).strip()
                if v == "" or v.startswith("|") or v.startswith(">"):
                    # Block scalar — start collecting
                    in_multiline = k
                    multiline_buf = []
                else:
                    current[k] = _strip_quotes(v)
                continue

    _flush_multiline()
    _flush_entry()

    return entries


# ── Trigger extraction ────────────────────────────────────────────────────────

def _extract_triggers_from_body(body: str) -> list[str]:
    """
    Find a '## Trigger' section and extract trigger phrases from it.
    Handles both backtick-wrapped and plain comma-separated triggers.
    """
    trigger_section = re.search(
        r"##\s+Trigger\s*\n(.*?)(?=\n##|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if not trigger_section:
        return []

    section_text = trigger_section.group(1)
    # Extract backtick-wrapped tokens first
    backtick = re.findall(r"`([^`]+)`", section_text)
    if backtick:
        return [t.strip() for t in backtick if t.strip()]

    # Fall back to comma-split of plain text
    plain = section_text.strip().replace("\n", " ")
    return [t.strip() for t in plain.split(",") if t.strip()]


def _extract_triggers_from_fm(fm: dict[str, Any]) -> list[str]:
    """
    Pull triggers from frontmatter 'triggers:' key.
    Value may be a string or a list of dicts/strings.
    """
    raw = fm.get("triggers")
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                out.append(str(list(item.values())[0]))
            else:
                out.append(str(item))
        return [t.strip() for t in out if t.strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


# ── Keyword extraction ────────────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "and", "for", "this", "that", "with", "from", "when", "will",
    "have", "been", "are", "not", "but", "can", "has", "its", "use",
    "any", "all", "more", "then", "than", "each", "also", "does", "into",
    "only", "same", "must", "before", "after",
}


def _extract_keywords(text: str) -> list[str]:
    """Extract lowercase words > 3 chars, deduplicated, no stop-words."""
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    seen: dict[str, None] = {}
    for w in words:
        if w not in _STOP_WORDS:
            seen[w] = None
    return list(seen.keys())[:40]  # cap at 40 to keep the column sane


# ── Workflow YAML parser ──────────────────────────────────────────────────────

def _parse_workflow_yaml(path: Path) -> dict[str, Any]:
    """
    Extract name, description, node_count, and skills_used from a workflow YAML.
    Line-by-line — no PyYAML dependency.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = {
        "name": path.stem,
        "description": "",
        "node_count": 0,
        "skills_used": [],
    }

    in_desc = False
    desc_lines: list[str] = []
    node_ids: list[str] = []
    skill_refs: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        # Top-level name
        name_m = re.match(r"^name:\s*(.+)", line)
        if name_m:
            result["name"] = _strip_quotes(name_m.group(1).strip())
            continue

        # Top-level description (may be block scalar with >)
        desc_m = re.match(r"^description:\s*(.*)", line)
        if desc_m:
            val = desc_m.group(1).strip()
            if val in (">", "|", ""):
                in_desc = True
                desc_lines = []
            else:
                result["description"] = _strip_quotes(val)
            continue

        if in_desc:
            if stripped and (line.startswith("  ") or line.startswith("\t")):
                desc_lines.append(stripped)
                continue
            else:
                result["description"] = " ".join(desc_lines)
                in_desc = False

        # Count node ids
        node_id_m = re.match(r"^\s+-\s+id:\s*(.+)", line)
        if node_id_m:
            node_ids.append(node_id_m.group(1).strip())
            continue

        # skill: references inside nodes
        skill_m = re.match(r"^\s+skill:\s*(.+)", line)
        if skill_m:
            skill_refs.append(_strip_quotes(skill_m.group(1).strip()))
            continue

    if in_desc:
        result["description"] = " ".join(desc_lines)

    result["node_count"] = len(node_ids)
    result["skills_used"] = list(dict.fromkeys(skill_refs))  # deduplicated, order-preserving

    return result


def _categorize_workflow(name: str) -> str:
    lower = name.lower()
    if any(k in lower for k in ("daily", "standup", "close", "morning", "eod")):
        return "daily"
    if any(k in lower for k in ("audit", "security", "review", "scan", "self-audit")):
        return "audit"
    return "feature"


# ── Chain dep extractor ───────────────────────────────────────────────────────

def _extract_chain_suggests(fm: dict[str, Any]) -> list[str]:
    """Return list of next-skill names from chain_suggests frontmatter."""
    raw = fm.get("chain_suggests", [])
    if not isinstance(raw, list):
        return []

    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        nxt = item.get("next", "").strip()
        if nxt:
            results.append(nxt)

    return results


# ── Main scanner ─────────────────────────────────────────────────────────────

def _count_words(text: str) -> int:
    return len(text.split())


def _find_skill_mds(skills_dir: Path) -> list[Path]:
    """
    Return all mode-level SKILL.md paths and the special workflow/SKILL.md.
    Skip pack-level SKILL.md (direct child of skills/<pack>/).
    """
    found: list[Path] = []

    for pack_dir in sorted(skills_dir.iterdir()):
        if not pack_dir.is_dir():
            continue

        modes_dir = pack_dir / "modes"
        if modes_dir.is_dir():
            # Normal pack with modes/ directory
            for mode_dir in sorted(modes_dir.iterdir()):
                skill_md = mode_dir / "SKILL.md"
                if skill_md.is_file():
                    found.append(skill_md)
        else:
            # Special case: pack with no modes/ (e.g. workflow/, setup/)
            skill_md = pack_dir / "SKILL.md"
            if skill_md.is_file():
                found.append(skill_md)

    return found


# ── Hydration ─────────────────────────────────────────────────────────────────

def hydrate(
    *,
    verbose: bool = False,
    dry_run: bool = False,
    db_path: Path | None = None,
) -> dict[str, int]:
    skills_dir = root / "skills"
    workflows_dir = root / "workflows"

    skill_count = 0
    gotcha_count = 0
    workflow_count = 0
    dep_count = 0

    # Collect (skill_id, chain_nexts, pack) for dep resolution after all skills known
    dep_pending: list[tuple[str, list[str], str]] = []

    if not dry_run:
        ok = clear_registry(db_path)
        if not ok:
            print("[WARN] clear_registry() failed — proceeding anyway")

    # ── Skills & gotchas ─────────────────────────────────────────────────────
    for skill_md in _find_skill_mds(skills_dir):
        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[WARN] Cannot read {skill_md}: {exc}")
            continue

        fm, body = _parse_frontmatter(text)

        # Determine pack and mode from path
        # Possible layouts:
        #   skills/<pack>/modes/<mode>/SKILL.md  → pack=<pack>, mode=<mode>
        #   skills/<pack>/SKILL.md               → pack=<pack>, mode=<pack>
        parts = skill_md.relative_to(skills_dir).parts
        if len(parts) == 4 and parts[1] == "modes":
            # skills/<pack>/modes/<mode>/SKILL.md
            pack_name = parts[0]
            mode_name = parts[2]
        elif len(parts) == 2:
            # skills/<pack>/SKILL.md
            pack_name = parts[0]
            mode_name = fm.get("name") or parts[0]
        else:
            print(f"[WARN] Unexpected path layout: {skill_md} — skipping")
            continue

        skill_id = f"{pack_name}:{mode_name}"

        # Frontmatter overrides for pack (some files say pack: core for quality modes — trust path)
        # We trust the directory structure over the frontmatter pack field.
        description = str(fm.get("description", "")).strip()

        # Triggers: combine frontmatter triggers + body ## Trigger section
        fm_triggers = _extract_triggers_from_fm(fm)
        body_triggers = _extract_triggers_from_body(body)
        all_triggers = list(dict.fromkeys(fm_triggers + body_triggers))
        triggers_str = ", ".join(all_triggers)

        # Gotchas sibling
        gotchas_path_obj = skill_md.parent / "gotchas.yml"
        gotchas_path_str: str | None = str(gotchas_path_obj) if gotchas_path_obj.is_file() else None

        word_count = _count_words(body)

        # chain_suggests → dep list
        chain_nexts = _extract_chain_suggests(fm)
        chains_to_str: str | None = (", ".join(chain_nexts)) if chain_nexts else None

        skill_path_str = str(skill_md)

        if verbose:
            print(
                f"  skill  {skill_id:<28} words={word_count:>4}  "
                f"triggers={len(all_triggers)}  deps={len(chain_nexts)}"
            )

        if not dry_run:
            ok = upsert_skill(
                skill_id,
                pack_name,
                mode_name,
                skill_path_str,
                description=description,
                triggers=triggers_str,
                gotchas_path=gotchas_path_str,
                word_count=word_count,
                chains_to=chains_to_str,
                db_path=db_path,
            )
            if not ok:
                print(f"[WARN] upsert_skill failed for {skill_id}")
            else:
                skill_count += 1
        else:
            skill_count += 1

        if chain_nexts:
            dep_pending.append((skill_id, chain_nexts, pack_name))

        # ── Gotchas ──────────────────────────────────────────────────────────
        if gotchas_path_str:
            try:
                gotcha_entries = _parse_gotchas_yml(gotchas_path_obj)
            except Exception as exc:
                print(f"[WARN] Cannot parse {gotchas_path_obj}: {exc}")
                gotcha_entries = []

            for entry in gotcha_entries:
                gotcha_id = entry.get("id", "")
                if not gotcha_id:
                    continue

                title = entry.get("title", "")
                severity = entry.get("severity", "medium")
                context_text = entry.get("context", "")
                fix_text = entry.get("fix", "")
                discovered = entry.get("discovered")

                keywords = _extract_keywords(f"{title} {context_text}")
                keywords_str = ", ".join(keywords)

                if verbose:
                    print(f"    gotcha {gotcha_id:<36} severity={severity}")

                if not dry_run:
                    ok = upsert_gotcha(
                        gotcha_id,
                        skill_id,
                        severity,
                        title,
                        context=context_text,
                        fix=fix_text,
                        keywords=keywords_str,
                        discovered=discovered,
                        db_path=db_path,
                    )
                    if not ok:
                        print(f"[WARN] upsert_gotcha failed for {gotcha_id} / {skill_id}")
                    else:
                        gotcha_count += 1
                else:
                    gotcha_count += 1

    # ── Workflows ─────────────────────────────────────────────────────────────
    for yaml_file in sorted(workflows_dir.glob("*.yaml")):
        try:
            wf = _parse_workflow_yaml(yaml_file)
        except Exception as exc:
            print(f"[WARN] Cannot parse {yaml_file}: {exc}")
            continue

        workflow_id = yaml_file.stem
        category = _categorize_workflow(wf["name"])
        skills_used_str = ", ".join(wf["skills_used"])

        if verbose:
            print(
                f"  workflow {workflow_id:<30} nodes={wf['node_count']:>3}  "
                f"category={category}  skills={len(wf['skills_used'])}"
            )

        if not dry_run:
            ok = upsert_workflow(
                workflow_id,
                str(yaml_file),
                description=wf["description"],
                node_count=wf["node_count"],
                skills_used=skills_used_str,
                category=category,
                db_path=db_path,
            )
            if not ok:
                print(f"[WARN] upsert_workflow failed for {workflow_id}")
            else:
                workflow_count += 1
        else:
            workflow_count += 1

    # ── Skill dependencies ────────────────────────────────────────────────────
    for from_skill, nexts, pack_name in dep_pending:
        for nxt in nexts:
            # Resolve to_skill: if nxt contains ':', it's already fully qualified
            if ":" in nxt:
                to_skill = nxt
            else:
                # Try same pack first, then fall back to any registered skill with that mode
                to_skill = f"{pack_name}:{nxt}"

            if verbose:
                print(f"  dep    {from_skill} -> {to_skill}  [chains_to]")

            if not dry_run:
                ok = upsert_skill_dep(from_skill, to_skill, "chains_to", db_path)
                if not ok:
                    print(f"[WARN] upsert_skill_dep failed: {from_skill} -> {to_skill}")
                else:
                    dep_count += 1
            else:
                dep_count += 1

    return {
        "skills": skill_count,
        "gotchas": gotcha_count,
        "workflows": workflow_count,
        "deps": dep_count,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Hydrate dream-studio SQLite registry from SKILL.md / gotchas.yml / workflow YAML files."
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Print each item as it's processed")
    ap.add_argument("--dry-run", action="store_true", help="Parse only — do not write to DB")
    args = ap.parse_args()

    label = "[DRY RUN] " if args.dry_run else ""
    print(f"{label}Hydrating registry from {root}/skills + {root}/workflows …")

    counts = hydrate(verbose=args.verbose, dry_run=args.dry_run)

    print(
        f"{label}Hydrated: {counts['skills']} skills, "
        f"{counts['gotchas']} gotchas, "
        f"{counts['workflows']} workflows, "
        f"{counts['deps']} deps"
    )


if __name__ == "__main__":
    main()
