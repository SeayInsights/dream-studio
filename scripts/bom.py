#!/usr/bin/env python3
"""Bill of Materials — emit a snapshot of build state as bom.json."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main(output_path: str = "bom.json") -> None:
    git_sha = run(["git", "rev-parse", "HEAD"])
    python_version = sys.version

    pip_raw = run([sys.executable, "-m", "pip", "freeze"])
    pip_packages: dict[str, str] = {}
    for line in pip_raw.splitlines():
        if not line.strip():
            continue
        if "==" in line:
            name, _, version = line.partition("==")
            pip_packages[name] = version
        else:
            pip_packages[line] = ""

    bom = {
        "git_sha": git_sha,
        "python_version": python_version,
        "build_date_utc": datetime.now(timezone.utc).isoformat(),
        "packages": pip_packages,
        "failed_tests": [],
    }

    Path(output_path).write_text(json.dumps(bom, indent=2), encoding="utf-8")
    print(f"BOM written to {output_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bom.json")
