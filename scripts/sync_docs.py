#!/usr/bin/env python3
"""sync_docs.py — regenerate the Workflows table in README.md from workflows/*.yaml

Usage:
    py -3.12 scripts/sync_docs.py        # update README in-place
    py -3.12 scripts/sync_docs.py --check # exit 1 if README is out of date (CI mode)
"""
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"
README = REPO_ROOT / "README.md"

TABLE_START = "<!-- workflows-table-start -->"
TABLE_END = "<!-- workflows-table-end -->"
MAX_NODES = 6
MAX_PURPOSE = 90


def node_flow(nodes):
    ids = [n["id"] for n in nodes]
    if len(ids) <= MAX_NODES:
        return " → ".join(ids)
    return " → ".join(ids[:MAX_NODES]) + " → …"


def purpose(description):
    flat = re.sub(r"\s+", " ", (description or "").strip())
    m = re.search(r"^(.{10,}?[.!?])(?:\s|$)", flat)
    sentence = m.group(1) if m else flat
    if len(sentence) > MAX_PURPOSE:
        sentence = sentence[:MAX_PURPOSE].rstrip() + "…"
    return sentence


def build_table():
    rows = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = data.get("name", path.stem)
        flow = node_flow(data.get("nodes", []))
        desc = purpose(data.get("description", ""))
        rows.append(f"| `{name}` | {flow} | {desc} |")
    header = "| Workflow | Nodes | Purpose |\n|---|---|---|"
    return header + "\n" + "\n".join(rows)


def current_block(text):
    m = re.search(
        re.escape(TABLE_START) + r"(.*?)" + re.escape(TABLE_END),
        text,
        flags=re.DOTALL,
    )
    return m.group(1).strip() if m else None


def update_readme(check_only=False):
    text = README.read_text(encoding="utf-8")

    if TABLE_START not in text:
        print(
            f"ERROR: '{TABLE_START}' sentinel not found in README.md.\n"
            "Add it manually around the Workflows table.",
            file=sys.stderr,
        )
        sys.exit(1)

    table = build_table()
    existing = current_block(text)

    if existing == table:
        print("README.md already up to date.")
        return

    if check_only:
        print("README.md is out of date — run `make docs` to fix.", file=sys.stderr)
        sys.exit(1)

    updated = re.sub(
        re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END),
        f"{TABLE_START}\n{table}\n{TABLE_END}",
        text,
        flags=re.DOTALL,
    )
    README.write_text(updated, encoding="utf-8")
    count = table.count("\n") - 1
    print(f"README.md updated — {count} workflow(s) documented.")


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    update_readme(check_only=check_only)
