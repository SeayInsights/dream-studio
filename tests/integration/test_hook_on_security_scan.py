"""Integration tests for on-security-scan hook."""

from __future__ import annotations

import io
import json


def _run(handler, payload: dict, capsys):
    import sys
    sys.stdin = io.StringIO(json.dumps(payload))
    mod = handler("on-security-scan")
    mod.main()
    return capsys.readouterr().out


def test_no_warning_on_clean_code(handler, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/utils.py",
            "new_string": "def add(a, b):\n    return a + b\n",
        },
    }
    out = _run(handler, payload, capsys)
    assert "[dream-studio] Security" not in out


def test_warns_on_hardcoded_password(handler, capsys):
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "config.py",
            "content": 'password = "mysecret123"\n',
        },
    }
    out = _run(handler, payload, capsys)
    assert "hardcoded credential" in out


def test_warns_on_eval(handler, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "app.py",
            "new_string": "result = eval(user_input)\n",
        },
    }
    out = _run(handler, payload, capsys)
    assert "eval()" in out


def test_warns_on_shell_true(handler, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "deploy.sh",
            "new_string": "subprocess.run(cmd, shell=True)\n",
        },
    }
    out = _run(handler, payload, capsys)
    assert "shell=True" in out


def test_skips_test_files(handler, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "tests/test_auth.py",
            "new_string": 'password = "test_secret"\n',
        },
    }
    out = _run(handler, payload, capsys)
    assert "[dream-studio] Security" not in out


def test_skips_non_source_extensions(handler, capsys):
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "report.md",
            "content": 'password = "leaked_secret"\n',
        },
    }
    out = _run(handler, payload, capsys)
    assert "[dream-studio] Security" not in out


def test_no_warning_on_empty_content(handler, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.py", "new_string": ""},
    }
    out = _run(handler, payload, capsys)
    assert "[dream-studio] Security" not in out


def test_ignores_non_edit_write_tools(handler, capsys):
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "config.py"},
    }
    out = _run(handler, payload, capsys)
    assert "[dream-studio] Security" not in out
