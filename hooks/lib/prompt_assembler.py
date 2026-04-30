"""
prompt_assembler.py — Cache-optimized prompt builder for subagent dispatch.

CLI:
    py hooks/lib/prompt_assembler.py --template=<name> --static-context=<path> \
        [--task-text=<text>] [--task-file=<path>] [--decisions=<text>]

Module API:
    from hooks.lib.prompt_assembler import assemble_prompt
    text = assemble_prompt(template, static_context_path, task_text=..., decisions=...)

Templates: implementer, reviewer, auditor, explorer
Static context (output of context_compiler) becomes the byte-identical prefix.
Dynamic content (task text, decisions) goes after the separator.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SEPARATOR = "═══════════════════════════════════════════"

_TEMPLATES_DIR = Path(__file__).resolve().parent / "prompt_templates"

_VALID_TEMPLATES = ("implementer", "reviewer", "auditor", "explorer")


def _read_template(template_name: str) -> str:
    if template_name not in _VALID_TEMPLATES:
        raise ValueError(
            f"Unknown template '{template_name}'. Valid: {', '.join(_VALID_TEMPLATES)}"
        )
    path = _TEMPLATES_DIR / f"{template_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def _build_dynamic_content(
    task_text: str | None = None,
    task_file: str | None = None,
    decisions: str | None = None,
) -> str:
    parts: list[str] = []

    if task_file is not None:
        p = Path(task_file).resolve()
        if p.exists():
            parts.append(p.read_text(encoding="utf-8").strip())

    if task_text is not None:
        parts.append(task_text.strip())

    if decisions is not None:
        parts.append(f"\n### Decisions\n{decisions.strip()}")

    return "\n\n".join(parts) if parts else "(no task provided)"


def assemble_prompt(
    template: str,
    static_context_path: str,
    task_text: str | None = None,
    task_file: str | None = None,
    decisions: str | None = None,
) -> str:
    sc_path = Path(static_context_path).resolve()
    if not sc_path.exists():
        raise FileNotFoundError(f"Static context not found: {sc_path}")

    static_context = sc_path.read_text(encoding="utf-8").rstrip("\n")
    template_text = _read_template(template)
    dynamic_content = _build_dynamic_content(task_text, task_file, decisions)

    result = template_text.replace("{{STATIC_CONTEXT}}", static_context)
    result = result.replace("{{DYNAMIC_CONTENT}}", dynamic_content)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble a cache-optimized prompt for a subagent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py hooks/lib/prompt_assembler.py --template=implementer --static-context=compiled.md --task-text="Build the API endpoint"
  py hooks/lib/prompt_assembler.py --template=reviewer --static-context=compiled.md --task-file=review-scope.md
  py hooks/lib/prompt_assembler.py --template=auditor --static-context=compiled.md --task-text="Audit security" --decisions="Use OWASP top 10"
""",
    )
    parser.add_argument(
        "--template",
        required=True,
        choices=_VALID_TEMPLATES,
        help="Agent role template",
    )
    parser.add_argument(
        "--static-context",
        required=True,
        metavar="PATH",
        help="Path to the static context file (output of context_compiler.py)",
    )
    parser.add_argument(
        "--task-text",
        default=None,
        metavar="TEXT",
        help="Inline task description",
    )
    parser.add_argument(
        "--task-file",
        default=None,
        metavar="PATH",
        help="Path to a file containing the task description",
    )
    parser.add_argument(
        "--decisions",
        default=None,
        metavar="TEXT",
        help="Relevant decisions/constraints for the agent",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        result = assemble_prompt(
            template=args.template,
            static_context_path=args.static_context,
            task_text=args.task_text,
            task_file=args.task_file,
            decisions=args.decisions,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.stdout.buffer.write(result.encode("utf-8"))


if __name__ == "__main__":
    main()
