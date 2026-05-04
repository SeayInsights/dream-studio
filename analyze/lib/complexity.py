"""
Complexity analysis module for project-intelligence platform.

Analyzes code complexity including cyclomatic complexity, function metrics,
and identifies god functions/objects.
"""

from pathlib import Path
from typing import Dict, Any, List
import re


def analyze_complexity(file_path: Path) -> Dict[str, Any]:
    """
    Analyze code complexity for a single file.

    Args:
        file_path: Path to source file

    Returns:
        {
            "file": str,
            "language": str,
            "total_lines": int,
            "function_count": int,
            "functions": List[Dict],  # {name, lines, complexity, is_god}
            "avg_complexity": float,
            "max_complexity": int,
            "max_function_length": int,
            "god_functions": List[str],  # functions >50 lines
            "complexity_score": float  # 0.0-1.0
        }
    """
    language = _detect_language(file_path)

    if language == "Python":
        return _analyze_python_complexity(file_path)
    elif language in ["JavaScript", "TypeScript"]:
        return _analyze_js_complexity(file_path)
    else:
        return {"error": f"Unsupported language: {language}"}


def _detect_language(file_path: Path) -> str:
    """Detect language from file extension."""
    ext = file_path.suffix
    if ext == ".py":
        return "Python"
    elif ext in [".js", ".ts", ".tsx", ".jsx"]:
        return "JavaScript" if ext in [".js", ".jsx"] else "TypeScript"
    return "Unknown"


def _analyze_python_complexity(file_path: Path) -> Dict[str, Any]:
    """Analyze Python file complexity."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "Failed to read file"}

    lines = content.splitlines()
    total_lines = len([l for l in lines if l.strip()])

    # Find functions (simple regex, not AST)
    functions = []
    function_pattern = r'^def\s+([a-zA-Z0-9_]+)\s*\('

    current_function = None
    function_start = 0

    for i, line in enumerate(lines):
        # Check for function definition
        match = re.match(function_pattern, line)
        if match:
            # Save previous function
            if current_function:
                function_lines = i - function_start
                complexity = _calculate_python_complexity(lines[function_start:i])
                functions.append({
                    "name": current_function,
                    "lines": function_lines,
                    "complexity": complexity,
                    "is_god": function_lines > 50
                })

            current_function = match.group(1)
            function_start = i

    # Save last function
    if current_function:
        function_lines = len(lines) - function_start
        complexity = _calculate_python_complexity(lines[function_start:])
        functions.append({
            "name": current_function,
            "lines": function_lines,
            "complexity": complexity,
            "is_god": function_lines > 50
        })

    # Calculate stats
    function_count = len(functions)
    avg_complexity = sum(f["complexity"] for f in functions) / function_count if function_count > 0 else 0
    max_complexity = max((f["complexity"] for f in functions), default=0)
    max_function_length = max((f["lines"] for f in functions), default=0)
    god_functions = [f["name"] for f in functions if f["is_god"]]

    # File-level complexity score
    complexity_score = _calculate_file_score(function_count, avg_complexity, max_function_length)

    return {
        "file": str(file_path),
        "language": "Python",
        "total_lines": total_lines,
        "function_count": function_count,
        "functions": functions,
        "avg_complexity": round(avg_complexity, 2),
        "max_complexity": max_complexity,
        "max_function_length": max_function_length,
        "god_functions": god_functions,
        "complexity_score": round(complexity_score, 2)
    }


def _calculate_python_complexity(lines: List[str]) -> int:
    """Calculate cyclomatic complexity for Python code."""
    complexity = 1  # base complexity

    branch_keywords = [
        r'\bif\b', r'\belif\b', r'\bfor\b', r'\bwhile\b',
        r'\btry\b', r'\bexcept\b', r'\band\b', r'\bor\b',
        r'\bmatch\b', r'\bcase\b'
    ]

    for line in lines:
        line = line.strip()
        for keyword in branch_keywords:
            if re.search(keyword, line):
                complexity += 1

    return complexity


def _analyze_js_complexity(file_path: Path) -> Dict[str, Any]:
    """Analyze JavaScript/TypeScript complexity (simplified)."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "Failed to read file"}

    lines = content.splitlines()
    total_lines = len([l for l in lines if l.strip()])

    # Find functions (function keyword, arrow functions, methods)
    functions = []
    function_patterns = [
        r'^function\s+([a-zA-Z0-9_]+)\s*\(',
        r'const\s+([a-zA-Z0-9_]+)\s*=\s*\(',
        r'^([a-zA-Z0-9_]+)\s*\([^)]*\)\s*{',  # methods
    ]

    current_function = None
    function_start = 0
    brace_count = 0

    for i, line in enumerate(lines):
        # Check for function definition
        for pattern in function_patterns:
            match = re.search(pattern, line)
            if match and not current_function:
                current_function = match.group(1)
                function_start = i
                brace_count = line.count('{') - line.count('}')
                break

        if current_function:
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0:
                # Function ended
                function_lines = i - function_start + 1
                complexity = _calculate_js_complexity(lines[function_start:i+1])
                functions.append({
                    "name": current_function,
                    "lines": function_lines,
                    "complexity": complexity,
                    "is_god": function_lines > 50
                })
                current_function = None

    # Calculate stats
    function_count = len(functions)
    avg_complexity = sum(f["complexity"] for f in functions) / function_count if function_count > 0 else 0
    max_complexity = max((f["complexity"] for f in functions), default=0)
    max_function_length = max((f["lines"] for f in functions), default=0)
    god_functions = [f["name"] for f in functions if f["is_god"]]

    complexity_score = _calculate_file_score(function_count, avg_complexity, max_function_length)

    language = "TypeScript" if file_path.suffix in [".ts", ".tsx"] else "JavaScript"

    return {
        "file": str(file_path),
        "language": language,
        "total_lines": total_lines,
        "function_count": function_count,
        "functions": functions,
        "avg_complexity": round(avg_complexity, 2),
        "max_complexity": max_complexity,
        "max_function_length": max_function_length,
        "god_functions": god_functions,
        "complexity_score": round(complexity_score, 2)
    }


def _calculate_js_complexity(lines: List[str]) -> int:
    """Calculate cyclomatic complexity for JS/TS."""
    complexity = 1

    branch_keywords = [
        r'\bif\b', r'\belse\b', r'\bfor\b', r'\bwhile\b',
        r'\btry\b', r'\bcatch\b', r'&&', r'\|\|',
        r'\bswitch\b', r'\bcase\b', r'\?'  # ternary
    ]

    for line in lines:
        for keyword in branch_keywords:
            if re.search(keyword, line):
                complexity += 1

    return complexity


def _calculate_file_score(function_count: int, avg_complexity: float, max_function_length: int) -> float:
    """
    Calculate normalized file-level complexity score.

    Args:
        function_count: Number of functions in file
        avg_complexity: Average cyclomatic complexity
        max_function_length: Longest function in lines

    Returns:
        0.0-1.0 (0 = simple, 1 = very complex)
    """
    # Normalize components
    norm_functions = min(function_count / 20, 1.0)  # 20+ functions = 1.0
    norm_complexity = min(avg_complexity / 10, 1.0)  # avg 10+ = 1.0
    norm_length = min(max_function_length / 100, 1.0)  # 100+ lines = 1.0

    # Weighted score
    score = (
        norm_functions * 0.3 +
        norm_complexity * 0.5 +
        norm_length * 0.2
    )

    return min(score, 1.0)
