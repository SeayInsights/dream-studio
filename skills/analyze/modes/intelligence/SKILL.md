---
ds:
  pack: analyze
  mode: intelligence
  mode_type: analysis
  inputs: [project_path, analysis_options, stack_context]
  outputs: [prd_document, health_score, violations, bugs, improvements]
  capabilities_required: [Read, Grep, Bash, Write]
  model_preference: sonnet
  estimated_duration: 15-45min
name: intelligence
description: Comprehensive project intelligence analysis with stack detection, PRD generation, and health scoring
triggers: ["analyze project:", "project intelligence:", "scan codebase:"]
model_tier: sonnet
---

# Analyze — Project Intelligence

## Before you start
Read `gotchas.yml` in this directory if it exists.

## Trigger
`analyze project: <path>`, `project intelligence: <path>`, `scan codebase: <path>`

## Purpose
Auto-detect stack, generate PRD, identify violations/bugs, provide 0-10 health scoring. Includes stack detection, architecture analysis, bug patterns, and actionable improvement suggestions.

## When to use
New project analysis | ongoing health monitoring | pre-ship quality gate

## Workflow

### 1. Validate path & check engine
Extract path (default: `.`), verify it exists. Import `analyze.engine.analyze_project` (fail if missing).

### 2. Determine mode
**Full** (default) | **Quick** (`--quick` → targeted) | **Incremental** (`--incremental`, requires git)

### 3. Run & display
```python
result = analyze_project(path=Path("<path>"), run_type="full")  # or "targeted", "incremental"
```
Display: health score + interpretation, stack, findings, PRD path, dashboard link.  
See `reference/output-format.md` for template.

## Flags
- `--quick` - Skip research (maps to run_type="targeted")
- `--incremental` - Analyze only changed files (requires git)
- `--verbose` - Show detailed progress

## Examples

**Current project:**
```
analyze project:
```

**Specific path:**
```
analyze project: ~/builds/my-app
```

**Quick scan:**
```
analyze project: ~/builds/my-app --quick
```

**Incremental:**
```
analyze project: --incremental
```

## Output files
- **PRD**: `.planning/specs/<project-name>/prd.md`
- **Database**: `~/.dream-studio/state/studio.db`
  - `reg_projects` - project metadata, health scores
  - `pi_analysis_runs` - run history, timing
  - `pi_violations`, `pi_bugs`, `pi_improvements` - findings
  - `ds_documents` - PRD with FTS5 search

## Error handling
See `reference/error-handling.md` for full error scenarios and recovery steps.

## Performance notes
- **Large codebases (>10k files)**: 30-45 min, uses Context7 progressive loading
- **Small projects (<1k files)**: 10-15 min
- **Incremental mode**: 5-10 min (10-50x faster for small changes)

## Integration with other skills

**Fix violations:**
```
Skill(skill="dream-studio:quality", args="debug")
# Context: Top 3 critical violations
```

**Implement improvements:**
```
Skill(skill="dream-studio:core", args="plan")
# Context: Top 5 high-priority improvements
```

**Security review:**
```
Skill(skill="dream-studio:quality", args="secure")
# Context: Security-related bugs
```

## Reference files
- `reference/output-format.md` - Display template
- `reference/error-handling.md` - Error scenarios
- `reference/health-interpretation.md` - Health score guide
