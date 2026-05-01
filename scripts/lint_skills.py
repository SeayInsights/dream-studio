"""lint_skills.py — Validate all SKILL.md files for structural correctness.

Usage:
    python scripts/lint_skills.py
    python scripts/lint_skills.py --path skills/core
    python scripts/lint_skills.py --verbose
"""

import argparse
import io
import re
import sys
from pathlib import Path

# Ensure stdout can handle Unicode (matters on Windows consoles)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# YAML frontmatter helpers (no external deps)
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict | None:
    """Return dict of frontmatter fields if delimited by ---, else None."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None
    raw = match.group(1)
    fields: dict = {}
    for line in raw.splitlines():
        # Simple key: value parse (handles quoted values, ignores nested YAML)
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            fields[key] = val
    return fields


# ---------------------------------------------------------------------------
# YAML gotchas.yml helpers
# ---------------------------------------------------------------------------

def parse_gotchas_yaml(text: str) -> dict:
    """
    Minimal YAML parser for gotchas.yml.

    Recognises:
      version: <value>
      avoid:
        - id: ...
          severity: ...
          title: ...
          context: ...
          fix: ...
    """
    result: dict = {"version": None, "avoid": []}

    # version field
    vm = re.search(r"^version:\s*(.+)", text, re.MULTILINE)
    if vm:
        result["version"] = vm.group(1).strip()

    # avoid block — split on list item markers
    avoid_block_match = re.search(
        r"^avoid:\s*\n((?:(?!^\w).*\n?)*)", text, re.MULTILINE
    )
    if avoid_block_match:
        avoid_text = avoid_block_match.group(1)
        # Split into individual entries on "  - " (2-space indent list items)
        entries_raw = re.split(r"^\s{0,4}-\s+", avoid_text, flags=re.MULTILINE)
        for entry in entries_raw:
            if not entry.strip():
                continue
            item: dict = {}
            for field in ("id", "severity", "title", "context", "fix"):
                fm = re.search(rf"^\s*{field}:\s*(.+)", entry, re.MULTILINE)
                if fm:
                    item[field] = fm.group(1).strip().strip('"').strip("'")
            if item:
                result["avoid"].append(item)

    return result


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

TRIGGER_PATTERNS = [r"^##\s+Trigger\b"]
STEPS_PATTERNS = [
    r"^##\s+Steps\b",
    r"^##\s+The Process\b",
    r"^##\s+Execution Protocol\b",
]
ANTIPATTERNS_PATTERNS = [r"^##\s+Anti-patterns\b"]


def has_section(text: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            return True
    return False


def section_word_counts(text: str) -> dict[str, int]:
    """Return {heading: word_count} for each ## heading block."""
    lines = text.splitlines()
    sections: dict[str, int] = {}
    current_heading: str | None = None
    current_words = 0

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            if current_heading is not None:
                sections[current_heading] = current_words
            current_heading = m.group(2).strip()
            current_words = 0
        else:
            current_words += len(line.split())

    if current_heading is not None:
        sections[current_heading] = current_words

    return sections


def word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Single-file validation
# ---------------------------------------------------------------------------

WORD_LIMIT = 800
REQUIRED_FM_FIELDS = ("name", "description", "pack")


