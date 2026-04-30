"""Project snapshot generator for dream-studio hooks.

Scans a project directory and produces a JSON snapshot covering directory
tree, stack detection, entry points, dependency counts, file count, LOC,
and git hash (for cache invalidation).

CLI usage:
    py hooks/lib/repo_context.py [--project-root .] [--output path]

Module usage:
    from lib.repo_context import generate_snapshot
    snapshot = generate_snapshot(project_root=Path("."))
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "__pycache__", ".sessions", ".dream-studio"}
)

SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".py", ".rs", ".go",
        ".astro", ".svelte", ".vue",
        ".css", ".scss", ".sass",
        ".html", ".htm",
        ".json", ".yaml", ".yml", ".toml",
        ".sql", ".sh", ".bash",
    }
)

# Dependencies considered "heavy" (large bundles, frameworks, DBs)
HEAVY_PACKAGES: frozenset[str] = frozenset(
    {
        "@astrojs/cloudflare", "astro", "next", "nuxt", "remix", "gatsby",
        "react", "react-dom", "vue", "@vue/core",
        "svelte", "@sveltejs/kit",
        "webpack", "esbuild", "rollup", "vite",
        "drizzle-orm", "prisma", "@prisma/client",
        "typeorm", "sequelize",
        "express", "fastify", "hono", "koa",
        "tensorflow", "torch", "numpy", "pandas", "scipy",
        "three", "babylon",
        "tailwindcss",
    }
)


# ---------------------------------------------------------------------------
# Directory tree (2 levels deep)
# ---------------------------------------------------------------------------

def _build_tree(root: Path, max_depth: int = 2) -> str:
    """Return a text directory tree string, skipping ignored directories."""
    lines: list[str] = []

    def _walk(path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        dirs = [e for e in entries if e.is_dir() and e.name not in SKIP_DIRS]
        files = [e for e in entries if e.is_file()]

        for entry in dirs:
            lines.append(f"{prefix}{entry.name}/")
            if depth < max_depth:
                _walk(entry, depth + 1, prefix + "  ")

        for entry in files:
            lines.append(f"{prefix}{entry.name}")

    _walk(root, 1, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

def _detect_stack(root: Path) -> dict[str, str | None]:
    """Heuristic stack detection from well-known config files."""
    language: str | None = None
    framework: str | None = None
    runtime: str | None = None
    db: str | None = None
    orm: str | None = None

    # Language detection
    if (root / "package.json").is_file():
        if (root / "tsconfig.json").is_file():
            language = "typescript"
        else:
            language = "javascript"

    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        language = "python"

    if (root / "Cargo.toml").is_file():
        language = "rust"

    if (root / "go.mod").is_file():
        language = "go"

    # Runtime
    if (root / "wrangler.toml").is_file():
        runtime = "cloudflare-workers"

    # Framework — glob for wildcard extension variants (e.g., astro.config.ts)
    framework_patterns: list[tuple[str, str]] = [
        ("astro.config.*", "astro"),
        ("next.config.*", "next"),
        ("vite.config.*", "vite"),
    ]
    for pattern, name in framework_patterns:
        if any(True for _ in root.glob(pattern)):
            framework = name
            break

    # ORM
    if any(True for _ in root.glob("drizzle.config.*")):
        orm = "drizzle"
    elif (root / "prisma" / "schema.prisma").is_file():
        orm = "prisma"

    # DB — infer from wrangler.toml content or known ORM
    if runtime == "cloudflare-workers":
        wrangler = root / "wrangler.toml"
        try:
            content = wrangler.read_text(encoding="utf-8", errors="ignore")
            if "d1_databases" in content:
                db = "d1"
            elif "kv_namespaces" in content:
                db = "kv"
            elif "r2_buckets" in content:
                db = "r2"
        except OSError:
            pass

    return {"language": language, "framework": framework, "runtime": runtime, "db": db, "orm": orm}


# ---------------------------------------------------------------------------
# Entry point detection
# ---------------------------------------------------------------------------

def _find_entry_points(root: Path) -> list[str]:
    """Locate likely entry-point files relative to root."""
    candidates: list[str] = [
        "src/index.*",
        "src/main.*",
        "src/app.*",
        "main.py",
        "manage.py",
        "src/pages/index.*",
    ]
    found: list[str] = []
    for pattern in candidates:
        for match in root.glob(pattern):
            if match.is_file():
                rel = match.relative_to(root).as_posix()
                if rel not in found:
                    found.append(rel)
    return found


# ---------------------------------------------------------------------------
# Dependency analysis
# ---------------------------------------------------------------------------

def _parse_dependencies(root: Path) -> dict:
    """Count and categorise dependencies from package.json or pyproject.toml."""
    prod_count = 0
    dev_count = 0
    heavy: list[str] = []

    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            prod_deps: dict = data.get("dependencies", {})
            dev_deps: dict = data.get("devDependencies", {})
            prod_count = len(prod_deps)
            dev_count = len(dev_deps)
            all_deps = set(prod_deps) | set(dev_deps)
            heavy = sorted(all_deps & HEAVY_PACKAGES)
        except (json.JSONDecodeError, OSError):
            pass
        return {"prod": prod_count, "dev": dev_count, "heavy": heavy}

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            # Minimal TOML parse: count lines inside [project.dependencies]
            in_deps = False
            in_optional = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    in_deps = stripped in ("[project.dependencies]", "[tool.poetry.dependencies]")
                    in_optional = stripped in (
                        "[project.optional-dependencies]",
                        "[tool.poetry.dev-dependencies]",
                        "[tool.poetry.group.dev.dependencies]",
                    )
                    continue
                if in_deps and stripped and not stripped.startswith("#"):
                    prod_count += 1
                elif in_optional and stripped and not stripped.startswith("#"):
                    dev_count += 1
        except OSError:
            pass
        return {"prod": prod_count, "dev": dev_count, "heavy": heavy}

    requirements = root / "requirements.txt"
    if requirements.is_file():
        try:
            lines = [
                ln.strip()
                for ln in requirements.read_text(encoding="utf-8", errors="ignore").splitlines()
                if ln.strip() and not ln.startswith("#")
            ]
            prod_count = len(lines)
        except OSError:
            pass

    return {"prod": prod_count, "dev": dev_count, "heavy": heavy}


# ---------------------------------------------------------------------------
# File count and LOC
# ---------------------------------------------------------------------------

def _count_files_and_loc(root: Path) -> tuple[int, int]:
    """Walk the project and count source files and total lines of code."""
    file_count = 0
    loc = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext not in SOURCE_EXTENSIONS:
                continue
            file_count += 1
            filepath = Path(dirpath) / filename
            try:
                with filepath.open(encoding="utf-8", errors="ignore") as fh:
                    loc += sum(1 for _ in fh)
            except OSError:
                pass

    return file_count, loc


# ---------------------------------------------------------------------------
# Git hash
# ---------------------------------------------------------------------------

def _git_hash(root: Path) -> str | None:
    """Return short git SHA, or None if git is unavailable or not a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_snapshot(project_root: Path | None = None) -> dict:
    """Scan *project_root* and return a project snapshot dict.

    All fields are safe to serialise to JSON. Missing values are None or
    empty collections — never raised exceptions.
    """
    root = Path(project_root or Path.cwd()).resolve()

    tree = _build_tree(root)
    stack = _detect_stack(root)
    entry_points = _find_entry_points(root)
    dependencies = _parse_dependencies(root)
    file_count, loc = _count_files_and_loc(root)
    git_hash = _git_hash(root)

    return {
        "tree": tree,
        "stack": stack,
        "entry_points": entry_points,
        "dependencies": dependencies,
        "file_count": file_count,
        "loc": loc,
        "git_hash": git_hash,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a project snapshot JSON for dream-studio context.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  py hooks/lib/repo_context.py\n"
            "  py hooks/lib/repo_context.py --project-root /path/to/project\n"
            "  py hooks/lib/repo_context.py --output snapshot.json\n"
        ),
    )
    parser.add_argument(
        "--project-root",
        default=".",
        metavar="PATH",
        help="Root directory of the project to scan (default: current directory).",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Write JSON to this file path instead of stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        parser.error(f"--project-root is not a directory: {root}")

    snapshot = generate_snapshot(root)
    output_text = json.dumps(snapshot, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_text, encoding="utf-8")
        except OSError as exc:
            import sys
            print(f"repo_context: cannot write output file: {exc}", file=sys.stderr)
            return 1
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
