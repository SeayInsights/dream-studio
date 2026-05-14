"""Stack adapters for project analysis."""

from control.analysis.stacks.base import AdapterRegistry, StackAdapter
from control.analysis.stacks.astro import AstroAdapter
from control.analysis.stacks.nextjs import NextJSAdapter
from control.analysis.stacks.python_generic import PythonGenericAdapter

__all__ = [
    "AdapterRegistry",
    "StackAdapter",
    "AstroAdapter",
    "NextJSAdapter",
    "PythonGenericAdapter",
]
