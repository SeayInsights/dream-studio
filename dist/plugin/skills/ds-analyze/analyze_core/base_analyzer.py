#!/usr/bin/env python3
"""
Base Analyzer - Abstract base class for domain-specific repository analyzers

All domain analyzers (design, career, finance, real estate, etc.) inherit from this
and implement domain-specific capability detection and scoring.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import re


class BaseAnalyzer(ABC):
    """
    Abstract base class for domain-specific repository analyzers

    Subclasses must implement:
    - get_domain_name() -> str
    - get_capabilities() -> List[str]
    - analyze_capability(capability: str) -> Dict
    - score_repository() -> Dict[str, float]

    Optionally override:
    - get_unique_features() -> List[str]
    - generate_recommendations(comparison_repos) -> List[str]
    """

    def __init__(self, repo_path: Path, repo_name: str):
        """
        Initialize analyzer

        Args:
            repo_path: Path to repository directory
            repo_name: Name of repository (for reporting)
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo_name = repo_name
        self.results = {}

        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {self.repo_path}")

        if not self.repo_path.is_dir():
            raise ValueError(f"Not a directory: {self.repo_path}")

    # Abstract methods - must be implemented by subclasses

    @abstractmethod
    def get_domain_name(self) -> str:
        """
        Return domain name (e.g., 'design', 'career', 'finance')

        Returns:
            Domain name string
        """

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """
        Return list of capabilities this domain analyzer detects

        Example for design:
            ['color_systems', 'typography', 'components', ...]

        Example for career:
            ['resume_templates', 'job_search', 'interview_prep', ...]

        Returns:
            List of capability names
        """

    @abstractmethod
    def analyze_capability(self, capability: str) -> dict[str, Any]:
        """
        Analyze a specific capability in the repository

        Args:
            capability: Name of capability to analyze

        Returns:
            {
                'detected': bool,           # Was capability found?
                'score': float,             # Score 0-10
                'evidence': List[str],      # File paths or indicators
                'count': int,               # Quantitative metric
                'quality': str              # 'excellent' | 'good' | 'adequate' | 'weak'
            }
        """

    @abstractmethod
    def score_repository(self) -> dict[str, float]:
        """
        Calculate overall repository scoring for this domain

        Returns:
            {
                'capability1': 8.5,
                'capability2': 7.0,
                ...
                'overall_score': 7.8
            }
        """

    # Optional methods - can be overridden by subclasses

    def get_unique_features(self) -> list[str]:
        """
        Identify unique features this repo has that others don't

        Override in subclass for domain-specific unique feature detection

        Returns:
            List of unique feature descriptions
        """
        return []

    def generate_recommendations(self, comparison_repos: list[str] | None = None) -> list[str]:
        """
        Generate actionable recommendations

        Args:
            comparison_repos: Optional list of repo names to compare against

        Returns:
            List of recommendation strings
        """
        return []

    # Common utility methods available to all analyzers

    def find_files(self, pattern: str, case_sensitive: bool = False) -> list[Path]:
        """
        Find files matching glob pattern

        Args:
            pattern: Glob pattern (e.g., '*.csv', '**/SKILL.md')
            case_sensitive: Whether to match case-sensitively (default: False)

        Returns:
            List of matching file paths
        """
        if case_sensitive:
            return list(self.repo_path.rglob(pattern))
        # Case-insensitive matching
        pattern_lower = pattern.lower()
        all_files = list(self.repo_path.rglob("*"))
        matches = []

        for f in all_files:
            if f.is_file():
                relative = str(f.relative_to(self.repo_path)).lower()
                # Simple glob matching (supports * wildcard)
                regex_pattern = (
                    pattern_lower.replace("**/", ".*").replace("*", "[^/]*").replace("?", ".")
                )
                if re.match(regex_pattern, relative):
                    matches.append(f)

        return matches

    def count_files(self, pattern: str, case_sensitive: bool = False) -> int:
        """
        Count files matching pattern

        Args:
            pattern: Glob pattern
            case_sensitive: Whether to match case-sensitively

        Returns:
            Number of matching files
        """
        return len(self.find_files(pattern, case_sensitive))

    def search_content(
        self, pattern: str, file_extensions: list[str] | None = None, max_results: int = 100
    ) -> list[dict[str, Any]]:
        """
        Search file content for regex pattern (grep-like)

        Args:
            pattern: Regex pattern to search for
            file_extensions: Optional list of extensions to search (e.g., ['.md', '.py'])
            max_results: Maximum number of results to return

        Returns:
            List of {
                'file': str (relative path),
                'line': int,
                'content': str,
                'match': str
            }
        """
        results = []
        regex = re.compile(pattern, re.IGNORECASE)

        # Get all text files
        if file_extensions:
            files = []
            for ext in file_extensions:
                files.extend(self.find_files(f"**/*{ext}"))
        else:
            # Default to common text extensions
            text_exts = [
                ".md",
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".css",
                ".html",
                ".json",
                ".yml",
                ".yaml",
                ".txt",
            ]
            files = []
            for ext in text_exts:
                files.extend(self.find_files(f"**/*{ext}"))

        for file_path in files:
            if len(results) >= max_results:
                break

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.split("\n"), 1):
                    match = regex.search(line)
                    if match:
                        results.append(
                            {
                                "file": str(file_path.relative_to(self.repo_path)),
                                "line": line_num,
                                "content": line.strip(),
                                "match": match.group(0),
                            }
                        )
                        if len(results) >= max_results:
                            break
            except Exception:
                # Skip files that can't be read
                continue

        return results

    def has_directory(self, dir_name: str) -> bool:
        """
        Check if directory exists in repo

        Args:
            dir_name: Directory name or path

        Returns:
            True if directory exists
        """
        dir_path = self.repo_path / dir_name
        return dir_path.exists() and dir_path.is_dir()

    def has_file(self, file_name: str) -> bool:
        """
        Check if file exists in repo

        Args:
            file_name: File name or path

        Returns:
            True if file exists
        """
        file_path = self.repo_path / file_name
        return file_path.exists() and file_path.is_file()

    def read_file(self, file_path: str) -> str | None:
        """
        Read file content

        Args:
            file_path: Relative path to file

        Returns:
            File content as string, or None if file doesn't exist or can't be read
        """
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return None

        try:
            return full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    def count_lines_in_file(self, file_path: str) -> int:
        """
        Count lines in a file

        Args:
            file_path: Path to file

        Returns:
            Number of lines, or 0 if file doesn't exist
        """
        content = self.read_file(file_path)
        if content is None:
            return 0
        return len(content.split("\n"))

    def calculate_quality_score(self, count: int, thresholds: dict[str, int]) -> tuple[float, str]:
        """
        Calculate quality score and label based on count and thresholds

        Args:
            count: Numeric count of something
            thresholds: Dict with 'excellent', 'good', 'adequate' thresholds

        Returns:
            (score: float 0-10, quality: str)

        Example:
            thresholds = {'excellent': 8, 'good': 5, 'adequate': 2}
            calculate_quality_score(10, thresholds) -> (10.0, 'excellent')
            calculate_quality_score(6, thresholds) -> (7.5, 'good')
            calculate_quality_score(3, thresholds) -> (5.0, 'adequate')
            calculate_quality_score(1, thresholds) -> (2.5, 'weak')
        """
        if count >= thresholds.get("excellent", 8):
            return (10.0, "excellent")
        if count >= thresholds.get("good", 5):
            ratio = count / thresholds["excellent"]
            return (round(7.0 + ratio * 3, 1), "good")
        if count >= thresholds.get("adequate", 2):
            ratio = count / thresholds["good"]
            return (round(4.0 + ratio * 3, 1), "adequate")
        if count > 0:
            ratio = count / thresholds["adequate"]
            return (round(1.0 + ratio * 3, 1), "weak")
        return (0.0, "weak")

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(repo='{self.repo_name}', domain='{self.get_domain_name()}')"
        )
