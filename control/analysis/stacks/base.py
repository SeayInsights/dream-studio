"""Base class for stack adapters and adapter registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class StackAdapter(ABC):
    """Abstract base for framework/stack adapters."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def detect(self, path: Path) -> float: ...

    @abstractmethod
    def analyze_stack(self, path: Path) -> Dict[str, Any]: ...

    def get_build_command(self) -> Optional[str]:
        return None

    def get_test_command(self) -> Optional[str]:
        return None

    def get_rules(self) -> List[Dict[str, Any]]:
        return []


class AdapterRegistry:
    """Registry that maps adapter names to adapter instances."""

    def __init__(self) -> None:
        self._adapters: Dict[str, StackAdapter] = {}

    def register(self, adapter: StackAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get_adapter(self, name: str) -> Optional[StackAdapter]:
        return self._adapters.get(name)
