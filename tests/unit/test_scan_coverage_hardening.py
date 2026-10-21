"""scan_coverage.py: the failure modes the #907 final verification left open (issue #908).

Each test here pins something a mutant of scan_coverage.py survived, or a claim the module
made that was false in a corner:

  * the 20-note cap cut the reason a result file "could not be read" while the unread
    limitation still said a refused file "is named in another limitation";
  * `decode_text` kept one list entry per decoder error (20 million for a 20 MB all-bad file);
  * the thresholds in `decode_text` (a tenth of the bytes undecodable, UTF-16 without a BOM
    guessed at 80% / 10% NULs) were untested;
  * a link or junction in a path: `_real` must follow links, so a scans directory and a
    candidate named through different spellings of the same directory are one scan;
  * `split_by_scan_dir`'s catch-all filed an internal failure under "ignored", which reads
    as a misnamed file; an internal failure is now reported as one.

(The issue text speaks of "50% thresholds" in decode_text; the module's own are 10%
undecodable and 80% / 10% NULs, and those are what is pinned.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tracemalloc
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"

sys.path.insert(0, str(ETL))
import scan_coverage  # noqa: E402

# -- decode_text: counted, not listed ---------------------------------------------------------------


def test_decode_text_counts_undecodable_bytes_instead_of_listing_them():
    """A 2 MB file of nothing but bad bytes must not cost a list entry per byte."""
    data = b"\xff" * 2_000_000
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="2000000 of its 2000000 bytes"):
            scan_coverage.decode_text(data, "x.json")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # the decoded text itself is two bytes a character; a per-error list would add eight more
    assert peak < 6 * len(data), f"peak {peak} bytes for {len(data)} input bytes"


def test_the_undecodable_count_does_not_leak_into_the_next_call():
    with pytest.raises(ValueError):
        scan_coverage.decode_text(b"\xff" * 50, "x.json")
    clean = scan_coverage.decode_text(b'{"a": 1}', "x.json")
    assert clean.degraded == [] and clean.text == '{"a": 1}'


def test_multi_byte_errors_count_every_byte():
    # a truncated 3-byte sequence is one decoder error spanning two bytes
    data = b"a" * 100 + b"\xe2\x82" + b"b" * 100
    got = scan_coverage.decode_text(data, "x.txt")
    assert got.degraded and got.degraded[0].startswith("2 undecodable byte(s)")


# -- decode_text: the thresholds ------------------------------------------------------------------


def test_exactly_a_tenth_undecodable_is_read_and_degraded():
    data = b"a" * 90 + b"\xff" * 10
    got = scan_coverage.decode_text(data, "x.txt")
    assert got.degraded and got.degraded[0].startswith("10 undecodable byte(s)")


def test_more_than_a_tenth_undecodable_is_not_text():
    data = b"a" * 89 + b"\xff" * 11
    with pytest.raises(ValueError, match="11 of its 100 bytes"):
        scan_coverage.decode_text(data, "x.txt")


def _utf16_like(pairs: int, odd_zero: int, even_zero: int) -> bytes:
    """`pairs` two-byte units; `odd_zero` of the odd (high) bytes and `even_zero` of the even
    (low) bytes are NUL, the rest are ASCII letters."""
    out = bytearray()
    for i in range(pairs):
        out.append(0 if i < even_zero else ord("a"))
        out.append(0 if i < odd_zero else ord("b"))
    return bytes(out)


def test_utf16_without_a_bom_is_guessed_at_eighty_percent_nuls():
    got = scan_coverage.decode_text(_utf16_like(10, odd_zero=8, even_zero=0), "x.txt")
    assert any("UTF-16 LE (no BOM)" in n for n in got.notes)


def test_utf16_without_a_bom_is_not_guessed_below_eighty_percent():
    with pytest.raises(ValueError, match="NUL"):
        scan_coverage.decode_text(_utf16_like(10, odd_zero=7, even_zero=0), "x.txt")


def test_utf16_guess_tolerates_a_tenth_of_the_other_bytes_being_nul_but_no_more():
    # 20 units; U+4100 is a letter-like CJK unit whose LOW byte is NUL and HIGH byte is not
    ok = ("a" * 18 + "䄀" * 2).encode("utf-16-le")  # 90% high bytes NUL, 10% low bytes NUL
    got = scan_coverage.decode_text(ok, "x.txt")
    assert any("UTF-16 LE (no BOM)" in n for n in got.notes)
    too_many = ("a" * 17 + "䄀" * 3).encode("utf-16-le")  # 15% low bytes NUL: not guessed
    with pytest.raises(ValueError, match="NUL"):
        scan_coverage.decode_text(too_many, "x.txt")


def test_big_endian_utf16_without_a_bom_follows_the_same_thresholds():
    # BE puts the NUL in the HIGH byte (even offset) of an ASCII-range unit
    at_edge = ("a" * 18 + "䄀" * 2).encode("utf-16-be")  # 90% even NUL, 10% odd NUL
    assert any("UTF-16 BE (no BOM)" in n for n in scan_coverage.decode_text(at_edge, "x").notes)
    below = ("a" * 14 + "䅂" * 6).encode("utf-16-be")  # only 70% even NUL, no odd NUL
    with pytest.raises(ValueError, match="NUL"):
        scan_coverage.decode_text(below, "x")
    too_many_odd = ("a" * 17 + "䄀" * 3).encode("utf-16-be")  # 15% odd NUL
    with pytest.raises(ValueError, match="NUL"):
        scan_coverage.decode_text(too_many_odd, "x")


def test_big_endian_utf16_without_a_bom_is_guessed_too():
    data = "hello world".encode("utf-16-be")
    got = scan_coverage.decode_text(data, "x.txt")
    assert got.text == "hello world"
    assert any("UTF-16 BE (no BOM)" in n for n in got.notes)


def test_a_file_too_short_to_judge_is_not_guessed_as_utf16():
    with pytest.raises(ValueError, match="NUL"):
        scan_coverage.decode_text(b"a\x00b", "x.txt")


# -- links and junctions ----------------------------------------------------------------------------


def _link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("cannot create a symlink here")
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if made.returncode != 0:
            pytest.skip("cannot create a symlink or junction here")


def _tree(root: Path) -> Path:
    scan = root / "real" / "app" / "2026-10-19"
    scan.mkdir(parents=True)
    (scan / "scan-meta.json").write_text("{}", encoding="utf-8")
    (scan / "checksec.json").write_text("{}", encoding="utf-8")
    (scan / "old").mkdir()
    (scan / "old" / "checksec.json").write_text("{}", encoding="utf-8")
    return scan


def test_a_candidate_named_through_a_link_belongs_to_the_scan_of_the_real_path(tmp_path: Path):
    scan = _tree(tmp_path)
    link = tmp_path / "link"
    _link(link, tmp_path / "real")
    via_link = link / "app" / "2026-10-19" / "checksec.json"
    stale_via_link = link / "app" / "2026-10-19" / "old" / "checksec.json"

    # the scans directory is spelled one way and the candidates another
    kept, ignored = scan_coverage.split_by_scan_dir(tmp_path / "real", [via_link, stale_via_link])
    assert kept == [via_link]
    assert [p for ps in ignored.values() for p in ps] == [stale_via_link]

    key, meta = scan_coverage.scan_key(via_link, tmp_path / "real")
    assert Path(key) == Path(os.path.realpath(scan))
    assert meta is not None and meta.name == "scan-meta.json"


def test_a_scans_directory_named_through_a_link_finds_the_real_scan(tmp_path: Path):
    scan = _tree(tmp_path)
    link = tmp_path / "link"
    _link(link, tmp_path / "real")
    real_candidate = scan / "checksec.json"

    kept, ignored = scan_coverage.split_by_scan_dir(link, [real_candidate])
    assert kept == [real_candidate] and ignored == {}

    found = scan_coverage.scan_dirs(link, [real_candidate])
    assert list(found) == [str(Path(os.path.realpath(scan)))]


def test_find_meta_walks_up_a_linked_path_and_stops_at_the_resolved_stop(tmp_path: Path):
    scan = _tree(tmp_path)
    link = tmp_path / "link"
    _link(link, tmp_path / "real")
    meta = scan_coverage.find_meta(link / "app" / "2026-10-19" / "old", tmp_path / "real")
    assert meta is not None and Path(os.path.realpath(meta)) == Path(
        os.path.realpath(scan / "scan-meta.json")
    )
    # a stop below the meta file hides it, whichever way the stop is spelled
    assert scan_coverage.find_meta(link / "app" / "2026-10-19" / "old", scan / "old") is None
    assert (
        scan_coverage.find_meta(
            link / "app" / "2026-10-19" / "old", link / "app" / "2026-10-19" / "old"
        )
        is None
    )


# -- split_by_scan_dir: an internal failure is reported, not filed as "ignored" ----------------


def test_an_unplaceable_candidate_is_reported_as_a_failure_not_as_a_misnamed_file(
    tmp_path: Path, monkeypatch
):
    scan = _tree(tmp_path)
    good = scan / "checksec.json"
    bad = scan / "yara-matches.json"
    bad.write_text("[]", encoding="utf-8")
    real_scan_key = scan_coverage.scan_key

    def flaky(path, scans_dir, resolve=scan_coverage._real):
        if path.name == "yara-matches.json":
            raise RuntimeError("simulated placement bug")
        return real_scan_key(path, scans_dir, resolve)

    monkeypatch.setattr(scan_coverage, "scan_key", flaky)
    unplaceable: dict = {}
    kept, ignored = scan_coverage.split_by_scan_dir(
        tmp_path / "real", [good, bad], unplaceable=unplaceable
    )

    assert kept == [good]
    assert [p for ps in ignored.values() for p in ps] == []  # NOT filed as ignored
    assert list(unplaceable) == [bad]
    assert "simulated placement bug" in unplaceable[bad]


def test_the_report_names_an_unplaceable_file_with_the_internal_error(tmp_path: Path, monkeypatch):
    scan = _tree(tmp_path)
    (scan / "yara-matches.json").write_text("[]", encoding="utf-8")
    real_scan_key = scan_coverage.scan_key

    def flaky(path, scans_dir, resolve=scan_coverage._real):
        if path.name == "yara-matches.json":
            raise RuntimeError("simulated placement bug")
        return real_scan_key(path, scans_dir, resolve)

    monkeypatch.setattr(scan_coverage, "scan_key", flaky)
    steps = [{"step": "checksec", "status": "ran", "tool": "checksec"}]
    (scan / "scan-meta.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")

    def read_file(path, target):
        return scan_coverage.Read("checksec", [], [], [])

    _, reports, n = scan_coverage.collect(
        "t",
        tmp_path / "real",
        [scan / "checksec.json", scan / "yara-matches.json"],
        ("checksec",),
        read_file,
        ("checksec.json", "yara-matches.json"),
        ("checksec", "yara"),
    )
    assert n == 1
    text = " ".join(x for r in reports for x in r["limitations"])
    assert "yara-matches.json could not be placed" in text
    assert "simulated placement bug" in text
    assert "yara-matches.json was ignored: results are read only from" not in text


def test_split_by_scan_dir_still_never_raises(tmp_path: Path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_coverage, "scan_key", boom)
    kept, ignored = scan_coverage.split_by_scan_dir(tmp_path, [tmp_path / "x" / "checksec.json"])
    assert kept == []


# -- the note cap keeps the reasons a file was refused ------------------------------------------------


def _assess_all(tmp_path: Path, state: scan_coverage.ScanRead) -> list[str]:
    d = tmp_path / "scan"
    d.mkdir(exist_ok=True)
    (d / "scan-meta.json").write_text(
        json.dumps({"steps": [{"step": "checksec", "status": "ran", "tool": "checksec"}]}),
        encoding="utf-8",
    )
    key = str(Path(os.path.realpath(d)))
    out = scan_coverage.assess_all({key: d / "scan-meta.json"}, ("checksec",), {key: state})
    return out[key]["limitations"]


def test_every_refusal_is_kept_however_many_files_were_ignored(tmp_path: Path):
    state = scan_coverage.ScanRead()
    state.refusals.extend(f"r{i}.json could not be read: bad" for i in range(30))
    state.ignored.extend(f"i{i}.json was ignored: wrong name" for i in range(60))
    limits = _assess_all(tmp_path, state)
    for i in range(30):
        assert f"r{i}.json could not be read: bad" in limits
    assert sum("was ignored" in x for x in limits) <= scan_coverage._NOTE_LIMIT


def test_the_ignored_notes_are_what_the_cap_cuts_and_the_cut_is_counted(tmp_path: Path):
    state = scan_coverage.ScanRead()
    state.refusals.append("checksec.json could not be read: corrupt")
    state.ignored.extend(f"i{i}.json was ignored: wrong name" for i in range(25))
    limits = _assess_all(tmp_path, state)
    assert "checksec.json could not be read: corrupt" in limits
    assert limits[-1] == "... and 5 more notes"
    assert sum("was ignored" in x for x in limits) == scan_coverage._NOTE_LIMIT


def test_other_notes_come_before_ignored_ones_when_the_cap_bites(tmp_path: Path):
    state = scan_coverage.ScanRead()
    state.notes.extend(f"encoding note {i}" for i in range(scan_coverage._NOTE_LIMIT))
    state.ignored.extend(f"i{i}.json was ignored: wrong name" for i in range(5))
    limits = _assess_all(tmp_path, state)
    assert sum(x.startswith("encoding note") for x in limits) == scan_coverage._NOTE_LIMIT
    assert not any("was ignored" in x for x in limits)
    assert limits[-1] == "... and 5 more notes"


def test_below_the_cap_nothing_is_summarised(tmp_path: Path):
    state = scan_coverage.ScanRead()
    state.ignored.extend(f"i{i}.json was ignored: wrong name" for i in range(3))
    limits = _assess_all(tmp_path, state)
    assert not any("more notes" in x for x in limits)
    assert sum("was ignored" in x for x in limits) == 3


def test_a_refusal_survives_a_pile_of_other_notes_from_other_files(tmp_path: Path):
    scan = tmp_path / "scans" / "app" / "2026-10-19"
    scan.mkdir(parents=True)
    steps = [{"step": s, "status": "ran", "tool": s} for s in ("checksec", "yara")]
    (scan / "scan-meta.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
    (scan / "checksec.json").write_text("{}", encoding="utf-8")  # reads, with 30 notes
    (scan / "yara-matches.json").write_text("{}", encoding="utf-8")  # raises when read

    def read_file(path, target):
        if path.name == "yara-matches.json":
            raise ValueError("corrupt yara output")
        return scan_coverage.Read("checksec", [], [], [f"encoding note {i}" for i in range(30)])

    _, reports, _ = scan_coverage.collect(
        "t",
        scan,
        [scan / "checksec.json", scan / "yara-matches.json"],
        ("checksec", "yara"),
        read_file,
        ("checksec.json", "yara-matches.json"),
        ("checksec", "yara"),
    )
    limits = reports[0]["limitations"]
    assert "yara-matches.json could not be read: corrupt yara output" in limits
    assert sum(x.startswith("encoding note") for x in limits) == scan_coverage._NOTE_LIMIT
    assert limits[-1] == "... and 10 more notes"


def test_the_unread_limitation_only_promises_what_the_cap_keeps(tmp_path: Path):
    """The sentence 'a file that was found and refused is named in another limitation' must
    stay true with 25 stray files beside a corrupt checksec.json."""
    scan = tmp_path / "scans" / "app" / "2026-10-19"
    scan.mkdir(parents=True)
    steps = [{"step": "checksec", "status": "ran", "tool": "checksec"}]
    (scan / "scan-meta.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
    (scan / "checksec.json").write_text("{ not json", encoding="utf-8")
    for i in range(25):
        (scan / f"checksec-copy{i:02d}.json").write_text("{}", encoding="utf-8")

    def read_file(path, target):
        json.loads(path.read_text(encoding="utf-8"))
        return scan_coverage.Read("checksec", [], [], [])

    _, reports, _ = scan_coverage.collect(
        "t",
        scan,
        [scan / "checksec.json"],
        ("checksec",),
        read_file,
        ("checksec.json",),
        ("checksec",),
    )
    limits = reports[0]["limitations"]
    unread = next(x for x in limits if "is recorded as ran but no checksec result was read" in x)
    assert "is named in another limitation" in unread
    assert any(x.startswith("checksec.json could not be read") for x in limits)
    assert limits[-1].startswith("... and ") and limits[-1].endswith(" more notes")
