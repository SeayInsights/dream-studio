"""AST-based Python component extraction for unified-discovery system.

Parses Python source files to extract functions, classes, and imports,
storing them in the pi_components table for graph analysis.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.event_store import studio_db
from core.config.database import transaction

logger = logging.getLogger(__name__)


@contextmanager
def _component_transaction(db_path: Path | None = None):
    """Open a write transaction, honoring explicit DB paths for test isolation."""
    if db_path is None:
        with transaction() as conn:
            yield conn
        return

    conn = studio_db._connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@dataclass
class Component:
    """Represents a Python component (function, class, or module)."""

    component_id: str
    project_id: str
    path: str
    name: str
    component_type: str  # "function" | "class" | "module"
    lines: int
    line_start: int
    line_end: int
    docstring: str | None = None
    imports: list[str] | None = None


@dataclass
class Import:
    """Represents an import statement."""

    module: str
    names: list[str]  # List of imported names (empty for `import foo`)
    line: int
    alias: str | None = None


def extract_imports(file_path: Path) -> list[Import]:
    """Parse import statements from a Python file.

    Args:
        file_path: Path to the Python file to parse

    Returns:
        List of Import objects representing all import statements

    Examples:
        >>> imports = extract_imports(Path("mymodule.py"))
        >>> [i.module for i in imports]
        ['os', 'sys', 'pathlib']
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        logger.warning(f"Syntax error in {file_path}: {e}")
        # Fallback to regex for imports only
        return _extract_imports_regex(file_path)
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {e}")
        return []

    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    Import(module=alias.name, names=[], alias=alias.asname, line=node.lineno)
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:  # Skip relative imports like `from . import foo`
                names = [alias.name for alias in node.names]
                imports.append(
                    Import(module=node.module, names=names, alias=None, line=node.lineno)
                )

    return imports


def _extract_imports_regex(file_path: Path) -> list[Import]:
    """Fallback regex-based import extraction for files with syntax errors.

    Args:
        file_path: Path to the Python file to parse

    Returns:
        List of Import objects extracted via regex
    """
    imports = []
    try:
        content = file_path.read_text(encoding="utf-8")

        # Match: import foo, bar, baz
        import_pattern = r"^\s*import\s+([\w\.,\s]+)"
        # Match: from foo import bar, baz
        from_pattern = r"^\s*from\s+([\w\.]+)\s+import\s+([\w\.,\s\*]+)"

        for i, line in enumerate(content.splitlines(), start=1):
            # Skip comments
            if line.strip().startswith("#"):
                continue

            match = re.match(import_pattern, line)
            if match:
                modules = [m.strip() for m in match.group(1).split(",")]
                for module in modules:
                    imports.append(Import(module=module, names=[], alias=None, line=i))

            match = re.match(from_pattern, line)
            if match:
                module = match.group(1)
                names = [n.strip() for n in match.group(2).split(",")]
                imports.append(Import(module=module, names=names, alias=None, line=i))

    except Exception as e:
        logger.error(f"Regex import extraction failed for {file_path}: {e}")

    return imports


def extract_functions(ast_tree: ast.AST) -> list[ast.FunctionDef]:
    """Walk AST to extract all function definitions.

    Args:
        ast_tree: Parsed AST tree from ast.parse()

    Returns:
        List of FunctionDef nodes
    """
    functions = []
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(node)
    return functions


