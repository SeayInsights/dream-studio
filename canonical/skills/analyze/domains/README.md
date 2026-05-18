# Domain Analyzers

Domain-specific repository analyzers for evaluating skill repositories across different domains.

## Quick Start

```python
from domains.registry import DomainAnalyzerRegistry
from pathlib import Path

# List available domains
print(DomainAnalyzerRegistry.list_domains())
# ['design', 'career', 'finance', 'real_estate']

# Auto-detect domain
domain = DomainAnalyzerRegistry.auto_detect_domain(Path('/path/to/repo'))

# Get analyzer
analyzer = DomainAnalyzerRegistry.get_analyzer(domain, Path('/path/to/repo'), 'repo-name')

# Analyze and score
scores = analyzer.score_repository()
print(f"Overall: {scores['overall_score']}/10")
```

## Available Domains

### Design (`design.py`)
Evaluates design system capabilities: color systems, typography, components, design systems, brand protocols, reasoning, anti-patterns, export formats, quality gates, register systems.

**Markers:** `DESIGN.md`, `colors.csv`, `typography.md`, `ui-reasoning.csv`, `brand-spec.md`, `device-frames/`

### Career (`career.py`)
Evaluates career/job search capabilities: resume templates, job search, interview prep, cover letters, salary negotiation, portfolio, ATS optimization, career progression, networking, skill assessment.

**Markers:** `resume/`, `job_search/`, `interview/`, `cover_letter/`, `salary/`, `portfolio/`, `ats/`

### Finance (`finance.py`)
Evaluates financial/accounting capabilities: accounting systems, invoicing, ledger, tax, budgeting, reporting, expenses, reconciliation, platform integration, compliance.

**Markers:** `accounting/`, `invoice/`, `ledger/`, `tax/`, `budget/`, `financial/`, `quickbooks/`, `xero/`

### Real Estate (`real_estate.py`)
Evaluates real estate/property capabilities: listings, MLS integration, CMA, valuation, market data, search, investment analysis, documents, CRM, reporting.

**Markers:** `property/`, `mls/`, `zillow/`, `realtor/`, `appraisal/`, `real-estate/`, `comp-analysis/`

## Architecture

```
domains/
├── __init__.py           # Exports DomainAnalyzerRegistry
├── registry.py           # Central registry for domain analyzers
├── design.py             # DesignSkillAnalyzer
├── career.py             # CareerSkillAnalyzer
├── finance.py            # FinanceSkillAnalyzer
├── real_estate.py        # RealEstateSkillAnalyzer
└── README.md             # This file

core/
├── __init__.py           # Exports BaseAnalyzer
└── base_analyzer.py      # Abstract base class
```

## Creating a New Domain Analyzer

1. **Create analyzer class** inheriting from `BaseAnalyzer`:

```python
# domains/my_domain.py

from core.base_analyzer import BaseAnalyzer

class MyDomainAnalyzer(BaseAnalyzer):
    WEIGHTS = {'cap1': 0.5, 'cap2': 0.5}  # Sum to 1.0
    
    def get_domain_name(self) -> str:
        return 'my_domain'
    
    def get_capabilities(self) -> List[str]:
        return ['cap1', 'cap2']
    
    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        # Return: {'detected': bool, 'score': float, 'evidence': List, 'count': int, 'quality': str}
        pass
    
    def score_repository(self) -> Dict[str, float]:
        # Calculate weighted overall score
        pass
```

2. **Register in `registry.py`**:

```python
try:
    from .my_domain import MyDomainAnalyzer
    DomainAnalyzerRegistry.register(
        'my_domain',
        MyDomainAnalyzer,
        markers=['file.md', 'directory/']
    )
except ImportError:
    pass
```

3. **Test**:

```python
analyzer = DomainAnalyzerRegistry.get_analyzer('my_domain', path, name)
print(analyzer.score_repository())
```

## BaseAnalyzer Utilities

All domain analyzers inherit these utilities:

- `find_files(pattern)` - Find files matching glob pattern
- `count_files(pattern)` - Count matching files
- `search_content(pattern)` - Grep-like content search
- `has_directory(name)` - Check if directory exists
- `has_file(name)` - Check if file exists
- `read_file(path)` - Read file content
- `calculate_quality_score(count, thresholds)` - Score quality from count

## Capability Result Format

Each capability analysis must return:

```python
{
    'detected': bool,        # Was capability found?
    'score': float,          # 0.0 - 10.0
    'evidence': List[str],   # File paths, indicators
    'count': int,            # Quantitative metric
    'quality': str           # 'excellent' | 'good' | 'adequate' | 'weak'
}
```

## Quality Scoring

Use `calculate_quality_score()` for consistent scoring:

```python
thresholds = {'excellent': 8, 'good': 5, 'adequate': 2}
score, quality = self.calculate_quality_score(count, thresholds)
# count >= 8 → (10.0, 'excellent')
# count >= 5 → (7.0-9.9, 'good')
# count >= 2 → (4.0-6.9, 'adequate')
# count < 2 → (0.0-3.9, 'weak')
```

## See Also

- [DOMAIN_ANALYZER_GUIDE.md](../DOMAIN_ANALYZER_GUIDE.md) - Full documentation
- [base_analyzer.py](../core/base_analyzer.py) - BaseAnalyzer source
- [registry.py](registry.py) - Registry source
