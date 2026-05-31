"""Multi-signal stack detection for project-intelligence platform.

Combines multiple detection strategies to identify project stack with confidence scoring.
"""

import json
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class StackSignal:
    """A signal indicating a particular stack."""

    name: str  # stack name
    confidence: float  # 0.0-1.0
    source: str  # where the signal came from
    evidence: List[str]  # supporting evidence


@dataclass
class DetectedStack:
    """Result of stack detection."""

    adapter: Optional[str]  # adapter name to use
    confidence: float  # overall confidence
    signals: List[StackSignal]  # all signals detected
    framework: Optional[str]  # framework name
    version: Optional[str]  # framework version if detected
    test_framework: Optional[str] = (
        None  # test framework for coverage parser dispatch (vitest/jest/pytest/mocha)
    )


def detect_stack(path: Path) -> DetectedStack:
    """
    Detect project stack using multiple signals.

    Args:
        path: Project root directory

    Returns:
        DetectedStack with adapter name and confidence
    """
    signals = []

    # Signal 1: Try repo_context detection
    try:
        from control.context.repo import _detect_stack

        detected = _detect_stack(path)
        if detected and isinstance(detected, dict):
            stack_name = detected.get("stack") or detected.get("framework")
            if stack_name and isinstance(stack_name, str):
                signals.append(
                    StackSignal(
                        name=stack_name.lower(),
                        confidence=0.7,
                        source="repo_context",
                        evidence=[f"Detected via repo_context: {stack_name}"],
                    )
                )
    except Exception:
        pass  # repo_context not available or failed

    # Signal 2: File-based detection
    signals.extend(_detect_by_files(path))

    # Combine signals into stack result
    result = _combine_signals(signals)

    # Augment with test framework for coverage parser dispatch
    result.test_framework = _detect_test_framework(path)

    return result


def _detect_by_files(path: Path) -> List[StackSignal]:
    """Detect stack by checking for key files."""
    signals = []

    # Check for Next.js
    if (path / "next.config.js").exists() or (path / "next.config.ts").exists():
        evidence = []
        if (path / "next.config.js").exists():
            evidence.append("next.config.js exists")
        if (path / "next.config.ts").exists():
            evidence.append("next.config.ts exists")

        signals.append(
            StackSignal(name="nextjs", confidence=0.9, source="file_check", evidence=evidence)
        )

    # Check for Astro
    if (path / "astro.config.mjs").exists() or (path / "astro.config.ts").exists():
        evidence = []
        if (path / "astro.config.mjs").exists():
            evidence.append("astro.config.mjs exists")
        if (path / "astro.config.ts").exists():
            evidence.append("astro.config.ts exists")

        signals.append(
            StackSignal(name="astro", confidence=0.9, source="file_check", evidence=evidence)
        )

    # Check for Python
    python_files = []
    if (path / "pyproject.toml").exists():
        python_files.append("pyproject.toml exists")
    if (path / "requirements.txt").exists():
        python_files.append("requirements.txt exists")
    if (path / "setup.py").exists():
        python_files.append("setup.py exists")

    if python_files:
        signals.append(
            StackSignal(name="python", confidence=0.8, source="file_check", evidence=python_files)
        )

    # Check for generic Node.js (only if no specific framework detected)
    if (path / "package.json").exists():
        has_framework = any(s.name in ("nextjs", "astro") for s in signals)
        if not has_framework:
            signals.append(
                StackSignal(
                    name="node",
                    confidence=0.6,
                    source="file_check",
                    evidence=["package.json exists (no specific framework)"],
                )
            )

    return signals


def _detect_test_framework(path: Path) -> Optional[str]:
    """
    Detect test framework for coverage parser dispatch (tst-001 and tst-010).

    Checks package.json devDependencies/dependencies for vitest/jest/mocha,
    and pyproject.toml / pytest.ini for pytest.

    Returns the test framework name string, or None if not detected.
    Priority: vitest > jest > mocha > pytest (JS/TS takes precedence when both present).
    """
    # Check package.json for JS/TS test frameworks
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with pkg_json.open(encoding="utf-8") as fh:
                pkg = json.load(fh)
            all_deps: dict = {}
            all_deps.update(pkg.get("dependencies", {}))
            all_deps.update(pkg.get("devDependencies", {}))
            if "vitest" in all_deps:
                return "vitest"
            if "jest" in all_deps or "@jest/core" in all_deps:
                return "jest"
            if "mocha" in all_deps:
                return "mocha"
        except Exception:
            pass  # malformed package.json — fall through

    # Check for Python test frameworks
    if (path / "pyproject.toml").exists() or (path / "pytest.ini").exists():
        return "pytest"

    return None


def _combine_signals(signals: List[StackSignal]) -> DetectedStack:
    """Combine signals and select best match."""
    if not signals:
        return DetectedStack(adapter=None, confidence=0.0, signals=[], framework=None, version=None)

    # Group by stack name, take max confidence
    stack_scores = {}
    for signal in signals:
        if signal.name not in stack_scores:
            stack_scores[signal.name] = signal.confidence
        else:
            # Multiple signals boost confidence (20% of signal confidence added)
            stack_scores[signal.name] = min(
                1.0, stack_scores[signal.name] + signal.confidence * 0.2
            )

    # Best match
    best_name = max(stack_scores.keys(), key=lambda k: stack_scores[k])
    best_confidence = stack_scores[best_name]

    # Framework name mapping
    framework_names = {"nextjs": "Next.js", "astro": "Astro", "python": "Python", "node": "Node.js"}

    return DetectedStack(
        adapter=best_name,
        confidence=best_confidence,
        signals=signals,
        framework=framework_names.get(best_name, best_name.title()),
        version=None,  # Version detection in Wave 3
    )
