"""Generic Python stack adapter."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import tomllib

from analyze.stacks.base import StackAdapter


class PythonGenericAdapter(StackAdapter):
    """Adapter for generic Python projects."""

    @property
    def name(self) -> str:
        """Adapter name."""
        return "python"

    def detect(self, path: Path) -> float:
        """
        Detect Python by checking for pyproject.toml, requirements.txt, setup.py.

        Args:
            path: Path to project root

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.0

        # Check for Python project files
        if (path / "pyproject.toml").exists():
            confidence += 0.5
        if (path / "requirements.txt").exists():
            confidence += 0.3
        if (path / "setup.py").exists():
            confidence += 0.2

        return min(1.0, confidence)

    def analyze_stack(self, path: Path) -> Dict[str, Any]:
        """
        Analyze Python project.

        Args:
            path: Path to project root

        Returns:
            Dictionary containing stack metadata
        """
        framework_version = None
        dependencies = []
        detected_frameworks = []

        # Parse pyproject.toml
        pyproject_path = path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)

                    # Extract dependencies
                    if "project" in data and "dependencies" in data["project"]:
                        deps = data["project"]["dependencies"]
                        dependencies = [dep.split("[")[0].split(">=")[0].split("==")[0].strip() for dep in deps]
                    elif "tool" in data and "poetry" in data["tool"] and "dependencies" in data["tool"]["poetry"]:
                        deps = data["tool"]["poetry"]["dependencies"]
                        dependencies = [k for k in deps.keys() if k != "python"]

                    # Detect framework
                    framework_keywords = {
                        "fastapi": "FastAPI",
                        "flask": "Flask",
                        "django": "Django",
                        "starlette": "Starlette",
                        "tornado": "Tornado",
                    }
                    for dep in dependencies:
                        dep_lower = dep.lower()
                        if dep_lower in framework_keywords:
                            detected_frameworks.append(framework_keywords[dep_lower])

            except (OSError, tomllib.TOMLDecodeError):
                pass

        # Parse requirements.txt
        requirements_path = path / "requirements.txt"
        if requirements_path.exists() and not dependencies:
            try:
                content = requirements_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep = line.split("==")[0].split(">=")[0].split("[")[0].strip()
                        dependencies.append(dep)

                        # Detect framework
                        framework_keywords = {
                            "fastapi": "FastAPI",
                            "flask": "Flask",
                            "django": "Django",
                            "starlette": "Starlette",
                            "tornado": "Tornado",
                        }
                        dep_lower = dep.lower()
                        if dep_lower in framework_keywords and framework_keywords[dep_lower] not in detected_frameworks:
                            detected_frameworks.append(framework_keywords[dep_lower])
            except OSError:
                pass

        # Detect config files
        config_files = []
        for config_name in ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "tox.ini", "pytest.ini"]:
            if (path / config_name).exists():
                config_files.append(config_name)

        # Detect entry points
        entry_points = []
        for entry in ["main.py", "app.py", "__main__.py", "src/main.py", "src/app.py"]:
            if (path / entry).exists():
                entry_points.append(entry)

        # Set framework name
        framework_name = "Python"
        if detected_frameworks:
            framework_name = f"Python ({', '.join(detected_frameworks)})"

        return {
            "framework": framework_name,
            "version": framework_version,
            "dependencies": dependencies,
            "config_files": config_files,
            "entry_points": entry_points,
        }

    def get_build_command(self) -> Optional[str]:
        """
        Return build command for Python.

        Returns:
            Build command string or None
        """
        # Return pip install if setup.py exists
        # Note: Removed setup.py check as it requires path parameter
        # This will be enhanced in Wave 3 when adapters get path context
        return None

    def get_test_command(self) -> Optional[str]:
        """
        Return test command for Python.

        Returns:
            Test command string
        """
        return "pytest"

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Return Python-specific analysis rules.

        Returns:
            List of rule dictionaries (placeholder for Wave 3)
        """
        return []
