"""Astro stack adapter."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json

from analyze.stacks.base import StackAdapter


class AstroAdapter(StackAdapter):
    """Adapter for Astro projects."""

    @property
    def name(self) -> str:
        """Adapter name."""
        return "astro"

    def detect(self, path: Path) -> float:
        """
        Detect Astro by checking for astro.config.* and package.json.

        Args:
            path: Path to project root

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.0

        # Check for astro.config files
        if (path / "astro.config.mjs").exists() or (path / "astro.config.ts").exists() or (path / "astro.config.js").exists():
            confidence += 0.6

        # Check package.json for "astro" dependency or @astrojs/* packages
        package_json = path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "astro" in deps:
                    confidence += 0.4
                elif any(dep.startswith("@astrojs/") for dep in deps.keys()):
                    confidence += 0.3
            except (json.JSONDecodeError, OSError):
                pass

        return min(1.0, confidence)

    def analyze_stack(self, path: Path) -> Dict[str, Any]:
        """
        Analyze Astro project.

        Args:
            path: Path to project root

        Returns:
            Dictionary containing stack metadata
        """
        package_json = path / "package.json"
        framework_version = None
        dependencies = []

        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = data.get("dependencies", {})
                framework_version = deps.get("astro", "unknown")
                dependencies = list(deps.keys())
            except (json.JSONDecodeError, OSError):
                pass

        # Detect config files
        config_files = []
        for config_name in ["astro.config.mjs", "astro.config.ts", "astro.config.js", "package.json", "tsconfig.json"]:
            if (path / config_name).exists():
                config_files.append(config_name)

        # Detect entry points
        entry_points = []
        for entry in ["src/pages/", "src/components/", "src/layouts/"]:
            if (path / entry).exists():
                entry_points.append(entry)

        return {
            "framework": "Astro",
            "version": framework_version,
            "dependencies": dependencies,
            "config_files": config_files,
            "entry_points": entry_points,
        }

    def get_build_command(self) -> Optional[str]:
        """
        Return build command for Astro.

        Returns:
            Build command string
        """
        return "npm run build"

    def get_test_command(self) -> Optional[str]:
        """
        Return test command for Astro.

        Returns:
            Test command string
        """
        return "npm test"

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Return Astro-specific analysis rules.

        Returns:
            List of rule dictionaries (placeholder for Wave 3)
        """
        return []
