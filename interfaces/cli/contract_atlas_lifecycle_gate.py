#!/usr/bin/env python3
"""Release gate for Contract Atlas lifecycle and sanitized export freshness."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.event_store.studio_db import _connect  # noqa: E402
from core.shared_intelligence.adapter_alignment import (  # noqa: E402
    register_default_adapter_authority_profiles,
)
from core.shared_intelligence.contract_atlas_lifecycle import (  # noqa: E402
    build_contract_atlas_freshness_manifest,
    validate_contract_atlas_lifecycle_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--changed-files", default=None)
    parser.add_argument("--docs-reviewed-no-change", action="append", default=[])
    args = parser.parse_args()

    changed_files = _changed_files(args)
    with tempfile.TemporaryDirectory(prefix="dream-studio-contract-atlas-gate-") as tmp:
        temp_root = Path(tmp)
        temp_home = temp_root / "home"
        _write_current_hook_surfaces(temp_home)
        os.environ["HOME"] = str(temp_home)
        os.environ["USERPROFILE"] = str(temp_home)
        db_path = temp_root / "state" / "studio.db"
        conn = _connect(db_path)
        try:
            register_default_adapter_authority_profiles(conn)
            manifest = build_contract_atlas_freshness_manifest(
                conn,
                repo_root=REPO_ROOT,
                project_id="dream-studio",
                changed_files=changed_files,
                reviewed_no_change_domains=args.docs_reviewed_no_change,
            )
        finally:
            conn.close()

    validation_errors = validate_contract_atlas_lifecycle_manifest(manifest)
    if validation_errors:
        manifest["status"] = "fail"
        manifest["manifest_validation_errors"] = validation_errors
    print(json.dumps(manifest, indent=2, sort_keys=True))
    raise SystemExit(0 if manifest["status"] == "pass" else 1)


def _changed_files(args: argparse.Namespace) -> list[str]:
    files = list(args.changed_file or [])
    if args.changed_files:
        normalized = str(args.changed_files).replace(";", "\n").replace(",", "\n")
        files.extend(item.strip() for item in normalized.splitlines() if item.strip())
    env_value = os.environ.get("DREAM_STUDIO_CHANGED_FILES")
    if env_value:
        normalized = env_value.replace(";", "\n").replace(",", "\n")
        files.extend(item.strip() for item in normalized.splitlines() if item.strip())
    if files:
        return sorted({item for item in files if item})

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    if base_ref:
        diff = _git_changed([base_ref + "...HEAD"])
        if diff:
            return diff

    pending = _git_changed(["--cached"]) + _git_changed(["HEAD"]) + _git_untracked()
    return sorted(set(pending))


def _git_changed(args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_untracked() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _write_current_hook_surfaces(home: Path) -> None:
    _write(
        home / ".claude" / "settings.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \\"C:/Users/Example/builds/dream-studio/hooks/run.py\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )
    _write(
        home / ".codex" / "hooks.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\\"C:/Users/Example/builds/dream-studio/hooks/run.cmd\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
