"""Traceability registry validation and helpers.

Validates .planning/traceability.yaml structure before skills modify it.
Called by build/verify skills to ensure YAML integrity.

Usage from hook or skill:
    from lib.traceability import validate_registry, load_registry

Usage from CLI:
    py hooks/lib/traceability.py validate .planning/traceability.yaml
    py hooks/lib/traceability.py summary .planning/traceability.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


REQUIRED_TOP_LEVEL = {"project", "spec_path", "plan_path", "created", "requirements", "summary"}
REQUIRED_REQUIREMENT = {"id", "description", "priority", "status"}
VALID_PRIORITIES = {"must", "should", "could"}
VALID_STATUSES = {"pending", "in_progress", "implemented", "verified"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _parse_yaml(path: Path) -> tuple[Optional[dict], Optional[str]]:
    """Parse YAML file, returning (data, error)."""
    try:
        size = path.stat().st_size
    except OSError as e:
        return None, f"Could not stat file: {e}"
    if size > MAX_FILE_SIZE:
        return None, f"File too large ({size} bytes, max {MAX_FILE_SIZE})"
    if size == 0:
        return None, "File is empty"

    if yaml is None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None, "File is not valid UTF-8"
        except Exception as e:
            return None, f"Could not read file: {e}"
        if text.strip().startswith("{") or ":" not in text:
            return None, "PyYAML not installed and file doesn't look like valid YAML"
        return None, "PyYAML not installed — cannot validate YAML structure. Install: pip install pyyaml"

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, "File is not valid UTF-8"
    except Exception as e:
        return None, f"Could not read file: {e}"

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, f"Invalid YAML: {e}"

    if not isinstance(data, dict):
        return None, f"Expected YAML mapping at top level, got {type(data).__name__}"

    return data, None


def validate_registry(path: Path) -> list[str]:
    """Validate traceability registry structure. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    data, parse_error = _parse_yaml(path)
    if parse_error:
        return [parse_error]
    assert data is not None

    missing_top = REQUIRED_TOP_LEVEL - set(data.keys())
    if missing_top:
        errors.append(f"Missing top-level keys: {', '.join(sorted(missing_top))}")

    requirements = data.get("requirements")
    if requirements is not None and not isinstance(requirements, list):
        errors.append(f"'requirements' must be a list, got {type(requirements).__name__}")
    elif isinstance(requirements, list):
        for i, req in enumerate(requirements):
            if not isinstance(req, dict):
                errors.append(f"requirements[{i}]: expected mapping, got {type(req).__name__}")
                continue

            prefix = f"requirements[{i}]"
            missing_req = REQUIRED_REQUIREMENT - set(req.keys())
            if missing_req:
                errors.append(f"{prefix}: missing keys: {', '.join(sorted(missing_req))}")

            req_id = req.get("id", "")
            if req_id and not str(req_id).startswith("TR-"):
                errors.append(f"{prefix}: id '{req_id}' must start with 'TR-'")

            priority = req.get("priority", "")
            if priority and str(priority) not in VALID_PRIORITIES:
                errors.append(f"{prefix}: priority '{priority}' must be one of {VALID_PRIORITIES}")

            status = req.get("status", "")
            if status and str(status) not in VALID_STATUSES:
                errors.append(f"{prefix}: status '{status}' must be one of {VALID_STATUSES}")

            tasks = req.get("tasks")
            if tasks is not None and not isinstance(tasks, list):
                errors.append(f"{prefix}: 'tasks' must be a list")

            commits = req.get("commits")
            if commits is not None and not isinstance(commits, list):
                errors.append(f"{prefix}: 'commits' must be a list")

            tests = req.get("tests")
            if tests is not None and not isinstance(tests, list):
                errors.append(f"{prefix}: 'tests' must be a list")

        ids = [str(r.get("id")) for r in requirements if isinstance(r, dict) and r.get("id")]
        dupes = [x for x in ids if ids.count(x) > 1]
        if dupes:
            errors.append(f"Duplicate TR-IDs: {', '.join(sorted(set(dupes)))}")

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, dict):
        errors.append(f"'summary' must be a mapping, got {type(summary).__name__}")

    return errors


def load_registry(path: Path) -> Optional[dict]:
    """Load and validate registry. Returns data if valid, None if invalid (prints errors)."""
    data, parse_error = _parse_yaml(path)
    if parse_error:
        print(f"[traceability] {parse_error}", file=sys.stderr)
        return None

    errors = validate_registry(path)
    if errors:
        for e in errors:
            print(f"[traceability] {e}", file=sys.stderr)
        return None

    return data


def summary(path: Path) -> str:
    """Generate a one-line summary of registry state."""
    data, err = _parse_yaml(path)
    if err:
        return f"ERROR: {err}"
    assert data is not None

    reqs = data.get("requirements") or []
    if not isinstance(reqs, list):
        return "ERROR: requirements is not a list"

    total = len(reqs)
    implemented = sum(1 for r in reqs if isinstance(r, dict) and r.get("status") == "implemented")
    verified = sum(1 for r in reqs if isinstance(r, dict) and r.get("status") == "verified")
    coverage = f"{(verified / total * 100):.0f}%" if total else "N/A"

    return f"{total} requirements, {implemented} implemented, {verified} verified ({coverage} coverage)"


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: traceability.py <validate|summary> <path>", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]
    path = Path(sys.argv[2])

    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    if command == "validate":
        errors = validate_registry(path)
        if errors:
            print(f"INVALID ({len(errors)} errors):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("VALID")
    elif command == "summary":
        print(summary(path))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
