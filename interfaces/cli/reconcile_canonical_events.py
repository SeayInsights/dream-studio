"""CLI wrapper for legacy canonical event reconciliation."""

from __future__ import annotations

from core.upgrade.canonical_event_reconciliation import main

if __name__ == "__main__":
    raise SystemExit(main())
