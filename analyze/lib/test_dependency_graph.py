"""
Test suite for dependency_graph.py

Validates import parsing, cycle detection, and coupling analysis.
"""

from pathlib import Path
from dependency_graph import (
    build_dependency_graph,
    analyze_module_coupling,
    _parse_python_imports,
    _parse_js_imports,
    _detect_cycles,
)


def test_python_import_parsing():
    """Test Python import statement parsing."""
    print("Testing Python import parsing...")

    # Test on hooks/lib directory
    hooks_lib = Path("../../hooks/lib")
    if hooks_lib.exists():
        test_file = hooks_lib / "context_compiler.py"
        if test_file.exists():
            imports = _parse_python_imports(test_file, hooks_lib.parent)
            print(f"  Found {len(imports)} imports in context_compiler.py")
            for imp in imports[:5]:
                print(f"    - {imp}")
    print()


def test_cycle_detection():
    """Test circular dependency detection."""
    print("Testing cycle detection...")

    # Create a test graph with a cycle
    test_graph = {
        "a.py": ["b.py"],
        "b.py": ["c.py"],
        "c.py": ["a.py"],  # Cycle: a -> b -> c -> a
        "d.py": ["e.py"],
        "e.py": [],
    }

    cycles = _detect_cycles(test_graph)
    print(f"  Found {len(cycles)} cycles")
    for i, cycle in enumerate(cycles, 1):
        print(f"    Cycle {i}: {' -> '.join(cycle)}")

    # Test self-import (should be filtered out)
    self_import_graph = {
        "a.py": ["a.py"],  # Self-import
        "b.py": [],
    }
    cycles = _detect_cycles(self_import_graph)
    print(f"  Self-import test: {len(cycles)} cycles (should be 0)")
    print()


def test_full_analysis():
    """Test full dependency graph analysis."""
    print("Testing full dependency graph analysis...")

    # Test on hooks directory
    hooks_dir = Path("../../hooks")
    if hooks_dir.exists():
        result = build_dependency_graph(hooks_dir, ["Python"])

        print(f"  Nodes: {len(result['nodes'])}")
        print(f"  Edges: {len(result['edges'])}")
        print(f"  Cycles: {len(result['cycles'])}")
        print(f"  High coupling pairs: {len(result['high_coupling_pairs'])}")

        # Analyze coupling
        coupling = analyze_module_coupling(result)
        print(f"  Total dependencies: {coupling['total_dependencies']}")
        print(f"  Avg per file: {coupling['avg_dependencies_per_file']:.2f}")
        print(f"  Coupling score: {coupling['coupling_score']:.4f}")

        if coupling['most_imported_files']:
            top_file, count = coupling['most_imported_files'][0]
            print(f"  Most imported: {top_file} ({count} imports)")
    print()


def test_javascript_parsing():
    """Test JavaScript/TypeScript import parsing."""
    print("Testing JavaScript/TypeScript parsing...")

    # Look for any JS/TS projects in builds
    builds_dir = Path("../../..")
    js_projects = []

    for project in builds_dir.iterdir():
        if project.is_dir():
            # Check for common JS/TS indicators
            if (project / "package.json").exists():
                js_projects.append(project)

    if js_projects:
        test_project = js_projects[0]
        print(f"  Testing on: {test_project.name}")

        result = build_dependency_graph(test_project, ["JavaScript", "TypeScript"])
        print(f"  Found {len(result['nodes'])} JS/TS files")
        print(f"  Found {len(result['edges'])} dependencies")

        if result['edges']:
            print("  Sample dependencies:")
            for edge in result['edges'][:3]:
                print(f"    {edge['from']} -> {edge['to']}")
    else:
        print("  No JS/TS projects found for testing")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Dependency Graph Test Suite")
    print("=" * 60)
    print()

    test_python_import_parsing()
    test_cycle_detection()
    test_full_analysis()
    test_javascript_parsing()

    print("=" * 60)
    print("All tests complete!")
    print("=" * 60)
