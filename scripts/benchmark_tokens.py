"""Compatibility shim — delegates to interfaces/cli/benchmark_tokens.py.

Docs and README reference ``scripts/benchmark_tokens.py``.
This shim forwards all invocations to the canonical location.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "interfaces" / "cli" / "benchmark_tokens.py"


def main() -> int:
    if not CANONICAL.exists():
        print(f"ERROR: canonical script not found at {CANONICAL}", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(CANONICAL)] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
