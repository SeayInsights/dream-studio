---
title: Tool Selection
description: Choosing the right debugging tools and techniques for different problem types
---

# Tool Selection Guide

Decision table for choosing the right tool during debugging workflows.

## Quick Reference

| Scenario | Use | Why | Avoid |
|----------|-----|-----|-------|
| Find where error message appears | Grep | Search across all files for exact string | Read (too narrow) |
| Find all files importing a module | Grep | Pattern search across codebase | LSP (overkill for simple import) |
| Understand function implementation | Read | See full context with line numbers | Grep (fragmented results) |
| Check current file state | Read | Get authoritative content | Bash cat (wrong tool) |
| Find all references to a symbol | LSP | Semantic understanding of code | Grep (misses dynamic references) |
| Jump to definition | LSP | Follows language semantics | Grep (finds strings, not definitions) |
| Find type hierarchy | LSP | Understands inheritance/interfaces | Grep (no semantic awareness) |
| Check git history for file | Bash git log | Version control query | Read (only shows current) |
| See what changed in commit | Bash git show | Diff inspection | Grep (not version-aware) |
| List files matching pattern | Glob | Fast pattern matching | Bash find (slower, wrong tool) |
| Search in specific file types | Grep with type filter | Scoped search | Glob then Read (inefficient) |
| Check if file exists | Bash test -f | Direct filesystem check | Read (errors on missing) |
| Read large file sections | Read with offset/limit | Pagination support | Bash cat (no pagination) |
| Find TODO comments | Grep | Simple text search | LSP (unnecessary) |
| Trace function call chain | LSP + Read | Definitions + context | Grep alone (misses semantics) |

## Detailed Scenarios

### Grep - Content Search

**Use when:**
- Searching for error messages across codebase
- Finding all TODO/FIXME comments
- Locating config values or constants
- Finding all files that import/use something
- Pattern matching across multiple files

**Parameters:**
```bash
# Basic search
pattern: "error message text"
output_mode: "files_with_matches"  # Start broad

# Then drill down
output_mode: "content"
context: 3  # Show surrounding lines

# Scoped search
type: "js"  # or "ts", "py", etc.
glob: "src/**/*.tsx"  # Specific paths
```

**Anti-patterns:**
- ❌ Using Grep to read entire files (use Read)
- ❌ Grep for symbol definitions (use LSP)
- ❌ Searching without output_mode (defaults to files_with_matches)
- ❌ Using -i when you know exact casing (slower)

### Read - File Inspection

**Use when:**
- Reading specific files you already know about
- Examining full file structure
- Checking current implementation
- Reading config/manifest files
- Following up on Grep results

**Parameters:**
```bash
# Full file
file_path: "/absolute/path/to/file.ts"

# Large files - use pagination
offset: 100  # Start at line 100
limit: 50    # Read 50 lines

# PDFs
pages: "1-5"  # Specific page range
```

**Anti-patterns:**
- ❌ Reading without knowing file path (use Grep/Glob first)
- ❌ Reading entire large files (use offset/limit)
- ❌ Using Bash cat instead of Read (wrong tool)
- ❌ Reading multiple files sequentially (use Grep for search)

### LSP - Semantic Code Intelligence

**Load first:**
```bash
ToolSearch(query="select:LSP")
```

**Use when:**
- Finding all references to a function/class
- Jumping to symbol definitions
- Exploring type hierarchies
- Understanding call graphs
- Refactoring needs

**Common operations:**
```bash
# Find definition
LSP(action: "definition", symbol: "functionName")

# Find all references
LSP(action: "references", symbol: "className")

# Get type information
LSP(action: "hover", symbol: "variable")

# List symbols in file
LSP(action: "documentSymbol", file: "/path/to/file.ts")
```

**Anti-patterns:**
- ❌ Using LSP for simple string searches (use Grep)
- ❌ LSP on non-code files (use Grep/Read)
- ❌ Calling LSP before ToolSearch (will fail)
- ❌ LSP for TODO comments (use Grep)

### Bash - System Operations

**Use when:**
- Git operations (log, diff, blame, show)
- File system checks (test -f, test -d)
- Process inspection (ps, lsof)
- Build commands (npm, cargo, etc.)
- Environment queries

**Common patterns:**
```bash
# Git history
git log --oneline -10
git blame path/to/file.ts
git show commit-hash

# File checks
test -f /path/to/file && echo "exists"
ls -la /path/to/dir

# Process checks
lsof -i :3000  # Check port usage
ps aux | grep node
```

**Anti-patterns:**
- ❌ Using find instead of Glob (slower)
- ❌ Using grep/cat instead of Grep/Read (wrong tool)
- ❌ Complex text processing in shell (use proper tools)

### Glob - File Pattern Matching

**Use when:**
- Finding files by name pattern
- Listing all files of certain type
- Checking if files exist before reading
- Building file lists for iteration

