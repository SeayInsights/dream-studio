# Dream Studio — Backlog

## Phantom SIGINT during pytest on Windows (RESOLVED)

Windows 11 + Python 3.12 + the ingest pipeline's rapid file moves and SQLite writes triggered phantom SIGINT delivery during pytest sessions. Investigation eliminated:

- All third-party pytest plugins (anyio, asyncio, aio, cov, faker)
- Pytest built-in plugins (cacheprovider, capture, faulthandler, terminalprogress)
- Python output buffering, colorama, ANSI escape handling
- Windows Defender, OneDrive sync, Logitech G HUB, GoXLR, Cowork
- WAL mode SQLite journal files (still occurred with DELETE mode)
- UCPD, CldFlt, gameflt filesystem filter drivers (detach test)
- Filesystem ACLs on TEMP (took ownership, recreated tree from scratch)
- SeCreateSymbolicLinkPrivilege (granted via Developer Mode + secpol.msc)
- Pytest's pytest-current and per-test symlink machinery

The signal source could not be fully isolated but was reproducibly bounded to calls through `ingest_pending` involving SQLite writes following file moves.

Resolution:

1. Module-level Windows console control handler in `spool/ingestor.py` using `SetConsoleCtrlHandler` via ctypes. Absorbs single phantom CTRL_C events while preserving real user Ctrl+C (two within 1 second forward to default handler). Production-facing.

2. SIGINT handler at the top of `tests/conftest.py` plus a `pytest_configure` hook that reinstalls our handler after pytest installs its own. Prevents pytest's SIGINT machinery from printing a KeyboardInterrupt banner after the test summary line.

Both fixes are Windows-only. Linux CI is unaffected. End users on Windows get the production handler automatically with no setup.

Future investigation if needed:
- Procmon trace during the actual SIGINT moment (not cleanup phase)
- Test on a fresh Windows machine to confirm machine-specific vs universal
- Try Python 3.11 or 3.13 to check for 3.12-specific regression
