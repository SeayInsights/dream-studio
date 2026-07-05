"""Static decision point discovery via AST analysis."""

from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiscoveredDecisionPoint:
    """A potential decision point found via static analysis."""

    file: str
    line: int
    code_snippet: str
    decision_type_guess: str
    confidence: float
    function_name: str = ""


def discover_decision_points(root_dirs: list[str]) -> list[DiscoveredDecisionPoint]:
    """Scan Python files for potential decision points.

    Args:
        root_dirs: List of directory paths to scan

    Returns:
        List of discovered decision points
    """
    decision_points = []

    for root_dir in root_dirs:
        root_path = Path(root_dir)
        if not root_path.exists():
            continue

        for py_file in root_path.rglob("*.py"):
            # Skip test files and migrations
            if "test" in py_file.name or "migration" in str(py_file):
                continue

            try:
                with open(py_file, encoding="utf-8") as f:
                    source = f.read()

                tree = ast.parse(source, filename=str(py_file))
                visitor = DecisionPointVisitor(str(py_file), source)
                visitor.visit(tree)
                decision_points.extend(visitor.decision_points)
            except (SyntaxError, UnicodeDecodeError):
                continue

    return decision_points


class DecisionPointVisitor(ast.NodeVisitor):
    """AST visitor to detect decision points."""

    def __init__(self, filename: str, source: str):
        self.filename = filename
        self.source_lines = source.split("\n")
        self.decision_points = []
        self.current_function = ""

    def visit_FunctionDef(self, node):
        """Track current function context."""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_If(self, node):
        """Detect if/elif branches with decision-like patterns."""
        # Check if this is a threshold comparison
        if self._is_threshold_comparison(node.test):
            snippet = self._get_code_snippet(node.lineno)
            self.decision_points.append(
                DiscoveredDecisionPoint(
                    file=self.filename,
                    line=node.lineno,
                    code_snippet=snippet,
                    decision_type_guess=self._guess_decision_type(snippet),
                    confidence=0.7,
                    function_name=self.current_function,
                )
            )

        # Check if this is a policy lookup pattern
        if self._is_policy_lookup(node.test):
            snippet = self._get_code_snippet(node.lineno)
            self.decision_points.append(
                DiscoveredDecisionPoint(
                    file=self.filename,
                    line=node.lineno,
                    code_snippet=snippet,
                    decision_type_guess="policy_check",
                    confidence=0.8,
                    function_name=self.current_function,
                )
            )

        self.generic_visit(node)

    def visit_Compare(self, node):
        """Detect comparison operations with constants."""
        # Skip if inside a decision we already logged
        if self._has_constant_operand(node):
            # Check if this looks like a decision (not just validation)
            if self._is_behavioral_comparison(node):
                snippet = self._get_code_snippet(node.lineno)
                if snippet and "if" in snippet:  # Only if it's in a conditional
                    self.decision_points.append(
                        DiscoveredDecisionPoint(
                            file=self.filename,
                            line=node.lineno,
                            code_snippet=snippet,
                            decision_type_guess="threshold_check",
                            confidence=0.5,
                            function_name=self.current_function,
                        )
                    )

        self.generic_visit(node)

    def visit_Return(self, node):
        """Detect return value selection logic."""
        if isinstance(node.value, ast.IfExp):
            # Ternary operator: value if condition else other
            snippet = self._get_code_snippet(node.lineno)
            self.decision_points.append(
                DiscoveredDecisionPoint(
                    file=self.filename,
                    line=node.lineno,
                    code_snippet=snippet,
                    decision_type_guess="return_selection",
                    confidence=0.6,
                    function_name=self.current_function,
                )
            )

        self.generic_visit(node)

    def visit_Call(self, node):
        """Detect calls to .get() with defaults (fallback logic)."""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and len(node.args) >= 2:
                # dict.get(key, default) is a decision point
                snippet = self._get_code_snippet(node.lineno)
                # Only if it's assigning to something or returning
                if snippet and ("=" in snippet or "return" in snippet):
                    self.decision_points.append(
                        DiscoveredDecisionPoint(
                            file=self.filename,
                            line=node.lineno,
                            code_snippet=snippet,
                            decision_type_guess="fallback_default",
                            confidence=0.4,
                            function_name=self.current_function,
                        )
                    )

        self.generic_visit(node)

    def _is_threshold_comparison(self, node) -> bool:
        """Check if node is a threshold comparison (e.g., x > 0.5)."""
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)):
                    # Check if comparing against a number
                    for comparator in node.comparators:
                        if isinstance(comparator, (ast.Constant, ast.Num)):
                            return True
        return False

    def _is_policy_lookup(self, node) -> bool:
        """Check if node accesses a POLICY dict."""
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                if "POLICY" in node.value.id.upper():
                    return True
        return False

    def _has_constant_operand(self, node) -> bool:
        """Check if comparison involves a constant."""
        for comparator in node.comparators:
            if isinstance(comparator, (ast.Constant, ast.Num, ast.Str)):
                return True
        return False

    def _is_behavioral_comparison(self, node) -> bool:
        """Check if comparison affects behavior (not just validation)."""
        # Heuristic: comparisons in control flow are behavioral
        # Comparisons in assertions/logging are not
        snippet = self._get_code_snippet(node.lineno)
        if not snippet:
            return False

        # Exclude logging and assertions
        if "log" in snippet.lower() or "assert" in snippet.lower():
            return False

        # Exclude raise statements
        if "raise" in snippet.lower():
            return False

        return True

    def _guess_decision_type(self, snippet: str) -> str:
        """Guess decision type from code snippet."""
        snippet_lower = snippet.lower()

        if "trust" in snippet_lower or "score" in snippet_lower:
            return "trust_score"
        if "ttl" in snippet_lower or "expire" in snippet_lower:
            return "ttl_assignment"
        if "unlock" in snippet_lower or "pattern" in snippet_lower:
            return "unlock_pattern"
        if "block" in snippet_lower or "allow" in snippet_lower:
            return "guardrail_policy"
        if "route" in snippet_lower or "dispatch" in snippet_lower:
            return "routing"
        return "unknown"

    def _get_code_snippet(self, lineno: int) -> str:
        """Extract code snippet around line number."""
        if 0 < lineno <= len(self.source_lines):
            line = self.source_lines[lineno - 1].strip()
            return line[:100]  # Truncate to 100 chars
        return ""
