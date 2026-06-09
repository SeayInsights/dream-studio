#!/usr/bin/env python3
"""Check or refresh Dream Studio repo publication readiness evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.release.repo_publication_readiness import (  # noqa: E402
    build_repo_publication_readiness,
    refresh_repo_publication_artifacts,
    validate_repo_publication_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "publication",
        help="Publication evidence output directory.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write publication evidence files. Default is dry run.",
    )
    parser.add_argument(
        "--clean-clone-status",
        choices=["pass", "fail", "not_run"],
        default="not_run",
        help="Status from a separate clean clone rehearsal.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless publication readiness validates fully.",
    )
    args = parser.parse_args()

    if args.execute:
        payload = refresh_repo_publication_artifacts(
            REPO_ROOT,
            output_dir=args.output_dir,
            execute=True,
            clean_clone_status=args.clean_clone_status,
        )
        readiness = payload["publication_readiness"]
    else:
        readiness = build_repo_publication_readiness(
            REPO_ROOT,
            clean_clone_status=args.clean_clone_status,
        )
        payload = readiness

    issues = validate_repo_publication_readiness(readiness)
    if issues:
        payload["validation_issues"] = issues
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
