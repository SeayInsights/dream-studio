"""Stack evidence helpers for project intelligence routes."""

import json
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

SAFE_STACK_FILE_NAMES = {
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "requirements-dev.txt",
    "go.mod",
    "Cargo.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "justfile",
}
SAFE_STACK_DIR_NAMES = {
    ".github",
    "adapter-projections",
    "core",
    "docs",
    "hooks",
    "interfaces",
    "migrations",
    "projections",
    "runtime",
    "skills",
    "tests",
    "workflows",
}
SENSITIVE_PATH_PARTS = {
    ".git",
    ".claude",
    ".codex",
    ".env",
    ".venv",
    "secrets",
    "credentials",
    "node_modules",
}


def _safe_project_root(project: dict[str, Any]) -> Path | None:
    raw_path = project.get("project_path")
    if not raw_path:
        return None
    root = Path(str(raw_path))
    if not root.is_absolute():
        root = Path.home() / "builds" / root
    try:
        resolved = root.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_dir():
        return None
    lowered_parts = {part.lower() for part in resolved.parts}
    if lowered_parts.intersection(SENSITIVE_PATH_PARTS):
        return None
    if "appdata" in lowered_parts and "temp" not in lowered_parts:
        return None
    return resolved


def _safe_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return path.name


def _safe_read_text(path: Path, *, max_bytes: int = 200_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _safe_manifest_dependencies(path: Path) -> list[str]:
    name = path.name.lower()
    if name == "package.json":
        text = _safe_read_text(path)
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        dependencies: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            section = payload.get(key)
            if isinstance(section, dict):
                dependencies.update(str(item) for item in section if item)
        return sorted(dependencies)
    if name == "pyproject.toml":
        try:
            if path.stat().st_size > 200_000:
                return []
            payload = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, tomllib.TOMLDecodeError):
            return []
        dependencies: set[str] = set()
        project = payload.get("project")
        if isinstance(project, dict):
            for dep in project.get("dependencies") or []:
                if isinstance(dep, str):
                    dependencies.add(dep.split(";", 1)[0].strip())
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for deps in optional.values():
                    if isinstance(deps, list):
                        dependencies.update(
                            dep.split(";", 1)[0].strip() for dep in deps if isinstance(dep, str)
                        )
        return sorted(dep for dep in dependencies if dep)
    if name.startswith("requirements") and name.endswith(".txt"):
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-", "http:", "https:", "git+")):
                continue
            dependencies.append(stripped.split(";", 1)[0].strip())
        return sorted(dict.fromkeys(dependencies))
    if name == "go.mod":
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("module ", "go ", "require (", ")")):
                dependencies.append(stripped.split()[0])
        return sorted(dict.fromkeys(dependencies))
    if name == "cargo.toml":
        text = _safe_read_text(path)
        if not text:
            return []
        dependencies = []
        in_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_deps = stripped in {"[dependencies]", "[dev-dependencies]"}
                continue
            if in_deps and stripped and not stripped.startswith("#") and "=" in stripped:
                dependencies.append(stripped.split("=", 1)[0].strip())
        return sorted(dict.fromkeys(dependencies))
    return []


