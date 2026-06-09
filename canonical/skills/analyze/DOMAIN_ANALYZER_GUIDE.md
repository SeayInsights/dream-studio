# Domain Analyzer Guide

## Overview

The domain-extensible analyzer evaluates repositories across different skill domains (design, career, finance, real estate) using automated, repeatable analysis with transparent scoring.

## Architecture

### Core Components

1. **BaseAnalyzer** (`core/base_analyzer.py`)
   - Abstract base class for all domain analyzers
   - Provides utility methods: `find_files()`, `search_content()`, `has_directory()`, etc.
   - Enforces standard result format for all capabilities

2. **DomainAnalyzerRegistry** (`domains/registry.py`)
   - Central registry for managing domain analyzers
   - Auto-registration of built-in analyzers
   - Domain auto-detection from repository markers

3. **Domain Analyzers** (`domains/*.py`)
   - `DesignSkillAnalyzer` - Design system capabilities
   - `CareerSkillAnalyzer` - Career/job search capabilities
   - `FinanceSkillAnalyzer` - Financial/accounting capabilities
   - `RealEstateSkillAnalyzer` - Real estate/property capabilities

### Analysis Flow

```
repo-analyzer.py (user-facing)
    ↓
analyze_repositories() (routing)
    ↓
DomainAnalyzerRegistry (domain selection)
    ↓
Domain Analyzer (e.g., DesignSkillAnalyzer)
    ↓
10 Capability Analysis Methods
    ↓
Weighted Overall Score
```

## Usage

### Command Line

```bash
# Analyze with auto-detection
py repo-analyzer.py /path/to/repo --auto-detect --verbose

# Analyze with explicit domain
py repo-analyzer.py /path/to/repo --domain design --format markdown

# List available domains
py repo-analyzer.py --list-domains

# Compare multiple repositories
py repo-analyzer.py /path/repo1 /path/repo2 --domain design --compare
```

### Python API

```python
from skills.analyze.repo_analyzer import analyze_repositories

# Domain-specific analysis
result = analyze_repositories(
    ['/path/to/design-repo'],
    domain='design',
    output_format='dict',
    verbose=True
)

print(f"Overall Score: {result['overall_scores']['repo-name']}/10")
print(f"Best in class: {result['best_in_class']}")

# General SKILL.md pattern analysis (backward compatible)
result = analyze_repositories(
    ['/path/to/repo'],
    domain='general',
    output_format='markdown'
)
```

### Using Registry Directly

```python
from domains.registry import DomainAnalyzerRegistry
from pathlib import Path

# Auto-detect domain
domain = DomainAnalyzerRegistry.auto_detect_domain(
    Path('/path/to/repo'),
    verbose=True
)

# Get analyzer for domain
analyzer = DomainAnalyzerRegistry.get_analyzer(
    domain,
    Path('/path/to/repo'),
    'repo-name'
)

# Analyze capabilities
scores = analyzer.score_repository()
print(f"Overall: {scores['overall_score']}/10")

# Analyze single capability
result = analyzer.analyze_capability('color_systems')
print(f"Score: {result['score']}/10")
print(f"Evidence: {result['evidence']}")
```

## Domain Capabilities

### Design (10 capabilities)

| Capability | Weight | Description |
|------------|--------|-------------|
| color_systems | 15% | Color palettes, OKLCH, contrast checking |
| typography | 12% | Font systems, type ramps, modular scales |
| components | 15% | UI kits, device frames, design tokens |
| design_systems | 12% | DESIGN.md, style guides, pattern libraries |
| brand_protocols | 10% | Brand specs, asset management, logos |
| reasoning | 12% | Design rationale, ui-reasoning databases |
| anti_patterns | 8% | Anti-pattern detection, validation rules |
| export_formats | 6% | Multi-format export (PPT, video, PDF) |
| quality_gates | 5% | Critique systems, accessibility checks |
| register_system | 5% | Register-aware design, brand.md |

### Career (10 capabilities)

| Capability | Weight | Description |
|------------|--------|-------------|
| resume_templates | 15% | Resume formats, multi-format generation |
| job_search | 12% | Job board integration, search automation |
| interview_prep | 15% | Question banks, mock interviews, STAR method |
| cover_letters | 10% | Cover letter generation, customization |
| salary_negotiation | 10% | Salary data, negotiation guides, calculators |
| portfolio | 10% | Portfolio templates, case studies |
| ats_optimization | 10% | ATS keyword analysis, resume parsing |
| career_progression | 8% | Career paths, skill gap analysis |
| networking | 5% | LinkedIn optimization, outreach templates |
| skill_assessment | 5% | Skill evaluation, certification guidance |

### Finance (10 capabilities)

| Capability | Weight | Description |
|------------|--------|-------------|
| accounting | 15% | Chart of accounts, double-entry bookkeeping |
| invoicing | 12% | Invoice generation, payment tracking |
| ledger | 15% | General ledger, transaction logging |
| tax | 10% | Tax calculation, forms, deduction tracking |
| budgeting | 10% | Budget planning, variance analysis |
| reporting | 12% | Financial statements, ratio analysis |
| expenses | 8% | Expense tracking, receipt management |
| reconciliation | 8% | Bank reconciliation, matching algorithms |
| integration | 5% | QuickBooks, Xero, banking APIs |
| compliance | 5% | Audit trails, GAAP/IFRS support |

