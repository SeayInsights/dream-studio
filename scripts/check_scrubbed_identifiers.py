"""Pre-commit hook: block re-introduction of scrubbed personal/client identifiers.

Phase 18.1.14a scrubbed personal email, former-client name, and related
identifying information from the repo. This hook prevents accidental
re-introduction by running on staged files at commit time.

To add an intentional exemption (e.g., a new file that legitimately contains
`info@twinrootsllc.com` as public contact branding), update EXEMPT_FILES below.

Exit codes:
- 0: no forbidden tokens found in staged files
- 1: at least one forbidden token found; commit blocked
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Forbidden tokens. Each is a regex pattern.
FORBIDDEN_PATTERNS = [
    r"***REMOVED***",
    r"***REMOVED***",
    r"dannis\.seay@twinrootsllc\.com",
    r"info@twinrootsllc\.com",
]

# Files where one or more forbidden tokens appear intentionally and must not
# block commits. Paths are relative to repo root, forward-slash separated.
EXEMPT_FILES: set[str] = {
    "SECURITY.md",  # info@twinrootsllc.com — intentional security disclosure contact
    "CHANGELOG.md",  # ***REMOVED*** in Phase 18.1.8 release note (line 355)
    # This file defines the forbidden patterns as string literals — must self-exempt
    "scripts/check_scrubbed_identifiers.py",
}


def main(argv: list[str]) -> int:
    failed = False
    compiled = [(re.compile(pattern), pattern) for pattern in FORBIDDEN_PATTERNS]
    for arg in argv[1:]:
        rel_path = arg.replace("\\", "/")
        if rel_path in EXEMPT_FILES:
            continue
        path = Path(arg)
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for compiled_pattern, original_pattern in compiled:
            if compiled_pattern.search(content):
                print(
                    f"BLOCKED: {arg} contains forbidden token matching: {original_pattern}",
                    file=sys.stderr,
                )
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
