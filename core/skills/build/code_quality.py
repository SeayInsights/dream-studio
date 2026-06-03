"""Code-quality build mode — static enforcement on generated Python code.

Implements the audit interface documented in:
  canonical/skills/quality/modes/code-quality/build/SKILL.md

12 static rules applied synchronously. No LLM calls. No DB connections.
Returns in < 500ms for typical generated function (100-200 LOC).
"""

from __future__ import annotations

import ast
import re
from typing import Any

# ── Tier constants (shared with SkillDispatcher) ───────────────────────────
TIER_T1 = "T1"  # block return
TIER_T2 = "T2"  # warn inline
TIER_T3 = "T3"  # advisory


def audit_generated_python(code_block: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Static-only audit of a generated Python code block.

    Called by SkillDispatcher.build() for Python artifacts.

    Args:
        code_block: The generated Python source code.
        context: Generation context (project_id, session_id, etc.).

    Returns:
        List of finding dicts: [{rule_id, severity, tier, excerpt, explanation}]
        Empty list = clean.
    """
    findings: list[dict[str, Any]] = []
    lines = code_block.splitlines()

    # ── cq-006: silent exception (BLOCK) ──────────────────────────────────
    # Detects: `except ...: pass` (single line) OR except block where body is only `pass`
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Single-line: except ...: pass
        if re.match(r"^except(\s+[\w.,\s()*]+)?:\s*pass\s*$", stripped):
            findings.append(
                {
                    "rule_id": "cq-006",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": stripped,
                    "explanation": "Silent exception: except block with only `pass` swallows errors silently.",
                    "line": i + 1,
                }
            )
            continue
        # Multi-line: `except ...:` on this line, next non-empty line is `pass`
        if re.match(r"^except(\s+[\w.,\s()*]+)?:\s*$", stripped):
            # Look at next non-empty line
            for j in range(i + 1, min(i + 5, len(lines))):
                next_stripped = lines[j].strip()
                if next_stripped:
                    if next_stripped == "pass":
                        findings.append(
                            {
                                "rule_id": "cq-006",
                                "severity": "critical",
                                "tier": TIER_T1,
                                "excerpt": stripped,
                                "explanation": "Silent exception: except block with only `pass` swallows errors silently.",
                                "line": i + 1,
                            }
                        )
                    break

    # ── cq-015: bare except without type (BLOCK) ──────────────────────────
    for i, line in enumerate(lines):
        stripped = line.strip()
        # bare `except:` — no exception type after `except`
        if re.match(r"^except\s*:", stripped):
            findings.append(
                {
                    "rule_id": "cq-015",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": stripped,
                    "explanation": "Bare `except:` catches everything including SystemExit and KeyboardInterrupt.",
                    "line": i + 1,
                }
            )

    # ── cq-012: mutable global default (BLOCK) ────────────────────────────
    # Module-level ALL_CAPS = [] or {} (mutable containers as globals)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^[A-Z_]{2,}\s*=\s*[\[{]", stripped):
            findings.append(
                {
                    "rule_id": "cq-012",
                    "severity": "critical",
                    "tier": TIER_T1,
                    "excerpt": line.strip(),
                    "explanation": "Mutable global constant: module-level mutable container will be shared across all callers.",
                    "line": i + 1,
                }
            )

    # ── cq-019: time.sleep in async context (BLOCK) ───────────────────────
    has_async = any("async def" in line or "await " in line for line in lines)
    if has_async:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(r"\btime\.sleep\s*\(", stripped) and "async def" in code_block:
                findings.append(
                    {
                        "rule_id": "cq-019",
                        "severity": "critical",
                        "tier": TIER_T1,
                        "excerpt": line.strip(),
                        "explanation": "time.sleep() in async code blocks the event loop. Use `await asyncio.sleep()` instead.",
                        "line": i + 1,
                    }
                )
                break

    # ── cq-A-explicit: wildcard imports (INFO/T3) ─────────────────────────
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^from\s+\S+\s+import\s+\*", stripped):
            findings.append(
                {
                    "rule_id": "cq-A-explicit",
                    "severity": "medium",
                    "tier": TIER_T3,
                    "excerpt": line.strip(),
                    "explanation": "Wildcard import pollutes namespace and makes dependencies unclear.",
                    "line": i + 1,
                }
            )

    # ── cq-002: function length > 50 lines (INFO/T3) ──────────────────────
    _check_function_length(lines, findings)

    # ── cq-003: parameter count > 4 (INFO/T3) ─────────────────────────────
    _check_param_count(code_block, findings)

    # ── cq-005: nesting depth > 3 (INFO/T3) ──────────────────────────────
    _check_nesting_depth(lines, findings)

    # ── cq-020: public function without docstring (INFO/T3) ──────────────
    _check_missing_docstring(code_block, findings)

    return findings


# ── Helpers ───────────────────────────────────────────────────────────────


def _check_function_length(lines: list[str], findings: list[dict]) -> None:
    """Flag functions exceeding 50 lines (cq-002)."""
    in_func = False
    func_start = 0
    func_name = ""
    indent_level = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        m = re.match(r"^(async\s+)?def\s+(\w+)\s*\(", stripped)
        if m:
            in_func = True
            func_start = i
            func_name = m.group(2)
            indent_level = len(line) - len(line.lstrip())
        elif in_func:
            # End of function: back to same or lesser indent with non-empty line
            if (
                stripped
                and (len(line) - len(line.lstrip())) <= indent_level
                and not stripped.startswith(("#", '"""', "'''"))
            ):
                func_len = i - func_start
                if func_len > 50:
                    findings.append(
                        {
                            "rule_id": "cq-002",
                            "severity": "medium",
                            "tier": TIER_T3,
                            "excerpt": f"def {func_name}(...): [{func_len} lines]",
                            "explanation": f"Function `{func_name}` is {func_len} lines (limit: 50). Consider extracting helpers.",
                            "line": func_start + 1,
                        }
                    )
                in_func = False

    # Check last function in file
    if in_func:
        func_len = len(lines) - func_start
        if func_len > 50:
            findings.append(
                {
                    "rule_id": "cq-002",
                    "severity": "medium",
                    "tier": TIER_T3,
                    "excerpt": f"def {func_name}(...): [{func_len} lines]",
                    "explanation": f"Function `{func_name}` is {func_len} lines (limit: 50). Consider extracting helpers.",
                    "line": func_start + 1,
                }
            )


