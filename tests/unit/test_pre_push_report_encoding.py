"""The gate runner must not die printing its own result.

Every gate passed, and `py -m core.gates.pre_push > out.txt` still exited on a
UnicodeEncodeError from the runner's last line. Gate output is captured with
errors="replace", so a byte the child could not express arrives as U+FFFD, and
the gate descriptions carry em dashes; a redirected stdout on Windows is cp1252,
which can encode neither. Redirecting is what this repo's own instructions tell
people to do, so the failure mode was reachable by following the documentation.

The property is narrow and worth stating plainly: whether the gates ran is not
a question the terminal's encoding gets to answer.
"""

from __future__ import annotations

import io

from core.gates.pre_push import _print_report

REPLACEMENT = "�"
REPORT = f"[FAIL] some-gate (1.2s)\n   hint: an em dash — and a replacement {REPLACEMENT} char\nOverall: FAIL"


class _Cp1252Stdout(io.TextIOBase):
    """A stdout that behaves like a redirected Windows console: cp1252, strict,
    and refusing to be reconfigured."""

    encoding = "cp1252"

    def __init__(self):
        self.written: list[str] = []

    def write(self, s):
        s.encode("cp1252")  # raises UnicodeEncodeError exactly as the real one does
        self.written.append(s)
        return len(s)

    def reconfigure(self, **kwargs):
        raise OSError("cannot reconfigure a redirected stream")


def test_report_prints_when_the_stream_cannot_be_reconfigured(monkeypatch):
    stream = _Cp1252Stdout()
    monkeypatch.setattr("sys.stdout", stream)

    _print_report(REPORT)

    out = "".join(stream.written)
    assert "Overall: FAIL" in out, "the verdict must survive the encoding"
    assert "some-gate" in out, "the failing gate must still be named"


def test_report_prints_when_the_stream_can_be_reconfigured(monkeypatch, capsys):
    """The ordinary path: reconfigure to UTF-8 and the text survives intact,
    em dash and all."""
    _print_report(REPORT)
    out = capsys.readouterr().out
    assert "Overall: FAIL" in out
    assert "—" in out, "reconfiguring should preserve the em dash, not replace it"


def test_a_plain_report_is_unchanged(capsys):
    _print_report("Overall: PASS")
    assert capsys.readouterr().out.strip() == "Overall: PASS"
