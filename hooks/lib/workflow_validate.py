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
    text = Path(yaml_path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    result: dict = {"name": None, "description": None, "version": None,
                    "gates": {}, "nodes": []}
    section: str | None = None
    gate_name: str | None = None
    node: dict | None = None
    in_block = False
    block_indent = 0

    for line in lines:
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
            key, val = _split_kv(stripped)
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
                k, v = _split_kv(stripped)
                result["gates"][gate_name][k] = _parse_scalar(v)
            continue

        if section == "nodes":
            if stripped.startswith("- id:"):
                if node:
                    result["nodes"].append(node)
                node = {"id": stripped.split(":", 1)[1].strip()}
            elif node and indent >= 4 and ":" in stripped:
                k, v = _split_kv(stripped)
                if v == "|":
                    node[k] = True
                    in_block, block_indent = True, indent
                else:
                    node[k] = _parse_scalar(v)
            continue

    if node:
        result["nodes"].append(node)
    return result


def _split_kv(line: str) -> tuple[str, str]:
    """Split a 'key: value' line, respecting quoted values with colons."""
    stripped = line.strip()
    idx = stripped.find(":")
    if idx < 0:
        return stripped, ""
    key = stripped[:idx].strip()
    rest = stripped[idx + 1:].strip()
    return key, rest


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


# ── Skill resolution ────────────────────────────────────────────────


def _resolve_skill(skill: str, plugin_root: Path) -> Path | None:
    """Find SKILL.md for a skill name, checking both flat and pack/mode layouts."""
    flat = plugin_root / "skills" / skill / "SKILL.md"
    if flat.is_file():
        return flat
    skills_dir = plugin_root / "skills"
    if not skills_dir.is_dir():
        return None
    for pack_dir in skills_dir.iterdir():
        if not pack_dir.is_dir():
            continue
        mode_path = pack_dir / "modes" / skill / "SKILL.md"
        if mode_path.is_file():
            return mode_path
    return None


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
            if not _resolve_skill(skill, plugin_root):
                errors.append(f"Node \"{nid}\": skill \"{skill}\" — "
                              f"{skill} not found in skills/ or any pack mode")

    # Validate on_failure at workflow level
    on_failure = data.get("on_failure")
    if on_failure is not None:
        valid_on_failure = {"abort"} | node_ids
        if not isinstance(on_failure, str):
            errors.append("Warning: on_failure must be a string (\"abort\" or a node ID)")
        elif on_failure not in valid_on_failure:
            errors.append(f"Warning: on_failure \"{on_failure}\" is not \"abort\" or a known node ID")

    # Validate new per-node fields
    for n in nodes:
        nid = n.get("id", "?")

        timeout = n.get("timeout_seconds")
        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                errors.append(f"Node \"{nid}\": timeout_seconds must be a positive integer")

        retry = n.get("retry")
        if retry is not None:
            if not isinstance(retry, dict):
                errors.append(f"Node \"{nid}\": retry must be a mapping")
            else:
                max_val = retry.get("max")
                if max_val is None:
                    errors.append(f"Node \"{nid}\": retry.max is required")
                elif not isinstance(max_val, int) or max_val <= 0:
                    errors.append(f"Node \"{nid}\": retry.max must be a positive integer")

        estimated_tokens = n.get("estimated_tokens")
        if estimated_tokens is not None:
            if not isinstance(estimated_tokens, int) or estimated_tokens < 0:
                errors.append(
                    f"Node \"{nid}\": estimated_tokens must be a non-negative integer"
                )

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
