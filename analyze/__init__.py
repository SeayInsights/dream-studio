"""Project Intelligence - Automated codebase analysis and PRD generation."""

from analyze.discovery import discover_project
from analyze.synthesis import generate_prd

__all__ = [
    "discover_project",
    "generate_prd",
]
