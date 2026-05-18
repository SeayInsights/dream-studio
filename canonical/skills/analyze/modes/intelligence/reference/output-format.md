# Output Format - Project Intelligence

Display template for analysis results.

## Summary Output

```
[SUCCESS] Project Intelligence Analysis Complete

Health Score: {health_score}/10
   {health_interpretation}

Stack Detected: {stack_name} (confidence: {confidence}%)

Findings:
   - {violations} architecture violations
   - {bugs} bugs detected
   - {improvements} improvement opportunities

PRD Generated: {prd_path}

View in Dashboard:
   Launch dashboard: py scripts/ds_dashboard.py
   Navigate to Projects tab -> {project_name}

Next Steps:
   1. {top_recommendation_1}
   2. {top_recommendation_2}
   3. {top_recommendation_3}
```

## Health Interpretations

- **9-10**: Excellent — well-architected, minimal issues
- **7-8**: Good — some minor issues, generally healthy
- **5-6**: Fair — multiple issues requiring attention
- **3-4**: Poor — significant technical debt, refactoring recommended
- **0-2**: Critical — major issues blocking maintainability

## Verbose Output (--verbose)

Add detailed section:
```
Detailed Results:
   Run ID: {run_id}
   Project ID: {project_id}
   Duration: {duration}s
   Phases: discovery -> research -> audit -> bugs -> synthesis
```
