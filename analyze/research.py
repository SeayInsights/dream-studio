from pathlib import Path
from typing import Dict, Any
import json

def research_stack(stack: Dict[str, Any], project_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Research stack compatibility and best practices.

    Args:
        stack: Stack metadata from adapter.analyze_stack()
        project_data: Project discovery data

    Returns:
        {
            "stack_name": str,
            "compatibility": {
                "deployment": List[str],  # compatible platforms
                "databases": List[str],
                "caching": List[str]
            },
            "best_practices": List[str],
            "common_issues": List[str],
            "recommended_tools": List[str],
            "research_notes": str
        }
    """
    stack_name = stack.get("framework", "unknown").lower()
    detected_stack = project_data.get("detected_stack", "").lower()

    # Static knowledge base (placeholder for web search)
    knowledge = _get_stack_knowledge(detected_stack or stack_name)

    # Cache in ds_documents
    _cache_research(stack_name, knowledge)

    return knowledge

def _get_stack_knowledge(stack_name: str) -> Dict[str, Any]:
    """Static knowledge base for known stacks."""

    knowledge_base = {
        "nextjs": {
            "stack_name": "Next.js",
            "compatibility": {
                "deployment": ["Vercel", "Netlify", "AWS Amplify", "Cloudflare Pages"],
                "databases": ["PostgreSQL", "MongoDB", "MySQL", "PlanetScale", "Supabase"],
                "caching": ["Redis", "Memcached", "Vercel KV"]
            },
            "best_practices": [
                "Use App Router for new projects (Next.js 13+)",
                "Enable Image Optimization",
                "Implement Incremental Static Regeneration (ISR)",
                "Use Server Components where possible",
                "Configure caching headers properly"
            ],
            "common_issues": [
                "Hydration mismatches between server/client",
                "Large bundle sizes (check build output)",
                "API route performance (consider edge functions)",
                "CORS issues with external APIs"
            ],
            "recommended_tools": [
                "TypeScript for type safety",
                "ESLint + Prettier for code quality",
                "Vercel Analytics for performance monitoring",
                "next-seo for SEO optimization"
            ],
            "research_notes": "Next.js is a production-ready React framework with excellent Vercel integration. " +
                            "The App Router (13+) represents a paradigm shift from Pages Router. " +
                            "Consider migration strategy if on Pages Router."
        },
        "astro": {
            "stack_name": "Astro",
            "compatibility": {
                "deployment": ["Netlify", "Vercel", "Cloudflare Pages", "GitHub Pages"],
                "databases": ["Any via server endpoints", "Supabase", "PlanetScale"],
                "caching": ["CDN caching", "Netlify Edge Functions"]
            },
            "best_practices": [
                "Leverage partial hydration",
                "Use framework integrations (@astrojs/react, @astrojs/vue)",
                "Optimize images with @astrojs/image",
                "Minimize client-side JavaScript",
                "Use content collections for type-safe content"
            ],
            "common_issues": [
                "Hydration directive confusion (client:load vs client:idle)",
                "Framework component compatibility",
                "SSR vs SSG configuration",
                "Asset optimization configuration"
            ],
            "recommended_tools": [
                "TypeScript",
                "Tailwind CSS",
                "MDX for content",
                "@astrojs/partytown for third-party scripts"
            ],
            "research_notes": "Astro excels at content-heavy sites with minimal JavaScript. " +
                            "Island architecture allows mixing frameworks. " +
                            "Consider for blogs, documentation, marketing sites."
        },
        "python": {
            "stack_name": "Python",
            "compatibility": {
                "deployment": ["AWS Lambda", "Google Cloud Functions", "Heroku", "Docker", "VPS"],
                "databases": ["PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis"],
                "caching": ["Redis", "Memcached", "Django cache framework"]
            },
            "best_practices": [
                "Use virtual environments (venv/poetry)",
                "Pin dependencies in requirements.txt",
                "Follow PEP 8 style guide",
                "Implement proper error handling",
                "Use type hints (Python 3.5+)",
                "Write tests (pytest recommended)"
            ],
            "common_issues": [
                "Dependency conflicts",
                "Global state in multi-threaded apps",
                "Memory leaks in long-running processes",
                "Slow startup time (import optimization needed)"
            ],
            "recommended_tools": [
                "pytest for testing",
                "black for code formatting",
                "mypy for type checking",
                "ruff for linting",
                "poetry for dependency management"
            ],
            "research_notes": "Python ecosystem is mature with excellent libraries. " +
                            "Consider framework choice: FastAPI (modern APIs), Flask (lightweight), Django (full-stack). " +
                            "Async support (asyncio) recommended for I/O-bound applications."
        }
    }

    # Return knowledge or generic placeholder
    return knowledge_base.get(stack_name, {
        "stack_name": stack_name.title(),
        "compatibility": {
            "deployment": ["Research needed"],
            "databases": ["Research needed"],
            "caching": ["Research needed"]
        },
        "best_practices": ["Pending web search integration"],
        "common_issues": ["Pending web search integration"],
        "recommended_tools": ["Pending web search integration"],
        "research_notes": f"Stack: {stack_name}. Full research will be available in Wave 4+ with web search integration."
    })

def _cache_research(stack_name: str, knowledge: Dict[str, Any]) -> None:
    """Cache research in ds_documents."""
    try:
        import sys
        from pathlib import Path as SysPath
        sys.path.insert(0, str(SysPath(__file__).resolve().parents[1] / "hooks"))

        from lib.document_store import DocumentStore

        content = json.dumps(knowledge, indent=2)

        DocumentStore.create(
            doc_type="research",
            title=f"Stack Research: {stack_name}",
            content=content,
            format="json",
            metadata={
                "stack": stack_name,
                "research_type": "static_knowledge",
                "version": "1.0"
            },
            tags=["research", "stack", stack_name],
            ttl_days=90  # Cache for 90 days
        )
    except Exception:
        pass  # Caching is optional