**Patterns:**
```bash
# All TypeScript files
pattern: "**/*.ts"

# Specific directory
pattern: "src/components/**/*.tsx"
path: "/absolute/path/to/search"

# Multiple extensions
pattern: "**/*.{ts,tsx,js,jsx}"
```

**Anti-patterns:**
- ❌ Using Glob to search file contents (use Grep)
- ❌ Bash find/ls instead of Glob (slower)
- ❌ Glob immediately after Write (file may not be visible yet)

## Workflow Patterns

### Pattern: Error Message Investigation

```
1. Grep for error text (output_mode: files_with_matches)
   → Get list of files
2. Grep with context (output_mode: content, context: 5)
   → See surrounding code
3. Read specific files
   → Understand full implementation
4. LSP to find related code
   → Trace call chain
```

### Pattern: Function Behavior Analysis

```
1. LSP definition
   → Find where function is defined
2. Read definition file
   → Understand implementation
3. LSP references
   → See all call sites
4. Read caller files
   → Understand usage patterns
```

### Pattern: Config/Setup Issues

```
1. Glob for config files (*.json, *.config.*)
   → Find relevant configs
2. Read config files
   → Check current values
3. Bash git log -- path/to/config
   → See recent changes
4. Bash git show commit-hash
   → Review what changed
```

### Pattern: Import/Dependency Issues

```
1. Read the file with error
   → See exact import statement
2. Grep for export of symbol
   → Find where it's exported
3. Read export file
   → Verify export exists
4. LSP definition (if needed)
   → Confirm semantic link
```

## Decision Tree

```
Need to find something?
├─ Know exact file? → Read
├─ Search by content? → Grep
├─ Search by filename? → Glob
└─ Semantic code search? → LSP

Need file history?
├─ When changed? → git log
├─ Who changed? → git blame
└─ What changed? → git show

Need to verify?
├─ File exists? → test -f
├─ Port in use? → lsof -i
└─ Process running? → ps aux

Reading files?
├─ <100 lines? → Read (full)
├─ >100 lines? → Read (offset/limit)
├─ PDF? → Read (pages parameter)
└─ Multiple files? → Grep first, then Read
```

## Performance Considerations

### Fast Operations
- Glob for file patterns (instant)
- Grep with type filter (fast, scoped)
- Read with offset/limit (paginated)
- test -f for existence checks

### Slower Operations
- Grep without type/glob filter (searches everything)
- Read entire large files (context waste)
- LSP on first load (needs initialization)
- Bash find (use Glob instead)

### Context Management
- Grep files_with_matches first (small output)
- Then Grep content on specific files (targeted)
- Read only what you need (use offset/limit)
- LSP after you know what to search (focused queries)

## Common Mistakes

### ❌ Wrong Tool
```bash
# Don't use Bash for content search
Bash("grep 'pattern' file.ts")  # Use Grep tool

# Don't use Read for search
Read("file1.ts")  # Then search in results
Read("file2.ts")  # Use Grep instead
```

### ❌ Too Broad
```bash
# Don't search everything
Grep(pattern: "config")  # Too many results

# Do scope it
Grep(pattern: "config", type: "json")
Grep(pattern: "config", glob: "src/**")
```

### ❌ Too Narrow
```bash
# Don't read blindly
Read("/src/utils/helper.ts")  # Might be wrong file

# Do search first
Grep(pattern: "helperFunction", output_mode: "files_with_matches")
```

### ❌ Wrong Order
```bash
# Don't read before finding
Read(file) → Search in output  # Inefficient

# Do search before reading
Grep(pattern) → Read(specific_files)  # Efficient
```

## Integration with Debug Workflow

### Phase 1: Reproduce
- **Bash**: Run application, trigger error
- **Read**: Check error logs if saved
- **Grep**: Find error message in code

### Phase 2: Locate
- **Grep**: Find all files with error/function
- **LSP**: Get definition of failing function
- **Read**: Examine implementation

### Phase 3: Analyze
- **Read**: Study code logic with context
- **LSP**: Trace call chain
- **Bash git**: Check recent changes

### Phase 4: Hypothesize
- **Read**: Verify assumptions in code
- **Grep**: Check for similar patterns
- **LSP**: Understand type flow

### Phase 5: Test
- **Bash**: Run tests/reproduction
- **Read**: Check test files
- **Grep**: Find related test cases

### Phase 6: Fix
- **Edit**: Apply fix
- **Bash**: Run verification
- **Read**: Confirm changes

## Tool Combination Strategies

### Serial: Narrow Down
```
Grep (broad) → Grep (focused) → Read (specific) → LSP (semantic)
```

### Parallel: Multi-Angle
```
Grep for error + LSP for symbol + Bash git log
→ Combine insights
```

### Iterative: Deep Dive
```
Read file → Find symbol → LSP definition → Read new file → Repeat
```

### Verification: Cross-Check
```
Grep for all occurrences + LSP references
→ Ensure complete coverage
```
