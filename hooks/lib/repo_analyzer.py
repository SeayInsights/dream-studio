#!/usr/bin/env python3
"""External Repository Analyzer for dream-studio project intelligence (Wave 6).

Analyzes external GitHub repos, extracts reusable patterns and building blocks,
then stores them for later reference.

Database tables:
- reg_analyzed_repos: repo metadata and analysis history
- reg_repo_extractions: extracted patterns and building blocks
- ds_documents: building blocks stored as searchable documents
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .document_store import DocumentStore
from .studio_db import _connect

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Stack Detection ─────────────────────────────────────────────────────────


def detect_stack(repo_path: Path) -> str:
    """
    Detect the primary tech stack from a repository.

    Detection order (priority):
    1. Check package.json for Node.js frameworks
    2. Check requirements.txt/pyproject.toml for Python
    3. Check go.mod for Go
    4. Check Cargo.toml for Rust
    5. Check pom.xml/build.gradle for Java

    Args:
        repo_path: Path to repository root

    Returns:
        Stack identifier (e.g., 'nextjs', 'react', 'django', 'fastapi', 'unknown')
    """
    # Node.js / JavaScript
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                if "next" in deps:
                    return "nextjs"
                if "react" in deps and "vite" in deps:
                    return "react-vite"
                if "react" in deps:
                    return "react"
                if "vue" in deps:
                    return "vue"
                if "svelte" in deps:
                    return "svelte"
                if "express" in deps:
                    return "express"
                if "@hono/node-server" in deps or "hono" in deps:
                    return "hono"
                return "nodejs"
        except (json.JSONDecodeError, OSError):
            pass

    # Python
    if (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists():
        try:
            # Check requirements.txt
            req_file = repo_path / "requirements.txt"
            if req_file.exists():
                content = req_file.read_text(encoding="utf-8").lower()
                if "django" in content:
                    return "django"
                if "fastapi" in content:
                    return "fastapi"
                if "flask" in content:
                    return "flask"

            # Check pyproject.toml
            pyproject = repo_path / "pyproject.toml"
            if pyproject.exists():
                content = pyproject.read_text(encoding="utf-8").lower()
                if "django" in content:
                    return "django"
                if "fastapi" in content:
                    return "fastapi"
                if "flask" in content:
                    return "flask"

            return "python"
        except OSError:
            pass

    # Go
    if (repo_path / "go.mod").exists():
        return "go"

    # Rust
    if (repo_path / "Cargo.toml").exists():
        return "rust"

    # Java
    if (repo_path / "pom.xml").exists():
        return "java-maven"
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "java-gradle"

    return "unknown"


# ── Pattern Extraction ──────────────────────────────────────────────────────


def extract_patterns(repo_path: Path, stack: str) -> list[dict]:
    """
    Extract common code patterns from repository.

    Patterns to look for:
    - Error handling patterns (try/catch, error boundaries)
    - API patterns (REST, GraphQL setup)
    - State management patterns (Redux, Zustand, Context)
    - Auth patterns (JWT, session, OAuth)

    Args:
        repo_path: Path to repository root
        stack: Detected stack identifier

    Returns:
        List of pattern dicts with: pattern_type, code_sample, description, file_path
    """
    patterns = []

    # JavaScript/TypeScript patterns
    if stack in ("nextjs", "react", "react-vite", "vue", "svelte", "nodejs", "express", "hono"):
        patterns.extend(_extract_js_patterns(repo_path))

    # Python patterns
    if stack in ("django", "fastapi", "flask", "python"):
        patterns.extend(_extract_python_patterns(repo_path))

    return patterns


def _extract_js_patterns(repo_path: Path) -> list[dict]:
    """Extract JavaScript/TypeScript patterns."""
    patterns = []

    # Search for error boundary pattern (React)
    for file in repo_path.rglob("*.tsx"):
        try:
            content = file.read_text(encoding="utf-8")
            if "componentDidCatch" in content or "ErrorBoundary" in content:
                # Extract the error boundary component
                match = re.search(
                    r"(class \w+ErrorBoundary[\s\S]{0,500}componentDidCatch[\s\S]{0,300}\})",
                    content
                )
                if match:
                    patterns.append({
                        "pattern_type": "error-boundary",
                        "code_sample": match.group(1)[:500],
                        "description": "React Error Boundary pattern for graceful error handling",
                        "file_path": str(file.relative_to(repo_path)),
                    })
                    break
        except (OSError, UnicodeDecodeError):
            continue

    # Search for API client pattern
    for file in repo_path.rglob("*.ts"):
        if "api" in file.name.lower() or "client" in file.name.lower():
            try:
                content = file.read_text(encoding="utf-8")
                if "axios" in content or "fetch" in content:
                    # Extract API setup
                    match = re.search(
                        r"(export\s+(?:const|class)\s+\w*(?:API|Client)\w*[\s\S]{0,400})",
                        content
                    )
                    if match:
                        patterns.append({
                            "pattern_type": "api-client",
                            "code_sample": match.group(1)[:500],
                            "description": "API client setup pattern",
                            "file_path": str(file.relative_to(repo_path)),
                        })
                        break
            except (OSError, UnicodeDecodeError):
                continue

    # Search for state management pattern
    for file in repo_path.rglob("*.ts"):
        if "store" in file.name.lower() or "state" in file.name.lower():
            try:
                content = file.read_text(encoding="utf-8")
                if "zustand" in content or "redux" in content or "createContext" in content:
                    match = re.search(
                        r"(export\s+(?:const|function)\s+\w*[Ss]tore\w*[\s\S]{0,400})",
                        content
                    )
                    if match:
                        patterns.append({
                            "pattern_type": "state-management",
                            "code_sample": match.group(1)[:500],
                            "description": "State management pattern",
                            "file_path": str(file.relative_to(repo_path)),
                        })
                        break
            except (OSError, UnicodeDecodeError):
                continue

    return patterns


def _extract_python_patterns(repo_path: Path) -> list[dict]:
    """Extract Python patterns."""
    patterns = []

    # Search for error handling pattern
    for file in repo_path.rglob("*.py"):
        try:
            content = file.read_text(encoding="utf-8")
            # Look for custom exception classes
            if "class" in content and "Exception" in content:
                match = re.search(
                    r"(class \w+Exception[\s\S]{0,300})",
                    content
                )
                if match:
                    patterns.append({
                        "pattern_type": "error-handling",
                        "code_sample": match.group(1)[:500],
                        "description": "Custom exception pattern for error handling",
                        "file_path": str(file.relative_to(repo_path)),
                    })
                    break
        except (OSError, UnicodeDecodeError):
            continue

    # Search for API route pattern (FastAPI/Flask)
    for file in repo_path.rglob("*.py"):
        if "route" in file.name.lower() or "api" in file.name.lower():
            try:
                content = file.read_text(encoding="utf-8")
                if "@app.route" in content or "@router." in content:
                    match = re.search(
                        r"(@(?:app\.route|router\.\w+)[\s\S]{0,400})",
                        content
                    )
                    if match:
                        patterns.append({
                            "pattern_type": "api-route",
                            "code_sample": match.group(1)[:500],
                            "description": "API route pattern",
                            "file_path": str(file.relative_to(repo_path)),
                        })
                        break
            except (OSError, UnicodeDecodeError):
                continue

    return patterns


# ── Building Block Extraction ───────────────────────────────────────────────


def extract_building_blocks(repo_path: Path, stack: str) -> list[dict]:
    """
    Extract reusable components/modules.

    Look for:
    - Utility functions (date formatting, string helpers)
    - Hooks (React hooks, composables)
    - Middleware (Express, Hono)
    - Config files (well-structured configs)

    Args:
        repo_path: Path to repository root
        stack: Detected stack identifier

    Returns:
        List of component dicts with: component_type, file_path, code, description
    """
    blocks = []

    # JavaScript/TypeScript building blocks
    if stack in ("nextjs", "react", "react-vite", "vue", "svelte", "nodejs", "express", "hono"):
        blocks.extend(_extract_js_blocks(repo_path))

    # Python building blocks
    if stack in ("django", "fastapi", "flask", "python"):
        blocks.extend(_extract_python_blocks(repo_path))

    return blocks


def _extract_js_blocks(repo_path: Path) -> list[dict]:
    """Extract JavaScript/TypeScript building blocks."""
    blocks = []
    extracted_files = set()
    max_blocks = 10  # Limit to avoid overwhelming storage

    # Look for utility files in common directories
    utils_dirs = ["utils", "lib", "helpers", "src/utils", "src/lib", "src/helpers"]
    for dir_name in utils_dirs:
        if len(blocks) >= max_blocks:
            break
        utils_path = repo_path / dir_name
        if utils_path.exists():
            for ext in ["*.ts", "*.tsx", "*.js"]:
                for file in utils_path.glob(ext):
                    if len(blocks) >= max_blocks:
                        break
                    if file in extracted_files:
                        continue
                    try:
                        content = file.read_text(encoding="utf-8")
                        if len(content) < 5000 and ("export" in content):
                            blocks.append({
                                "component_type": "utility",
                                "file_path": str(file.relative_to(repo_path)),
                                "code": content[:2000],
                                "description": f"Utility functions from {file.name}",
                            })
                            extracted_files.add(file)
                    except (OSError, UnicodeDecodeError):
                        continue

    # Look for custom hooks in various locations
    hooks_dirs = ["hooks", "src/hooks", "src"]
    for dir_name in hooks_dirs:
        if len(blocks) >= max_blocks:
            break
        hooks_path = repo_path / dir_name
        if hooks_path.exists():
            # Search for files starting with "use"
            for ext in ["*.ts", "*.tsx", "*.js"]:
                for file in hooks_path.glob(ext):
                    if len(blocks) >= max_blocks:
                        break
                    if file in extracted_files:
                        continue
                    if file.stem.lower().startswith("use"):
                        try:
                            content = file.read_text(encoding="utf-8")
                            if len(content) < 3000:
                                blocks.append({
                                    "component_type": "hook",
                                    "file_path": str(file.relative_to(repo_path)),
                                    "code": content[:2000],
                                    "description": f"Custom React hook: {file.stem}",
                                })
                                extracted_files.add(file)
                        except (OSError, UnicodeDecodeError):
                            continue

    return blocks


def _extract_python_blocks(repo_path: Path) -> list[dict]:
    """Extract Python building blocks."""
    blocks = []
    extracted_files = set()
    max_blocks = 10  # Limit to avoid overwhelming storage

    # Look for utility modules in common directories
    utils_dirs = ["utils", "lib", "helpers", "src/utils", "src/lib", "app/utils"]
    for dir_name in utils_dirs:
        if len(blocks) >= max_blocks:
            break
        utils_path = repo_path / dir_name
        if utils_path.exists():
            for file in utils_path.glob("*.py"):
                if len(blocks) >= max_blocks:
                    break
                if file in extracted_files or file.name.startswith("__"):
                    continue
                try:
                    content = file.read_text(encoding="utf-8")
                    if len(content) < 5000 and ("def " in content):
                        blocks.append({
                            "component_type": "utility",
                            "file_path": str(file.relative_to(repo_path)),
                            "code": content[:2000],
                            "description": f"Utility functions from {file.name}",
                        })
                        extracted_files.add(file)
                except (OSError, UnicodeDecodeError):
                    continue

    return blocks


# ── Storage Functions ───────────────────────────────────────────────────────


def store_extractions(repo_id: int, extractions: list[dict], extraction_type: str) -> None:
    """
    Store extractions in reg_repo_extractions and ds_documents.

    Args:
        repo_id: ID from reg_analyzed_repos
        extractions: List of extraction dicts
        extraction_type: 'pattern' or 'building-block'
    """
    # First, store all extractions in reg_repo_extractions
    extraction_ids = []
    with _connect() as c:
        for extraction in extractions:
            extraction_id = _generate_extraction_id(repo_id, extraction)
            extraction_ids.append(extraction_id)

            c.execute(
                """INSERT OR REPLACE INTO reg_repo_extractions
                   (extraction_id, repo_id, extraction_type, title, file_path,
                    code_sample, description, times_used, effectiveness_score, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)""",
                (
                    extraction_id,
                    repo_id,
                    extraction_type,
                    extraction.get("pattern_type") or extraction.get("component_type", "unknown"),
                    extraction.get("file_path"),
                    extraction.get("code_sample") or extraction.get("code"),
                    extraction.get("description"),
                    _NOW(),
                ),
            )

    # Then, store building blocks in ds_documents (requires separate connection)
    if extraction_type == "building-block":
        for i, extraction in enumerate(extractions):
            extraction_id = extraction_ids[i]

            # Create document
            doc_id = DocumentStore.create(
                doc_type="building-block",
                title=extraction.get("description", "Untitled building block"),
                content=extraction.get("code", ""),
                metadata={
                    "repo_id": repo_id,
                    "component_type": extraction.get("component_type"),
                    "file_path": extraction.get("file_path"),
                },
                keywords=f"{extraction.get('component_type')} {extraction.get('file_path', '')}",
            )

            # Link document to extraction
            with _connect() as c:
                c.execute(
                    "UPDATE reg_repo_extractions SET document_id = ? WHERE extraction_id = ?",
                    (doc_id, extraction_id),
                )


def _generate_extraction_id(repo_id: int, extraction: dict) -> int:
    """Generate a unique extraction ID based on repo_id and extraction content."""
    content = f"{repo_id}:{extraction.get('file_path', '')}:{extraction.get('description', '')}"
    hash_hex = hashlib.sha256(content.encode()).hexdigest()[:16]
    return int(hash_hex, 16) % (10**15)  # Keep it within reasonable integer range


# ── Main Analysis Function ──────────────────────────────────────────────────


def analyze_repo(repo_url: str, shallow: bool = True) -> dict:
    """
    Clone and analyze external repo.

    Args:
        repo_url: GitHub repo URL (e.g., 'https://github.com/vercel/next.js')
        shallow: If True, use --depth=1 for faster clone

    Returns:
        {
            'repo_id': int,
            'repo_name': str,
            'patterns_count': int,
            'building_blocks_count': int,
            'analysis_timestamp': str,
            'stack': str
        }

    Steps:
        1. Clone repo to temp directory
        2. Detect stack
        3. Extract patterns
        4. Extract building blocks
        5. Store in reg_repo_extractions and ds_documents
        6. Clean up temp directory
    """
    temp_dir = None

    try:
        # 1. Clone repo to temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="repo-analysis-"))
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_path = temp_dir / repo_name

        clone_cmd = ["git", "clone"]
        if shallow:
            clone_cmd.extend(["--depth=1"])
        clone_cmd.extend([repo_url, str(clone_path)])

        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        # 2. Detect stack
        stack = detect_stack(clone_path)

        # 3. Extract patterns
        patterns = extract_patterns(clone_path, stack)

        # 4. Extract building blocks
        building_blocks = extract_building_blocks(clone_path, stack)

        # 5. Store in database
        with _connect() as c:
            # Check if repo already exists
            existing = c.execute(
                "SELECT repo_id FROM reg_analyzed_repos WHERE repo_url = ?",
                (repo_url,)
            ).fetchone()

            if existing:
                repo_id = existing[0]
                # Update existing repo
                c.execute(
                    """UPDATE reg_analyzed_repos
                       SET last_analyzed = ?,
                           analysis_count = analysis_count + 1,
                           framework = ?,
                           patterns_extracted = ?,
                           building_blocks_extracted = ?
                       WHERE repo_id = ?""",
                    (_NOW(), stack, len(patterns), len(building_blocks), repo_id),
                )
            else:
                # Insert new repo
                cursor = c.execute(
                    """INSERT INTO reg_analyzed_repos
                       (repo_url, repo_name, first_analyzed, last_analyzed,
                        analysis_count, framework, patterns_extracted, building_blocks_extracted)
                       VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                    (repo_url, repo_name, _NOW(), _NOW(), stack, len(patterns), len(building_blocks)),
                )
                repo_id = cursor.lastrowid

        # Store extractions
        if patterns:
            store_extractions(repo_id, patterns, "pattern")
        if building_blocks:
            store_extractions(repo_id, building_blocks, "building-block")

        return {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "patterns_count": len(patterns),
            "building_blocks_count": len(building_blocks),
            "analysis_timestamp": _NOW(),
            "stack": stack,
        }

    finally:
        # 6. Clean up temp directory
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
