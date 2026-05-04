"""Project Intelligence - Automated codebase analysis and PRD generation."""

from analyze.discovery import discover_project
from analyze.research import research_stack
from analyze.audit import audit_architecture
from analyze.bugs import analyze_bugs
from analyze.synthesis import generate_prd
from analyze.engine import analyze_project

__all__ = [
    "analyze_project",
    "discover_project",
    "research_stack",
    "audit_architecture",
    "analyze_bugs",
    "generate_prd",
]
