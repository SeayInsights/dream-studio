# Health Score Interpretation

Health scores range from 0-10 based on violations, complexity, and bug patterns.

## Score Ranges

### 9-10: Excellent
- Well-architected codebase
- Minimal technical debt
- Few or no critical issues
- Strong separation of concerns
- Good test coverage patterns

**Recommended:** Maintain current standards

### 7-8: Good  
- Some minor issues present
- Generally healthy architecture
- Low-to-moderate technical debt
- Occasional code smells

**Recommended:** Address medium-priority improvements when convenient

### 5-6: Fair
- Multiple issues requiring attention
- Moderate technical debt
- Some architectural violations
- Several code quality concerns

**Recommended:** Plan refactoring for high-priority violations

### 3-4: Poor
- Significant technical debt
- Multiple architectural violations
- Refactoring strongly recommended
- High bug density

**Recommended:** Immediate attention to critical violations; schedule major refactor

### 0-2: Critical
- Major issues blocking maintainability
- Severe architectural problems
- High security risk
- Project health at risk

**Recommended:** Emergency refactoring required; consider rewrite for worst cases

## Calculation Factors

Health score is calculated from:
- **Violations** (weight: 2x for critical, 1x for high, 0.5x for medium, 0.1x for low)
- **Complexity** (cyclomatic complexity, function/file size)
- **Bug patterns** (security issues, code smells)

Formula: `10 - (critical×2 + high×1 + medium×0.5 + low×0.1)`, clamped to 0-10
