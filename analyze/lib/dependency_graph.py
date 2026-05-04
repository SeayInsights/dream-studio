"""
Dependency graph analysis for project-intelligence platform.

Builds directed graphs from source code imports, detects circular dependencies,
and measures coupling strength between files.
"""

from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
import re
from collections import defaultdict


def build_dependency_graph(path: Path, languages: List[str]) -> Dict[str, Any]:
    """
    Build dependency graph from source files.

    Analyzes import statements to construct a directed graph of file dependencies,
    detect circular dependencies, and calculate coupling strength between files.

    Args:
        path: Project root directory to analyze
        languages: Languages to analyze (e.g., ['Python', 'JavaScript', 'TypeScript'])

    Returns:
        {
            "nodes": List[str],  # file paths relative to root
            "edges": List[Dict],  # {from, to, count} import relationships
            "cycles": List[List[str]],  # circular dependency chains
            "coupling": Dict[Tuple[str, str], int],  # file pair → import count
            "high_coupling_pairs": List[Tuple[str, str, int]]  # pairs with >5 imports
        }
    """
    graph = defaultdict(list)
    coupling = defaultdict(int)
    nodes = set()

    # Parse Python files
    if any(lang.lower() in ['python', 'py'] for lang in languages):
        python_files = list(path.rglob("*.py"))
        for py_file in python_files:
            if _should_skip(py_file):
                continue
            imports = _parse_python_imports(py_file, path)
            rel_path = str(py_file.relative_to(path))
            nodes.add(rel_path)
            for imported_file in imports:
                graph[rel_path].append(imported_file)
                coupling[(rel_path, imported_file)] += 1
                nodes.add(imported_file)

    # Parse JavaScript/TypeScript files
    if any(lang.lower() in ['javascript', 'typescript', 'js', 'ts'] for lang in languages):
        js_extensions = ["*.js", "*.ts", "*.tsx", "*.jsx"]
        js_files = []
        for ext in js_extensions:
            js_files.extend(path.rglob(ext))

        for js_file in js_files:
            if _should_skip(js_file):
                continue
            imports = _parse_js_imports(js_file, path)
            rel_path = str(js_file.relative_to(path))
            nodes.add(rel_path)
            for imported_file in imports:
                graph[rel_path].append(imported_file)
                coupling[(rel_path, imported_file)] += 1
                nodes.add(imported_file)

    # Build edges list with import counts
    edges = []
    for from_file, to_files in graph.items():
        import_counts = defaultdict(int)
        for to_file in to_files:
            import_counts[to_file] += 1
        for to_file, count in import_counts.items():
            edges.append({"from": from_file, "to": to_file, "count": count})

    # Detect circular dependencies
    cycles = _detect_cycles(graph)

    # Find high coupling pairs (>5 imports between two files)
    high_coupling = [(f1, f2, count) for (f1, f2), count in coupling.items() if count > 5]
    high_coupling.sort(key=lambda x: x[2], reverse=True)

    return {
        "nodes": sorted(nodes),
        "edges": edges,
        "cycles": cycles,
        "coupling": dict(coupling),
        "high_coupling_pairs": high_coupling
    }


def _should_skip(file_path: Path) -> bool:
    """
    Determine if a file should be skipped during analysis.

    Skips test files, generated code, migrations, and dependency directories.

    Args:
        file_path: Path to check

    Returns:
        True if file should be skipped, False otherwise
    """
    skip_patterns = [
        "test_", "_test.py", ".test.", ".spec.",
        "node_modules", "__pycache__", ".next", "dist/", "build/",
        "migrations/", ".git/", "venv/", ".venv/"
    ]
    path_str = str(file_path)
    return any(pattern in path_str for pattern in skip_patterns)


def _parse_python_imports(file_path: Path, root: Path) -> List[str]:
    """
    Parse Python import statements and resolve to file paths.

    Handles both 'import X' and 'from X import Y' statements.

    Args:
        file_path: Python file to parse
        root: Project root for resolving relative paths

    Returns:
        List of imported file paths (relative to root)
    """
    imports = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Match: import X, from X import Y
        import_patterns = [
            r'^import\s+([a-zA-Z0-9_.]+)',
            r'^from\s+([a-zA-Z0-9_.]+)\s+import',
        ]

        for line in content.splitlines():
            line = line.strip()
            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module = match.group(1)
                    # Try to resolve to file path
                    resolved = _resolve_python_import(module, file_path, root)
                    if resolved:
                        imports.append(resolved)
    except Exception:
        # Ignore files that can't be read
        pass

    return imports


def _resolve_python_import(module: str, from_file: Path, root: Path) -> str | None:
    """
    Resolve Python module name to file path.

    Converts dotted module names (e.g., 'foo.bar') to file paths and checks
    if they exist in the project.

    Args:
        module: Module name (e.g., 'foo.bar.baz')
        from_file: File containing the import statement
        root: Project root directory

    Returns:
        Relative file path if resolved, None otherwise
    """
    # Convert module.submodule to module/submodule.py
    module_path = module.replace(".", "/")

    # Try different locations
    candidates = [
        root / f"{module_path}.py",
        root / module_path / "__init__.py",
        from_file.parent / f"{module_path}.py",
        from_file.parent / module_path / "__init__.py",
    ]

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_relative_to(root):
                return str(candidate.relative_to(root))
        except ValueError:
            # Not relative to root
            continue

    return None


