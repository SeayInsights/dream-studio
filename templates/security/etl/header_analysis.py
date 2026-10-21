"""
header_analysis.py -- binary-scan step A7: PE/ELF header checks, written as header-analysis.json.

Writes exactly what parse_binary.py reads for the `header_analysis` step:

    {"format": "pe" | "elf", "checks": {"<check>": true | false, ...}, "notes": ["..."]}

`true` means the property holds, `false` means it does not (each `false` becomes a finding).
Only checks this script can actually compute are written; a check it cannot decide is left
out, never written as `true`.

    PE  (needs pefile):         signed (only ever `true`), debug_symbols_stripped
    ELF (needs pyelftools):     interpreter_trusted, symbols_stripped,
                                no_writable_executable_sections

`no_known_vulnerable_compiler` (examples.md used to list it for PE) is not computed: it would
need a list of defective compiler versions, and none ships. `signed` is written only when an
embedded Authenticode signature block is present, and then as `true` (the signature is NOT
verified). Its absence proves nothing: Windows system files (notepad.exe, cmd.exe) are signed
through catalogs that pefile cannot see, so "no embedded block" is never written as `false`;
`notes` says the check was not made. A PE or ELF whose headers point past the end of the
file (a truncated copy) is refused, not analysed.

Usage:
    py -3.12 header_analysis.py <binary> --output <scan-dir>/header-analysis.json

Exit status, for the run record (examples.md Step A7):
    0  wrote the file: record `header_analysis` as `ran`, tool `pefile` or `pyelftools`
    3  the library for the binary's format is not installed: record `skipped`, with the
       message printed on stderr as the reason
    2  not a PE or ELF file, or it could not be read: record `skipped` (other format) or
       `failed` (unreadable), with the message printed on stderr as the reason
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_UNREADABLE, EXIT_NO_LIBRARY = 0, 2, 3

#: Where a system dynamic loader lives, and what real distributions call it. Derived from
#: glibc and musl's own naming, not from a pattern that "looks like a loader": a name that
#: merely starts with `ld-linux` (`/lib64/ld-linux-evil`, `ld-linux-x86-64.so.2.evil`) is NOT one.
TRUSTED_LOADER_DIRS = frozenset(
    {"/lib", "/lib32", "/lib64", "/libx32", "/usr/lib", "/usr/lib32", "/usr/lib64", "/usr/libx32"}
)
#: Debian/Ubuntu multiarch: /lib/x86_64-linux-gnu, /usr/lib/aarch64-linux-gnu, ...
_MULTIARCH_DIR = re.compile(r"/(?:usr/)?lib(?:32|64|x32)?/[a-z0-9_]+-linux-[a-z0-9]+")
_LOADER_NAME = re.compile(
    r"ld-linux(?:-(?:x86-64|aarch64|armhf|x32|mipsn8|riscv64-lp64d?|loongarch-lp64[ds]))?"
    r"\.so\.[0-9]+"
    r"|ld64\.so\.[12]"
    r"|ld\.so\.1"
    r"|ld-musl-(?:x86_64|aarch64|armhf|arm|i386|s390x|powerpc64le|powerpc|riscv64|mips|mipsel"
    r"|mips64|loongarch64)\.so\.1"
)

SHF_WRITE, SHF_EXECINSTR = 0x1, 0x4

IMAGE_DIRECTORY_ENTRY_SECURITY = 4
IMAGE_DIRECTORY_ENTRY_DEBUG = 6


def detect_format(head: bytes) -> str | None:
    """`pe`, `elf`, or None, from the first bytes of the file."""
    if head.startswith(b"\x7fELF"):
        return "elf"
    if head.startswith(b"MZ"):
        return "pe"
    return None


def interpreter_is_trusted(interp: str | None) -> bool:
    """No interpreter (a static binary) or a standard system loader is trusted."""
    if not interp:
        return True
    directory = posixpath.dirname(interp)
    return bool(
        (directory in TRUSTED_LOADER_DIRS or _MULTIARCH_DIR.fullmatch(directory))
        and _LOADER_NAME.fullmatch(posixpath.basename(interp))
    )


def pe_extent_problem(pe, file_size: int) -> str | None:
    """Why this PE cannot be analysed because it runs past the end of the file, or because the
    header declares more than could be read; None if it does not. A truncated copy still parses its headers, and its directory offsets point
    past EOF: reading `signed` or the symbol table from it would be reading nothing."""
    declared = pe.FILE_HEADER.NumberOfSections
    parsed = len(getattr(pe, "sections", ()))
    if declared != parsed:
        # pefile stops at the end of the data: a file cut inside (or before) the section
        # table parses fewer sections than its header declares, and an extent check over the
        # sections that survived says nothing about the ones that did not.
        return f"the header declares {declared} sections but only {parsed} could be read"
    if pe.OPTIONAL_HEADER.SizeOfHeaders > file_size:
        return "the headers run past the end of the file"
    security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[IMAGE_DIRECTORY_ENTRY_SECURITY]
    if security.VirtualAddress and security.VirtualAddress + security.Size > file_size:
        return "the certificate table lies past the end of the file"
    header = pe.FILE_HEADER
    symbols = header.NumberOfSymbols
    if symbols and header.PointerToSymbolTable + 18 * symbols > file_size:
        return "the COFF symbol table lies past the end of the file"
    for section in getattr(pe, "sections", ()):
        if section.SizeOfRawData and section.PointerToRawData + section.SizeOfRawData > file_size:
            return "a section's data lies past the end of the file"
    return None


def pe_checks(pe, file_size: int) -> tuple[dict[str, bool], list[str]]:
    """Checks from an open pefile.PE of a file of `file_size` bytes. `pe` needs
    OPTIONAL_HEADER.DATA_DIRECTORY (entries with VirtualAddress and Size), FILE_HEADER
    (NumberOfSymbols, PointerToSymbolTable) and `sections` (PointerToRawData, SizeOfRawData).
    Raises ValueError for a PE that runs past the end of the file."""
    problem = pe_extent_problem(pe, file_size)
    if problem:
        raise ValueError(f"the PE file is truncated or malformed: {problem}")
    security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[IMAGE_DIRECTORY_ENTRY_SECURITY]
    embedded = bool(security.VirtualAddress and security.Size)
    checks: dict[str, bool] = {}
    notes: list[str] = []
    if embedded:
        checks["signed"] = True
        notes.append(
            "signed: an embedded Authenticode signature block is present; the signature was "
            "not verified"
        )
    else:
        # Not `signed: false`. Windows system files are signed through catalogs, which
        # pefile cannot see, so the absence of an embedded block says nothing.
        notes.append(
            "signed: not reported. No embedded Authenticode signature block was found, which "
            "does not mean the file is unsigned: catalog signatures (Windows system files) "
            "are not checked by this script"
        )
    # A PDB path in the debug directory is not embedded symbols (an MSVC build has one);
    # a COFF symbol table is.
    checks["debug_symbols_stripped"] = not pe.FILE_HEADER.NumberOfSymbols
    notes.append(
        "debug_symbols_stripped: a PDB path in the debug directory is not counted, "
        "only an embedded COFF symbol table"
    )
    return checks, notes


def elf_checks(elf) -> tuple[dict[str, bool], list[str]]:
    """Checks from an open elftools ELFFile (iter_segments, iter_sections, get_section_by_name)."""
    interp = None
    for segment in elf.iter_segments():
        if segment["p_type"] == "PT_INTERP":
            interp = segment.get_interp_name()
            break
    writable_exec = any(
        (section["sh_flags"] & SHF_WRITE) and (section["sh_flags"] & SHF_EXECINSTR)
        for section in elf.iter_sections()
    )
    checks = {
        "interpreter_trusted": interpreter_is_trusted(interp),
        "symbols_stripped": elf.get_section_by_name(".symtab") is None,
        "no_writable_executable_sections": not writable_exec,
    }
    return checks, []


def analyze(path: Path) -> tuple[str, str, dict[str, bool], list[str]]:
    """(format, tool, checks, notes). Raises LookupError(message) for an unsupported file,
    ImportError(message) when the library is missing, OSError/ValueError for an unreadable one."""
    with path.open("rb") as fh:
        fmt = detect_format(fh.read(4))
    if fmt is None:
        raise LookupError(f"{path.name} is not a PE or ELF file; no header analysis for it")
    if fmt == "pe":
        try:
            import pefile
        except ImportError:
            raise ImportError("pefile is not installed") from None
        pe = pefile.PE(str(path), fast_load=True)
        try:
            checks, notes = pe_checks(pe, path.stat().st_size)
        finally:
            pe.close()
        return "pe", "pefile", checks, notes
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError:
        raise ImportError("pyelftools is not installed") from None
    with path.open("rb") as fh:
        checks, notes = elf_checks(ELFFile(fh))
    return "elf", "pyelftools", checks, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PE/ELF header checks -> header-analysis.json")
    parser.add_argument("binary", help="Path to the binary to analyze")
    parser.add_argument("--output", required=True, help="Where to write header-analysis.json")
    args = parser.parse_args(argv)

    try:
        fmt, tool, checks, notes = analyze(Path(args.binary))
    except ImportError as exc:
        print(f"[header_analysis] {exc}", file=sys.stderr)
        return EXIT_NO_LIBRARY
    except LookupError as exc:
        print(f"[header_analysis] {exc.args[0]}", file=sys.stderr)
        return EXIT_UNREADABLE
    except Exception as exc:  # noqa: BLE001 - an unreadable binary is a recorded outcome
        print(f"[header_analysis] could not read {args.binary}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    out = {"format": fmt, "checks": checks}
    if notes:
        out["notes"] = notes
    try:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"[header_analysis] could not write {args.output}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    print(f"[header_analysis] {fmt} checks by {tool} -> {args.output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
