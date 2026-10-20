---
dream_studio:
  skill_id: ds-analyze
  pack: analyze
  mode: intelligence
  mode_type: analysis
  inputs: [project_path, analysis_options, stack_context]
  outputs: [prd_document, health_score, violations, bugs, improvements]
  capabilities_required: [Read, Grep, Bash, Write]
  model_preference: sonnet
  estimated_duration: 15-45min
  write_posture: independent
  lifecycle: published
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
Extract path (default: `.`), verify it exists. Import `control.analysis.engine.analyze_project` (fail if missing).

### 2. Determine mode
**Full** (default) | **Quick** (`--quick` → targeted) | **Incremental** (`--incremental`, requires git)

### 3. Run & display
```python
from control.analysis.engine import analyze_project
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
- **PRD**: `~/.dream-studio/projects/<project-name>/planning/specs/prd.md` (also stored as a document; it is not written into the analyzed project)
- **Database**: `~/.dream-studio/state/studio.db`
  - `business_projects` - the analyzed project is registered here when it is not already
  - `ai_canonical_events` - one `analysis.*` event per phase, after `ds spool ingest`
    (the engine writes them to the spool, `~/.dream-studio/events/spool/`)
- **Documents**: `~/.dream-studio/state/files.db`, table `ds_documents` - a copy of the PRD,
  with an FTS5 index

Findings (violations, bugs, improvements) and the health score are returned in the result, and
the PRD lists the detected bugs; none of them is stored in a database table.

## Error handling
See `reference/error-handling.md` for full error scenarios and recovery steps.

## Performance notes
- **Large codebases (>10k files)**: 30-45 min, uses Context7 progressive loading
- **Small projects (<1k files)**: 10-15 min
- **Incremental mode**: 5-10 min (10-50x faster for small changes)

## Integration with other skills

**Fix violations:**
```
Skill(skill="ds-code-health", args="debug")
# Context: Top 3 critical violations
```

**Implement improvements:**
```
Skill(skill="ds-core", args="plan")
# Context: Top 5 high-priority improvements
```

**Security review:**
```
Skill(skill="ds-security", args="review")
# Context: Security-related bugs
```

## Reference files
- `reference/output-format.md` - Display template
- `reference/error-handling.md` - Error scenarios
- `reference/health-interpretation.md` - Health score guide
