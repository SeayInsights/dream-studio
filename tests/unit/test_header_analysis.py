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
import os
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


#: Big enough that every offset the fakes use lies inside the file.
FILE_SIZE = 0xA000


def _fake_pe(
    signed: bool,
    symbols: int,
    sections: tuple[tuple[int, int], ...] = ((0x400, 0x1000),),
    symbol_pointer: int = 0x8000,
    declared_sections: int | None = None,
    size_of_headers: int = 0x400,
) -> SimpleNamespace:
    directories = [SimpleNamespace(VirtualAddress=0, Size=0) for _ in range(16)]
    if signed:
        directories[4] = SimpleNamespace(VirtualAddress=0x9000, Size=0x2E0)
    return SimpleNamespace(
        OPTIONAL_HEADER=SimpleNamespace(DATA_DIRECTORY=directories, SizeOfHeaders=size_of_headers),
        FILE_HEADER=SimpleNamespace(
            NumberOfSymbols=symbols,
            PointerToSymbolTable=symbol_pointer,
            # a header that declares more sections than pefile could parse is a cut file
            NumberOfSections=len(sections) if declared_sections is None else declared_sections,
        ),
        sections=[
            SimpleNamespace(PointerToRawData=pointer, SizeOfRawData=size)
            for pointer, size in sections
        ],
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


def test_pe_checks_a_signature_block_reads_signed_true():
    checks, notes = header_analysis.pe_checks(_fake_pe(signed=True, symbols=0), FILE_SIZE)
    assert checks == {"signed": True, "debug_symbols_stripped": True}
    assert any("not verified" in n and "present" in n for n in notes)


def test_no_embedded_signature_is_never_written_as_signed_false():
    """notepad.exe and cmd.exe are Authenticode-valid through a catalog pefile cannot see:
    `signed: false` would become a finding about a signed file."""
    checks, notes = header_analysis.pe_checks(_fake_pe(signed=False, symbols=40), FILE_SIZE)
    assert checks == {"debug_symbols_stripped": False}
    assert "signed" not in checks
    text = " ".join(notes)
    assert "signed: not reported" in text and "catalog signatures" in text
    assert "block is present" not in text  # no claim of a block next to the absent check


def test_pe_signed_needs_both_an_address_and_a_size():
    pe = _fake_pe(signed=False, symbols=0)
    pe.OPTIONAL_HEADER.DATA_DIRECTORY[4] = SimpleNamespace(VirtualAddress=0x9000, Size=0)
    assert "signed" not in header_analysis.pe_checks(pe, FILE_SIZE)[0]
    pe.OPTIONAL_HEADER.DATA_DIRECTORY[4] = SimpleNamespace(VirtualAddress=0, Size=0x2E0)
    assert "signed" not in header_analysis.pe_checks(pe, FILE_SIZE)[0]


# -- a truncated PE is refused, not analysed ---------------------------------------------------------


@pytest.mark.parametrize(
    "pe, what",
    [
        (_fake_pe(signed=True, symbols=0), "certificate table"),
        (_fake_pe(signed=False, symbols=10, symbol_pointer=0x9FF8), "COFF symbol table"),
        (_fake_pe(signed=False, symbols=0, sections=((0x9800, 0x1000),)), "section"),
    ],
    ids=["certificate-table", "symbol-table", "section-data"],
)
def test_offsets_past_the_end_of_the_file_are_refused(pe, what):
    with pytest.raises(ValueError, match=what):
        header_analysis.pe_checks(pe, 0x9000 if what == "certificate table" else 0xA000)


def test_a_header_that_declares_sections_pefile_could_not_parse_is_refused():
    """A PE cut to 512 bytes: the headers parse, the header says 8 sections, pefile reads 0,
    and with no section to look at no extent check ever ran (it exited 0)."""
    pe = _fake_pe(signed=False, symbols=0, sections=(), declared_sections=8)
    with pytest.raises(ValueError, match="declares 8 sections but only 0"):
        header_analysis.pe_checks(pe, 512)
    pe = _fake_pe(signed=False, symbols=0, sections=((0x400, 0x100),), declared_sections=3)
    with pytest.raises(ValueError, match="declares 3 sections but only 1"):
        header_analysis.pe_checks(pe, FILE_SIZE)
    pe = _fake_pe(signed=False, symbols=0, sections=((0x400, 0x100),), declared_sections=2)
    with pytest.raises(ValueError, match="declares 2 sections but only 1"):  # off by one
        header_analysis.pe_checks(pe, FILE_SIZE)
    pe = _fake_pe(signed=False, symbols=0, sections=((0x400, 0x100),), declared_sections=0)
    with pytest.raises(ValueError, match="declares 0 sections but only 1"):  # more than declared
        header_analysis.pe_checks(pe, FILE_SIZE)


def test_headers_that_run_past_the_end_of_the_file_are_refused():
    pe = _fake_pe(signed=False, symbols=0, sections=(), size_of_headers=0x400)
    with pytest.raises(ValueError, match="headers"):
        header_analysis.pe_checks(pe, 0x3FF)
    header_analysis.pe_checks(pe, 0x400)  # exactly the headers: fine for a file with no sections


def test_a_pe_with_no_sections_at_all_is_still_readable_when_intact():
    pe = _fake_pe(signed=False, symbols=0, sections=(), declared_sections=0)
    assert header_analysis.pe_checks(pe, FILE_SIZE)[0] == {"debug_symbols_stripped": True}


def test_offsets_exactly_at_the_end_of_the_file_are_fine():
    pe = _fake_pe(signed=True, symbols=0, sections=((0x400, 0x8C00),))
    # certificate table ends at 0x9000 + 0x2E0 = 0x92E0; the section at 0x400 + 0x8C00 = 0x9000
    header_analysis.pe_checks(pe, 0x92E0)
    with pytest.raises(ValueError):
        header_analysis.pe_checks(pe, 0x92DF)


def test_a_section_with_no_raw_data_is_not_a_truncation():
    header_analysis.pe_checks(_fake_pe(False, 0, sections=((0x9999999, 0),)), FILE_SIZE)


def test_a_truncated_pe_exits_2_through_main_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _install_fake_libs(monkeypatch, _fake_pe(signed=True, symbols=0), None)
    binary = tmp_path / "trunc.exe"
    binary.write_bytes(b"MZ" + b"\x00" * 998)  # 1000 bytes: the fake's offsets are past EOF
    out = tmp_path / "h.json"
    assert header_analysis.main([str(binary), "--output", str(out)]) == 2
    err = capsys.readouterr().err
    assert "truncated" in err and "headers run past the end" in err
    assert not out.exists()


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


REAL_LOADERS = [
    "/lib64/ld-linux-x86-64.so.2",
    "/lib/ld-linux.so.2",
    "/lib/ld-linux-aarch64.so.1",
    "/lib/ld-linux-armhf.so.3",
    "/lib/ld-linux-riscv64-lp64d.so.1",
    "/lib/ld-linux-riscv64-lp64.so.1",
    "/lib/ld-linux-mipsn8.so.1",
    "/libx32/ld-linux-x32.so.2",
    "/lib64/ld-linux-loongarch-lp64d.so.1",
    "/lib64/ld64.so.2",
    "/lib/ld64.so.1",
    "/usr/lib/ld.so.1",
    "/lib/ld-musl-x86_64.so.1",
    "/lib/ld-musl-aarch64.so.1",
    "/lib/ld-musl-armhf.so.1",
    "/lib/ld-musl-s390x.so.1",
    "/usr/lib64/ld-linux-x86-64.so.2",
    "/usr/lib/ld-linux-aarch64.so.1",
    # Debian and Ubuntu multiarch
    "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
    "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
    "/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
    "/lib/arm-linux-gnueabihf/ld-linux-armhf.so.3",
    "/lib/i386-linux-gnu/ld-linux.so.2",
    "/lib/powerpc64le-linux-gnu/ld64.so.2",
    "/lib/s390x-linux-gnu/ld64.so.1",
    "/lib32/ld-linux.so.2",
]
LOOKALIKES = [
    "/lib64/ld-linux-evil",
    "/lib64/ld-linux-evil.so.2",
    "/lib64/ld-linux-x86-64.so.2.evil",
    "/lib64/ld-linux-x86-64.so.2/../../tmp/x",
    "/lib64/../tmp/ld-linux-x86-64.so.2",
    "/tmp/ld-linux-x86-64.so.2",
    "/lib64/evil.so",
    "/lib64/ld-linux-x86-64.so.",
    "/lib64/ld-linux-x86-64.so.2 ",
    "/lib64/ld-linux-x86-64.so.2\n",
    "/lib64/ld-musl-evil.so.1",
    "/lib64/ld-musl-x86_64.so.2",
    "/lib64/ld.so.2",
    "/lib64/ld64.so.3",
    "/lib/evil-linux-gnu/../ld-linux-x86-64.so.2",
    "/lib/x86_64-linux-gnu/sub/ld-linux-x86-64.so.2",
    "/opt/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
    "/nix/store/abc-glibc/lib/ld-linux-x86-64.so.2",
    "ld-linux-x86-64.so.2",
    "/lib64/LD-LINUX-X86-64.SO.2",
]


@pytest.mark.parametrize("interp", REAL_LOADERS)
def test_every_real_loader_in_a_system_directory_is_trusted(interp: str):
    assert header_analysis.interpreter_is_trusted(interp) is True


@pytest.mark.parametrize("interp", LOOKALIKES)
def test_lookalikes_and_other_directories_are_not_trusted(interp: str):
    assert header_analysis.interpreter_is_trusted(interp) is False


@pytest.mark.parametrize(
    "interp, trusted",
    [
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
    path.write_bytes(magic + b"\x00" * (FILE_SIZE - len(magic)))
    return path


def test_pe_output_is_read_by_parse_binary(tmp_path: Path, monkeypatch):
    _install_fake_libs(monkeypatch, _fake_pe(signed=False, symbols=40), None)
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
    # only what was established is a finding: symbols are embedded; "unsigned" is not claimed
    assert [f["rule_id"] for f in findings] == ["BIN-hdr-debug_symbols_stripped"]
    assert degraded == []  # every value was a boolean the parser could read
    assert any("catalog signatures" in n for n in notes)  # and the caveat reaches the limitations


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
    pe = set(header_analysis.pe_checks(_fake_pe(True, 0), FILE_SIZE)[0])
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


def test_a_missing_output_directory_is_created(tmp_path: Path, monkeypatch):
    _install_fake_libs(monkeypatch, _fake_pe(signed=True, symbols=0), None)
    out = tmp_path / "does" / "not" / "exist" / "header-analysis.json"
    assert header_analysis.main([str(_binary(tmp_path, b"MZ")), "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["format"] == "pe"


def test_an_output_that_cannot_be_written_exits_2_not_with_a_traceback(
    tmp_path: Path, monkeypatch, capsys
):
    _install_fake_libs(monkeypatch, _fake_pe(signed=True, symbols=0), None)
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    code = header_analysis.main(
        [str(_binary(tmp_path, b"MZ")), "--output", str(blocker / "sub" / "h.json")]
    )
    assert code == 2
    assert "could not write" in capsys.readouterr().err


def test_the_documented_exit_codes_hold_from_a_fresh_interpreter(tmp_path: Path):
    """No traceback, only 0, 2 or 3, for the three ways a run can end."""
    missing_dir = tmp_path / "nope" / "h.json"
    text = tmp_path / "t.txt"
    text.write_text("hello", encoding="utf-8")
    run = [sys.executable, str(ETL / "header_analysis.py")]
    for args, expected in (
        ([str(text), "--output", str(missing_dir)], 2),
        ([str(tmp_path / "absent.exe"), "--output", str(missing_dir)], 2),
    ):
        proc = subprocess.run(
            run + args, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        assert proc.returncode == expected, proc.stderr
        assert "Traceback" not in proc.stderr


# -- etl_home near the root of the filesystem ---------------------------------------------------------


@pytest.mark.parametrize(
    "parts",
    [("etl",), ("app", "etl"), ("tools", "etl"), ("a", "b", "etl")],
    ids=["root/etl", "root/app/etl", "root/tools/etl", "root/a/b/etl"],
)
def test_an_etl_directory_near_the_filesystem_root_is_installed_not_a_checkout(parts):
    import etl_home

    anchor = Path(Path.cwd().anchor)
    location = anchor.joinpath(*parts, "etl_home.py")
    assert etl_home._checkout_root(location) is None  # no IndexError


def test_a_shallow_install_falls_back_to_the_environment(monkeypatch, tmp_path):
    import etl_home

    anchor = Path(Path.cwd().anchor)
    location = anchor / "etl" / "etl_home.py"
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "h"))
    assert etl_home.home_dir(location) == tmp_path / "h"
    monkeypatch.delenv("DREAM_STUDIO_HOME")
    assert etl_home.home_dir(location) == Path.home() / ".dream-studio"


def test_the_real_location_is_still_recognised_as_a_checkout():
    import etl_home

    assert etl_home._checkout_root() == REPO_ROOT


# -- the doc ------------------------------------------------------------------------------------------


def test_step_a7_documents_the_script_and_its_exit_codes():
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    a7 = text.split("### Step A7")[1].split("### Step A8")[0].lower()
    assert "header_analysis.py" in a7 and "--output" in a7
    assert "exits 0" in a7 and "exits 3" in a7 and "exits 2" in a7
    assert "no_known_vulnerable_compiler" in a7 and "not computed" in a7
    assert "not verified" in a7  # `signed` is a signature block, not a valid signature
    assert "`signed`, only ever as `true`" in a7
    assert "not written as `false`" in a7 and "catalogs that pefile cannot see" in a7
    assert "is truncated" in a7 and "missing `--output` directory is created" in a7
    assert '"signed": false' not in a7  # the example must not show the claim we refuse to make


# -- real libraries, when present --------------------------------------------------------------------


def test_real_library_pe_on_the_running_interpreter(tmp_path: Path):
    pytest.importorskip("pefile")
    if sys.platform != "win32":
        pytest.skip("the interpreter is not a PE file here")
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([sys.executable, "--output", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "pe" and "debug_symbols_stripped" in data["checks"]
    assert set(data["checks"]) <= {"signed", "debug_symbols_stripped"}
    parse_binary.parse_header_json(data, "python", "", [], [])


def _windows_system_binary(name: str) -> Path:
    path = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / name
    if sys.platform != "win32" or not path.is_file():
        pytest.skip(f"{name} is not available here")
    return path


@pytest.mark.parametrize("name", ["notepad.exe", "cmd.exe"])
def test_real_library_catalog_signed_system_binaries_are_never_reported_unsigned(
    tmp_path: Path, name: str
):
    """notepad.exe and cmd.exe are Authenticode-valid through a catalog: pefile sees no embedded
    block, and the script must not turn that into `signed: false`."""
    pytest.importorskip("pefile")
    out = tmp_path / "header-analysis.json"
    assert header_analysis.main([str(_windows_system_binary(name)), "--output", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["checks"].get("signed") is not False
    findings = parse_binary.parse_header_json(data, name, "", [], [])
    assert "BIN-hdr-signed" not in {f["rule_id"] for f in findings}


def test_real_library_a_truncated_pe_is_refused(tmp_path: Path, capsys):
    pytest.importorskip("pefile")
    if sys.platform != "win32":
        pytest.skip("the interpreter is not a PE file here")
    truncated = tmp_path / "python-trunc.exe"
    truncated.write_bytes(Path(sys.executable).read_bytes()[:1000])
    out = tmp_path / "h.json"
    assert header_analysis.main([str(truncated), "--output", str(out)]) == 2
    assert "truncated" in capsys.readouterr().err
    assert not out.exists()


def _needed_extent(pefile_module, path: Path) -> int:
    """The end of the last thing the script reads from the FULL file: headers, section raw
    data, symbol table, certificate table."""
    pe = pefile_module.PE(str(path), fast_load=True)
    ends = [pe.OPTIONAL_HEADER.SizeOfHeaders]
    security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]
    if security.VirtualAddress and security.Size:
        ends.append(security.VirtualAddress + security.Size)
    header = pe.FILE_HEADER
    if header.NumberOfSymbols:
        ends.append(header.PointerToSymbolTable + 18 * header.NumberOfSymbols)
    ends += [s.PointerToRawData + s.SizeOfRawData for s in pe.sections if s.SizeOfRawData]
    pe.close()
    return max(ends)


@pytest.mark.parametrize("name", ["python", "notepad.exe", "kernel32.dll"])
def test_real_library_a_cut_is_accepted_exactly_when_every_field_read_is_intact(
    tmp_path: Path, name: str
):
    """The truncation fuzz, kept as a test: for a stride of cuts and every boundary the script
    reads (+-1), `analyze` accepts the cut iff it reaches the end of the full file's last
    extent. A 512-byte cut of notepad.exe (header says 8 sections, pefile parses 0) was
    accepted before the declared-section-count check."""
    pefile = pytest.importorskip("pefile")
    if sys.platform != "win32":
        pytest.skip("needs the Windows system binaries")
    path = Path(sys.executable) if name == "python" else _windows_system_binary(name)
    data = path.read_bytes()
    need = _needed_extent(pefile, path)
    cuts = set(range(0, len(data), max(1, len(data) // 120)))
    cuts.update({0, 1, 63, 64, 255, 256, 511, 512, 513, 1000, 1023, 1024, 1025, 4096})
    cuts.update({need - 1, need, need + 1} & set(range(len(data) + 1)))
    wrong = []
    for cut in sorted(c for c in cuts if 0 <= c <= len(data)):
        cut_file = tmp_path / "cut.bin"
        cut_file.write_bytes(data[:cut])
        try:
            header_analysis.analyze(cut_file)
            accepted = True
        except Exception:  # noqa: BLE001 - any refusal is a refusal
            accepted = False
        if accepted != (cut >= need):
            wrong.append((cut, accepted))
    assert wrong == []


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
