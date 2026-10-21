"""header_analysis.py writes the header-analysis.json that parse_binary.py reads (issue #908).

WHY. binary-scan step A7 used to be a code sketch ("# Check: unsigned, debug symbols, known
vulnerable compiler") plus a JSON example, and nothing ever produced the file: the format was
invented, untested against pefile or pyelftools, and one of its three PE checks
(`no_known_vulnerable_compiler`) cannot be computed from a PE header at all. The step is now a
script that writes exactly the checks it can compute, and a test holds its output to what
`parse_header_json` accepts.

WHAT IS AND IS NOT VERIFIED HERE. pefile and pyelftools were not installed where this was
written, so the check logic is exercised against stand-ins shaped like the two libraries'
documented API (a PE with `OPTIONAL_HEADER.DATA_DIRECTORY` and `FILE_HEADER.NumberOfSymbols`;
an ELF with `iter_segments`, `iter_sections`, `get_section_by_name` and `PT_INTERP`'s
`get_interp_name`). That proves the logic and the file shape, not that the real libraries
return those attributes. The two `real_library` tests run the script against a real binary
when the library is installed and are skipped when it is not, which is the state this was
written in: UNVERIFIED against the real libraries until they run somewhere that has them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"
EXAMPLES = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "binary-scan" / "examples.md"

sys.path.insert(0, str(ETL))
sys.path.insert(0, str(REPO_ROOT))
import header_analysis  # noqa: E402
import parse_binary  # noqa: E402

# -- stand-ins shaped like the libraries --------------------------------------------------------


def _fake_pe(signed: bool, symbols: int) -> SimpleNamespace:
    directories = [SimpleNamespace(VirtualAddress=0, Size=0) for _ in range(16)]
    if signed:
        directories[4] = SimpleNamespace(VirtualAddress=0x9000, Size=0x2E0)
    return SimpleNamespace(
        OPTIONAL_HEADER=SimpleNamespace(DATA_DIRECTORY=directories),
        FILE_HEADER=SimpleNamespace(NumberOfSymbols=symbols),
        close=lambda: None,
    )


class _Segment(dict):
    def __init__(self, p_type: str, interp: str | None = None):
        super().__init__(p_type=p_type)
        self._interp = interp

    def get_interp_name(self) -> str | None:
        return self._interp


def _fake_elf(
    interp: str | None = "/lib64/ld-linux-x86-64.so.2",
    sections: tuple[tuple[str, int], ...] = ((".text", 0x6), (".data", 0x3)),
    symtab: bool = False,
) -> SimpleNamespace:
    segments = [_Segment("PT_LOAD")] + ([_Segment("PT_INTERP", interp)] if interp else [])
    secs = [{"name": n, "sh_flags": f} for n, f in sections]
    return SimpleNamespace(
        iter_segments=lambda: iter(segments),
        iter_sections=lambda: iter(secs),
        get_section_by_name=lambda name: ({"name": name} if symtab and name == ".symtab" else None),
    )


# -- the checks -----------------------------------------------------------------------------------


def test_pe_checks_signed_and_symbols():
    checks, notes = header_analysis.pe_checks(_fake_pe(signed=True, symbols=0))
    assert checks == {"signed": True, "debug_symbols_stripped": True}
    checks, _ = header_analysis.pe_checks(_fake_pe(signed=False, symbols=1200))
    assert checks == {"signed": False, "debug_symbols_stripped": False}
    assert any("not verified" in n for n in notes)  # a signature block is not a valid signature


def test_pe_signed_needs_both_an_address_and_a_size():
    pe = _fake_pe(signed=False, symbols=0)
    pe.OPTIONAL_HEADER.DATA_DIRECTORY[4] = SimpleNamespace(VirtualAddress=0x9000, Size=0)
    assert header_analysis.pe_checks(pe)[0]["signed"] is False
    pe.OPTIONAL_HEADER.DATA_DIRECTORY[4] = SimpleNamespace(VirtualAddress=0, Size=0x2E0)
    assert header_analysis.pe_checks(pe)[0]["signed"] is False


def test_elf_checks_for_a_hardened_binary():
    checks, _ = header_analysis.elf_checks(_fake_elf())
    assert checks == {
        "interpreter_trusted": True,
        "symbols_stripped": True,
        "no_writable_executable_sections": True,
    }


def test_elf_checks_for_a_weak_binary():
    elf = _fake_elf(
        interp="/tmp/evil-loader", sections=((".text", 0x6), (".rwx", 0x7)), symtab=True
    )
    checks, _ = header_analysis.elf_checks(elf)
    assert checks == {
        "interpreter_trusted": False,
        "symbols_stripped": False,
        "no_writable_executable_sections": False,
    }


def test_a_static_elf_has_no_interpreter_and_that_is_trusted():
    assert header_analysis.elf_checks(_fake_elf(interp=None))[0]["interpreter_trusted"] is True


@pytest.mark.parametrize(
    "interp, trusted",
    [
        ("/lib64/ld-linux-x86-64.so.2", True),
        ("/lib/ld-linux.so.2", True),
        ("/lib/ld-linux-aarch64.so.1", True),
        ("/lib/ld-musl-x86_64.so.1", True),
        ("/usr/lib/ld.so.1", True),
        ("/lib64/ld-linux-x86-64.so.2/../../tmp/x", False),
        ("/tmp/ld-linux-x86-64.so.2", False),
        ("/lib64/evil.so", False),
        ("ld-linux-x86-64.so.2", False),
        ("", True),
        (None, True),
    ],
)
def test_interpreter_trust(interp: str | None, trusted: bool):
    assert header_analysis.interpreter_is_trusted(interp) is trusted


@pytest.mark.parametrize("flags, ok", [(0x1, True), (0x4, True), (0x5, False), (0x7, False)])
def test_only_a_section_both_writable_and_executable_fails(flags: int, ok: bool):
    elf = _fake_elf(sections=((".x", flags),))
    assert header_analysis.elf_checks(elf)[0]["no_writable_executable_sections"] is ok


def test_format_is_decided_by_the_magic_bytes():
    assert header_analysis.detect_format(b"MZ\x90\x00") == "pe"
    assert header_analysis.detect_format(b"\x7fELF") == "elf"
    assert header_analysis.detect_format(b"#!/bin/sh") is None
    assert (
        header_analysis.detect_format(b"M") is None and header_analysis.detect_format(b"MX") is None
    )
    assert header_analysis.detect_format(b"\x7fEL") is None
    assert header_analysis.detect_format(b"") is None


# -- the file it writes is the file parse_binary reads ----------------------------------------------


def _install_fake_libs(monkeypatch, pe: SimpleNamespace | None, elf: SimpleNamespace | None):
    if pe is not None:
        mod = types.ModuleType("pefile")
        mod.PE = lambda path, fast_load=False: pe
        monkeypatch.setitem(sys.modules, "pefile", mod)
    if elf is not None:
        names = ("elftools", "elftools.elf", "elftools.elf.elffile")
        mods = {n: types.ModuleType(n) for n in names}
        mods["elftools.elf.elffile"].ELFFile = lambda fh: elf
        for n, m in mods.items():
            monkeypatch.setitem(sys.modules, n, m)


def _binary(tmp_path: Path, magic: bytes, name: str = "app.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(magic + b"\x00" * 64)
    return path


def test_pe_output_is_read_by_parse_binary(tmp_path: Path, monkeypatch):
    _install_fake_libs(monkeypatch, _fake_pe(signed=False, symbols=0), None)
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([str(_binary(tmp_path, b"MZ")), "--output", str(out)]) == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "pe"
    assert set(data["checks"]) <= set(parse_binary.HEADER_CHECK_META)
    assert all(isinstance(v, bool) for v in data["checks"].values())
    assert "no_known_vulnerable_compiler" not in data["checks"]  # not computable, not written
    assert parse_binary.detect_step(data, out.name) == "header_analysis"

    degraded: list[str] = []
    notes: list[str] = []
    findings = parse_binary.parse_header_json(data, "app", "", degraded, notes)
    assert [f["rule_id"] for f in findings] == ["BIN-hdr-signed"]  # signed=false is the finding
    assert degraded == []  # every value was a boolean the parser could read
    assert any("not verified" in n for n in notes)  # and the caveat reaches the limitations


def test_elf_output_is_read_by_parse_binary(tmp_path: Path, monkeypatch):
    elf = _fake_elf(interp="/tmp/x", sections=((".text", 0x7),), symtab=True)
    _install_fake_libs(monkeypatch, None, elf)
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([str(_binary(tmp_path, b"\x7fELF")), "--output", str(out)]) == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "elf"
    assert set(data["checks"]) == set(parse_binary.HEADER_FORMAT_CHECKS["elf"])
    degraded: list[str] = []
    findings = parse_binary.parse_header_json(data, "app", "", degraded, [])
    assert {f["rule_id"] for f in findings} == {
        "BIN-hdr-interpreter_trusted",
        "BIN-hdr-symbols_stripped",
        "BIN-hdr-no_writable_executable_sections",
    }
    assert degraded == []


def test_every_check_the_script_can_write_is_one_the_parser_lists():
    pe = set(header_analysis.pe_checks(_fake_pe(True, 0))[0])
    elf = set(header_analysis.elf_checks(_fake_elf())[0])
    assert pe <= set(parse_binary.HEADER_FORMAT_CHECKS["pe"])
    assert elf == set(parse_binary.HEADER_FORMAT_CHECKS["elf"])


def test_notes_in_the_file_reach_the_limitations_and_junk_notes_do_not_crash():
    data = {"format": "pe", "checks": {"signed": True}, "notes": ["a caveat", 3, None, "b\x1b[31m"]}
    notes: list[str] = []
    parse_binary.parse_header_json(data, "app", "", [], notes)
    assert "a caveat" in notes and all(isinstance(n, str) and n.isprintable() for n in notes)
    parse_binary.parse_header_json({**data, "notes": "not a list"}, "app", "", [], [])


# -- the outcomes the run record needs ---------------------------------------------------------------


def _blocked_import(module: str, binary: str, output: str) -> str:
    """A fresh interpreter in which `import <module>` fails, running the script's main."""
    return (
        "import sys; sys.modules[%r] = None; sys.path.insert(0, %r); import header_analysis; "
        "sys.exit(header_analysis.main([%r, '--output', %r]))" % (module, str(ETL), binary, output)
    )


