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

## Trigger
`analyze project: <path>`, `project intelligence: <path>`, `scan codebase: <path>`

## Purpose
Comprehensive codebase analysis that detects your stack, generates a Product Requirements Document (PRD), identifies architecture violations, finds bugs, and provides health scoring. Uses the project-intelligence platform built in Waves 0-4.

**Key capabilities:**
- **Stack detection** — Auto-detect Next.js, Astro, Python, and other stacks
- **PRD generation** — Full product requirements document based on discovered architecture
- **Health scoring** — 0-10 score based on violations, complexity, and bug patterns
- **Violation detection** — Circular dependencies, god objects, layer violations
- **Bug analysis** — Security issues, code smells, risk patterns
- **Improvement suggestions** — Actionable recommendations with effort estimates

## When to use

**New project analysis:**
- Understand an unfamiliar codebase quickly
- Generate documentation for undocumented projects
- Assess technical debt before refactoring

**Ongoing project health:**
- Monitor health score trends over time
- Track violation and bug counts
- Validate improvements after refactoring

**Pre-ship quality gate:**
- Run before major releases to catch issues
- Verify no critical violations introduced
- Ensure health score meets standards

## Before you start
Read `gotchas.yml` in this directory if it exists.

## Workflow

### 1. Parse input and validate path

Extract project path from user message. Default to current directory (`.`) if no path specified.

Validate that the path exists and is a directory:
```bash
test -d "<path>" && echo "Valid" || echo "Invalid path"
```

### 2. Determine analysis mode

Support two modes via flags:

**Full analysis (default):**
- All 5 phases: Discovery → Research → Audit → Bug Analysis → Synthesis
- Estimated time: 15-45 minutes depending on project size
- Generates complete PRD with all findings

**Quick analysis (`--quick`):**
- Skip research phase (no stack compatibility lookups)
- Discovery → Audit → Bug Analysis → Synthesis
- Estimated time: 10-20 minutes
- PRD may have incomplete compatibility notes

**Incremental analysis (`--incremental`):**
- Analyze only files changed since last analysis
- Requires git repository
- Estimated time: 5-15 minutes
- Updates existing PRD with new findings

### 3. Check for analyze.engine module

Verify the analysis engine is available:
```bash
py -c "from analyze.engine import analyze_project; print('Engine available')"
```

If the import fails, report that Wave 2-4 components are not yet installed and the intelligence mode requires the full project-intelligence platform.

### 4. Invoke analysis engine

**Full analysis:**
```python
from pathlib import Path
from analyze.engine import analyze_project

result = analyze_project(
    path=Path("<project-path>"),
    run_type="full",
    skip_phases=[]
)
```

**Quick analysis:**
```python
result = analyze_project(
    path=Path("<project-path>"),
    run_type="quick",
    skip_phases=["research"]
)
```

**Incremental analysis:**
```python
result = analyze_project(
    path=Path("<project-path>"),
    run_type="incremental",
    skip_phases=[]
)
```

The engine returns a dict with:
- `run_id`: Analysis run identifier
- `project_id`: Project identifier
- `prd_path`: Path to generated PRD file
- `health_score`: 0-10 health score
- `violations_found`: Count of architecture violations
- `bugs_found`: Count of detected bugs
- `improvements_suggested`: Count of improvement recommendations
- `status`: "completed" or "failed"
- `error_message`: Error details if failed

### 5. Display analysis summary

Present the results to the user in a clear, actionable format:

```
✅ Project Intelligence Analysis Complete

📊 Health Score: {health_score}/10
   {health_interpretation}

🔍 Stack Detected: {stack_name} (confidence: {confidence}%)

📈 Findings:
   • {violations_found} architecture violations
   • {bugs_found} bugs detected
   • {improvements_suggested} improvement opportunities

📄 PRD Generated: {prd_path}

🔗 View in Dashboard: 
   Launch dashboard: py scripts/ds_dashboard.py
   Navigate to Projects tab → {project_name}

📋 Next Steps:
   {top_3_recommendations}
```

