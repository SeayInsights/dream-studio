#!/usr/bin/env python3
"""CLI tool for execution graph operations.

Usage:
    # Create project
    python interfaces/cli/exec_graph.py create project "Build Auth System"

    # Create child node
    python interfaces/cli/exec_graph.py create task "Implement JWT" --parent <parent_id>

    # Show node details
    python interfaces/cli/exec_graph.py show <node_id>

    # List children
    python interfaces/cli/exec_graph.py children <node_id>

    # Update status
    python interfaces/cli/exec_graph.py status <node_id> active|completed|failed

    # Show tree
    python interfaces/cli/exec_graph.py tree <node_id>
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.execution.graph import ExecutionGraphManager, ExecutionNode


def format_node(node: ExecutionNode, indent: int = 0) -> str:
    """Format node for display."""
    prefix = "  " * indent
    status_icon = {
        "pending": "[ ]",
        "active": "[~]",
        "completed": "[x]",
        "failed": "[!]",
        "blocked": "[-]",
        "skipped": "[ ]",
    }.get(node.status, "[?]")

    line = f"{prefix}{status_icon} {node.node_type}: {node.title} ({node.node_id[:8]})"
    return line


def cmd_create(args):
    """Create a new node."""
    graph = ExecutionGraphManager()
    node_id = graph.create_node(
        node_type=args.node_type,
        title=args.title,
        description=args.description,
        parent_id=args.parent,
        priority=args.priority,
    )
    print(f"Created {args.node_type}: {node_id}")
    print(f"Title: {args.title}")


def cmd_show(args):
    """Show node details."""
    graph = ExecutionGraphManager()
    node = graph.get_node(args.node_id)

    if not node:
        print(f"Node not found: {args.node_id}")
        return 1

    print(f"Node ID: {node.node_id}")
    print(f"Type: {node.node_type}")
    print(f"Title: {node.title}")
    print(f"Status: {node.status}")
    if node.description:
        print(f"Description: {node.description}")
    if node.parent_id:
        print(f"Parent: {node.parent_id}")
    print(f"Created: {node.created_at}")
    if node.started_at:
        print(f"Started: {node.started_at}")
    if node.completed_at:
        print(f"Completed: {node.completed_at}")
    if node.context_tokens:
        print(f"Context Tokens: {node.context_tokens}")

    # Show dependencies
    deps = graph.get_dependencies(node.node_id)
    if deps:
        print(f"\nDependencies ({len(deps)}):")
        for dep in deps:
            target = graph.get_node(dep.target_node_id)
            if target:
                print(f"  {dep.dependency_type}: {target.title} ({target.status})")

    # Show outputs
    outputs = graph.get_outputs(node.node_id)
    if outputs:
        print(f"\nOutputs ({len(outputs)}):")
        for out in outputs:
            print(f"  {out.output_type}: {out.output_summary or '(no summary)'}")
            if out.file_paths:
                print(f"    Files: {len(out.file_paths)}")

    return 0


def cmd_children(args):
    """List child nodes."""
    graph = ExecutionGraphManager()
    children = graph.get_children(args.node_id)

    if not children:
        print(f"No children for node: {args.node_id}")
        return 0

    print(f"Children of {args.node_id}:")
    for child in children:
        print(f"  {format_node(child, indent=0)}")

    return 0


def cmd_status(args):
    """Update node status."""
    graph = ExecutionGraphManager()
    success = graph.update_status(args.node_id, args.status)

    if success:
        print(f"Updated {args.node_id} status: {args.status}")
        return 0
    print(f"Failed to update status")
    return 1


def cmd_tree(args):
    """Show execution tree from node."""
    graph = ExecutionGraphManager()

    def print_tree(node_id: str, indent: int = 0):
        node = graph.get_node(node_id)
        if not node:
            return

        print(format_node(node, indent))

        children = graph.get_children(node_id)
        for child in children:
            print_tree(child.node_id, indent + 1)

    print_tree(args.node_id)
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Execution graph operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create command
    create_parser = subparsers.add_parser("create", help="Create new node")
    create_parser.add_argument(
        "node_type", choices=["project", "prd", "plan", "phase", "wave", "task"]
    )
    create_parser.add_argument("title", help="Node title")
    create_parser.add_argument("--description", "-d", help="Node description")
    create_parser.add_argument("--parent", "-p", help="Parent node ID")
    create_parser.add_argument("--priority", type=int, default=0, help="Priority")
    create_parser.set_defaults(func=cmd_create)

    # Show command
    show_parser = subparsers.add_parser("show", help="Show node details")
    show_parser.add_argument("node_id", help="Node ID")
    show_parser.set_defaults(func=cmd_show)

    # Children command
    children_parser = subparsers.add_parser("children", help="List child nodes")
    children_parser.add_argument("node_id", help="Parent node ID")
    children_parser.set_defaults(func=cmd_children)

    # Status command
    status_parser = subparsers.add_parser("status", help="Update node status")
    status_parser.add_argument("node_id", help="Node ID")
    status_parser.add_argument(
        "status", choices=["pending", "active", "blocked", "completed", "failed", "skipped"]
    )
    status_parser.set_defaults(func=cmd_status)

    # Tree command
    tree_parser = subparsers.add_parser("tree", help="Show execution tree")
    tree_parser.add_argument("node_id", help="Root node ID")
    tree_parser.set_defaults(func=cmd_tree)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
