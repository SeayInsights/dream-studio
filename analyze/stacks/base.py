"""Base adapter system for stack-specific analysis."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional


class StackAdapter(ABC):
    """Base adapter for stack-specific analysis."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name (e.g., 'nextjs', 'astro', 'python')."""
        pass

    @abstractmethod
    def detect(self, path: Path) -> float:
        """
        Detect if this stack is present.

        Args:
            path: Path to project root

        Returns:
            Confidence score 0.0-1.0
        """
        pass

    @abstractmethod
    def analyze_stack(self, path: Path) -> Dict[str, Any]:
        """
        Analyze the stack and return metadata.

        Args:
            path: Path to project root

        Returns:
            Dictionary containing:
                - framework: str - Framework name
                - version: str - Version string
                - dependencies: List[str] - List of dependencies
                - config_files: List[str] - Configuration files found
                - entry_points: List[str] - Entry point files
        """
        pass

    @abstractmethod
    def get_build_command(self) -> Optional[str]:
        """
        Return build command for this stack.

        Returns:
            Build command (e.g., 'npm run build') or None if not applicable
        """
        pass

    @abstractmethod
    def get_test_command(self) -> Optional[str]:
        """
        Return test command for this stack.

        Returns:
            Test command (e.g., 'npm test') or None if not applicable
        """
        pass

    @abstractmethod
    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Return stack-specific analysis rules.

        Returns:
            List of rule dictionaries, each containing:
                - id: str - Rule identifier
                - category: str - 'best_practice', 'security', 'performance'
                - description: str - Human-readable description
                - check: callable - Function(path: Path) -> List[violation_dict]
        """
        pass


class AdapterRegistry:
    """Registry for stack adapters."""

    def __init__(self):
        self._adapters: Dict[str, StackAdapter] = {}

    def register(self, adapter: StackAdapter) -> None:
        """
        Register an adapter.

        Args:
            adapter: StackAdapter instance to register
        """
        self._adapters[adapter.name] = adapter

    def detect_adapter(self, path: Path) -> Optional[StackAdapter]:
        """
        Detect which adapter to use based on confidence scores.

        Args:
            path: Path to project root

        Returns:
            Adapter with highest confidence (>0.5), or None if no match
        """
        best_adapter = None
        best_score = 0.5  # minimum threshold

        for adapter in self._adapters.values():
            score = adapter.detect(path)
            if score > best_score:
                best_score = score
                best_adapter = adapter

        return best_adapter

    def list_adapters(self) -> List[str]:
        """
        List all registered adapter names.

        Returns:
            List of adapter names
        """
        return list(self._adapters.keys())

    def get_adapter(self, name: str) -> Optional[StackAdapter]:
        """
        Get adapter by name.

        Args:
            name: Adapter name

        Returns:
            StackAdapter instance or None if not found
        """
        return self._adapters.get(name)
