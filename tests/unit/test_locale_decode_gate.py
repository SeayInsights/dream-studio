"""Locale-decode gate tests (WO-LOCALE-DECODE-SILENT-LOSS).

Asserting that ``encoding=`` appears in the source would prove nothing about the
defect, so the failure mode itself is reproduced here: a child emitting a byte
that is undecodable under both cp1252 and strict UTF-8 is survivable by the
guarded call, and from the unguarded one it comes back as success-with-no-output.

That last part was measured, not assumed. The first version of this file asserted
the unguarded call would raise or hang, ran an elaborate child-interpreter dance
to avoid hanging the suite, and failed — because the real behaviour is quieter
and worse than either guess.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from core.gates.locale_decode_gate import (
    SourceUnreadable,
    locale_decoded_calls,
    main,
)

# 0x8D is unmapped in cp1252 AND an invalid UTF-8 start byte, so the same child
# output breaks the default decode on Windows and on Linux/macOS alike. It is the
# byte the discovering push tripped over, and it is a continuation byte in the
# UTF-8 encoding of the cross mark this repo's own gate output uses.
_BAD_BYTE_CHILD = "import sys; sys.stdout.buffer.write(b'ok\\x8ddone'); sys.stdout.flush()"


def _write(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# ── The gate's detection ────────────────────────────────────────────────────────


def test_gate_flags_a_locale_decoded_call(tmp_path):
    _write(
        tmp_path,
        "offender.py",
        """
        import subprocess

        def check():
            return subprocess.run(["git", "log"], capture_output=True, text=True)
        """,
    )
    sites = locale_decoded_calls(tmp_path)
    assert len(sites) == 1
    assert sites[0].path == "offender.py"
    assert sites[0].kwarg == "text"
    assert sites[0].call == "run"
    # The reported line is the kwarg's, so the message points at what to change.
    assert sites[0].line == 5


def test_gate_passes_when_encoding_is_set(tmp_path):
    _write(
        tmp_path,
        "compliant.py",
        """
        import subprocess

        subprocess.run(["git", "log"], capture_output=True, text=True, encoding="utf-8")
        subprocess.check_output(["git", "log"], text=True, encoding="utf-8", errors="replace")
        subprocess.run(["git", "log"], capture_output=True)  # bytes mode, no decode
        """,
    )
    assert locale_decoded_calls(tmp_path) == []
    assert main([str(tmp_path)]) == 0


def test_universal_newlines_is_the_same_defect(tmp_path):
    _write(
        tmp_path,
        "legacy.py",
        """
        import subprocess

        subprocess.check_output(["git", "log"], universal_newlines=True)
        """,
    )
    sites = locale_decoded_calls(tmp_path)
    assert [s.kwarg for s in sites] == ["universal_newlines"]


def test_detection_is_ast_based_not_textual(tmp_path):
    """A textual scan would flag all three of these. None is a call."""
    _write(
        tmp_path,
        "lookalikes.py",
        """
        '''Docstring mentioning text=True on purpose.'''
        import subprocess

        NOTE = "pass text=True to decode"
        # subprocess.run(cmd, text=True) — commented out
        subprocess.run(["git", "log"], capture_output=True, text=True, encoding="utf-8")
        """,
    )
    assert locale_decoded_calls(tmp_path) == []


def test_multiline_call_is_detected(tmp_path):
    """A call spanning lines has no single line to grep — the reason for the AST."""
    _write(
        tmp_path,
        "spread.py",
        """
        import subprocess

        subprocess.run(
            ["git", "log"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        """,
    )
    sites = locale_decoded_calls(tmp_path)
    assert len(sites) == 1
    assert sites[0].line == 7


def test_unreadable_source_fails_loudly_rather_than_reporting_clean(tmp_path):
    """Gap WO 681b294e's lesson: a scan that swallows read errors reports "no
    violations" for files it never opened."""
    _write(tmp_path, "broken.py", "def f(:\n    pass\n")
    with pytest.raises(SourceUnreadable):
        locale_decoded_calls(tmp_path)
    assert main([str(tmp_path)]) == 2


def test_generated_and_vendored_trees_are_out_of_scope(tmp_path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "gen.py").write_text(
        "import subprocess\nsubprocess.run(['x'], text=True)\n", encoding="utf-8"
    )
    assert locale_decoded_calls(tmp_path) == []


# ── The failure mode itself ─────────────────────────────────────────────────────


def test_non_cp1252_child_output_does_not_raise():
    """The guarded form survives a byte no default codec can decode."""
    completed = subprocess.run(
        [sys.executable, "-c", _BAD_BYTE_CHILD],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0
    # The undecodable byte became a replacement char; the surrounding output survived.
    assert "ok" in completed.stdout and "done" in completed.stdout


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="the silent-loss shape is Windows-specific: only there does subprocess read "
    "the pipes on threads whose death is invisible to the caller",
)
def test_the_unguarded_form_loses_output_and_still_reports_success():
    """The defect, as measured rather than as assumed.

    The obvious guess is that a bad decode raises, or that the parent hangs on the
    pipe nobody drained. On Windows/CPython 3.12 it does neither: the reader
    *thread* raises UnicodeDecodeError, ``run()`` returns in under a tenth of a
    second, ``returncode`` is 0, and ``stdout`` is silently **None** — the
    thread's traceback goes to the parent's stderr, which is exactly where a git
    hook's output is nobody's job to read.

    That is the shape that matters. A caller reading the return code sees success;
    a caller doing ``result.stdout or ""`` sees no output and concludes there was
    none; a caller doing ``result.stdout.splitlines()`` gets AttributeError and
    fails for a reason unrelated to what it was checking.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _BAD_BYTE_CHILD],
        capture_output=True,
        text=True,  # locale-decode-gate: intentional — this call IS the defect under test
        timeout=60,
    )
    assert completed.returncode == 0, "the child succeeded; only the parent's decode failed"
    assert completed.stdout is None, (
        "the unguarded read returned output, so this interpreter no longer loses it "
        f"silently and the gate's rationale needs revisiting: {completed.stdout!r}"
    )


def test_the_unguarded_form_is_not_survivable_anywhere():
    """Cross-platform half of the claim: no default gives back the child's bytes.

    On POSIX the default codec is UTF-8 and the same byte is invalid there too, so
    the read raises in the main thread instead of losing the output quietly. Either
    way the caller never receives what the child wrote — which is the whole reason
    ``encoding=`` is not optional.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _BAD_BYTE_CHILD],
            capture_output=True,
            text=True,  # locale-decode-gate: intentional — this call IS the defect under test
            timeout=60,
        )
    except (UnicodeDecodeError, ValueError):
        return  # raised outright — the POSIX shape
    assert completed.stdout is None or "�" in completed.stdout, (
        "an unguarded read returned the child's text intact, which no documented "
        f"default codec should do for this byte: {completed.stdout!r}"
    )