def validate_skill_md(skill_path: Path, verbose: bool) -> tuple[bool, list[str], list[str]]:
    """
    Validate one SKILL.md.

    Returns (passed: bool, errors: list[str], warnings: list[str])
    """
    errors: list[str] = []
    warnings: list[str] = []

    text = skill_path.read_text(encoding="utf-8", errors="replace")
    total_words = word_count(text)

    # 1. Frontmatter
    fm = parse_frontmatter(text)
    if fm is None:
        errors.append("missing YAML frontmatter (--- delimiters not found)")
    else:
        for field in REQUIRED_FM_FIELDS:
            if field not in fm or not fm[field]:
                errors.append(f"frontmatter missing required field: {field!r}")

    # 2. Trigger section
    if not has_section(text, TRIGGER_PATTERNS):
        errors.append("missing '## Trigger' section")

    # 3. Steps section
    if not has_section(text, STEPS_PATTERNS):
        errors.append(
            "missing steps section (expected '## Steps', '## The Process', "
            "or '## Execution Protocol')"
        )

    # 4. Anti-patterns (warn only)
    if not has_section(text, ANTIPATTERNS_PATTERNS):
        warnings.append("missing '## Anti-patterns' section")

    # 5. Word count
    oversized_note = ""
    if total_words > WORD_LIMIT:
        sec_counts = section_word_counts(text)
        if sec_counts:
            largest_sec, largest_wc = max(sec_counts.items(), key=lambda kv: kv[1])
            oversized_note = f'OVERSIZED (largest: "{largest_sec}" {largest_wc} words)'
        else:
            oversized_note = "OVERSIZED (no sections detected)"
        errors.append(f"{total_words} words — {oversized_note}")

    # 6 & 7. gotchas.yml check
    skill_dir = skill_path.parent
    parent_dir = skill_dir.parent

    gotchas_path: Path | None = None
    for candidate in (skill_dir / "gotchas.yml", parent_dir / "gotchas.yml"):
        if candidate.exists():
            gotchas_path = candidate
            break

    if gotchas_path is None:
        warnings.append("no gotchas.yml found in skill dir or parent dir")
    else:
        gotchas_text = gotchas_path.read_text(encoding="utf-8", errors="replace")
        g = parse_gotchas_yaml(gotchas_text)

        # 7a. version field
        if not g["version"]:
            errors.append(f"gotchas.yml ({gotchas_path.name}) missing 'version' field")

        # 7b. avoid entries structure
        for i, entry in enumerate(g["avoid"]):
            entry_id = entry.get("id", f"entry[{i}]")
            for required_field in ("id", "severity", "title", "context"):
                if required_field not in entry:
                    errors.append(
                        f"gotchas.yml avoid[{entry_id}] missing required field: {required_field!r}"
                    )
            if "fix" not in entry:
                warnings.append(
                    f"gotchas.yml avoid[{entry_id}] missing 'fix' field"
                )

    passed = len(errors) == 0
    return passed, errors, warnings, total_words, oversized_note


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

PASS_ICON = "✓"   # ✓
FAIL_ICON = "✗"   # ✗
WARN_ICON = "⚠"   # ⚠


def format_result(
    skill_path: Path,
    root: Path,
    passed: bool,
    errors: list[str],
    warnings: list[str],
    total_words: int,
    oversized_note: str,
    verbose: bool,
) -> str:
    rel = skill_path.relative_to(root.parent) if root.parent in skill_path.parents else skill_path
    word_str = f"({total_words} words)"

    if not passed:
        icon = FAIL_ICON
        suffix_parts = []
        # Show first OVERSIZED error inline; the rest appear in verbose
        if oversized_note:
            suffix_parts.append(oversized_note)
        # Non-oversized errors
        non_size_errors = [e for e in errors if "words —" not in e]
        if non_size_errors:
            suffix_parts.append("; ".join(non_size_errors))
        suffix = f" — {'; '.join(suffix_parts)}" if suffix_parts else ""
        line = f"{icon} {rel} {word_str}{suffix}"
    elif warnings:
        icon = WARN_ICON
        line = f"{icon} {rel} {word_str} — {'; '.join(warnings)}"
    else:
        icon = PASS_ICON
        line = f"{icon} {rel} {word_str}"

    if verbose:
        details: list[str] = []
        for err in errors:
            details.append(f"    ERROR: {err}")
        for warn in warnings:
            details.append(f"    WARN:  {warn}")
        if details:
            line += "\n" + "\n".join(details)

    return line


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files for structural correctness.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Directory to scan (default: skills/ relative to repo root)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all checks per file",
    )
    args = parser.parse_args()

    # Resolve scan root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        scan_root = repo_root / "skills"

    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(2)

    skill_files = sorted(scan_root.rglob("SKILL.md"))
    if not skill_files:
        print(f"No SKILL.md files found under {scan_root}", file=sys.stderr)
        sys.exit(0)

    passed_count = 0
    failed_count = 0
    warn_count = 0

    for skill_path in skill_files:
        passed, errors, warnings, total_words, oversized_note = validate_skill_md(
            skill_path, args.verbose
        )
        line = format_result(
            skill_path,
            scan_root,
            passed,
            errors,
            warnings,
            total_words,
            oversized_note,
            args.verbose,
        )
        print(line)

        if not passed:
            failed_count += 1
        else:
            passed_count += 1
        if warnings:
            warn_count += 1

    print()
    print(f"{passed_count} passed, {failed_count} failed, {warn_count} warnings")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
