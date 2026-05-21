"""Source-only skill-sync regression check for the pre-push gate.

Runs the subset of skill-sync checks that depend on source files alone (not
on the operator's local install). Currently this is the A4/A5 enforcement-
block invariant: the compiler `_ENFORCEMENT_BLOCK` constant must contain no
`py -m interfaces.cli.ds` references.

Exit codes:
    0 — all source-level checks pass
    1 — regression detected; details printed to stderr
"""

from __future__ import annotations

import json
import sys

from core.health.doctor import _check_enforcement_block_no_cli


def main() -> int:
    cli_refs = _check_enforcement_block_no_cli()
    if not cli_refs:
        print(json.dumps({"status": "pass", "checks": {"enforcement_block_cli_refs": []}}))
        return 0

    print(
        json.dumps(
            {
                "status": "fail",
                "checks": {"enforcement_block_cli_refs": cli_refs},
                "fail_reason": (
                    "Compiler _ENFORCEMENT_BLOCK contains CLI references " "(A4/A5 regression)."
                ),
            }
        ),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
