"""Multi-repository ingestor.

Ingests multiple repositories and normalizes into canonical object model.
PRESERVES repository boundaries. NO cross-repo inference at this stage.
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
from pathlib import Path

from .model import Repository, Module, Edge, RelationshipType


@dataclass
class ParsedModule:
    """Package-local parsed module summary for org intelligence ingestion."""

    path: str
    imports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    loc: int = 0


@dataclass
class RepoStructure:
    """Package-local repository parse result."""

    modules: list[ParsedModule] = field(default_factory=list)


class RepoParser:
    """Small package-local parser; avoids importing main runtime internals."""

    SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def parse(self) -> RepoStructure:
        modules: list[ParsedModule] = []
        for path in sorted(self.repo_path.rglob("*.py")):
            if any(part in self.SKIP_DIRS for part in path.parts):
                continue
            modules.append(self._parse_file(path))
        return RepoStructure(modules=modules)

    def _parse_file(self, path: Path) -> ParsedModule:
        relative = path.relative_to(self.repo_path).as_posix()
        source = path.read_text(encoding="utf-8", errors="ignore")
        loc = sum(1 for line in source.splitlines() if line.strip())
        imports: list[str] = []
        functions: list[str] = []
        classes: list[str] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ParsedModule(path=relative, loc=loc)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

        dependencies = [
            f"{module.replace('.', '/')}.py" for module in imports if not module.startswith(".")
        ]
        return ParsedModule(
            path=relative,
            imports=sorted(set(imports)),
            functions=sorted(set(functions)),
            classes=sorted(set(classes)),
            dependencies=sorted(set(dependencies)),
            loc=loc,
        )


class MultiRepoIngestor:
    """Ingest multiple repositories into canonical object model.

    Deterministic. NO heuristics. Direct mapping from file system + AST.
    """

    def __init__(self):
        self.repositories: dict[str, Repository] = {}
        self.modules: dict[str, Module] = {}
        self.edges: list[Edge] = []

    def ingest_repository(self, repo_path: str, repo_name: str | None = None) -> str:
        """Ingest a single repository.

        Args:
            repo_path: Path to repository
            repo_name: Optional name (defaults to directory name)

        Returns:
            Repository ID
        """
        repo_path_obj = Path(repo_path).resolve()

        if not repo_path_obj.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        # Generate repository ID
        repo_id = self._generate_repo_id(repo_path_obj, repo_name)

        # Create repository node
        repo = Repository(id=repo_id, name=repo_name or repo_path_obj.name, path=str(repo_path_obj))

        # Parse repository using existing repo intelligence
        parser = RepoParser(str(repo_path_obj))
        structure = parser.parse()

        # Convert modules
        for module_info in structure.modules:
            module_id = self._generate_module_id(repo_id, module_info.path)

            module = Module(
                id=module_id,
                repo_id=repo_id,
                file_path=module_info.path,
                imports=module_info.imports,
                exports=module_info.functions + module_info.classes,
                loc=module_info.loc,
                coupling_score=0.0,  # Will be computed by graph builder
            )

            self.modules[module_id] = module

            # Add CONTAINS edge: Repository → Module
            self.edges.append(
                Edge(
                    from_node=repo_id,
                    to_node=module_id,
                    relationship_type=RelationshipType.CONTAINS,
                    evidence={"file_path": module_info.path},
                )
            )

            # Add DEPENDENCY edges: Module → Module (via imports)
            for imported in module_info.dependencies:
                imported_module_id = self._generate_module_id(repo_id, imported)
                if imported_module_id in self.modules:
                    self.edges.append(
                        Edge(
                            from_node=module_id,
                            to_node=imported_module_id,
                            relationship_type=RelationshipType.DEPENDENCY,
                            evidence={"import": imported},
                        )
                    )

        # Update repository metrics
        repo.module_count = len([m for m in self.modules.values() if m.repo_id == repo_id])
        repo.loc = sum(m.loc for m in self.modules.values() if m.repo_id == repo_id)

        self.repositories[repo_id] = repo

        return repo_id

    def ingest_folder(self, folder_path: str) -> list[str]:
        """Ingest all repositories in a folder.

        Args:
            folder_path: Path to folder containing repositories

        Returns:
            List of repository IDs
        """
        folder = Path(folder_path).resolve()

        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Folder does not exist: {folder_path}")

        repo_ids = []

        # Look for directories with .git or package.json or setup.py (repository indicators)
        for subdir in folder.iterdir():
            if not subdir.is_dir():
                continue

            # Skip common non-repo directories
            if subdir.name in [".git", "node_modules", ".venv", "venv", "__pycache__"]:
                continue

            # Check if it looks like a repository
            is_repo = (
                (subdir / ".git").exists()
                or (subdir / "package.json").exists()
                or (subdir / "setup.py").exists()
                or (subdir / "pyproject.toml").exists()
            )

            if is_repo:
                try:
                    repo_id = self.ingest_repository(str(subdir), subdir.name)
                    repo_ids.append(repo_id)
                except Exception as e:
                    print(f"Warning: Failed to ingest {subdir.name}: {e}")

        return repo_ids

    def ingest_multiple(self, repo_paths: list[str]) -> list[str]:
        """Ingest multiple repositories.

        Args:
            repo_paths: List of repository paths

        Returns:
            List of repository IDs
        """
        repo_ids = []
        for repo_path in repo_paths:
            try:
                repo_id = self.ingest_repository(repo_path)
                repo_ids.append(repo_id)
            except Exception as e:
                print(f"Warning: Failed to ingest {repo_path}: {e}")

        return repo_ids

    def _generate_repo_id(self, repo_path: Path, repo_name: str | None = None) -> str:
        """Generate deterministic repository ID.

        Args:
            repo_path: Repository path
            repo_name: Optional repository name

        Returns:
            Repository ID
        """
        if repo_name:
            return f"repo:{repo_name}"
        # Use last directory name
        return f"repo:{repo_path.name}"

    def _generate_module_id(self, repo_id: str, file_path: str) -> str:
        """Generate deterministic module ID.

        Args:
            repo_id: Repository ID
            file_path: File path (relative to repo)

        Returns:
            Module ID
        """
        # Normalize file path (remove .py extension, convert to module path)
        normalized = file_path.replace("\\", "/").replace("/", ".").replace(".py", "")
        return f"{repo_id}:{normalized}"

    def get_results(self) -> tuple[dict[str, Repository], dict[str, Module], list[Edge]]:
        """Get ingestion results.

        Returns:
            (repositories, modules, edges)
        """
        return self.repositories, self.modules, self.edges
