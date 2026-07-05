#!/usr/bin/env python3
"""
Domain Analyzer Registry

Central registry for all domain-specific repository analyzers.
Supports registration, retrieval, and auto-detection of domain analyzers.
"""

from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base_analyzer import BaseAnalyzer


class DomainAnalyzerRegistry:
    """
    Registry of available domain analyzers

    Usage:
        # Register an analyzer
        DomainAnalyzerRegistry.register('design', DesignSkillAnalyzer)

        # Get analyzer instance
        analyzer = DomainAnalyzerRegistry.get_analyzer('design', repo_path, repo_name)

        # Auto-detect domain
        domain = DomainAnalyzerRegistry.auto_detect_domain(repo_path)

        # List available domains
        domains = DomainAnalyzerRegistry.list_domains()
    """

    _analyzers: dict[str, type[BaseAnalyzer]] = {}
    _domain_markers: dict[str, list[str]] = {}

    @classmethod
    def register(
        cls, domain: str, analyzer_class: type[BaseAnalyzer], markers: list[str] | None = None
    ):
        """
        Register a domain analyzer

        Args:
            domain: Domain name (e.g., 'design', 'career', 'finance')
            analyzer_class: Analyzer class (must inherit from BaseAnalyzer)
            markers: Optional list of file/directory markers for auto-detection

        Raises:
            TypeError: If analyzer_class doesn't inherit from BaseAnalyzer
        """
        if not issubclass(analyzer_class, BaseAnalyzer):
            raise TypeError(f"{analyzer_class} must inherit from BaseAnalyzer")

        cls._analyzers[domain] = analyzer_class

        if markers:
            cls._domain_markers[domain] = markers

    @classmethod
    def get_analyzer(cls, domain: str, repo_path: Path, repo_name: str) -> BaseAnalyzer:
        """
        Get analyzer instance for domain

        Args:
            domain: Domain name
            repo_path: Path to repository
            repo_name: Name of repository

        Returns:
            Initialized analyzer instance

        Raises:
            ValueError: If domain is not registered
        """
        if domain not in cls._analyzers:
            available = ", ".join(cls.list_domains())
            raise ValueError(
                f"Unknown domain: '{domain}'. "
                f"Available domains: {available}. "
                f"Use --list-domains to see all registered analyzers."
            )

        analyzer_class = cls._analyzers[domain]
        return analyzer_class(repo_path, repo_name)

    @classmethod
    def list_domains(cls) -> list[str]:
        """
        List all registered domains

        Returns:
            List of domain names
        """
        return sorted(cls._analyzers.keys())

    @classmethod
    def get_domain_info(cls) -> dict[str, dict[str, any]]:
        """
        Get information about all registered domains

        Returns:
            {
                'design': {
                    'class': 'DesignSkillAnalyzer',
                    'markers': ['DESIGN.md', 'colors.csv', ...],
                    'capabilities_count': 10
                },
                ...
            }
        """
        info = {}

        for domain, analyzer_class in cls._analyzers.items():
            # Create temporary instance to get capabilities
            temp_path = Path(".")
            try:
                temp_analyzer = analyzer_class(temp_path, "temp")
                capabilities = temp_analyzer.get_capabilities()
            except Exception:
                capabilities = []

            info[domain] = {
                "class": analyzer_class.__name__,
                "markers": cls._domain_markers.get(domain, []),
                "capabilities_count": len(capabilities),
                "capabilities": capabilities,
            }

        return info

    @classmethod
    def auto_detect_domain(cls, repo_path: Path, verbose: bool = False) -> str:
        """
        Auto-detect most likely domain based on repo contents

        Args:
            repo_path: Path to repository
            verbose: Print detection scoring

        Returns:
            Domain name (e.g., 'design', 'career', 'finance')
            Returns 'general' if no domain scores above threshold
        """
        repo_path = Path(repo_path)

        if not repo_path.exists():
            return "general"

        domain_scores = {}

        # Score each domain based on markers
        for domain, markers in cls._domain_markers.items():
            score = 0

            for marker in markers:
                # Check if marker is a file or directory
                matches = list(repo_path.rglob(f"**/*{marker}*"))
                if matches:
                    score += 1
                    if verbose:
                        print(f"[DETECT] {domain}: found '{marker}' ({len(matches)} matches)")

            domain_scores[domain] = score

        if verbose:
            print(f"\n[DETECT] Domain scores: {domain_scores}")

        # Return domain with highest score, or 'general' if all zero
        if not domain_scores or max(domain_scores.values()) == 0:
            if verbose:
                print("[DETECT] No domain markers found, defaulting to 'general'")
            return "general"

        best_domain = max(domain_scores, key=domain_scores.get)

        if verbose:
            print(f"[DETECT] Detected domain: {best_domain} (score: {domain_scores[best_domain]})")

        return best_domain

    @classmethod
    def is_registered(cls, domain: str) -> bool:
        """
        Check if domain is registered

        Args:
            domain: Domain name

        Returns:
            True if domain is registered
        """
        return domain in cls._analyzers

    @classmethod
    def unregister(cls, domain: str) -> bool:
        """
        Unregister a domain analyzer

        Args:
            domain: Domain name

        Returns:
            True if domain was unregistered, False if not found
        """
        if domain in cls._analyzers:
            del cls._analyzers[domain]
            if domain in cls._domain_markers:
                del cls._domain_markers[domain]
            return True
        return False

    @classmethod
    def clear(cls):
        """Clear all registered analyzers (for testing)"""
        cls._analyzers.clear()
        cls._domain_markers.clear()


# Import and register all available domain analyzers
def _register_builtin_analyzers():
    """Register all built-in domain analyzers"""
    try:
        from .design import DesignSkillAnalyzer

        DomainAnalyzerRegistry.register(
            "design",
            DesignSkillAnalyzer,
            markers=[
                "DESIGN.md",
                "colors.csv",
                "typography.md",
                "ui-reasoning.csv",
                "brand-spec.md",
                "color-and-contrast.md",
                "device-frames",
                "anti-pattern",
            ],
        )
    except ImportError:
        pass  # Design analyzer not yet implemented

    try:
        from .career import CareerSkillAnalyzer

        DomainAnalyzerRegistry.register(
            "career",
            CareerSkillAnalyzer,
            markers=[
                "resume",
                "job_search",
                "interview",
                "cover_letter",
                "career",
                "salary",
                "portfolio",
                "ats",
            ],
        )
    except ImportError:
        pass  # Career analyzer not yet implemented

    try:
        from .finance import FinanceSkillAnalyzer

        DomainAnalyzerRegistry.register(
            "finance",
            FinanceSkillAnalyzer,
            markers=[
                "accounting",
                "invoice",
                "ledger",
                "tax",
                "budget",
                "financial",
                "expense",
                "reconciliation",
                "quickbooks",
                "xero",
            ],
        )
    except ImportError:
        pass  # Finance analyzer not yet implemented

    try:
        from .real_estate import RealEstateSkillAnalyzer

        DomainAnalyzerRegistry.register(
            "real_estate",
            RealEstateSkillAnalyzer,
            markers=[
                "property",
                "mls",
                "zillow",
                "realtor",
                "appraisal",
                "real-estate",
                "real_estate",
                "comp-analysis",
            ],
        )
    except ImportError:
        pass  # Real estate analyzer not yet implemented


# Auto-register built-in analyzers on module import
_register_builtin_analyzers()
