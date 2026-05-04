"""Next.js stack adapter."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json

from analyze.stacks.base import StackAdapter


class NextJSAdapter(StackAdapter):
    """Adapter for Next.js projects."""

    @property
    def name(self) -> str:
        """Adapter name."""
        return "nextjs"

    def detect(self, path: Path) -> float:
        """
        Detect Next.js by checking for next.config.* and package.json.

        Args:
            path: Path to project root

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.0

        # Check for next.config files
        if (path / "next.config.js").exists() or (path / "next.config.ts").exists() or (path / "next.config.mjs").exists():
            confidence += 0.6

        # Check package.json for "next" dependency
        package_json = path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "next" in deps:
                    confidence += 0.4
            except (json.JSONDecodeError, OSError):
                pass

        return min(1.0, confidence)

    def analyze_stack(self, path: Path) -> Dict[str, Any]:
        """
        Analyze Next.js project.

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
                framework_version = deps.get("next", "unknown")
                dependencies = list(deps.keys())
            except (json.JSONDecodeError, OSError):
                pass

        # Detect config files
        config_files = []
        for config_name in ["next.config.js", "next.config.ts", "next.config.mjs", "package.json", "tsconfig.json"]:
            if (path / config_name).exists():
                config_files.append(config_name)

        # Detect entry points
        entry_points = []
        for entry in ["pages/", "app/", "src/pages/", "src/app/"]:
            if (path / entry).exists():
                entry_points.append(entry)

        return {
            "framework": "Next.js",
            "version": framework_version,
            "dependencies": dependencies,
            "config_files": config_files,
            "entry_points": entry_points,
        }

    def get_build_command(self) -> Optional[str]:
        """
        Return build command for Next.js.

        Returns:
            Build command string
        """
        return "npm run build"

    def get_test_command(self) -> Optional[str]:
        """
        Return test command for Next.js.

        Returns:
            Test command string
        """
        return "npm test"

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Return Next.js-specific analysis rules.

        Returns:
            List of rule dictionaries (placeholder for Wave 3)
        """
        return []
