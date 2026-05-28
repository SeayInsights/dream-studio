"""Shared utility: external trust boundary detection for ds-quality skills.

Used by:
  - ds-quality:code-quality (18.4.3): cq-016 validate-at-internal-boundaries
    excludes external entry points — those are sec-003/sec-007's domain
  - ds-quality:security (18.4.1): sec-003 may consult this to identify
    external entry points for priority classification

Convention established in 18.4.3 as the first canonical skill shared utility.
Location: canonical/skills/quality/shared/ — shared across quality-pack skills.

External trust boundary = function that receives data from outside the system's
trust domain. Security skill owns validation rules for these. Code-quality
skill's internal-boundary validation rule explicitly excludes them.
"""

from __future__ import annotations

import ast
import re

# ── Framework decorator patterns ────────────────────────────────────────────

# FastAPI / Starlette route decorators
_FASTAPI_DECORATORS = frozenset(
    {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "options",
        "trace",
        "websocket",
        "on_event",
    }
)

# Flask route decorators
_FLASK_DECORATORS = frozenset({"route", "get", "post", "put", "delete", "patch"})

# Click / Typer CLI command decorators
_CLI_DECORATORS = frozenset(
    {
        "command",
        "group",
        "argument",
        "option",
    }
)

# Dream Studio-specific: argparse subcommand entry points
# Matches function signatures used in interfaces/cli/ds.py and siblings
_DS_CLI_PATTERN = re.compile(r"^cmd_|^run_.*command$")

# Dream Studio-specific: hook handler functions
# Matches runtime/hooks/meta/*.py and runtime/hooks/core/*.py
# Signature: def main(payload: dict) or def handler(payload: dict)
_DS_HOOK_PATTERN = re.compile(r"^main$|^handler$|^handle_|^on_")


def is_external_entry_point(func_node: ast.FunctionDef) -> bool:
    """Return True if the function is an external trust boundary entry point.

    External entry points receive data from outside the system's trust domain.
    Security skill owns validation rules for these. Code-quality's internal
    validation rule (cq-016) excludes them.

    Decision C (18.4.3): Option C primary — code-quality excludes these
    patterns and defers to sec-003/sec-007. Option B fallback when detection
    is ambiguous (gray zones emit cross-reference findings from both skills).
    """
    # Check decorator-based patterns
    for decorator in func_node.decorator_list:
        if _is_fastapi_route(decorator):
            return True
        if _is_flask_route(decorator):
            return True
        if _is_cli_decorator(decorator):
            return True

    # Check Dream Studio-specific function name patterns
    name = func_node.name
    if _DS_CLI_PATTERN.match(name):
        return True

    # Check hook handler signature: def main/handler(payload: dict)
    if _DS_HOOK_PATTERN.match(name) and _has_dict_payload_param(func_node):
        return True

    return False


def classify_boundary(func_node: ast.FunctionDef) -> str:
    """Classify a function's trust boundary type.

    Returns one of:
      'external' — receives data from outside the system's trust domain
      'internal' — only receives data from within the trust domain
      'ambiguous' — cannot reliably determine; emit cross-reference findings
    """
    if is_external_entry_point(func_node):
        return "external"
    # Ambiguity heuristics: partner API clients, service mesh, custom IPC
    # For now, treat unknown as internal. Extend as gray zones are discovered.
    return "internal"


# ── Private helpers ──────────────────────────────────────────────────────────


def _is_fastapi_route(decorator: ast.expr) -> bool:
    """Check if decorator is a FastAPI/Starlette route decorator."""
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in _FASTAPI_DECORATORS
    if isinstance(decorator, ast.Call):
        return _is_fastapi_route(decorator.func)
    return False


def _is_flask_route(decorator: ast.expr) -> bool:
    """Check if decorator is a Flask route decorator."""
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in _FLASK_DECORATORS
    if isinstance(decorator, ast.Call):
        return _is_flask_route(decorator.func)
    return False


def _is_cli_decorator(decorator: ast.expr) -> bool:
    """Check if decorator is a Click/Typer CLI entry point decorator."""
    # @click.command, @app.command, @group.command, etc.
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in _CLI_DECORATORS
    if isinstance(decorator, ast.Call):
        return _is_cli_decorator(decorator.func)
    # @command directly (if click is imported with `from click import command`)
    if isinstance(decorator, ast.Name):
        return decorator.id in _CLI_DECORATORS
    return False


def _has_dict_payload_param(func_node: ast.FunctionDef) -> bool:
    """Check if a function has a parameter annotated as dict (hook pattern)."""
    for arg in func_node.args.args:
        if arg.annotation is None:
            continue
        ann = arg.annotation
        # annotation is `dict` (bare Name)
        if isinstance(ann, ast.Name) and ann.id == "dict":
            return True
        # annotation is `Dict[str, Any]` (subscript)
        if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
            if ann.value.id in ("Dict", "dict"):
                return True
    return False
