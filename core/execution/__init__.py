"""Real execution layer for repository actions.

Tool-backed execution helpers are loaded lazily so package import remains
side-effect free and does not imply GitHub, CI, or local command availability.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "GitHubAdapter": ("core.execution.github_adapter", "GitHubAdapter"),
    "GitHubExecutionResult": ("core.execution.github_adapter", "GitHubExecutionResult"),
    "CICollector": ("core.execution.ci_collector", "CICollector"),
    "CIResult": ("core.execution.ci_collector", "CIResult"),
    "TestResult": ("core.execution.ci_collector", "TestResult"),
    "RealFeedbackEngine": ("core.execution.real_feedback", "RealFeedbackEngine"),
    "RealActionFeedback": ("core.execution.real_feedback", "RealActionFeedback"),
}

__all__ = [
    "GitHubAdapter",
    "GitHubExecutionResult",
    "CICollector",
    "CIResult",
    "TestResult",
    "RealFeedbackEngine",
    "RealActionFeedback",
]


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
