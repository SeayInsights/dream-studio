"""Stack adapter system for project intelligence."""

from analyze.stacks.base import StackAdapter, AdapterRegistry
from analyze.stacks.nextjs import NextJSAdapter
from analyze.stacks.astro import AstroAdapter
from analyze.stacks.python_generic import PythonGenericAdapter

__all__ = [
    "StackAdapter",
    "AdapterRegistry",
    "NextJSAdapter",
    "AstroAdapter",
    "PythonGenericAdapter",
]
