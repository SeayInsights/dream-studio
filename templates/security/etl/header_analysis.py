"""
header_analysis.py -- binary-scan step A7: PE/ELF header checks, written as header-analysis.json.

Writes exactly what parse_binary.py reads for the `header_analysis` step:

    {"format": "pe" | "elf", "checks": {"<check>": true | false, ...}, "notes": ["..."]}

`true` means the property holds, `false` means it does not (each `false` becomes a finding).
Only checks this script can actually compute are written; a check it cannot decide is left
out, never written as `true`.

    PE  (needs pefile):         signed, debug_symbols_stripped
    ELF (needs pyelftools):     interpreter_trusted, symbols_stripped,
                                no_writable_executable_sections

`no_known_vulnerable_compiler` (examples.md used to list it for PE) is not computed: it would
need a list of defective compiler versions, and none ships. `signed` means an Authenticode
signature block is present; the signature is NOT verified, and `notes` says so.

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

#: Directories a system dynamic loader lives in, and the file names of the loaders.
TRUSTED_LOADER_DIRS = frozenset(
    {"/lib", "/lib32", "/lib64", "/libx32", "/usr/lib", "/usr/lib32", "/usr/lib64", "/usr/libx32"}
)
_LOADER_NAME = re.compile(r"^ld(-linux[\w.+-]*|-musl[\w.+-]*|\.so)(\.\d+)?$")

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
    return posixpath.dirname(interp) in TRUSTED_LOADER_DIRS and bool(
        _LOADER_NAME.match(posixpath.basename(interp))
    )


def pe_checks(pe) -> tuple[dict[str, bool], list[str]]:
    """Checks from an open pefile.PE. `pe` needs OPTIONAL_HEADER.DATA_DIRECTORY (a list of
    entries with VirtualAddress and Size) and FILE_HEADER.NumberOfSymbols."""
    directories = pe.OPTIONAL_HEADER.DATA_DIRECTORY
    security = directories[IMAGE_DIRECTORY_ENTRY_SECURITY]
    checks = {
        "signed": bool(security.VirtualAddress and security.Size),
        # A PDB path in the debug directory is not embedded symbols (an MSVC build has one);
        # a COFF symbol table is.
        "debug_symbols_stripped": not pe.FILE_HEADER.NumberOfSymbols,
    }
    notes = [
        "signed: an Authenticode signature block is present; the signature was not verified",
        "debug_symbols_stripped: a PDB path in the debug directory is not counted, "
        "only an embedded COFF symbol table",
    ]
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
            checks, notes = pe_checks(pe)
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
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"[header_analysis] {fmt} checks by {tool} -> {args.output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