def extract_classes(ast_tree: ast.AST) -> list[ast.ClassDef]:
    """Walk AST to extract all class definitions.

    Args:
        ast_tree: Parsed AST tree from ast.parse()

    Returns:
        List of ClassDef nodes
    """
    classes = []
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node)
    return classes


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a function or class node.

    Args:
        node: AST node (FunctionDef or ClassDef)

    Returns:
        Docstring text if present, otherwise None
    """
    return ast.get_docstring(node)


def _calculate_lines(node: ast.AST, source_lines: list[str]) -> int:
    """Calculate the number of lines spanned by an AST node.

    Args:
        node: AST node
        source_lines: List of source code lines

    Returns:
        Number of lines (end_lineno - lineno + 1)
    """
    if hasattr(node, "end_lineno") and node.end_lineno is not None:
        return node.end_lineno - node.lineno + 1
    # Fallback: estimate by looking for next function/class
    return 1


def _make_component_id(project_id: str, file_path: str, name: str) -> str:
    """Generate a unique component ID.

    Format: {project_id}:{file_path_hash}:{name}

    Args:
        project_id: Project identifier
        file_path: Relative path to the file
        name: Component name

    Returns:
        Unique component ID string
    """
    # Use short hash of file path to keep IDs manageable
    path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:12]
    return f"{project_id}:{path_hash}:{name}"


def extract_components(
    file_path: Path, project_id: str, project_root: Path | None = None
) -> list[Component]:
    """Parse Python file and return all components (functions, classes, module).

    Args:
        file_path: Path to the Python file to parse
        project_id: Project identifier for the component
        project_root: Optional project root for relative path calculation

    Returns:
        List of Component objects representing all extractable components

    Examples:
        >>> components = extract_components(Path("mymodule.py"), "my-project")
        >>> [c.name for c in components]
        ['MyClass', 'my_function', 'helper']
    """
    # Calculate relative path
    if project_root:
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)

    # Replace backslashes with forward slashes for consistency
    rel_path = rel_path.replace("\\", "/")

    # Empty file check
    try:
        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            logger.debug(f"Skipping empty file: {file_path}")
            return []
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return []

    # Parse AST
    try:
        tree = ast.parse(content, filename=str(file_path))
        source_lines = content.splitlines()
    except SyntaxError as e:
        logger.warning(f"Syntax error in {file_path}: {e}. Skipping AST extraction.")
        return []
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {e}")
        return []

    components = []

    # Extract imports
    imports = extract_imports(file_path)
    import_modules = [imp.module for imp in imports]

    # Extract functions
    functions = extract_functions(tree)
    for func in functions:
        component_id = _make_component_id(project_id, rel_path, func.name)
        lines = _calculate_lines(func, source_lines)

        components.append(
            Component(
                component_id=component_id,
                project_id=project_id,
                path=rel_path,
                name=func.name,
                component_type="function",
                lines=lines,
                line_start=func.lineno,
                line_end=getattr(func, "end_lineno", func.lineno),
                docstring=_get_docstring(func),
                imports=import_modules,
            )
        )

    # Extract classes
    classes = extract_classes(tree)
    for cls in classes:
        component_id = _make_component_id(project_id, rel_path, cls.name)
        lines = _calculate_lines(cls, source_lines)

        components.append(
            Component(
                component_id=component_id,
                project_id=project_id,
                path=rel_path,
                name=cls.name,
                component_type="class",
                lines=lines,
                line_start=cls.lineno,
                line_end=getattr(cls, "end_lineno", cls.lineno),
                docstring=_get_docstring(cls),
                imports=import_modules,
            )
        )

    return components


def save_to_db(components: list[Component], db_path: Path | None = None) -> bool:
    """Upsert components to the pi_components table and populate pi_dependencies.

    Args:
        components: List of Component objects to save
        db_path: Optional database path (defaults to studio.db)

    Returns:
        True if successful, False otherwise

    Notes:
        - Uses INSERT OR REPLACE to handle updates
        - Stores imports as JSON array
        - Sets last_analyzed to current timestamp
        - Extracts and saves dependencies to pi_dependencies table
    """
    if not components:
        logger.debug("No components to save")
        return True

    try:
        with _component_transaction(db_path) as conn:
            # First pass: save all components
            for comp in components:
                # Convert imports list to JSON
                imports_json = json.dumps(comp.imports) if comp.imports else None

                conn.execute(
                    """INSERT OR REPLACE INTO pi_components
                       (component_id, project_id, path, name, component_type,
                        lines, imports, last_analyzed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (
                        comp.component_id,
                        comp.project_id,
                        comp.path,
                        comp.name,
                        comp.component_type,
                        comp.lines,
                        imports_json,
                    ),
                )

            # Second pass: extract and save dependencies
            dependencies_saved = 0
            skipped_external = set()
            skipped_notfound = set()

            for comp in components:
                if not comp.imports:
                    continue

                # For each import, try to find matching component in the database
                for import_module in comp.imports:
                    # Skip external imports (standard library, third-party packages)
                    if _is_external_import(import_module):
                        skipped_external.add(import_module)
                        continue

                    # Find target component(s) that match this import
                    # Strategy: match by path pattern
                    # Example: import "lib.studio_db" -> path should match "lib/studio_db.py"
                    module_path = import_module.replace(".", "/")

                    # Try multiple matching strategies:
                    # 1. Exact module path (e.g., "lib/studio_db.py")
                    # 2. Module as directory with __init__.py (e.g., "lib/__init__.py" for import "lib")
                    # Be more strict to avoid false positives like "lib" matching "analyze/lib"
                    target_components = conn.execute(
                        """SELECT DISTINCT component_id, path FROM pi_components
                           WHERE project_id = ?
                           AND component_id != ?
                           AND (
                               path = ? OR
                               path = ? OR
                               path LIKE ? OR
                               (path = ? AND ? NOT LIKE '%/%')
                           )""",
                        (
                            comp.project_id,
                            comp.component_id,
                            f"{module_path}.py",  # exact: lib/studio_db.py
                            f"{module_path}/__init__.py",  # package: lib/__init__.py
                            f"{module_path}/%.py",  # submodule: lib/studio_db/foo.py
                            f"{module_path}.py",  # for single-level imports
                            module_path,
                        ),  # avoid matching nested paths
                    ).fetchall()

                    if not target_components:
                        skipped_notfound.add(import_module)
                        continue

                    for target_id, target_path in target_components:
                        # Skip self-references (same file)
                        if target_path == comp.path:
                            continue

                        # Generate dependency ID
                        dep_id = _make_dependency_id(comp.component_id, target_id)

                        # Insert dependency
                        conn.execute(
                            """INSERT OR REPLACE INTO pi_dependencies
                               (dependency_id, project_id, from_component, to_component, dependency_type)
                               VALUES (?, ?, ?, ?, ?)""",
                            (dep_id, comp.project_id, comp.component_id, target_id, "import"),
                        )
                        dependencies_saved += 1

            # Log summary
            if skipped_external:
                logger.debug(
                    f"Skipped {len(skipped_external)} external imports: {list(skipped_external)[:5]}"
                )
            if skipped_notfound:
                logger.debug(
                    f"Could not resolve {len(skipped_notfound)} imports: {list(skipped_notfound)[:5]}"
                )

        logger.info(
            f"Saved {len(components)} components and {dependencies_saved} dependencies to database"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to save components/dependencies to database: {e}")
        return False


def _is_external_import(module: str) -> bool:
    """Check if an import is external (standard library or third-party).

    Args:
        module: Import module name (e.g., 'os', 'requests', 'core.event_store.studio_db')

    Returns:
        True if external, False if internal to the project

    Notes:
        - Standard library modules are considered external
        - Imports starting with project-specific prefixes are internal
    """
    # Common standard library modules
    stdlib_modules = {
        "os",
        "sys",
        "json",
        "re",
        "pathlib",
        "typing",
        "datetime",
        "time",
        "collections",
        "functools",
        "itertools",
        "logging",
        "argparse",
        "subprocess",
        "sqlite3",
        "hashlib",
        "ast",
        "dataclasses",
        "enum",
        "abc",
        "contextlib",
        "io",
        "unittest",
        "pytest",
        "__future__",
    }

    # Check if it's a standard library module or starts with one
    module_root = module.split(".")[0]
    if module_root in stdlib_modules:
        return True

    # Common third-party packages
    common_third_party = {
        "requests",
        "flask",
        "django",
        "numpy",
        "pandas",
        "matplotlib",
        "pytest",
        "click",
        "fastapi",
        "networkx",
        "pydantic",
        "anthropic",
    }
    if module_root in common_third_party:
        return True

    # If it starts with project-specific prefixes, it's internal
    internal_prefixes = ["hooks", "lib", "scripts", "skills"]
    if module_root in internal_prefixes:
        return False

    # Default to external for unknown modules
    return True


def _make_dependency_id(from_component: str, to_component: str) -> str:
    """Generate a unique dependency ID.

    Args:
        from_component: Source component ID
        to_component: Target component ID

    Returns:
        Unique dependency ID string
    """
    # Create deterministic ID from both component IDs
    combined = f"{from_component}:{to_component}"
    dep_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
    return f"dep:{dep_hash}"
