#!/usr/bin/env python3
"""CLI tool for context compilation.

Demonstrates the Context Compiler's token savings by compiling
minimal context for execution nodes.

Usage:
    # Compile context for a node
    python interfaces/cli/compile_context.py <node_id>

    # Export as JSON
    python interfaces/cli/compile_context.py <node_id> --export

    # Show detailed breakdown
    python interfaces/cli/compile_context.py <node_id> --verbose
"""

import sys
import json
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.execution.context_compiler import ContextCompiler


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Compile minimal context for execution nodes")
    parser.add_argument("node_id", help="Node ID to compile context for")
    parser.add_argument("--export", action="store_true", help="Export context as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed component breakdown")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    # Compile context
    compiler = ContextCompiler()
    compiled = compiler.compile_for_node(args.node_id)

    if not compiled:
        print(f"Failed to compile context for node: {args.node_id}")
        return 1

    # Format output
    if args.export:
        # Export as JSON
        context_dict = compiler.export_context(compiled)
        output = json.dumps(context_dict, indent=2)
    else:
        # Format as report
        output = compiler.format_report(compiled)

        if args.verbose:
            # Add detailed component data
            output += "\n\n" + "=" * 70
            output += "\nDETAILED COMPONENTS\n"
            output += "=" * 70
            output += f"\n\nGOAL:\n{compiled.goal}\n"

            if compiled.constraints:
                output += f"\nCONSTRAINTS:\n"
                for i, c in enumerate(compiled.constraints, 1):
                    output += f"  {i}. {c}\n"

            if compiled.dependency_outputs:
                output += f"\nDEPENDENCY OUTPUTS (full):\n"
                output += json.dumps(compiled.dependency_outputs, indent=2)
                output += "\n"

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Context written to: {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
