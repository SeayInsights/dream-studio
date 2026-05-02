"""
Repository Analyzer

Systematic analysis of SKILL.md files to extract patterns and organizational structures.
"""

import re
import json
import yaml
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


@dataclass
class SkillAnalysis:
    """Analysis result for a single SKILL.md file"""
    path: str
    repo: str
    name: str
    line_count: int
    has_frontmatter: bool
    frontmatter: Dict[str, Any]
    has_decision_tables: bool
    decision_table_count: int
    has_do_dont_examples: bool
    do_dont_count: int
    has_workflow_section: bool
    has_validation_section: bool
    has_response_contract: bool
    has_version_guards: bool
    version_guard_count: int
    code_block_count: int
    reference_link_count: int
    anchor_link_count: int
    sections: List[str]
    trigger_keywords: List[str]


@dataclass
class RepoStructure:
    """Repository organization and architectural patterns"""
    repo: str
    total_skills: int
    skills_with_references: int
    reference_files: List[str]
    design_systems: List[str]
    has_claude_md: bool
    has_agents_md: bool
    has_skill_standards: bool
    has_pr_template: bool
    has_validation_ci: bool
    directory_structure: Dict[str, int]


class RepoAnalyzer:
    """
    Analyzes repositories for SKILL.md patterns and organizational structures.

    Usage:
        analyzer = RepoAnalyzer()
        analyzer.add_repo(Path('/path/to/repo'), 'repo-name')
        analyzer.analyze_all()
        report = analyzer.generate_report()
    """

    def __init__(self):
        self.skill_analyses: List[SkillAnalysis] = []
        self.repo_structures: Dict[str, RepoStructure] = {}
        self.patterns_found: Dict[str, List[Dict]] = defaultdict(list)
        self.repos_to_analyze: List[tuple[Path, str]] = []

    def add_repo(self, repo_path: Path, repo_name: str):
        """Add a repository to the analysis queue"""
        self.repos_to_analyze.append((repo_path, repo_name))

    def extract_frontmatter(self, content: str) -> tuple[bool, Dict]:
        """Extract YAML frontmatter from markdown"""
        if not content.startswith('---'):
            return False, {}

        parts = content.split('---', 2)
        if len(parts) < 3:
            return False, {}

        try:
            fm = yaml.safe_load(parts[1])
            return True, fm or {}
        except:
            return False, {}

    def count_decision_tables(self, content: str) -> tuple[bool, int]:
        """Count markdown tables that look like decision matrices"""
        table_pattern = r'\|[^\n]+\|[^\n]+\|\s*\n\s*\|[-:\s|]+\|\s*\n(\s*\|[^\n]+\|\s*\n)+'

        # Filter for decision-style headers
        decision_keywords = [
            'scenario', 'when', 'use', 'why', 'tradeoff', 'approach',
            'situation', 'tool', 'method', 'strategy', 'goal'
        ]
        decision_tables = []

        for table_match in re.finditer(table_pattern, content):
            table = table_match.group(0)
            header = table.split('\n')[0].lower()
            if any(kw in header for kw in decision_keywords):
                decision_tables.append(table)

        return len(decision_tables) > 0, len(decision_tables)

    def count_do_dont_examples(self, content: str) -> tuple[bool, int]:
        """Count DO/DON'T side-by-side examples"""
        patterns = [
            r'❌\s*(DON\'?T|Bad|Wrong|Anti-pattern)',
            r'✅\s*(DO|Good|Right|Pattern)',
            r'\*\*DON\'?T\*\*',
            r'\*\*DO\*\*'
        ]

        matches = sum(len(re.findall(p, content, re.IGNORECASE)) for p in patterns)
        return matches > 0, matches

    def extract_sections(self, content: str) -> List[str]:
        """Extract markdown section headers (##, ###)"""
        headers = re.findall(r'^#{2,3}\s+(.+)$', content, re.MULTILINE)
        return headers

    def count_version_guards(self, content: str) -> tuple[bool, int]:
        """Count version-specific guards (e.g., Terraform 1.6+, Python 3.10+)"""
        pattern = r'(?:Terraform|OpenTofu|Python|Node|npm|pnpm|React|Next\.js)\s+(?:\d+\.)+\d+\+'
        matches = re.findall(pattern, content, re.IGNORECASE)
        return len(matches) > 0, len(matches)

    def count_code_blocks(self, content: str) -> int:
        """Count fenced code blocks"""
        return len(re.findall(r'```[\s\S]*?```', content))

    def count_reference_links(self, content: str) -> int:
        """Count links to reference files (progressive disclosure pattern)"""
        return len(re.findall(r'\[.*?\]\(references/.*?\.md.*?\)', content))

    def count_anchor_links(self, content: str) -> int:
        """Count anchor links (#section)"""
        return len(re.findall(r'\[.*?\]\(.*?#.*?\)', content))

    def extract_trigger_keywords(self, frontmatter: Dict) -> List[str]:
        """Extract trigger keywords from frontmatter"""
        triggers = []
        if 'triggers' in frontmatter:
            if isinstance(frontmatter['triggers'], list):
                triggers = frontmatter['triggers']
            elif isinstance(frontmatter['triggers'], str):
                triggers = [frontmatter['triggers']]
        if 'keywords' in frontmatter:
            if isinstance(frontmatter['keywords'], list):
                triggers.extend(frontmatter['keywords'])
        return triggers

    def analyze_skill_file(self, file_path: Path, repo: str, base_path: Optional[Path] = None) -> SkillAnalysis:
        """
        Comprehensive analysis of a SKILL.md file

        Args:
            file_path: Path to SKILL.md file
            repo: Repository name
            base_path: Base path for relative path calculation (optional)

        Returns:
            SkillAnalysis with all detected patterns
        """
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')

        has_fm, fm = self.extract_frontmatter(content)
        has_decision, decision_count = self.count_decision_tables(content)
        has_do_dont, do_dont_count = self.count_do_dont_examples(content)
        has_version, version_count = self.count_version_guards(content)

        # Check for key sections
        content_lower = content.lower()
        has_workflow = 'workflow' in content_lower or '## workflow' in content_lower
        has_validation = 'validation' in content_lower or 'validate' in content_lower
        has_response_contract = 'response contract' in content_lower or 'output contract' in content_lower

        # Calculate relative path
        if base_path:
            rel_path = str(file_path.relative_to(base_path))
        else:
            rel_path = str(file_path)

        return SkillAnalysis(
            path=rel_path,
            repo=repo,
            name=fm.get('name', file_path.stem),
            line_count=len(lines),
            has_frontmatter=has_fm,
            frontmatter=fm,
            has_decision_tables=has_decision,
            decision_table_count=decision_count,
            has_do_dont_examples=has_do_dont,
            do_dont_count=do_dont_count,
            has_workflow_section=has_workflow,
            has_validation_section=has_validation,
            has_response_contract=has_response_contract,
            has_version_guards=has_version,
            version_guard_count=version_count,
            code_block_count=self.count_code_blocks(content),
            reference_link_count=self.count_reference_links(content),
            anchor_link_count=self.count_anchor_links(content),
            sections=self.extract_sections(content),
            trigger_keywords=self.extract_trigger_keywords(fm)
        )

    def analyze_repo_structure(self, repo_path: Path, repo_name: str) -> RepoStructure:
        """
        Analyze overall repository organization

        Args:
            repo_path: Path to repository root
            repo_name: Repository name

        Returns:
            RepoStructure with organizational metrics
        """
        skills = list(repo_path.rglob('SKILL.md'))
        references = list(repo_path.rglob('references/*.md'))
        design_systems = list(repo_path.rglob('design-systems/*/DESIGN.md'))

        # Count skills with collocated references
        skills_with_refs = 0
        for skill in skills:
            ref_dir = skill.parent / 'references'
            if ref_dir.exists() and ref_dir.is_dir():
                skills_with_refs += 1

        # Check for key documentation files
        has_claude = (repo_path / 'CLAUDE.md').exists()
        has_agents = (repo_path / 'AGENTS.md').exists()
        has_standards = (repo_path / '.github' / 'SKILL_STANDARDS.md').exists() or \
                       (repo_path / 'CONTRIBUTING.md').exists()
        has_pr_template = (repo_path / '.github' / 'PULL_REQUEST_TEMPLATE.md').exists()
        has_ci = (repo_path / '.github' / 'workflows' / 'validate.yml').exists()

        # Directory depth analysis
        dir_structure = defaultdict(int)
        for item in repo_path.rglob('*'):
            if item.is_file():
                depth = len(item.relative_to(repo_path).parts) - 1
                dir_structure[f'depth_{depth}'] += 1

        return RepoStructure(
            repo=repo_name,
            total_skills=len(skills),
            skills_with_references=skills_with_refs,
            reference_files=[str(r.relative_to(repo_path)) for r in references],
            design_systems=[str(d.relative_to(repo_path)) for d in design_systems],
            has_claude_md=has_claude,
            has_agents_md=has_agents,
            has_skill_standards=has_standards,
            has_pr_template=has_pr_template,
            has_validation_ci=has_ci,
            directory_structure=dict(dir_structure)
        )

    def find_patterns(self):
        """
        Extract and categorize patterns from analyzed skills

        Patterns detected:
        - progressive_disclosure: SKILL.md with references/
        - decision_tables: Decision matrices for routing
        - do_dont_examples: Side-by-side anti-patterns
        - response_contracts: Structured output schemas
        - version_guards: Version-specific feature gates
        - frontmatter_patterns: Structured metadata
        """
        for analysis in self.skill_analyses:
            repo = analysis.repo

            # Pattern: Progressive disclosure (SKILL.md + references/)
            if analysis.reference_link_count > 0:
                self.patterns_found['progressive_disclosure'].append({
                    'repo': repo,
                    'file': analysis.path,
                    'ref_links': analysis.reference_link_count
                })

            # Pattern: Decision tables
            if analysis.has_decision_tables:
                self.patterns_found['decision_tables'].append({
                    'repo': repo,
                    'file': analysis.path,
                    'count': analysis.decision_table_count
                })

            # Pattern: DO/DON'T examples
            if analysis.has_do_dont_examples:
                self.patterns_found['do_dont_examples'].append({
                    'repo': repo,
                    'file': analysis.path,
                    'count': analysis.do_dont_count
                })

            # Pattern: Response contracts
            if analysis.has_response_contract:
                self.patterns_found['response_contracts'].append({
                    'repo': repo,
                    'file': analysis.path
                })

            # Pattern: Version guards
            if analysis.has_version_guards:
                self.patterns_found['version_guards'].append({
                    'repo': repo,
                    'file': analysis.path,
                    'count': analysis.version_guard_count
                })

            # Pattern: Structured frontmatter
            if analysis.has_frontmatter and analysis.frontmatter:
                fm_keys = set(analysis.frontmatter.keys())
                self.patterns_found['frontmatter_patterns'].append({
                    'repo': repo,
                    'file': analysis.path,
                    'keys': list(fm_keys)
                })

    def analyze_all(self, verbose: bool = True):
        """
        Run analysis on all queued repositories

        Args:
            verbose: Print progress messages (default: True)
        """
        if verbose:
            print(f"[ANALYZE] Starting analysis of {len(self.repos_to_analyze)} repositories...")

        for repo_path, repo_name in self.repos_to_analyze:
            if not repo_path.exists():
                if verbose:
                    print(f"[WARN] Repository not found: {repo_path}")
                continue

            if verbose:
                print(f"\n[REPO] Analyzing {repo_name}...")

            # Analyze repository structure
            self.repo_structures[repo_name] = self.analyze_repo_structure(repo_path, repo_name)

            # Analyze all SKILL.md files
            for skill_file in repo_path.rglob('SKILL.md'):
                if verbose:
                    print(f"  - {skill_file.relative_to(repo_path)}")
                analysis = self.analyze_skill_file(skill_file, repo_name, base_path=repo_path)
                self.skill_analyses.append(analysis)

        # Extract patterns
        if verbose:
            print(f"\n[EXTRACT] Extracting patterns...")
        self.find_patterns()

        if verbose:
            print(f"\n[DONE] Analysis complete!")
            print(f"   - Total SKILL.md files analyzed: {len(self.skill_analyses)}")
            print(f"   - Patterns identified: {len(self.patterns_found)}")

    def generate_report(self) -> Dict:
        """
        Generate comprehensive analysis report

        Returns:
            Dictionary with summary, repo_structures, skill_analyses, patterns, statistics
        """
        return {
            'summary': {
                'total_skills_analyzed': len(self.skill_analyses),
                'repos_analyzed': list(self.repo_structures.keys()),
                'patterns_found': list(self.patterns_found.keys())
            },
            'repo_structures': {k: asdict(v) for k, v in self.repo_structures.items()},
            'skill_analyses': [asdict(s) for s in self.skill_analyses],
            'patterns': {k: v for k, v in self.patterns_found.items()},
            'statistics': self.generate_statistics()
        }

    def generate_statistics(self) -> Dict:
        """Generate comparative statistics across repositories"""
        stats = {
            'by_repo': defaultdict(lambda: defaultdict(int)),
            'averages': {},
            'pattern_adoption_rate': {}
        }

        for analysis in self.skill_analyses:
            repo = analysis.repo
            stats['by_repo'][repo]['total_skills'] += 1
            stats['by_repo'][repo]['total_lines'] += analysis.line_count
            if analysis.has_decision_tables:
                stats['by_repo'][repo]['with_decision_tables'] += 1
            if analysis.has_do_dont_examples:
                stats['by_repo'][repo]['with_do_dont'] += 1
            if analysis.has_response_contract:
                stats['by_repo'][repo]['with_response_contract'] += 1
            if analysis.has_version_guards:
                stats['by_repo'][repo]['with_version_guards'] += 1
            if analysis.reference_link_count > 0:
                stats['by_repo'][repo]['with_progressive_disclosure'] += 1

        # Calculate adoption rates
        for repo in stats['by_repo']:
            total = stats['by_repo'][repo]['total_skills']
            if total > 0:
                stats['pattern_adoption_rate'][repo] = {
                    'decision_tables': f"{stats['by_repo'][repo]['with_decision_tables'] / total * 100:.1f}%",
                    'do_dont_examples': f"{stats['by_repo'][repo]['with_do_dont'] / total * 100:.1f}%",
                    'response_contracts': f"{stats['by_repo'][repo]['with_response_contract'] / total * 100:.1f}%",
                    'version_guards': f"{stats['by_repo'][repo]['with_version_guards'] / total * 100:.1f}%",
                    'progressive_disclosure': f"{stats['by_repo'][repo]['with_progressive_disclosure'] / total * 100:.1f}%"
                }
                stats['averages'][repo] = {
                    'avg_lines_per_skill': stats['by_repo'][repo]['total_lines'] / total,
                    'avg_decision_tables_per_skill': sum(a.decision_table_count for a in self.skill_analyses if a.repo == repo) / total,
                    'avg_code_blocks_per_skill': sum(a.code_block_count for a in self.skill_analyses if a.repo == repo) / total
                }

        return dict(stats)