def test_a_missing_library_exits_3_with_the_reason_and_writes_nothing(tmp_path: Path):
    out = tmp_path / "header-analysis.json"
    code = _blocked_import("pefile", str(_binary(tmp_path, b"MZ")), str(out))
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8"
    )
    assert proc.returncode == 3, proc.stderr
    assert "pefile is not installed" in proc.stderr
    assert not out.exists()


def test_elf_without_pyelftools_exits_3(tmp_path: Path, monkeypatch, capsys):
    for name in ("elftools", "elftools.elf", "elftools.elf.elffile"):
        monkeypatch.setitem(sys.modules, name, None)
    out = tmp_path / "h.json"
    assert header_analysis.main([str(_binary(tmp_path, b"\x7fELF")), "--output", str(out)]) == 3
    assert "pyelftools is not installed" in capsys.readouterr().err
    assert not out.exists()


def test_a_file_that_is_neither_pe_nor_elf_exits_2(tmp_path: Path, capsys):
    out = tmp_path / "h.json"
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")
    assert header_analysis.main([str(text), "--output", str(out)]) == 2
    assert "not a PE or ELF file" in capsys.readouterr().err
    assert not out.exists()


def test_a_missing_file_exits_2(tmp_path: Path, capsys):
    assert header_analysis.main([str(tmp_path / "nope.exe"), "--output", str(tmp_path / "h")]) == 2
    assert "could not read" in capsys.readouterr().err


