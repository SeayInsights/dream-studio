#!/usr/bin/env python3
"""Validate a workflow YAML file before execution.

Checks: unique node IDs, dependency references exist, gate references
defined, skill files exist on disk, no cycles (Kahn's algorithm).
Exit 0 = valid, exit 1 = errors found.

Usage:
  workflow_validate.py <yaml-path> [--plugin-root PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402


# ── YAML parser (workflow subset only, zero dependencies) ────────────


def parse_workflow(yaml_path: str) -> dict:
    with open(yaml_path, encoding="utf-8") as f:
        lines = f.readlines()

    result: dict = {"name": None, "description": None, "version": None,
                    "gates": {}, "nodes": []}
    section: str | None = None
    gate_name: str | None = None
    node: dict | None = None
    in_block = False
    block_indent = 0

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if not stripped or stripped.startswith("#"):
            continue

        if in_block:
            if indent > block_indent:
                continue
            in_block = False

        # Top-level keys
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if key == "gates":
                section, gate_name = "gates", None
                if node:
                    result["nodes"].append(node)
                    node = None
            elif key == "nodes":
                section, gate_name = "nodes", None
                if node:
                    result["nodes"].append(node)
                    node = None
            else:
                result[key] = _parse_scalar(val)
            continue

        if section == "gates":
            if indent == 2 and stripped.endswith(":"):
                gate_name = stripped[:-1].strip()
                result["gates"][gate_name] = {}
            elif indent >= 4 and gate_name and ":" in stripped:
                k, _, v = stripped.partition(":")
                result["gates"][gate_name][k.strip()] = _parse_scalar(v.strip())
            continue

        if section == "nodes":
            if stripped.startswith("- id:"):
                if node:
                    result["nodes"].append(node)
                node = {"id": stripped.split(":", 1)[1].strip()}
            elif node and indent >= 4 and ":" in stripped:
                k, _, v = stripped.partition(":")
                k, v = k.strip(), v.strip()
                if v == "|":
                    node[k] = True
                    in_block, block_indent = True, indent
                else:
                    node[k] = _parse_scalar(v)
            continue

    if node:
        result["nodes"].append(node)
    return result


def _parse_scalar(val: str):
    if not val:
        return None
    if val.startswith("[") and val.endswith("]"):
        return [i.strip().strip("'\"") for i in val[1:-1].split(",") if i.strip()]
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    try:
        return int(val)
    except ValueError:
        pass
    return val


# ── Validation ───────────────────────────────────────────────────────


def validate(data: dict, plugin_root: Path) -> list[str]:
    errors: list[str] = []
    nodes = data.get("nodes", [])
    gates = set(data.get("gates", {}).keys())
    node_ids: set[str] = set()

    for n in nodes:
        nid = n.get("id")
        if not nid:
            errors.append("Node missing 'id' field")
            continue
        if nid in node_ids:
            errors.append(f"Duplicate node id: \"{nid}\"")
        node_ids.add(nid)

    for n in nodes:
        nid = n.get("id", "?")

        has_skill = "skill" in n
        has_command = "command" in n
        if not has_skill and not has_command:
            errors.append(f"Node \"{nid}\": needs 'skill' or 'command'")
        if has_skill and has_command:
            errors.append(f"Node \"{nid}\": has both 'skill' and 'command'")

        deps = n.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if dep not in node_ids:
                errors.append(f"Node \"{nid}\": depends_on \"{dep}\" — not found")

        gate = n.get("gate")
        if gate and gate not in gates:
            errors.append(f"Node \"{nid}\": gate \"{gate}\" not in gates section")

        skill = n.get("skill")
        if skill:
            skill_path = plugin_root / "skills" / skill / "SKILL.md"
            if not skill_path.is_file():
                errors.append(f"Node \"{nid}\": skill \"{skill}\" — "
                              f"{skill_path} not found")

    # Cycle detection — Kahn's algorithm
    in_degree = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue
        deps = n.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if dep in node_ids:
                adj[dep].append(nid)
                in_degree[nid] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        current = queue.pop(0)
        visited += 1
        for neighbor in adj[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited < len(node_ids):
        cycle_nodes = [nid for nid, deg in in_degree.items() if deg > 0]
        errors.append(f"Cycle detected: {', '.join(cycle_nodes)}")

    return errors


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="workflow_validate",
        description="Validate a workflow YAML file",
    )
    parser.add_argument("yaml_path")
    parser.add_argument("--plugin-root")
    args = parser.parse_args()

    if args.plugin_root:
        root = Path(args.plugin_root)
    else:
        try:
            root = paths.plugin_root()
        except RuntimeError:
            root = Path(__file__).resolve().parents[2]

    if not Path(args.yaml_path).is_file():
        print(f"Error: {args.yaml_path} not found", file=sys.stderr)
        sys.exit(1)

    data = parse_workflow(args.yaml_path)
    errors = validate(data, root)

    if errors:
        print(f"FAIL: {args.yaml_path}")
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        n = len(data.get("nodes", []))
        g = len(data.get("gates", {}))
        print(f"OK: {args.yaml_path} — {n} nodes, {g} gates")
        sys.exit(0)


if __name__ == "__main__":
    main()
