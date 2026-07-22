"""File-based signal detection and signal combination for stack detection.

WO-GF-CONTROL-INSTALL-split: see detector.py facade docstring.
"""

from __future__ import annotations

from pathlib import Path

from .detector_shared import DetectedStack, StackSignal


def _detect_by_files(path: Path) -> list[StackSignal]:
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

    # Check for Go
    if (path / "go.mod").exists():
        signals.append(
            StackSignal(
                name="go",
                confidence=0.95,
                source="file_check",
                evidence=["go.mod exists"],
            )
        )

    # Check for Rust
    if (path / "Cargo.toml").exists():
        signals.append(
            StackSignal(
                name="rust",
                confidence=0.95,
                source="file_check",
                evidence=["Cargo.toml exists"],
            )
        )

    return signals


def _combine_signals(signals: list[StackSignal]) -> DetectedStack:
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
    framework_names = {
        "nextjs": "Next.js",
        "astro": "Astro",
        "python": "Python",
        "node": "Node.js",
        "go": "Go",
        "rust": "Rust",
    }

    return DetectedStack(
        adapter=best_name,
        confidence=best_confidence,
        signals=signals,
        framework=framework_names.get(best_name, best_name.title()),
        version=None,  # Version detection in Wave 3
    )