def _parse_js_imports(file_path: Path, root: Path) -> List[str]:
    """
    Parse JavaScript/TypeScript import statements.

    Handles ES6 imports and CommonJS require() statements.
    Only resolves local/relative imports (not node_modules).

    Args:
        file_path: JS/TS file to parse
        root: Project root for resolving relative paths

    Returns:
        List of imported file paths (relative to root)
    """
    imports = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Match: import X from 'path', require('path')
        import_patterns = [
            r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
            r'require\(["\']([^"\']+)["\']\)',
        ]

        for line in content.splitlines():
            for pattern in import_patterns:
                matches = re.findall(pattern, line)
                for module in matches:
                    # Skip node_modules (only process relative imports)
                    if not module.startswith('.'):
                        continue
                    resolved = _resolve_js_import(module, file_path, root)
                    if resolved:
                        imports.append(resolved)
    except Exception:
        # Ignore files that can't be read
        pass

    return imports


def _resolve_js_import(module: str, from_file: Path, root: Path) -> str | None:
    """
    Resolve JavaScript/TypeScript import path to file.

    Handles relative imports (./file, ../file) and tries common extensions.

    Args:
        module: Import path (e.g., './utils/helper')
        from_file: File containing the import statement
        root: Project root directory

    Returns:
        Relative file path if resolved, None otherwise
    """
    # Handle relative imports: ./file, ../file
    if module.startswith('./') or module.startswith('../'):
        base_dir = from_file.parent
        try:
            target = (base_dir / module).resolve()
        except Exception:
            return None

        # Try with and without extensions
        candidates = [
            target,
            target.with_suffix('.js'),
            target.with_suffix('.ts'),
            target.with_suffix('.tsx'),
            target.with_suffix('.jsx'),
            target / "index.js",
            target / "index.ts",
            target / "index.tsx",
        ]

        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_relative_to(root):
                    return str(candidate.relative_to(root))
            except ValueError:
                # Not relative to root
                continue

    return None


def _detect_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    """
    Detect circular dependencies using depth-first search.

    Finds all cycles in the dependency graph where A → B → C → A.
    Filters out self-imports (file importing itself).

    Args:
        graph: Adjacency list representation {file: [imported_files]}

    Returns:
        List of cycles, where each cycle is a list of file paths forming a loop
    """
    cycles = []
    visited = set()
    rec_stack = set()
    path = []

    def dfs(node: str) -> None:
        """Depth-first search to detect cycles."""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                # Found cycle
                try:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]

                    # Filter out self-imports (single node cycles)
                    if len(cycle) <= 2:
                        continue

                    # Deduplicate cycles (same cycle, different starting point)
                    cycle_normalized = tuple(sorted(cycle))
                    if cycle_normalized not in [tuple(sorted(c)) for c in cycles]:
                        cycles.append(cycle)
                except ValueError:
                    # Node not in path (shouldn't happen, but defensive)
                    pass

        path.pop()
        rec_stack.remove(node)

    # Run DFS from each unvisited node
    for node in graph:
        if node not in visited:
            dfs(node)

    return cycles


def analyze_module_coupling(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze coupling strength and provide architectural insights.

    Args:
        graph_data: Output from build_dependency_graph()

    Returns:
        {
            "total_dependencies": int,
            "avg_dependencies_per_file": float,
            "most_imported_files": List[Tuple[str, int]],  # (file, import_count)
            "most_dependent_files": List[Tuple[str, int]],  # (file, outgoing_count)
            "coupling_score": float  # 0-1, higher = more coupled
        }
    """
    edges = graph_data["edges"]
    nodes = graph_data["nodes"]

    if not nodes:
        return {
            "total_dependencies": 0,
            "avg_dependencies_per_file": 0.0,
            "most_imported_files": [],
            "most_dependent_files": [],
            "coupling_score": 0.0
        }

    # Count incoming edges (how many files import this file)
    incoming = defaultdict(int)
    for edge in edges:
        incoming[edge["to"]] += edge["count"]

    # Count outgoing edges (how many files this file imports)
    outgoing = defaultdict(int)
    for edge in edges:
        outgoing[edge["from"]] += edge["count"]

    # Most imported files
    most_imported = sorted(incoming.items(), key=lambda x: x[1], reverse=True)[:10]

    # Most dependent files (import the most)
    most_dependent = sorted(outgoing.items(), key=lambda x: x[1], reverse=True)[:10]

    # Calculate coupling score (0-1)
    total_deps = sum(edge["count"] for edge in edges)
    max_possible = len(nodes) * (len(nodes) - 1)  # Complete graph
    coupling_score = total_deps / max_possible if max_possible > 0 else 0.0

    return {
        "total_dependencies": total_deps,
        "avg_dependencies_per_file": total_deps / len(nodes),
        "most_imported_files": most_imported,
        "most_dependent_files": most_dependent,
        "coupling_score": min(coupling_score, 1.0)
    }
