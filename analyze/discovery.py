"""
Discovery Phase - Project Inventory and Metadata Extraction

Analyzes a project directory to gather:
- File inventory (counts by extension and directory)
- Lines of code statistics
- Programming languages used
- Git metadata (commits, contributors, age)
- Entry points and configuration files
- Project type classification (greenfield vs brownfield)
- Stack detection

Wave 4 Integration: Context7 for large projects (10k+ files)
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess
import sys
from datetime import datetime, timezone

# Context7 integration for large codebases (Wave 4)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks" / "lib"))
    from context.context7_manager import Context7Manager
    _CONTEXT7_AVAILABLE = True
except ImportError:
    _CONTEXT7_AVAILABLE = False
    Context7Manager = None


def discover_project(path: Path, use_context7: bool = False, query: str = "") -> Dict[str, Any]:
    """
    Discover project structure and metadata.

    Args:
        path: Project root directory
        use_context7: If True and project has 10k+ files, use Context7 progressive loading
        query: Optional query for Context7 relevance ranking (e.g., "authentication security")

    Returns:
        Complete project discovery dict with:
        - project_name: extracted from config files or directory name
        - project_path: absolute path to project
        - file_inventory: counts by extension and directory
        - lines_of_code: total and by language
        - languages: detected programming languages
        - git_metadata: commits, contributors, dates, age
        - entry_points: likely entry point files
        - project_type: greenfield or brownfield
        - config_files: found configuration files
        - detected_stack: stack adapter name if detected
        - context7_metadata: (if enabled) progressive loading stats
    """
    path = Path(path).resolve()

    # Quick file count to determine if Context7 is needed
    inventory = _inventory_files(path)
    total_files = inventory["total_files"]

    result = {
        "project_name": _get_project_name(path),
        "project_path": str(path),
        "file_inventory": inventory,
        "lines_of_code": _count_lines(path),
        "languages": _detect_languages(path),
        "git_metadata": _get_git_metadata(path),
        "entry_points": _find_entry_points(path),
        "project_type": _determine_project_type(path),
        "config_files": _find_config_files(path),
        "detected_stack": _detect_stack_wrapper(path)
    }

    # Context7 integration for large projects (Wave 4)
    if use_context7 and _CONTEXT7_AVAILABLE and total_files >= 10000:
        print(f"📊 Large project detected ({total_files:,} files) - using Context7 progressive loading")
        manager = Context7Manager(max_tokens=150000)
        context_result = manager.load_codebase(path, query or "project structure analysis")

        result["context7_metadata"] = {
            "enabled": True,
            "total_files": total_files,
            "files_loaded": len(context_result.get("details", [])),
            "tokens_used": context_result.get("tokens_used", 0),
            "coverage": context_result.get("coverage", 0.0),
            "query": query or "project structure analysis"
        }
        print(f"   ✅ Loaded {len(context_result.get('details', []))} most relevant files ({context_result.get('coverage', 0)*100:.1f}% coverage)")
    elif use_context7 and total_files >= 10000:
        result["context7_metadata"] = {
            "enabled": False,
            "reason": "Context7Manager not available",
            "total_files": total_files
        }

    return result


def _get_project_name(path: Path) -> str:
    """
    Get project name from package.json, pyproject.toml, or directory name.

    Priority:
    1. package.json "name" field
    2. pyproject.toml [project] name or [tool.poetry] name
    3. Directory name as fallback
    """
    # Check package.json
    if (path / "package.json").exists():
        try:
            import json
            data = json.loads((path / "package.json").read_text())
            if "name" in data:
                return data["name"]
        except:
            pass

    # Check pyproject.toml
    if (path / "pyproject.toml").exists():
        try:
            import tomllib
            data = tomllib.loads((path / "pyproject.toml").read_text())
            if "project" in data and "name" in data["project"]:
                return data["project"]["name"]
            if "tool" in data and "poetry" in data["tool"] and "name" in data["tool"]["poetry"]:
                return data["tool"]["poetry"]["name"]
        except:
            pass

    # Fallback to directory name
    return path.name


def _inventory_files(path: Path) -> Dict[str, Any]:
    """
    Count files by extension and directory.

    Excludes common ignore patterns:
    - .git, node_modules, __pycache__
    - .venv, venv, dist, build
    - .next, .vercel

    Returns:
        total_files: total count
        by_extension: {".py": 120, ".js": 45, ...}
        by_directory: {"src/": 80, "tests/": 40, ...}
    """
    by_extension = {}
    by_directory = {}
    total_files = 0

    # Skip common ignore patterns
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".vercel"}

    for file_path in path.rglob("*"):
        if file_path.is_file():
            # Skip if in ignored directory
            if any(ignored in file_path.parts for ignored in ignore_dirs):
                continue

            total_files += 1

            # By extension
            ext = file_path.suffix or "(no extension)"
            by_extension[ext] = by_extension.get(ext, 0) + 1

            # By directory (relative to project root)
            rel_dir = str(file_path.relative_to(path).parent)
            by_directory[rel_dir] = by_directory.get(rel_dir, 0) + 1

    return {
        "total_files": total_files,
        "by_extension": by_extension,
        "by_directory": by_directory
    }


def _count_lines(path: Path) -> Dict[str, Any]:
    """
    Count lines of code by language.

    Simplified LOC counting - counts non-empty lines.
    Skips common ignore directories.

    Returns:
        total: total LOC across all languages
        by_language: {"Python": 5000, "JavaScript": 2000}
        by_file_type: {".py": 5000, ".js": 2000}
    """
    language_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".c": "C",
        ".cpp": "C++",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP"
    }

    by_file_type = {}
    by_language = {}
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}

    for file_path in path.rglob("*"):
        if file_path.is_file() and file_path.suffix in language_map:
            if any(ignored in file_path.parts for ignored in ignore_dirs):
                continue

            try:
                lines = len([l for l in file_path.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()])
                ext = file_path.suffix
                lang = language_map[ext]

                by_file_type[ext] = by_file_type.get(ext, 0) + lines
                by_language[lang] = by_language.get(lang, 0) + lines
            except:
                pass

    total = sum(by_language.values())

    return {
        "total": total,
        "by_language": by_language,
        "by_file_type": by_file_type
    }


def _detect_languages(path: Path) -> List[str]:
    """
    Detect programming languages used in project.

    Returns languages sorted by LOC descending.
    """
    loc_data = _count_lines(path)
    # Sort by LOC descending
    languages = sorted(loc_data["by_language"].items(), key=lambda x: x[1], reverse=True)
    return [lang for lang, _ in languages]


def _get_git_metadata(path: Path) -> Dict[str, Any]:
    """
    Extract git metadata if repo exists.

    Returns:
        is_git_repo: bool
        total_commits: int (if git repo)
        contributors: List[str] (if git repo)
        first_commit_date: ISO8601 string (if git repo)
        last_commit_date: ISO8601 string (if git repo)
        repo_age_days: int (if git repo)
    """
    try:
        # Check if git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return {"is_git_repo": False}

        # Get total commits
        commits_result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        total_commits = int(commits_result.stdout.strip()) if commits_result.returncode == 0 else 0

        # Get contributors
        contributors_result = subprocess.run(
            ["git", "shortlog", "-sn", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        contributors = []
        if contributors_result.returncode == 0:
            for line in contributors_result.stdout.strip().split("\n"):
                if line.strip():
                    # Format: "  10  John Doe"
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        contributors.append(parts[1])

        # Get first and last commit dates
        first_commit_result = subprocess.run(
            ["git", "log", "--reverse", "--format=%aI", "--max-count=1"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        first_commit_date = first_commit_result.stdout.strip() if first_commit_result.returncode == 0 else None

        last_commit_result = subprocess.run(
            ["git", "log", "--format=%aI", "--max-count=1"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        last_commit_date = last_commit_result.stdout.strip() if last_commit_result.returncode == 0 else None

        # Calculate repo age
        repo_age_days = 0
        if first_commit_date:
            try:
                first_dt = datetime.fromisoformat(first_commit_date.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                repo_age_days = (now - first_dt).days
            except:
                pass

        return {
            "is_git_repo": True,
            "total_commits": total_commits,
            "contributors": contributors,
            "first_commit_date": first_commit_date,
            "last_commit_date": last_commit_date,
            "repo_age_days": repo_age_days
        }

    except Exception:
        return {"is_git_repo": False}


def _find_entry_points(path: Path) -> List[str]:
    """
    Find likely entry point files.

    Checks for common entry point names in root and src/:
    - Python: main.py, app.py, __main__.py
    - JavaScript/TypeScript: index.js, index.ts, server.js, server.ts
    """
    entry_points = []
    common_names = ["main.py", "app.py", "__main__.py", "index.js", "index.ts", "server.js", "server.ts"]

    for name in common_names:
        if (path / name).exists():
            entry_points.append(name)
        # Also check src/
        if (path / "src" / name).exists():
            entry_points.append(f"src/{name}")

    return entry_points


def _determine_project_type(path: Path) -> str:
    """
    Determine if greenfield or brownfield based on git history.

    Classification:
    - No git repo: greenfield
    - > 100 commits OR > 1 year old: brownfield
    - Otherwise: greenfield
    """
    git_meta = _get_git_metadata(path)
    if not git_meta["is_git_repo"]:
        return "greenfield"  # No git = probably new

    # Brownfield if > 100 commits or > 1 year old
    if git_meta["total_commits"] > 100 or git_meta["repo_age_days"] > 365:
        return "brownfield"

    return "greenfield"


def _find_config_files(path: Path) -> List[str]:
    """
    Find configuration files in project root.

    Checks for common config patterns:
    - Package managers: package.json, pyproject.toml, requirements.txt
    - Build tools: tsconfig.json, next.config.js, astro.config.mjs
    - Environment: .env, .env.example
    - Docker: docker-compose.yml, Dockerfile
    - Linters: .gitignore, .prettierrc, .eslintrc
    """
    config_patterns = [
        "package.json", "package-lock.json",
        "pyproject.toml", "requirements.txt", "setup.py",
        "tsconfig.json", "next.config.js", "next.config.ts",
        "astro.config.mjs", "astro.config.ts",
        ".env", ".env.example",
        "docker-compose.yml", "Dockerfile",
        ".gitignore", ".prettierrc", ".eslintrc"
    ]

    found = []
    for pattern in config_patterns:
        if (path / pattern).exists():
            found.append(pattern)

    return found


def _detect_stack_wrapper(path: Path) -> Optional[str]:
    """
    Detect stack using detector.py.

    Returns adapter name if confidence > 0.5, else None.
    """
    try:
        from analyze.stacks.detector import detect_stack
        result = detect_stack(path)
        return result.adapter if result.confidence > 0.5 else None
    except:
        return None
