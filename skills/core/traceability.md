# Traceability Management — Core Module

Reusable traceability patterns for linking requirements → tasks → commits → tests via TR-IDs.

## Usage

When a skill needs traceability operations, reference this module:
```
## Imports
- core/traceability.md — traceability management
```

## Patterns

### Check if traceability is active
```bash
test -f .planning/traceability.yaml && echo "ACTIVE" || echo "INACTIVE"
```

**Rule:** Only perform traceability operations if the file exists. Never create it from build/verify skills.

### Validate traceability file
```bash
py "../../hooks/lib/traceability.py" validate .planning/traceability.yaml
```

Always validate BEFORE modifying the file. If validation fails, warn and skip updates — don't corrupt a broken file.

### Update TR-ID with commit
After creating a commit for a task:

1. Check if traceability is active
2. Validate the file
3. Append commit SHA to the `commits` list for each TR-ID this task implements
4. Update requirement status:
   - `planned` → `in_progress` (first commit)
   - `in_progress` → `implemented` (task complete)
5. Re-validate after editing

**Example flow:**
```bash
if [ -f .planning/traceability.yaml ]; then
  # Validate first
  py "../../hooks/lib/traceability.py" validate .planning/traceability.yaml
  
  if [ $? -eq 0 ]; then
    # Edit: append commit SHA to TR-001's commits list
    # Edit: update TR-001 status to in_progress or implemented
    
    # Re-validate
    py "../../hooks/lib/traceability.py" validate .planning/traceability.yaml
  else
    echo "⚠️ Traceability file invalid, skipping update"
  fi
fi
```

### Update TR-ID with test
After creating tests for a verified requirement:

1. Check if traceability is active
2. Validate the file
3. Append test file paths to the `tests` list for each verified TR-ID
4. Update requirement status to `verified` if tests pass
5. Update summary counts
6. Re-validate after editing

### When to skip traceability operations

**Always skip if:**
- `.planning/traceability.yaml` doesn't exist
- Validation fails (file is corrupt)
- User explicitly disabled traceability for this plan

**Never:**
- Create traceability.yaml from build/verify skills (only plan skill creates it)
- Modify a file that failed validation
- Assume traceability is active without checking

## Traceability file structure

```yaml
version: 1.0
project: <name>
plan: <path-to-plan.md>

requirements:
  TR-001:
    description: User can log in with email/password
    priority: must
    status: planned  # planned | in_progress | implemented | verified
    tasks: [1, 2]
    commits: []      # Populated by build skill
    tests: []        # Populated by verify skill
  
  TR-002:
    description: Session persists for 24 hours
    priority: should
    status: planned
    tasks: [3]
    commits: []
    tests: []

summary:
  total: 2
  must: 1
  should: 1
  could: 0
  planned: 2
  in_progress: 0
  implemented: 0
  verified: 0
```

## Status lifecycle

```
planned → in_progress → implemented → verified
```

- **planned:** Requirement identified, tasks created
- **in_progress:** First commit made
- **implemented:** All tasks complete, code merged
- **verified:** Tests exist and pass

## Coverage reporting

When traceability is active, report coverage:
```
Traceability: 5 of 8 requirements verified (62.5%)
- TR-001 ✅ verified
- TR-002 ✅ verified
- TR-003 ✅ verified
- TR-004 ✅ verified
- TR-005 ✅ verified
- TR-006 ❌ implemented (needs tests)
- TR-007 ❌ in_progress
- TR-008 ❌ planned
```

## Used by
plan (creates), build (updates commits), verify (updates tests)
