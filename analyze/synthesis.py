"""
Synthesis phase for Project Intelligence Platform.
Generates PRDs from discovery and analysis data.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone


def generate_prd(
    project_id: str,
    project_data: Dict[str, Any],
    stack: Dict[str, Any],
    research: Optional[Dict[str, Any]] = None,
    audit: Optional[Dict[str, Any]] = None,
    bugs: Optional[Dict[str, Any]] = None
) -> Path:  # noqa: ARG001 (research/audit unused until Wave 3)
    """
    Generate PRD from project analysis data.

    Args:
        project_id: Unique project identifier
        project_data: Output from discover_project()
        stack: Stack analysis from adapter.analyze_stack()
        research: Research findings (optional, Wave 3+)
        audit: Architecture audit (optional, Wave 3+)
        bugs: Bug detection results (optional, Wave 3+)

    Returns:
        Path to generated PRD file
    """
    project_name = project_data.get("project_name", "unknown")

    # Create specs directory
    specs_dir = Path(".planning/specs") / project_name
    specs_dir.mkdir(parents=True, exist_ok=True)

    # Generate PRD content
    prd_content = _generate_prd_content(project_id, project_data, stack, research, audit, bugs)

    # Write PRD file
    prd_path = specs_dir / "prd.md"
    prd_path.write_text(prd_content, encoding="utf-8")

    # Store in ds_documents
    _store_in_documents(project_name, prd_path, prd_content)

    return prd_path


def _generate_prd_content(
    project_id: str,
    project_data: Dict[str, Any],
    stack: Dict[str, Any],
    research: Optional[Dict[str, Any]],
    audit: Optional[Dict[str, Any]],
    bugs: Optional[Dict[str, Any]]
) -> str:
    """Generate PRD markdown content."""

    timestamp = datetime.now(timezone.utc).isoformat()
    project_name = project_data.get("project_name", "unknown")
    detected_stack = project_data.get("detected_stack", "unknown")

    # Extract metrics
    total_files = project_data.get("file_inventory", {}).get("total_files", 0)
    loc_data = project_data.get("lines_of_code", {})
    total_loc = loc_data.get("total", 0)
    languages = project_data.get("languages", [])
    primary_language = languages[0] if languages else "unknown"

    git_meta = project_data.get("git_metadata", {})
    repo_age_days = git_meta.get("repo_age_days", 0)
    contributors = git_meta.get("contributors", [])
    contributor_count = len(contributors)

    project_type = project_data.get("project_type", "unknown")

    # Build PRD sections
    sections = []

    # Header
    sections.append(f"# Project Requirements Document: {project_name}\n")
    sections.append(f"**Generated:** {timestamp}")
    sections.append(f"**Analyzer:** Project Intelligence Platform v2.0")
    sections.append(f"**Stack:** {detected_stack}\n")
    sections.append("---\n")

    # Executive Summary
    sections.append("## Executive Summary\n")
    sections.append(f"Project: **{project_name}**\n")
    sections.append(f"**Key Metrics:**")
    sections.append(f"- Total Files: {total_files:,}")
    sections.append(f"- Lines of Code: {total_loc:,}")
    sections.append(f"- Primary Language: {primary_language}")
    sections.append(f"- Project Age: {repo_age_days} days ({repo_age_days // 365} years)")
    sections.append(f"- Contributors: {contributor_count}\n")
    sections.append(f"**Current State:** {project_type.title()}\n")
    sections.append("---\n")

    # Technical Stack
    sections.append("## Technical Stack\n")

    framework = stack.get("framework", "Unknown")
    version = stack.get("version", "unknown")
    dependencies = stack.get("dependencies", [])

    sections.append(f"**Detected Stack:** {detected_stack}")
    sections.append(f"**Framework:** {framework} {version}\n")
    sections.append(f"**Dependencies:** ({len(dependencies)} total)\n")

    if dependencies:
        sections.append("Top dependencies:")
        for dep in dependencies[:10]:
            sections.append(f"- {dep}")
        sections.append("")

    # Language breakdown
    by_language = loc_data.get("by_language", {})
    if by_language:
        sections.append("**Languages:**\n")
        for lang, lines in sorted(by_language.items(), key=lambda x: x[1], reverse=True):
            percentage = (lines / total_loc * 100) if total_loc > 0 else 0
            sections.append(f"- {lang}: {lines:,} lines ({percentage:.1f}%)")
        sections.append("")

    # Build tools
    build_cmd = stack.get("build_command")
    test_cmd = stack.get("test_command")
    sections.append("**Build Tools:**")
    if build_cmd:
        sections.append(f"- Build Command: `{build_cmd}`")
    if test_cmd:
        sections.append(f"- Test Command: `{test_cmd}`")
    sections.append("\n---\n")

    # Architecture
    sections.append("## Architecture\n")
    sections.append("**Project Structure:**\n")

    # Top-level directories
    by_directory = project_data.get("file_inventory", {}).get("by_directory", {})
    top_dirs = sorted(by_directory.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_dirs:
        sections.append("Key directories:")
        for dir_name, file_count in top_dirs:
            sections.append(f"- `{dir_name}/` - {file_count} files")
        sections.append("")

    # Entry points
    entry_points = project_data.get("entry_points", [])
    if entry_points:
        sections.append("**Entry Points:**")
        for ep in entry_points:
            sections.append(f"- `{ep}`")
        sections.append("")

    # Config files
    config_files = project_data.get("config_files", [])
    if config_files:
        sections.append("**Configuration Files:**")
        for cf in config_files:
            sections.append(f"- `{cf}`")
        sections.append("")

    sections.append("\n---\n")

    # Known Issues
    sections.append("## Known Issues\n")
    if bugs and bugs.get("bugs"):
        sections.append(f"**{len(bugs['bugs'])} bugs detected** (automated analysis)\n")
        # List critical/high bugs
        critical = [b for b in bugs["bugs"] if b.get("severity") == "critical"]
        high = [b for b in bugs["bugs"] if b.get("severity") == "high"]

        if critical:
            sections.append("### Critical Issues:")
            for bug in critical[:5]:
                sections.append(f"- **{bug.get('file')}:{bug.get('line')}** - {bug.get('issue')}")
            sections.append("")

        if high:
            sections.append("### High Priority:")
            for bug in high[:5]:
                sections.append(f"- **{bug.get('file')}:{bug.get('line')}** - {bug.get('issue')}")
            sections.append("")
    else:
        sections.append("No automated bug analysis available yet (Wave 3+).\n")

    sections.append("---\n")

    # Risk Assessment
    sections.append("## Risk Assessment\n")
    sections.append("**Technical Debt:** Pending deep analysis (Wave 3)\n")
    sections.append("**Security Concerns:** Pending security scan (Wave 4)\n")
    sections.append("**Maintainability Score:** Pending\n")
    sections.append("---\n")

    # Development Roadmap
    sections.append("## Development Roadmap\n")
    sections.append("**Recommended Next Steps:**\n")

    if project_type == "greenfield":
        sections.append("1. Establish CI/CD pipeline")
        sections.append("2. Add comprehensive test coverage")
        sections.append("3. Document API/architecture")
    else:  # brownfield
        sections.append("1. Audit technical debt and prioritize refactoring")
        sections.append("2. Improve test coverage in critical paths")
        sections.append("3. Update dependencies and address security vulnerabilities")

    sections.append("\n---\n")

    # Appendix
    sections.append("## Appendix\n")
    sections.append("**Analysis Metadata:**")
    sections.append(f"- Analysis Run ID: {project_id}")
    sections.append(f"- Analysis Date: {timestamp}")
    sections.append("- Discovery Phase: ✓ Complete")
    sections.append("- Research Phase: Pending (Wave 3)")
    sections.append("- Audit Phase: Pending (Wave 3)")
    sections.append("- Bug Detection: Pending (Wave 3)")
    sections.append("- Synthesis Phase: ✓ Complete\n")

    sections.append("**Source Files:**")
    sections.append(f"- Project Path: `{project_data.get('project_path')}`")
    sections.append(f"- PRD Location: `.planning/specs/{project_name}/prd.md`\n")
    sections.append("---\n")
    sections.append("*Generated by Project Intelligence Platform - dream-studio*\n")

    return "\n".join(sections)


def _store_in_documents(project_name: str, prd_path: Path, content: str) -> None:
    """Store PRD in ds_documents table."""
    try:
        import sys
        from pathlib import Path as SysPath
        sys.path.insert(0, str(SysPath(__file__).resolve().parents[1] / "hooks"))

        from lib.document_store import DocumentStore

        DocumentStore.create(
            doc_type="prd",
            title=f"PRD: {project_name}",
            content=content,
            project_id=project_name,
            format="markdown",
            metadata={
                "project_name": project_name,
                "generated_by": "project_intelligence_platform",
                "version": "2.0",
                "path": str(prd_path)
            },
            tags=["prd", "analysis", "project-intelligence"],
            keywords=f"prd {project_name} requirements analysis"
        )
    except Exception:
        pass  # Document store update is optional