**Health score interpretation:**
- 9-10: Excellent — well-architected, minimal issues
- 7-8: Good — some minor issues, generally healthy
- 5-6: Fair — multiple issues requiring attention
- 3-4: Poor — significant technical debt, refactoring recommended
- 0-2: Critical — major issues blocking maintainability

### 6. Link to PRD document

The PRD is written to `.planning/specs/<project-name>/prd.md` and stored in the `ds_documents` SQLite table.

Provide the absolute path to the PRD file so the user can review detailed findings:

```
Read the full PRD for detailed architecture, risks, and recommendations:
   cat "{absolute_prd_path}"
```

### 7. Offer dashboard visualization

If the analytics dashboard is available, suggest launching it:

```bash
# Launch dashboard
py scripts/ds_dashboard.py

# Then navigate to:
# Projects tab → {project_name} → view health trends, bugs, violations
```

The dashboard provides interactive visualizations:
- Health score gauge (Chart.js doughnut chart)
- Bug severity breakdown
- Violation types and counts
- Improvement priority matrix
- Analysis run history

## Flags

- `--quick`: Skip research phase for faster analysis
- `--incremental`: Analyze only changed files (requires git)
- `--verbose`: Show detailed progress during analysis

## Examples

**Analyze current project:**
```
analyze project:
```

**Analyze specific path:**
```
analyze project: ~/builds/my-app
```

**Quick scan (no research):**
```
analyze project: ~/builds/my-app --quick
```

**Incremental update:**
```
analyze project: --incremental
```

## Output files

All analysis outputs are stored in:
- **PRD**: `.planning/specs/<project-name>/prd.md` (markdown)
- **Database**: `~/.dream-studio/state/studio.db` (SQLite)
  - `reg_projects` table (project metadata, health scores)
  - `pi_analysis_runs` table (run history, timing, findings counts)
  - `pi_violations` table (architecture violations with severity)
  - `pi_bugs` table (detected bugs with risk scores)
  - `pi_improvements` table (recommendations with effort estimates)
  - `ds_documents` table (PRD document with FTS5 search)

## Error handling

**Path not found:**
```
❌ Error: Path does not exist: {path}
Please provide a valid project directory.
```

**Analysis engine not available:**
```
❌ Error: Project intelligence engine not installed
The intelligence mode requires Waves 0-4 of project-intelligence to be complete.
Missing module: analyze.engine

To install, run the project-intelligence build workflow.
```

**Analysis failed:**
```
❌ Analysis failed: {error_message}

Partial results may be available in the database.
Check logs for details: cat ~/.dream-studio/logs/analysis-errors.log
```

## Performance notes

**Large codebases (>10k files):**
- Uses Context7 progressive context loading (Wave 4)
- Analyzes skeleton first, then loads details progressively
- Token budget: 150k tokens
- Expected time: 30-45 minutes

**Small projects (<1k files):**
- Full context loading
- Expected time: 10-15 minutes

**Incremental mode:**
- Git diff detection for changed files only
- Expected time: 5-10 minutes (10-50x faster for small changes)

## Integration with other skills

**After analysis, common follow-up actions:**

**Fix violations:**
```
Invoke: Skill(skill="dream-studio:quality", args="debug")
Context: Top 3 critical violations from analysis
```

**Implement improvements:**
```
Invoke: Skill(skill="dream-studio:core", args="plan")
Context: Top 5 high-priority improvements from analysis
```

**Security review:**
```
Invoke: Skill(skill="dream-studio:quality", args="secure")
Context: Security-related bugs from analysis
```

**Generate architecture docs:**
```
Read PRD → extract architecture section → expand into ARCHITECTURE.md
```

## Acceptance criteria

For this mode to be considered complete and working:

1. ✅ Can analyze a project and return results
2. ✅ Generates PRD in `.planning/specs/<project>/prd.md`
3. ✅ Stores results in SQLite database
4. ✅ Returns health score (0-10)
5. ✅ Detects stack correctly (>80% confidence)
6. ✅ Finds at least 1 violation or bug (on non-trivial projects)
7. ✅ Provides actionable recommendations
8. ✅ Links to dashboard visualization
9. ✅ Supports --quick and --incremental flags
10. ✅ Handles errors gracefully with clear messages
