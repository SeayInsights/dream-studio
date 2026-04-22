"""
init_security_state.py

Initializes the ~/.dream-studio/security/ directory tree and related
paths for the enterprise security architecture.

Idempotent — safe to re-run. Only creates missing dirs/files; never
overwrites existing ones.
"""

import json
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
HOME = Path.home()
DS = HOME / ".dream-studio"

DIRS = [
    DS / "clients",
    DS / "security" / "scans",
    DS / "security" / "datasets",
    DS / "security" / "rules",
    DS / "security" / "reports",
    DS / "security" / "actions",
]

FEEDS_DIR = DS / "feeds"
SECURITY_FEED = FEEDS_DIR / "security.json"
SECURITY_SCHEMA = FEEDS_DIR / "security.schema.json"

# ── Feed content ────────────────────────────────────────────────────────
SECURITY_FEED_INITIAL: dict = {
    "schema_version": 1,
    "last_updated": None,
    "last_scan": {
        "client": None,
        "date": None,
        "repos_scanned": 0,
        "findings_count": 0,
        "org_score": None,
    },
    "last_report": {
        "path": None,
        "date": None,
    },
    "active_workflow": {
        "key": None,
        "status": None,
    },
}

SECURITY_SCHEMA_INITIAL: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://dream-studio/feeds/security.schema.json",
    "title": "SecurityFeed",
    "description": "State feed for dream-studio enterprise security scanning.",
    "type": "object",
    "required": ["schema_version"],
    "properties": {
        "schema_version": {
            "type": "integer",
            "description": "Monotonically increasing schema version.",
        },
        "last_updated": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "ISO-8601 timestamp of the last write to this file.",
        },
        "last_scan": {
            "type": "object",
            "description": "Metadata for the most recent org scan run.",
            "properties": {
                "client": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"], "format": "date-time"},
                "repos_scanned": {"type": "integer", "minimum": 0},
                "findings_count": {"type": "integer", "minimum": 0},
                "org_score": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
            },
        },
        "last_report": {
            "type": "object",
            "description": "Most recent generated report.",
            "properties": {
                "path": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "active_workflow": {
            "type": "object",
            "description": "Currently running (or last run) workflow.",
            "properties": {
                "key": {"type": ["string", "null"]},
                "status": {
                    "type": ["string", "null"],
                    "enum": [None, "pending", "running", "success", "failed"],
                },
            },
        },
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────

def ensure_dir(path: Path) -> bool:
    """Create directory if missing. Returns True if created."""
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def ensure_json_file(path: Path, content: dict) -> bool:
    """Write JSON file only if it does not already exist. Returns True if created."""
    if path.exists():
        return False
    path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    return True


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    created: list[str] = []

    # Ensure feeds dir exists (should already exist, but guard anyway)
    if ensure_dir(FEEDS_DIR):
        created.append(f"  [dir]  {FEEDS_DIR}")

    # Create security subdirectory tree
    for d in DIRS:
        if ensure_dir(d):
            created.append(f"  [dir]  {d}")

    # Create feed files
    if ensure_json_file(SECURITY_FEED, SECURITY_FEED_INITIAL):
        created.append(f"  [file] {SECURITY_FEED}")

    if ensure_json_file(SECURITY_SCHEMA, SECURITY_SCHEMA_INITIAL):
        created.append(f"  [file] {SECURITY_SCHEMA}")

    # Report
    if created:
        print("Created:")
        for item in created:
            print(item)
    else:
        print("State already initialized — nothing to do.")


if __name__ == "__main__":
    main()
