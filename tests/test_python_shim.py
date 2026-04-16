"""Tests for hooks.lib.python_shim."""

from __future__ import annotations

import pytest

from lib import python_shim


def test_detect_python_returns_first_match(monkeypatch):
    def fake_which(name):
        return "/usr/bin/" + name if name == "py" else None

    monkeypatch.setattr(python_shim.shutil, "which", fake_which)
    assert python_shim.detect_python() == "/usr/bin/py"


def test_detect_python_falls_through_to_python3(monkeypatch):
    def fake_which(name):
        return "/usr/bin/python3" if name == "python3" else None

    monkeypatch.setattr(python_shim.shutil, "which", fake_which)
    assert python_shim.detect_python() == "/usr/bin/python3"


def test_detect_python_falls_through_to_python(monkeypatch):
    def fake_which(name):
        return "/usr/bin/python" if name == "python" else None

    monkeypatch.setattr(python_shim.shutil, "which", fake_which)
    assert python_shim.detect_python() == "/usr/bin/python"


def test_detect_python_raises_when_nothing_found(monkeypatch):
    monkeypatch.setattr(python_shim.shutil, "which", lambda name: None)
    with pytest.raises(python_shim.PythonNotFoundError) as exc:
        python_shim.detect_python()
    message = str(exc.value)
    assert "No Python interpreter found" in message
    # Install instructions vary per platform, but every variant includes "Python".
    assert "Python" in message


def test_detect_python_custom_candidate_order(monkeypatch):
    monkeypatch.setattr(
        python_shim.shutil,
        "which",
        lambda name: "/opt/" + name if name == "pypy3" else None,
    )
    assert python_shim.detect_python(("pypy3",)) == "/opt/pypy3"
