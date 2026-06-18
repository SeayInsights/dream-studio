"""WO-DASH-RESTART: `ds dashboard` must be able to stop/restart a running server
and optionally hot-reload, instead of silently serving a stale process.

Module-level functions so the work order's bare TEST-CHECK node-ids resolve.
All process/subprocess interaction is mocked — no real server is spawned and no
real process is killed.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import interfaces.cli.ds_dashboard as dash


def test_restart_stops_existing_then_relaunches():
    """--restart stops the running server, then relaunches via the boot path."""
    with (
        patch.object(dash, "_port_in_use", return_value=True),
        patch.object(dash, "cmd_stop", return_value=0) as mock_stop,
        patch.object(dash, "_launch_and_serve", return_value=0) as mock_launch,
        patch.object(dash.time, "sleep", return_value=None),
    ):
        rc = dash.cmd_restart(8099, "127.0.0.1", open_browser=False)

    assert rc == 0
    assert mock_stop.called, "restart must stop the existing server first"
    assert mock_launch.called, "restart must relaunch after stopping"


def test_restart_aborts_if_stop_fails():
    """If the existing server can't be stopped, restart aborts (does not relaunch)."""
    with (
        patch.object(dash, "_port_in_use", return_value=True),
        patch.object(dash, "cmd_stop", return_value=1),
        patch.object(dash, "_launch_and_serve", return_value=0) as mock_launch,
        patch.object(dash.time, "sleep", return_value=None),
    ):
        rc = dash.cmd_restart(8099, "127.0.0.1")

    assert rc == 1
    assert not mock_launch.called, "must not relaunch if the stale server could not be stopped"


def test_reload_flag_passes_through_to_uvicorn():
    """launch_server appends --reload to the uvicorn command only when reload=True."""
    with patch.object(dash.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        dash.launch_server(8099, "127.0.0.1", reload=True)
        cmd_with = mock_popen.call_args[0][0]
    assert "--reload" in cmd_with, "reload=True must pass --reload to uvicorn"

    with patch.object(dash.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        dash.launch_server(8099, "127.0.0.1", reload=False)
        cmd_without = mock_popen.call_args[0][0]
    assert "--reload" not in cmd_without, "reload must be OFF by default"


def test_open_warns_when_port_in_use(capsys):
    """When the port is already in use, the default launch WARNS about a possibly
    stale server and prints the restart command (instead of silently attaching)."""
    with (
        patch.object(sys, "argv", ["ds_dashboard"]),
        patch.object(dash, "_port_in_use", return_value=True),
        patch.object(dash, "webbrowser") as mock_web,
    ):
        rc = dash.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "already running" in out
    assert "stale" in out.lower(), "must warn the running server may be stale"
    assert "--restart" in out, "must print the restart command to recover"
    assert mock_web.open.called, "still opens the browser after warning"


def test_help_documents_restart():
    """`ds dashboard --help` documents --restart and stop."""
    result = subprocess.run(
        [sys.executable, "interfaces/cli/ds_dashboard.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    text = result.stdout + result.stderr
    assert "--restart" in text, "help must document --restart"
    assert "stop" in text.lower(), "help must document stop"


def test_end_to_end():
    """The restart/stop/reload surface is wired: helpers exist, launch_server takes a
    reload flag, and the parser accepts the new flags."""
    import inspect

    for fn in ("_find_pid_on_port", "_kill_pid", "cmd_stop", "cmd_restart", "launch_server"):
        assert hasattr(dash, fn), f"{fn} missing"

    assert "reload" in inspect.signature(dash.launch_server).parameters

    # The parser accepts --restart / --stop / --reload without error.
    for flag in ("--restart", "--stop", "--reload"):
        with (
            patch.object(sys, "argv", ["ds_dashboard", flag]),
            patch.object(dash, "cmd_stop", return_value=0),
            patch.object(dash, "cmd_restart", return_value=0),
            patch.object(dash, "_launch_and_serve", return_value=0),
            patch.object(dash, "_port_in_use", return_value=False),
        ):
            rc = dash.main()
            assert rc == 0, f"{flag} should parse and dispatch cleanly"