def test_a_binary_the_library_cannot_parse_exits_2(tmp_path: Path, monkeypatch, capsys):
    mod = types.ModuleType("pefile")

    def explode(path, fast_load=False):
        raise ValueError("DOS Header magic not found.")

    mod.PE = explode
    monkeypatch.setitem(sys.modules, "pefile", mod)
    code = header_analysis.main([str(_binary(tmp_path, b"MZ")), "--output", str(tmp_path / "h")])
    assert code == 2
    assert "DOS Header magic not found" in capsys.readouterr().err


# -- the doc ------------------------------------------------------------------------------------------


def test_step_a7_documents_the_script_and_its_exit_codes():
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    a7 = text.split("### Step A7")[1].split("### Step A8")[0].lower()
    assert "header_analysis.py" in a7 and "--output" in a7
    assert "exits 0" in a7 and "exits 3" in a7 and "exits 2" in a7
    assert "no_known_vulnerable_compiler" in a7 and "not computed" in a7
    assert "not verified" in a7  # `signed` is a signature block, not a valid signature


# -- real libraries, when present --------------------------------------------------------------------


def test_real_library_pe_on_the_running_interpreter(tmp_path: Path):
    pytest.importorskip("pefile")
    if sys.platform != "win32":
        pytest.skip("the interpreter is not a PE file here")
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([sys.executable, "--output", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "pe" and set(data["checks"]) == {"signed", "debug_symbols_stripped"}
    parse_binary.parse_header_json(data, "python", "", [], [])


def test_real_library_elf_on_a_system_binary(tmp_path: Path):
    pytest.importorskip("elftools")
    candidate = next((p for p in (Path("/bin/ls"), Path("/usr/bin/ls")) if p.is_file()), None)
    if candidate is None:
        pytest.skip("no ELF binary to analyze here")
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([str(candidate), "--output", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "elf"
    parse_binary.parse_header_json(data, "ls", "", [], [])
