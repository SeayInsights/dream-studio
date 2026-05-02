---
ds:
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
Systematic analysis of SKILL.md patterns, organizational structures, and quality indicators across one or more repositories. Generates quantitative adoption metrics, cross-repo comparisons, and actionable enhancement recommendations.

Uses the `shared/repo-analysis` utility to extract 10 pattern types:
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

### 3. Invoke repo-analyzer.py

Use the integration wrapper at `skills/analyze/repo-analyzer.py`:

**For single repo:**
```python
py skills/analyze/repo-analyzer.py <repo-path> --format markdown --verbose
```

**For comparison:**
```python
py skills/analyze/repo-analyzer.py <repo1> <repo2> --compare --verbose
```

**For enhancement extraction:**
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
analyze repo: C:\Users\Dannis Seay\builds\dream-studio
```