### Real Estate (10 capabilities)

| Capability | Weight | Description |
|------------|--------|-------------|
| listings | 12% | Property listings, photo management |
| mls_integration | 15% | MLS API, RETS/WebAPI, IDX compliance |
| cma | 15% | Comparative market analysis, comp selection |
| valuation | 12% | Property valuation, AVM, appraisal methods |
| market_data | 10% | Market trends, neighborhood statistics |
| search | 8% | Property search, geospatial, filters |
| investment_analysis | 10% | ROI, cash flow, cap rate calculations |
| documents | 8% | Contract generation, e-signature |
| crm | 5% | Client management, lead tracking |
| reporting | 5% | Market reports, data visualization |

## Scoring Methodology

### Capability Analysis Result Format

Each capability analysis returns:

```python
{
    'detected': bool,           # Was capability found?
    'score': float,             # Score 0-10
    'evidence': List[str],      # File paths or indicators
    'count': int,               # Quantitative metric
    'quality': str              # 'excellent' | 'good' | 'adequate' | 'weak'
}
```

### Quality Thresholds

Quality is calculated using `calculate_quality_score(count, thresholds)`:

```python
thresholds = {
    'excellent': 8,  # Count >= 8 → 10.0 score, 'excellent'
    'good': 5,       # Count >= 5 → 7.0-9.9 score, 'good'
    'adequate': 2    # Count >= 2 → 4.0-6.9 score, 'adequate'
}                    # Count < 2 → 0.0-3.9 score, 'weak'
```

### Overall Score Calculation

Overall score is weighted average:

```python
overall = sum(
    capability_score * weight
    for capability, weight in WEIGHTS.items()
)
```

## Auto-Detection

Domains are auto-detected by scoring file markers:

**Design markers:**
- `DESIGN.md`, `colors.csv`, `typography.md`, `ui-reasoning.csv`
- `brand-spec.md`, `color-and-contrast.md`, `device-frames/`

**Career markers:**
- `resume/`, `job_search/`, `interview/`, `cover_letter/`
- `salary/`, `portfolio/`, `ats/`, `career/`

**Finance markers:**
- `accounting/`, `invoice/`, `ledger/`, `tax/`, `budget/`
- `financial/`, `expense/`, `reconciliation/`, `quickbooks/`, `xero/`

**Real Estate markers:**
- `property/`, `mls/`, `zillow/`, `realtor/`, `appraisal/`
- `real-estate/`, `real_estate/`, `comp-analysis/`

## Output Formats

### Dict (default)

Python dictionary with full analysis results:

```python
{
    'domain': 'design',
    'repositories': ['repo1', 'repo2'],
    'capability_matrix': {
        'repo1': {'color_systems': 8.5, 'typography': 7.0, ...},
        'repo2': {'color_systems': 9.0, 'typography': 8.5, ...}
    },
    'overall_scores': {'repo1': 7.8, 'repo2': 8.2},
    'best_in_class': {
        'color_systems': {'repository': 'repo2', 'score': 9.0},
        ...
    },
    'unique_features': {
        'repo1': ['OKLCH color space', 'Video export'],
        'repo2': ['3D virtual tours']
    }
}
```

### JSON

JSON-formatted string (same structure as dict).

### Markdown

Human-readable markdown report:

```markdown
# Design Skill Analysis

## Summary
- Analyzed repositories: repo1, repo2
- Domain: design

## Overall Scores
| Repository | Overall Score |
|------------|---------------|
| repo1      | 7.8/10        |
| repo2      | 8.2/10        |

## Capability Matrix
| Capability    | repo1 | repo2 | Best   |
|---------------|-------|-------|--------|
| color_systems | 8.5   | 9.0   | repo2  |
| typography    | 7.0   | 8.5   | repo2  |
...

## Unique Features
### repo1
- OKLCH color space implementation
- Video export pipeline

### repo2
- 3D virtual tour integration
```

## Extending with New Domains

### Step 1: Create Analyzer Class

```python
# domains/new_domain.py

from core.base_analyzer import BaseAnalyzer
from typing import Dict, List, Any

class NewDomainAnalyzer(BaseAnalyzer):
    WEIGHTS = {
        'capability1': 0.20,
        'capability2': 0.15,
        # ... sum to 1.0
    }
    
    def get_domain_name(self) -> str:
        return 'new_domain'
    
    def get_capabilities(self) -> List[str]:
        return ['capability1', 'capability2', ...]
    
    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        # Route to _analyze_capability1(), etc.
        pass
    
    def score_repository(self) -> Dict[str, float]:
        scores = {}
        for cap in self.get_capabilities():
            result = self.analyze_capability(cap)
            scores[cap] = result['score']
        
        overall = sum(scores[c] * self.WEIGHTS[c] for c in scores)
        scores['overall_score'] = round(overall, 1)
        return scores
    
    def _analyze_capability1(self) -> Dict[str, Any]:
        evidence = []
        count = 0
        
        # Use BaseAnalyzer utilities:
        files = self.find_files('**/*pattern*.{py,js}')
        matches = self.search_content(r'keyword|pattern')
        
        if files:
            evidence.append(f"{len(files)} files found")
            count += len(files)
        
        thresholds = {'excellent': 8, 'good': 5, 'adequate': 2}
        score, quality = self.calculate_quality_score(count, thresholds)
        
        return {
            'detected': count > 0,
            'score': score,
            'evidence': evidence,
            'count': count,
            'quality': quality
        }
```