def _repo_stack_evidence(project: dict[str, Any]) -> dict[str, Any]:
    root = _safe_project_root(project)
    if root is None:
        return {
            "classification": "unavailable",
            "reason": "Project path is missing, unverified, or in a sensitive runtime area.",
            "source_refs": [],
            "confirmed_dependency_edges": False,
            "inferred_dependency_edges": [],
            "secret_contents_read": False,
            "derived_view": True,
            "primary_authority": False,
        }

    manifests: list[dict[str, Any]] = []
    config_files: list[str] = []
    workflow_files: list[str] = []
    frontend_surfaces: list[str] = []
    api_route_files: list[str] = []
    migration_files: list[str] = []
    skill_files: list[str] = []
    hook_files: list[str] = []
    adapter_projection_files: list[str] = []
    language_counts: Counter[str] = Counter()
    inferred_edges: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        if len(config_files) + len(workflow_files) + len(frontend_surfaces) > 600:
            break
        if not path.is_file():
            continue
        rel = _safe_rel(root, path)
        lowered_parts = {part.lower() for part in Path(rel).parts}
        if lowered_parts.intersection(SENSITIVE_PATH_PARTS):
            continue
        suffix = path.suffix.lower()
        if suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".go", ".rs"}:
            language_counts[suffix.lstrip(".")] += 1
        if path.name in SAFE_STACK_FILE_NAMES:
            deps = _safe_manifest_dependencies(path)
            manifests.append(
                {
                    "path": rel,
                    "dependency_names": deps[:50],
                    "dependency_count": len(deps),
                    "evidence_kind": "package_or_runtime_manifest",
                    "source_ref": rel,
                }
            )
            for dep in deps[:50]:
                inferred_edges.append(
                    {
                        "from": rel,
                        "to": dep,
                        "type": "manifest_declared_dependency",
                        "confirmation_status": "inferred_unverified",
                        "rendered_by_default": False,
                        "source_refs": [rel],
                    }
                )
        if path.name in SAFE_STACK_FILE_NAMES or any(
            part in SAFE_STACK_DIR_NAMES for part in Path(rel).parts
        ):
            config_files.append(rel)
        if rel.startswith(".github/workflows/"):
            workflow_files.append(rel)
        if suffix in {".html", ".jsx", ".tsx"} and any(
            part in {"frontend", "src", "app", "pages", "components", "projections"}
            for part in Path(rel).parts
        ):
            frontend_surfaces.append(rel)
        if suffix == ".py" and ("routes" in Path(rel).parts or "api" in Path(rel).parts):
            api_route_files.append(rel)
        if "migrations" in Path(rel).parts:
            migration_files.append(rel)
        if Path(rel).name == "SKILL.md" or "skills" in Path(rel).parts:
            skill_files.append(rel)
        if "hooks" in Path(rel).parts:
            hook_files.append(rel)
        if "adapter-projections" in Path(rel).parts:
            adapter_projection_files.append(rel)

    evidence_refs = sorted(
        dict.fromkeys(
            [item["path"] for item in manifests]
            + config_files[:40]
            + workflow_files[:20]
            + api_route_files[:20]
            + frontend_surfaces[:20]
            + migration_files[:20]
            + skill_files[:20]
            + hook_files[:20]
            + adapter_projection_files[:20]
        )
    )

    return {
        "classification": "confirmed" if evidence_refs else "honest_empty_state",
        "reason": (
            "Read-only repo scan found stack/config evidence."
            if evidence_refs
            else "No safe stack/config evidence was found under the project path."
        ),
        "project_root": str(root),
        "package_manifests": manifests[:20],
        "config_files": sorted(dict.fromkeys(config_files))[:80],
        "workflow_files": sorted(dict.fromkeys(workflow_files))[:40],
        "api_route_files": sorted(dict.fromkeys(api_route_files))[:60],
        "frontend_surfaces": sorted(dict.fromkeys(frontend_surfaces))[:60],
        "migration_files": sorted(dict.fromkeys(migration_files))[:60],
        "skill_files": sorted(dict.fromkeys(skill_files))[:60],
        "hook_files": sorted(dict.fromkeys(hook_files))[:60],
        "adapter_projection_files": sorted(dict.fromkeys(adapter_projection_files))[:60],
        "languages": dict(sorted(language_counts.items())),
        "source_refs": evidence_refs,
        "inferred_dependency_edges": inferred_edges[:200],
        "inferred_dependency_count": len(inferred_edges),
        "confirmed_dependency_edges": False,
        "secret_contents_read": False,
        "repo_mutation_authorized": False,
        "derived_view": True,
        "primary_authority": False,
    }
