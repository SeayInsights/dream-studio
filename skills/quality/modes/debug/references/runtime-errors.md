---
title: Runtime Errors
description: Debugging execution-time errors, exceptions, and stack traces
---

# Runtime Errors

Reference for diagnosing and fixing runtime errors.


## Dependencies

**When this occurs:**
- Import statements fail with `ModuleNotFoundError`
- Code runs but crashes with missing attribute/method errors
- Version conflicts cause unexpected behavior
- Package installed but not found by runtime

**How to trace:**

1. **Verify installation environment**
   ```powershell
   # Check which Python is running
   Get-Command python, py | Select-Object Source
   
   # List installed packages in active environment
   py -m pip list
   ```

2. **Check import path resolution**
   - Use `Read` to examine the failing import line
   - Use `Grep` to find where the module is defined in the codebase
   - Pattern: `grep -r "from <module>" --type py` to see all import variations

3. **Trace dependency chain**
   - Read `requirements.txt`, `pyproject.toml`, or `package.json`
   - Check for version pinning conflicts (e.g., `pkg>=1.0,<2.0` vs transitive dep requiring `pkg>=2.0`)
   - Use `py -m pip show <package>` to see installed version and dependencies

4. **Verify package contents**
   ```powershell
   # Find where package is installed
   py -c "import <module>; print(<module>.__file__)"
   
   # List package contents
   Get-ChildItem (Split-Path (py -c "import <module>; print(<module>.__file__)"))
   ```

**Common patterns:**
- **Virtual environment not activated** - check `$env:VIRTUAL_ENV` is set
- **Multiple Python versions** - `py` launcher picks wrong version
- **Dev dependencies missing** - installed package but not dev extras (`pip install -e .[dev]`)
- **Cached imports** - old `.pyc` files; delete `__pycache__` directories

**Anti-patterns:**
- Assuming `python` points to the right interpreter without verifying
- Installing packages globally instead of in project venv
- Not checking `pip list` before assuming a package is missing

**Tool recommendations:**
- `Bash` or `PowerShell` for environment inspection
- `Read` for lockfiles/dependency manifests
- `Grep` with `--type py` to trace import usage patterns


## Types

**When this occurs:**
- `TypeError: 'NoneType' object is not callable/subscriptable`
- `AttributeError: 'X' object has no attribute 'Y'`
- Type checker passes but runtime fails
- Duck typing assumptions break

**How to trace:**

1. **Identify the failing line**
   - Read the stack trace bottom-to-top
   - Use `Read` to view the exact line with context (`-B 5 -A 5`)
   - Note the variable name and operation that failed

2. **Trace variable origin**
   ```bash
   # Find all assignments to the variable
   grep -n "variable_name\s*=" file.py
   
   # Find function return statements if variable is from a call
   grep -B 10 "def function_name" file.py | grep "return"
   ```

3. **Check type annotations and defaults**
   - Use `Read` to examine function signature
   - Look for `Optional[T]`, `T | None`, or missing type hints
   - Trace all code paths that could return `None`

4. **Inspect runtime state**
   - Add temporary `print(f"{var=}, {type(var)=}")` statements
   - Use LSP "Go to Definition" to understand expected type
   - Check if variable is conditionally assigned (may be unbound in some paths)

5. **Trace attribute access**
   ```bash
   # Find class definition
   grep -n "class ClassName" --type py
   
   # Find all method/attribute definitions
   grep -n "def method_name\|self.attr_name =" file.py
   ```

**Common patterns:**
- **Unguarded None returns** - function returns `None` on error path without documenting
- **Dictionary .get() without default** - `config.get("key")` returns `None`, then `.attribute` fails
- **Conditional assignment** - variable only assigned in `if` branch, accessed in both
- **API changes** - dependency updated, removed/renamed attributes

**Anti-patterns:**
- Searching for the attribute name globally without checking the object type first
- Assuming type hints are enforced at runtime (they're not in Python)
- Not checking if a function explicitly returns `None` vs missing `return` statement

**Tool recommendations:**
- `Grep` with `-B/-A` context to trace data flow
- `Read` with line range to see surrounding logic
- `LSP` (load via ToolSearch) for type-aware navigation
- `Bash` to add print debugging and re-run


## Imports

**When this occurs:**
- `ImportError: cannot import name 'X' from 'Y'`
- `ModuleNotFoundError: No module named 'X'`
- Code works in REPL but fails when run as script
- Circular import errors

**How to trace:**

1. **Map the import structure**
   ```bash
   # Find all imports of the problematic module
   grep -n "from module import\|import module" --type py
   
   # Find the module's own imports
   read path/to/module.py | grep "^import\|^from"
   ```

2. **Check file structure vs import paths**
   - Use `Glob` to verify file exists: `**/*module_name*.py`
   - Verify `__init__.py` exists in package directories
   - Check if import uses absolute vs relative paths

3. **Trace circular dependencies**
   ```bash
   # Build import graph manually
   # For each file in the cycle, list its imports
   grep "^from \|^import " file1.py
   grep "^from \|^import " file2.py
   
   # Look for A imports B, B imports A patterns
   ```

4. **Check import timing**
   - Module-level imports run when module loads
   - Use `Read` to see if import is at top-level vs inside function
   - Trace if imported name is defined before or after import statement in target module

5. **Verify package structure**
   ```bash
   # List directory structure
   ls -R package_name/
   
   # Check for __init__.py at each level
   find package_name/ -name "__init__.py"
   ```

**Common patterns:**
- **Circular imports** - A imports B at module level, B imports A at module level
- **Missing __init__.py** - directory exists but Python doesn't recognize it as package
- **Relative import depth mismatch** - `from ..module import X` but script run from wrong directory
- **Star imports hiding issues** - `from module import *` imports name that doesn't exist yet

**Anti-patterns:**
- Trying to fix circular imports by moving imports without understanding the dependency cycle
- Adding `.` to `sys.path` instead of fixing package structure
- Using relative imports in scripts meant to be run directly (use absolute imports)

**Tool recommendations:**
- `Grep` with pattern `^from |^import ` to map all imports
- `Glob` to verify file structure matches import paths
- `Read` to check `__init__.py` contents and export lists
- `Bash` with `find` to verify package structure

**Progressive disclosure:**
- For circular import resolution strategies, see `references/circular-imports.md` (future)
- For package structure patterns, see `references/package-structure.md` (future)
- For import performance debugging, see `references/import-profiling.md` (future)
