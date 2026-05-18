---
dream_studio:
  skill_id: ds-analyze
  pack: analyze
  mode: repo
  mode_type: analysis
  inputs: [repository_data, pr_history, issue_patterns, codebase_structure]
  outputs: [pattern_analysis, comparison_report, recommendations]
  capabilities_required: [Read, Grep, Bash, Agent]
  model_preference: sonnet
  estimated_duration: 30-60min
name: repo
description: Repository pattern analysis and cross-repo comparison
triggers: ["analyze repo:", "repo patterns:", "compare repos:", "repo analysis:"]
model_tier: sonnet
---

# Analyze — Repository Pattern Analysis

## Trigger
`analyze repo: <repo-paths>`, `repo patterns: <repo-paths>`, `compare repos: <repo1> <repo2>`

## Purpose
Systematic analysis of repositories with two modes:

### 1. General Analysis (default)
SKILL.md patterns, organizational structures, and quality indicators. Generates quantitative adoption metrics, cross-repo comparisons, and actionable enhancement recommendations.

Extracts 10 pattern types:
1. **progressive_disclosure** — SKILL.md + references/ pattern
2. **decision_tables** — routing/classification matrices
3. **do_dont_examples** — anti-pattern examples
4. **response_contracts** — structured output schemas
5. **version_guards** — version-specific compatibility notes
6. **frontmatter** — structured metadata
7. **testing_patterns** — test organization and coverage
8. **cicd_patterns** — CI/CD platforms and deployment strategies
9. **docs_patterns** — documentation quality indicators
10. **code_quality_patterns** — linters, formatters, type checkers

### 2. Domain-Specific Analysis (--domain flag)
Evaluates repositories for domain-specific capabilities with quantitative scoring (0-10 scale):

**Design Domain** (`--domain design`):
- color_systems, typography, components, design_systems, brand_protocols
- reasoning, anti_patterns, export_formats, quality_gates, register_system

**Career Domain** (`--domain career`):
- resume_templates, job_search, interview_prep, cover_letters
- salary_negotiation, portfolio, ats_optimization, career_progression
- networking, skill_assessment

**Finance Domain** (`--domain finance`):
- accounting, invoicing, ledger, tax, budgeting
- reporting, expenses, reconciliation, integration, compliance

**Real Estate Domain** (`--domain real_estate`):
- listings, mls_integration, cma, valuation, market_data
- search, investment_analysis, documents, crm, reporting

Each capability scores 0-10 with quality labels (excellent/good/adequate/weak) and evidence-based detection.

## When to use

**Single repo analysis:**
- Audit current project's pattern adoption
- Identify quality gaps and improvement opportunities
- Generate baseline metrics for tracking progress

**Cross-repo comparison:**
- Extract proven patterns from external repos (e.g., terraform-skill, open-design)
- Identify enhancement opportunities for target repo
- Benchmark against best-in-class repositories

**Self-analysis:**
- Evaluate dream-studio's own pattern adoption
- Track pattern rollout progress
- Identify inconsistencies across skills

## Workflow

### 1. Parse input and validate paths

Extract repository paths from user message. Paths can be:
- Absolute paths: `/path/to/repo`
- Relative paths: `../terraform-skill`
- Current directory: `.`

Validate that each path exists and is a directory.

### 2. Determine analysis mode

**Single repo** (1 path):
- Focus on pattern adoption metrics
- Generate improvement recommendations
- Output: Markdown report with actionable next steps

**Multi-repo comparison** (2+ paths):
- Side-by-side pattern adoption comparison
- Identify gaps between repos
- Extract enhancement opportunities
- Output: Comparison table + recommendations

### 3. Invoke repo analysis

**Recommended: Use the automated wrapper** (handles GitHub URLs and local paths):

```bash
# Single repo (GitHub URL or local path)
py modes/repo/analyze-repos.py <repo-url-or-path> --format markdown --verbose

# Compare multiple repos (mix of URLs and local paths)
py modes/repo/analyze-repos.py <repo1> <repo2> <repo3> --compare --verbose

# Examples - General Analysis
py modes/repo/analyze-repos.py https://github.com/user/repo --verbose
py modes/repo/analyze-repos.py /path/to/repo1 /path/to/repo2 --compare

# Examples - Domain-Specific Analysis
py modes/repo/analyze-repos.py https://github.com/user/design-repo --domain design --verbose
py modes/repo/analyze-repos.py repo1/ repo2/ repo3/ --domain career --compare
py modes/repo/analyze-repos.py /path/to/repo --auto-detect --verbose
```

