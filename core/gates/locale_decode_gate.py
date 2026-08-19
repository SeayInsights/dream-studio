"""Locale-decode gate (WO-LOCALE-DECODE-SILENT-LOSS).

``subprocess.run(..., text=True)`` with no ``encoding=`` decodes the child's
output with ``locale.getpreferredencoding(False)`` — cp1252 on Windows. Every
gate in this repo emits UTF-8, so one byte cp1252 leaves unmapped (0x81, 0x8D,
0x8F, 0x90, 0x9D) raises UnicodeDecodeError inside subprocess's reader *thread*.

Measured on Windows/CPython 3.12, what follows is not a crash and not a hang:
``run()`` returns in under a tenth of a second with ``returncode == 0`` and
``stdout is None``. The thread's traceback lands on the parent's stderr, which
in a git hook is nobody's job to read. So the caller is handed success plus no
output, and what it does next decides the damage: reading the return code sees a
pass, ``stdout or ""`` sees "there was no output", and ``stdout.splitlines()``
dies with AttributeError for a reason unrelated to what it was checking.

The triggering characters are ordinary, not exotic — ❌ (E2 9D **8C**), ← (E2 86
**90**), the emoji variation selector (EF B8 **8F**), 📁, ● — and 53 files in
this repo already contain one. Found when a push printed a bare reader-thread
traceback and no gate output at all. An AST sweep then showed 118 sites, 62 in
product code, across eleven of the blocking gate files. At most sites the
verdict itself survived (they decide on exit codes) and what was lost was the
*evidence* — but nothing was checking, which is why 62 accumulated. Hence this
gate.

Detection is AST-based, not textual: ``text=True`` inside a string, a comment,
or a docstring is not a call, and a call spanning several lines has no single
line to grep. The scan reports the *keyword's* own position so the message
points at the argument to fix.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that are not ours to fix (vendored, generated, or transient).
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "graphify-out",
        "dist",  # generated plugin distribution — regenerated from canonical sources
    }
)

# The subprocess entry points that decode child output.
_SPAWNING_CALLS = frozenset({"run", "check_output", "Popen", "check_call"})

# Either kwarg turns on text mode; both share the locale-codec default.
_TEXT_KWARGS = frozenset({"text", "universal_newlines"})


# The one legitimate reason to write an unguarded call is to demonstrate the defect,
# which the gate's own test must do. Marking the line exempts it — and the gate then
# PRINTS every exemption on the pass path, because an escape hatch nobody can see is
# how the 62 sites got here. The marker carries its own reason so the print explains
# itself: `text=True,  # locale-decode-gate: intentional — <why>`.
_EXEMPT_MARKER = "locale-decode-gate: intentional"


@dataclass(frozen=True)
class LocaleDecodeSite:
    """One subprocess call that will decode child output with the locale codec."""

    path: str  # repo-relative, forward slashes
    line: int  # line of the offending kwarg, not the call
    call: str  # run / check_output / Popen / check_call
    kwarg: str  # text / universal_newlines
    exempt: bool = False  # carries the inline marker

    @property
    def is_test(self) -> bool:
        return self.path.startswith("tests/")

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.path}:{self.line}  {self.call}(... {self.kwarg}=True) has no encoding="


class SourceUnreadable(RuntimeError):
    """A Python file under scan could not be read or parsed.

    Raised rather than skipped, for the reason the test-list gate learned the
    hard way (gap WO 681b294e): a scan that swallows read errors reports "no
    violations" for files it never looked at, and a gate that cannot read its
    inputs must fail loudly instead of passing vacuously.
    """


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*.py")
        if not any(part in _SKIP_DIRS for part in p.relative_to(root).parts)
    )


def locale_decoded_calls(root: Path | None = None) -> list[LocaleDecodeSite]:
    """Every subprocess call that decodes child output with the locale codec.

    A call that passes ``encoding=`` is compliant whatever the value: naming a
    codec is a decision, and this gate polices unexamined defaults rather than
    the choice itself. ``errors=`` is not required here — it governs what
    happens to undecodable bytes once a codec is chosen, which is the caller's
    call to make.
    """
    root = root or _REPO_ROOT
    sites: list[LocaleDecodeSite] = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            source_lines = source.splitlines()
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeDecodeError) as exc:
            raise SourceUnreadable(f"{rel} unreadable: {exc}") from exc
        except SyntaxError as exc:
            # A file this interpreter cannot parse may still be valid for the
            # project's target version, so it is reported, not silently skipped.
            raise SourceUnreadable(f"{rel} unparseable: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                continue
            if name not in _SPAWNING_CALLS:
                continue
            kwargs = {k.arg for k in node.keywords if k.arg}
            if "encoding" in kwargs:
                continue
            for keyword in node.keywords:
                if keyword.arg not in _TEXT_KWARGS:
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and value.value is True:
                    line_text = (
                        source_lines[keyword.lineno - 1]
                        if keyword.lineno <= len(source_lines)
                        else ""
                    )
                    sites.append(
                        LocaleDecodeSite(
                            path=rel,
                            line=keyword.lineno,
                            call=name,
                            kwarg=str(keyword.arg),
                            exempt=_EXEMPT_MARKER in line_text,
                        )
                    )
    return sites


def main(argv: list[str] | None = None) -> int:
    """Blocking gate: any locale-decoded subprocess call fails the push.

    Product and test sites are reported separately but both block. A test that
    silently loses a child's output is not the lesser problem: it is a test
    asserting against an empty string it believes came from the child.
    """
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]).resolve() if argv else _REPO_ROOT
    try:
        sites = locale_decoded_calls(root)
    except SourceUnreadable as exc:
        print(f"locale-decode gate: FAILED — {exc}")
        print("  A gate that cannot read its inputs must not report a pass.")
        return 2

    exempt = [s for s in sites if s.exempt]
    sites = [s for s in sites if not s.exempt]

    if not sites:
        print("locale-decode gate: PASSED — no subprocess call relies on the locale codec.")
        _print_exemptions(exempt)
        return 0

    product = [s for s in sites if not s.is_test]
    tests = [s for s in sites if s.is_test]
    print(f"locale-decode gate: FAILED — {len(sites)} site(s) decode child output with the")
    print("  platform locale codec (cp1252 on Windows). One non-cp1252 byte raises")
    print("  UnicodeDecodeError in subprocess's reader thread and HANGS the parent.")
    for label, group in (("product", product), ("tests", tests)):
        if not group:
            continue
        print(f"\n  {label} ({len(group)}):")
        for site in group:
            print(f"    {site}")
    print('\n  Fix: add encoding="utf-8", errors="replace" to each call.')
    _print_exemptions(exempt)
    return 1


def _print_exemptions(exempt: list[LocaleDecodeSite]) -> None:
    """Always name the exempted sites, on pass and on fail alike.

    An exemption that only shows up when someone goes looking is the same shape as
    the defect it is exempting: present, load-bearing, and unread.
    """
    if not exempt:
        return
    print(f"\n  {len(exempt)} exempted site(s) (marked {_EXEMPT_MARKER!r}):")
    for site in exempt:
        print(f"    {site.path}:{site.line}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