### Step 2: Register in Registry

```python
# domains/registry.py

def _register_builtin_analyzers():
    # ... existing registrations ...
    
    try:
        from .new_domain import NewDomainAnalyzer
        DomainAnalyzerRegistry.register(
            'new_domain',
            NewDomainAnalyzer,
            markers=['file1.md', 'dir1/', 'pattern*']
        )
    except ImportError:
        pass
```

### Step 3: Test

```python
from domains.registry import DomainAnalyzerRegistry

analyzer = DomainAnalyzerRegistry.get_analyzer(
    'new_domain',
    Path('/path/to/repo'),
    'repo-name'
)

scores = analyzer.score_repository()
print(scores)
```

## Examples

### Example 1: Analyze Design Repo

```bash
py repo-analyzer.py ~/repos/huashu-design \
    --domain design \
    --format markdown \
    --verbose
```

### Example 2: Compare Multiple Design Repos

```bash
py repo-analyzer.py \
    ~/repos/huashu-design \
    ~/repos/ui-ux-pro-max \
    ~/repos/impeccable \
    ~/repos/open-design \
    --domain design \
    --compare \
    --format json > comparison.json
```

### Example 3: Auto-Detect and Analyze

```python
from pathlib import Path
from skills.analyze.repo_analyzer import analyze_repositories
from domains.registry import DomainAnalyzerRegistry

repo_path = Path('~/repos/mystery-repo')

# Auto-detect domain
domain = DomainAnalyzerRegistry.auto_detect_domain(repo_path, verbose=True)
print(f"Detected: {domain}")

# Analyze with detected domain
result = analyze_repositories(
    [str(repo_path)],
    domain=domain,
    output_format='dict'
)

# Extract insights
repo_name = repo_path.name
overall = result['overall_scores'][repo_name]
print(f"\n{repo_name} Overall Score: {overall}/10")

# Find best capabilities
scores = result['capability_matrix'][repo_name]
best_caps = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
print(f"\nTop 3 Capabilities:")
for cap, score in best_caps:
    print(f"  {cap}: {score}/10")

# Show unique features
if repo_name in result['unique_features']:
    print(f"\nUnique Features:")
    for feature in result['unique_features'][repo_name]:
        print(f"  - {feature}")
```

## Testing

Run the integration test suite:

```bash
cd skills/analyze
py test_analyzer.py
```

Run domain registration test:

```bash
cd skills/analyze
py test_domains.py
```

## Troubleshooting

### "Unknown domain" error

Make sure the domain is registered:

```python
from domains.registry import DomainAnalyzerRegistry
print(DomainAnalyzerRegistry.list_domains())
```

If missing, check that the analyzer module is imported in `registry.py`.

### ImportError for domain analyzer

Check the module path and imports:

```python
# Verify import works
from domains.design import DesignSkillAnalyzer
```

### Low scores on expected capabilities

Run with `--verbose` to see detection details:

```bash
py repo-analyzer.py /path/to/repo --domain design --verbose
```

Check the evidence list to see what was detected.

### Auto-detection picks wrong domain

Domain markers overlap. Use `--domain` to force a specific domain:

```bash
py repo-analyzer.py /path/to/repo --domain career
```

Or adjust marker weights in `registry.py`.

## Performance

- **Single repo analysis**: 2-5 seconds (depending on repo size)
- **Multi-repo comparison**: ~3 seconds per repo
- **Search operations**: Uses regex caching, ~100ms per search
- **File globbing**: Fast (Python pathlib), <100ms for most repos

For large repos (>10k files), analysis may take 10-30 seconds.

## Backward Compatibility

General SKILL.md pattern analysis is still available:

```python
# Uses legacy RepoAnalyzer
result = analyze_repositories(
    ['/path/to/repo'],
    domain='general',  # or domain=None
    output_format='dict'
)

# Returns old format with patterns, not capabilities
print(result['patterns'])
print(result['summary'])
```

## Future Enhancements

Planned improvements:

1. **Caching**: Cache analysis results for faster re-runs
2. **Parallel analysis**: Analyze multiple repos concurrently
3. **Incremental updates**: Only re-analyze changed files
4. **Custom weights**: Allow users to override capability weights
5. **Report templates**: Customizable markdown/HTML report templates
6. **CI integration**: GitHub Actions workflow for PR analysis
7. **Trend tracking**: Store historical scores for trend analysis
8. **AI recommendations**: Use LLM to generate improvement suggestions based on capability gaps