def _check_param_count(code_block: str, findings: list[dict]) -> None:
    """Flag functions with > 4 parameters (cq-003)."""
    try:
        tree = ast.parse(code_block)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            # Count: positional + keyword-only + *args + **kwargs
            n_params = (
                len(args.args)
                + len(args.kwonlyargs)
                + (1 if args.vararg else 0)
                + (1 if args.kwarg else 0)
            )
            # Exclude `self` and `cls`
            positional_names = [a.arg for a in args.args]
            if positional_names and positional_names[0] in ("self", "cls"):
                n_params -= 1
            if n_params > 4:
                findings.append(
                    {
                        "rule_id": "cq-003",
                        "severity": "medium",
                        "tier": TIER_T3,
                        "excerpt": f"def {node.name}(...): {n_params} parameters",
                        "explanation": f"`{node.name}` has {n_params} parameters (limit: 4). Consider grouping into a dataclass or config object.",
                        "line": node.lineno,
                    }
                )


def _check_nesting_depth(lines: list[str], findings: list[dict]) -> None:
    """Flag code with nesting depth > 3 (cq-005, rough heuristic)."""
    for i, line in enumerate(lines):
        indent = len(line) - len(line.lstrip())
        # 4-space indents = nesting level; > 3 nesting = > 12 spaces
        nesting = indent // 4
        if nesting > 3 and line.strip():
            findings.append(
                {
                    "rule_id": "cq-005",
                    "severity": "medium",
                    "tier": TIER_T3,
                    "excerpt": line.rstrip(),
                    "explanation": f"Nesting depth {nesting} at line {i + 1} (limit: 3). Extract deeply nested logic into a helper.",
                    "line": i + 1,
                }
            )
            break  # one finding per block, don't spam


def _check_missing_docstring(code_block: str, findings: list[dict]) -> None:
    """Flag public functions without docstrings (cq-020)."""
    try:
        tree = ast.parse(code_block)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue  # private functions exempt
            if not (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                findings.append(
                    {
                        "rule_id": "cq-020",
                        "severity": "low",
                        "tier": TIER_T3,
                        "excerpt": f"def {node.name}(...)",
                        "explanation": f"Public function `{node.name}` has no docstring.",
                        "line": node.lineno,
                    }
                )
