# Dependency Graph Analysis

## Overview

`dependency_graph.py` builds directed graphs from source code imports, detects circular dependencies, and measures coupling strength between files.

## Features

### 1. Multi-Language Import Parsing
- **Python**: `import X`, `from X import Y`
- **JavaScript/TypeScript**: `import X from 'Y'`, `require('Y')`
- Uses regex patterns (no full AST required for MVP)

### 2. Dependency Graph Construction
- **Nodes**: File paths (relative to project root)
- **Edges**: Import relationships with weights (count of imports)
- **Directed graph**: A → B means A imports B

### 3. Circular Dependency Detection
- DFS-based cycle detection
- Filters out self-imports (file importing itself)
- Returns complete cycle paths (A → B → C → A)

### 4. Coupling Analysis
- **Coupling strength**: Count of imports between file pairs
- **High coupling**: Flags pairs with >5 imports
- **Coupling score**: 0-1 normalized score (0=loose, 1=tight)
- **Central modules**: Most imported files
- **High fan-out**: Files that import many others

## Usage

```python
from pathlib import Path
from analyze.lib.dependency_graph import build_dependency_graph, analyze_module_coupling

# Build dependency graph
path = Path("path/to/project")
languages = ["Python", "JavaScript", "TypeScript"]
result = build_dependency_graph(path, languages)

# Result structure
{
    "nodes": [...],  # List of file paths
    "edges": [{"from": "a.py", "to": "b.py", "count": 3}, ...],
    "cycles": [["a.py", "b.py", "c.py", "a.py"], ...],
    "coupling": {("a.py", "b.py"): 3, ...},
    "high_coupling_pairs": [("x.py", "y.py", 8), ...]
}

# Analyze coupling strength
coupling = analyze_module_coupling(result)
print(f"Total dependencies: {coupling['total_dependencies']}")
print(f"Coupling score: {coupling['coupling_score']:.4f}")
print(f"Most imported: {coupling['most_imported_files'][0]}")
```

## Example Output

```
DEPENDENCY GRAPH ANALYSIS
Files analyzed: 40
Dependencies mapped: 37
Coupling score: 0.0237 (0=loose, 1=tight)
Circular dependencies: 0 detected

Central Modules (most imported):
  1. lib\__init__.py: 10 imports
  2. lib\studio_db.py: 7 imports
  3. lib\workflow_validate.py: 3 imports

High Fan-Out Modules:
  1. lib\workflow_state.py: 7 dependencies
  2. lib\workflow_engine.py: 5 dependencies
```

## Implementation Details

### Import Resolution

**Python:**
- Converts `module.submodule` → `module/submodule.py`
- Checks both absolute and relative paths
- Handles `__init__.py` for packages

**JavaScript/TypeScript:**
- Only processes relative imports (`./file`, `../file`)
- Skips `node_modules` dependencies
- Tries multiple extensions (.js, .ts, .tsx, .jsx)
- Handles `index.js` barrel files

### Files Skipped
- Test files: `test_*.py`, `*.test.js`, `*.spec.ts`
- Generated code: `dist/`, `build/`, `.next/`
- Dependencies: `node_modules/`, `venv/`, `__pycache__/`
- Migrations: `migrations/`

### Cycle Detection Algorithm
1. Depth-first search with recursion stack
2. Detects back edges (neighbor in recursion stack)
3. Extracts cycle path from DFS path
4. Deduplicates equivalent cycles
5. Filters self-imports (single-node cycles)

### Coupling Metrics

**Coupling Score Formula:**
```
coupling_score = total_imports / max_possible_edges
max_possible_edges = n * (n - 1)  # Complete directed graph
```

**Interpretation:**
- 0.00-0.05: Loose coupling (healthy)
- 0.05-0.15: Moderate coupling
- 0.15-0.30: Tight coupling (consider refactoring)
- 0.30+: Very tight coupling (high risk)

## Testing

Run test suite:
```bash
cd analyze/lib
python test_dependency_graph.py
```

Tests cover:
- Python import parsing
- JavaScript/TypeScript parsing
- Cycle detection (including self-import filtering)
- Coupling analysis
- Multi-language support

## Future Enhancements

1. **Full AST parsing** for more accurate import resolution
2. **Transitive dependencies** (A → B → C implies A depends on C)
3. **Dependency layers** (categorize by architectural layer)
4. **Import impact analysis** (what breaks if file X is removed)
5. **Visualization** (GraphViz/D3.js rendering)
6. **Historical trends** (coupling score over time)
