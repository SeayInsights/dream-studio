"""Structure checking library for on-structure-check hook.

Checks if source files are placed outside standard directories and emits
advisory nudges when violations are found.
"""

from __future__ import annotations

import json
from pathlib import Path

SOURCE_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx"}

# Files allowed at root level
ROOT_ALLOWLIST = {
    "setup.py",
    "conftest.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "app.py",
    "main.py",
    "index.js",
    "index.ts",
    "next.config.js",
    "next.config.ts",
    "vite.config.ts",
    "vite.config.js",
    "tailwind.config.js",
    "tailwind.config.ts",
}

# Top-level dirs that are non-standard names for source code
NONSTANDARD_DIRS = {"util", "utils", "helper", "helpers", "common", "shared", "misc"}


def find_project_root(file_path: str) -> Path:
    """Find project root by looking for .git or pyproject.toml."""
    p = Path(file_path).resolve().parent
    for _ in range(10):
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path(file_path).resolve().parent


def extract_file_path(payload: dict) -> str:
    """Extract file path from tool payload."""
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            return ""
    return tool_input.get("file_path", "")


def is_source_file(file_path: str) -> bool:
    """Check if file is a source file we care about."""
    return Path(file_path).suffix.lower() in SOURCE_EXTS


def check_structure_violation(file_path: str) -> str | None:
    """Check if file violates structure conventions. Returns violation message or None."""
    p = Path(file_path)
    root = find_project_root(file_path)

    try:
        rel = p.resolve().relative_to(root)
    except ValueError:
        return None

    parts = rel.parts
    if len(parts) == 0:
        return None

    if len(parts) == 1:
        # File directly at project root
        if p.name not in ROOT_ALLOWLIST:
            return (
                f"{p.name} is at the project root — consider placing source files in src/ or lib/."
            )
    elif len(parts) >= 2:
        top = parts[0].lower()
        if top in NONSTANDARD_DIRS:
            return f"{parts[0]}/ is a non-standard directory name — consider src/ or lib/ instead."

    return None


def emit_nudge_once(violation: str, file_path: str, state_dir: Path) -> None:
    """Print violation nudge once per file using sentinel files."""
    root = find_project_root(file_path)
    p = Path(file_path)

    slug = str(root).replace("\\", "-").replace("/", "-").replace(":", "-")[:80]
    key = f"structure-{slug}-{p.name}"
    sentinel = state_dir / f"{key}.json"

    if sentinel.exists():
        return

    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("{}", encoding="utf-8")
    except Exception:
        return

    print(
        f"\n[dream-studio] Structure: {violation} Run /structure-audit for a full report.\n",
        flush=True,
    )