# ── The exemption, and its visibility ───────────────────────────────────────────


def test_marked_sites_are_exempt_but_never_invisible(tmp_path, capsys):
    """The escape hatch has to exist — this file's own two calls need it — but an
    exemption nobody can see is the shape of the defect it exempts."""
    _write(
        tmp_path,
        "demo.py",
        """
        import subprocess

        # locale-decode-gate: intentional — demonstrates the defect
        subprocess.run(["git", "log"], capture_output=True, text=True)  # locale-decode-gate: intentional
        """,
    )
    sites = locale_decoded_calls(tmp_path)
    assert [s.exempt for s in sites] == [True]

    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "PASSED" in out
    assert "1 exempted site(s)" in out
    assert "demo.py:5" in out, "the exempted site must be named, not merely tolerated"


def test_the_marker_must_be_on_the_kwarg_line(tmp_path):
    """A marker in the file header would exempt the whole file by accident."""
    _write(
        tmp_path,
        "sloppy.py",
        """
        # locale-decode-gate: intentional
        import subprocess

        subprocess.run(["git", "log"], capture_output=True, text=True)
        """,
    )
    sites = locale_decoded_calls(tmp_path)
    assert [s.exempt for s in sites] == [False]
    assert main([str(tmp_path)]) == 1


# ── The regression guard ────────────────────────────────────────────────────────


def test_this_repository_has_no_locale_decoded_calls():
    """The guard that matters: 62 product sites accumulated because nothing checked."""
    unguarded = [s for s in locale_decoded_calls() if not s.exempt]
    assert unguarded == [], "new locale-decoded subprocess call(s):\n" + "\n".join(
        f"  {s}" for s in unguarded
    )


def test_the_only_exemptions_in_this_repository_are_this_file_s_demonstrations():
    """Exemptions are meant to stay rare. If this assertion starts failing, the
    marker is being used as a way past the gate rather than a way to test it."""
    exempt = [s for s in locale_decoded_calls() if s.exempt]
    assert {s.path for s in exempt} <= {
        "tests/unit/test_locale_decode_gate.py"
    }, "the exemption marker escaped this file: " + ", ".join(sorted(s.path for s in exempt))
