"""Changelog and README quality checking for on-changelog-nudge hook."""

from __future__ import annotations

import subprocess
from pathlib import Path

SOURCE_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".sh", ".gd", ".cs"}
SKIP_DIRS = {
    "tests",
    "test",
    "docs",
    "templates",
    "scripts",
    ".github",
    "__pycache__",
    "node_modules",
}

README_REQUIRED = [
    ("badge", ["![CI]", "![Version]", "shields.io", "img.shields"]),
    ("quick start", ["## Quick Start", "## Quickstart", "## Getting Started"]),
    ("usage", ["## Usage", "## Commands", "## Skills"]),
    ("structure", ["## Project Structure", "```\n", "├──", "└──"]),
    ("contributing", ["## Contributing", "## Development"]),
]


def run_git(args: list[str], cwd: Path) -> str:
    """Run git command and return stdout, or empty string on error."""
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def find_project_root(start: Path) -> Path:
    """Walk up to the nearest .git or pyproject.toml."""
    p = start.resolve()
    for _ in range(8):
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start


def get_git_status(root: Path) -> list[str]:
    """Get git status --porcelain as list of lines."""
    status = run_git(["status", "--porcelain"], root)
    return status.splitlines() if status else []


def analyze_changes(status_lines: list[str]) -> dict[str, bool]:
    """Analyze git status lines for source, changelog, and README changes.

    Returns:
        dict with keys: source_changed, changelog_changed, readme_changed
    """
    source_changed = False
    changelog_changed = False
    readme_changed = False

    for line in status_lines:
        if len(line) < 4:
            continue
        fname = line[3:].strip()
        p = Path(fname)

        if p.name.upper() in ("CHANGELOG.MD", "CHANGELOG"):
            changelog_changed = True
            continue

        if "README" in p.name.upper() and p.name.upper().endswith(("README.MD", "README")):
            readme_changed = True

        if set(p.parts) & SKIP_DIRS:
            continue

        if p.suffix.lower() in SOURCE_EXTS:
            source_changed = True

    return {
        "source_changed": source_changed,
        "changelog_changed": changelog_changed,
        "readme_changed": readme_changed,
    }


def print_changelog_nudge() -> None:
    """Print advisory to update CHANGELOG.md."""
    print(
        "\n[dream-studio] Source files changed — CHANGELOG.md not updated. Consider adding an entry.\n",
        flush=True,
    )


def check_and_nudge_readme_quality(root: Path) -> None:
    """Check README.md quality and print nudge if sections are missing."""
    readme = root / "README.md"
    if not readme.exists():
        return
    try:
        content = readme.read_text(encoding="utf-8")
    except Exception:
        return
    missing = []
    for section_name, indicators in README_REQUIRED:
        if not any(ind in content for ind in indicators):
            missing.append(section_name)
    if missing:
        print(
            f"\n[dream-studio] README updated but missing sections: {', '.join(missing)}. "
            f"Run /harden to scaffold them.\n",
            flush=True,
        )