The wrapper automatically:
- Detects GitHub URLs and clones them to temp directory
- Validates local paths
- Invokes the repo-analyzer
- Cleans up temp files on completion

**Alternative: Direct analyzer usage** (for local paths only):

```python
py ../../repo-analyzer.py <repo-path> --format markdown --verbose
py ../../repo-analyzer.py <repo1> <repo2> --compare --verbose
```

**Programmatic usage:**
```python
from skills.analyze.repo_analyzer import extract_patterns_for_enhancement

result = extract_patterns_for_enhancement(
    source_repos=['/path/to/source1', '/path/to/source2'],
    target_repo='/path/to/target',
    min_adoption_threshold=0.5,
    verbose=True
)
```

### 4. Parse and structure results

The analyzer returns:
- **summary**: aggregate metrics (total skills, repos analyzed, patterns found)
- **repo_structures**: organizational details (CLAUDE.md, CI, PR templates)
- **skill_analyses**: per-file pattern detection
- **patterns**: instances of each pattern type
- **statistics**: adoption rates, averages, comparisons

### 5. Generate recommendations

For each repo analyzed, identify:

**Quick wins** (low effort, high impact):
- Add references/ for progressive disclosure
- Add PR template (.github/PULL_REQUEST_TEMPLATE.md)
- Add CI validation workflow

**Pattern gaps** (adoption < 30%):
- List missing pattern types
- Estimate implementation effort
- Prioritize by ROI

**Structural improvements**:
- Add CLAUDE.md if missing
- Add skill standards documentation
- Standardize frontmatter schemas

### 6. Format output

**For single repo:**
```markdown
# Repository Analysis: <repo-name>

## Summary
- Total SKILL.md files: X
- Pattern adoption: Y%
- Top gaps: [list]

## Pattern Adoption
| Pattern | Adoption |
|---------|----------|
| progressive_disclosure | 60% |
| decision_tables | 40% |
...

## Recommendations
1. **Add progressive disclosure** (4-6 hours)
   - Create references/ directories for 5 skills
   - Split long SKILL.md files
   
2. **Standardize frontmatter** (2-3 hours)
   - Add triggers to 8 skills
   - Add version to all frontmatter
...
```

**For comparison:**
```markdown
# Repository Comparison

## Overview
Comparing: <repo1> vs <repo2>

## Adoption Rates
| Pattern | <repo1> | <repo2> | Gap |
|---------|---------|---------|-----|
| progressive_disclosure | 100% | 0% | -100% |
...

## Enhancement Opportunities
Based on <repo1> patterns, <repo2> could benefit from:
1. Progressive disclosure (8-12 hours effort)
2. Decision tables (6-10 hours effort)
...
```

## Integration with multi mode

The repo analysis can feed into multi-perspective analysis:

1. Run repo analysis first to get quantitative data
2. Pass results to `analyze multi evaluate-strategy` for qualitative assessment
3. Combine quantitative metrics with strategic recommendations

Example:
```
User: "analyze repo: terraform-skill open-design. Then evaluate how to enhance dream-studio"

Step 1: Run repo analysis (this mode)
Step 2: Pass results to multi mode with evaluate-strategy
Step 3: Synthesize enhancement roadmap
```

## Anti-patterns

- **Analyzing without validation** — Always verify paths exist before invoking analyzer
- **Skipping recommendations** — Raw metrics without actionable next steps aren't helpful
- **Ignoring effort estimates** — Always include time estimates for recommendations
- **Analysis paralysis** — Don't analyze more than 5 repos at once; focus on actionable comparisons
- **Forgetting self-analysis** — Use this mode to audit dream-studio itself periodically

## Output contract

Return a structured Markdown report with:

**Required sections:**
1. Summary (1-3 sentences)
2. Pattern adoption table
3. Recommendations (prioritized, with effort estimates)

**Optional sections:**
4. Repository structures comparison
5. Detailed pattern instances
6. Statistical analysis

**Format:**
- Use tables for metrics
- Use bullet lists for recommendations
- Include file paths in backticks
- Link to pattern documentation where relevant

## Example invocations

**Audit current project:**
```
analyze repo: .
```

**Compare external repos:**
```
analyze repo: /path/to/terraform-skill /path/to/open-design
```

**Extract enhancement patterns:**
```
analyze repo: terraform-skill open-design --target dream-studio
```

**Self-analysis:**
```
analyze repo: C:\Users\Example User\builds\dream-studio
```
