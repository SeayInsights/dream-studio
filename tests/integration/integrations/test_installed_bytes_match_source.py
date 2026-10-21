"""A fresh install reads healthy, and an installed file is the source file, byte for byte.

WHY. On Windows `integrations.health.doctor` reported `installed_drifted` on a FRESH
install. Two things disagreed about a file's bytes:

  * the manifest recorded the SHA-256 of the source file as it sits in the working tree,
    where git's `text=auto` checkout has made .j2, .mjs, .ps1, .html, .csv, .ts files CRLF
    (the committed blobs are LF);
  * `atomic_write` wrote the projected text with the PLATFORM's newlines, and the doctor
    read it back through `read_text`, which folds CRLF to LF before hashing.

So any file whose working-tree bytes were CRLF hashed differently on the two sides. The
fix is at the cause: the installer writes the projected text exactly (LF, the committed
form, on every OS), the manifest records the hash of what it writes (never of a
checkout's newline conversion), and a file git says must stay CRLF (`*.cmd`, `*.bat`:
.gitattributes) is copied as bytes, so its CRLF survives. The doctor accepts the exact
bytes or the newline-folded text, so an install made before the fix still verifies.

Hermetic: every test installs into a temp config root and a temp home.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from integrations.health import IntegrationState, doctor
from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.manifest import read_manifest, verify_file_hashes

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "templates" / "security"


@pytest.fixture()
def fresh(tmp_path: Path):
    config_root = tmp_path / "claude_config"
    config_root.mkdir()
    ds_home = tmp_path / "ds_home"
    ClaudeCodeInstaller(
        config_root, "user", canonical_root=REPO_ROOT / "canonical", ds_home=ds_home
    ).install("execute")
    return config_root, ds_home


def _tree_files() -> list[Path]:
    return sorted(
        p
        for p in SOURCE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")
    )


def test_a_fresh_install_reads_healthy_in_the_integration_doctor(fresh):
    config_root, ds_home = fresh
    result = doctor(
        "claude_code",
        config_root,
        ds_home=ds_home,
        canonical_root=REPO_ROOT / "canonical",
        spool_root=config_root.parent / "no_spool",
    )
    assert result["drift"] == []
    assert result["state"] == IntegrationState.INSTALLED_VERIFIED.value


def test_the_manifest_verifies_clean_after_a_fresh_install(fresh):
    config_root, ds_home = fresh
    manifest = read_manifest("claude_code", ds_home, config_root)
    assert manifest is not None and manifest["files"]
    assert verify_file_hashes(manifest) == []


def test_every_security_file_is_installed_as_exactly_the_committed_bytes(fresh):
    """Byte equality for every file type in the ds-security tree: .j2, .yaml, .py, .md, ...
    (the working-tree source may be CRLF where git converted it; the committed blob and the
    installed file are LF)."""
    config_root, _ = fresh
    installed_root = config_root / "skills" / "ds-security" / "templates" / "security"
    suffixes = set()
    for source in _tree_files():
        installed = installed_root / source.relative_to(SOURCE)
        suffixes.add(source.suffix)
        assert installed.is_file(), source
        want = source.read_bytes().replace(b"\r\n", b"\n")
        assert installed.read_bytes() == want, f"{source.relative_to(SOURCE)} is not byte-equal"
    assert {".j2", ".py", ".yaml", ".md"} <= suffixes  # the types the tree actually holds


def test_no_installed_skill_text_file_has_platform_newlines_the_source_lacks(fresh):
    config_root, _ = fresh
    crlf = [
        p.relative_to(config_root).as_posix()
        for p in (config_root / "skills").rglob("*")
        if p.is_file()
        and p.suffix in {".j2", ".mjs", ".ps1", ".html", ".csv", ".ts", ".md", ".py"}
        and b"\r\n" in p.read_bytes()
        and b"\r\n" not in _source_bytes_for(config_root, p)
    ]
    assert crlf == []


def _source_bytes_for(config_root: Path, installed: Path) -> bytes:
    rel = installed.relative_to(config_root / "skills")
    skill_id, rest = rel.parts[0], Path(*rel.parts[1:])
    key = skill_id.removeprefix("ds-")
    candidates = [
        REPO_ROOT / "canonical" / "skills" / skill_id / rest,
        REPO_ROOT / "canonical" / "skills" / key / rest,
        REPO_ROOT / rest,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_bytes().replace(b"\r\n", b"\n")
    return b""


def test_an_operator_edited_file_is_still_drift(fresh):
    config_root, ds_home = fresh
    target = config_root / "skills" / "ds-security" / "templates" / "security" / "binary"
    edited = next(target.glob("*.j2"))
    edited.write_bytes(edited.read_bytes() + b"# edited by the operator\n")
    manifest = read_manifest("claude_code", ds_home, config_root)
    drift = verify_file_hashes(manifest)
    assert drift == [f"hash_mismatch: {edited}"]
    result = doctor(
        "claude_code", config_root, ds_home=ds_home, canonical_root=REPO_ROOT / "canonical"
    )
    assert result["state"] == IntegrationState.INSTALLED_DRIFTED.value


def test_a_deleted_file_is_still_drift(fresh):
    config_root, ds_home = fresh
    gone = config_root / "skills" / "ds-security" / "templates" / "security" / "README.md"
    gone.unlink()
    drift = verify_file_hashes(read_manifest("claude_code", ds_home, config_root))
    assert drift == [f"missing: {gone}"]


def test_a_line_ending_only_edit_is_not_drift_for_text_but_a_content_edit_is(fresh):
    """The doctor folds newlines for text, so a CRLF save (an editor on Windows) of an
    otherwise identical file is not reported; changing a character is."""
    config_root, ds_home = fresh
    target = config_root / "skills" / "ds-security" / "templates" / "security" / "README.md"
    original = target.read_bytes()
    target.write_bytes(original.replace(b"\n", b"\r\n"))
    manifest = read_manifest("claude_code", ds_home, config_root)
    assert verify_file_hashes(manifest) == []
    target.write_bytes(original.replace(b"Templates", b"Tempolates", 1))
    assert verify_file_hashes(manifest) == [f"hash_mismatch: {target}"]


@pytest.mark.parametrize(
    "variant",
    [
        lambda b: b.replace(b"\n", b"\r", 1),  # a lone CR is not a CRLF
        lambda b: b.replace(b"\n", b"\xc2\x85", 1),  # NEL is not a newline here
        lambda b: b.replace(b"\n", b"\xe2\x80\xa8", 1),  # nor U+2028
        lambda b: b"\xef\xbb\xbf" + b,  # a BOM is a changed byte sequence
        lambda b: b.replace(b"\n", b"\r\r\n", 1),  # a CR left over after the fold
        lambda b: b.replace(b"\n", b"\n\n", 1),  # an added blank line
    ],
    ids=["lone-cr", "nel", "line-separator", "bom", "double-cr", "blank-line"],
)
def test_the_newline_fold_folds_only_crlf_and_nothing_else_is_forgiven(fresh, variant):
    config_root, ds_home = fresh
    target = config_root / "skills" / "ds-security" / "templates" / "security" / "README.md"
    original = target.read_bytes()
    target.write_bytes(variant(original))
    manifest = read_manifest("claude_code", ds_home, config_root)
    assert verify_file_hashes(manifest) == [f"hash_mismatch: {target}"]


def test_a_blank_line_added_to_a_file_with_none_is_drift(tmp_path: Path):
    """A synthetic file with no blank line: the fold must not read an added one as the same."""
    from integrations.manifest import compute_hash

    path = tmp_path / "f.txt"
    manifest = {"files": [{"path": str(path), "content_hash": compute_hash(b"a\nb\n")}]}
    path.write_bytes(b"a\r\nb\r\n")
    assert verify_file_hashes(manifest) == []
    path.write_bytes(b"a\n\nb\n")
    assert verify_file_hashes(manifest) == [f"hash_mismatch: {path}"]


def test_the_doctors_directory_hash_folds_only_crlf(tmp_path: Path):
    """The freshness hash is the other fold: CRLF == LF, and a lone CR, NEL or BOM is not."""
    from core.health.doctor_skill_sync import _compute_directory_hash

    def digest(content: bytes) -> str:
        d = tmp_path / f"d{len(list(tmp_path.iterdir()))}"
        d.mkdir()
        (d / "a.txt").write_bytes(content)
        return _compute_directory_hash(d)

    base = b"one\ntwo\n"
    assert digest(base.replace(b"\n", b"\r\n")) == digest(base)
    for other in (
        b"one\rtwo\r",
        b"one\xc2\x85two\xc2\x85",
        b"\xef\xbb\xbf" + base,
        b"one\r\r\ntwo\n",
    ):
        assert digest(other) != digest(base), other


def test_an_install_made_before_the_fix_still_verifies(fresh):
    """An older manifest recorded the hash of the working-tree source bytes (CRLF) for some
    files, and the file on disk was written with platform newlines: both forms verify."""
    config_root, ds_home = fresh
    manifest = read_manifest("claude_code", ds_home, config_root)
    entry = next(
        e
        for e in manifest["files"]
        if str(e["path"]).endswith("binary" + "\\analyze.sh.j2")
        or str(e["path"]).endswith("binary/analyze.sh.j2")
    )
    path = Path(entry["path"])
    crlf_bytes = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(crlf_bytes)  # what an older install wrote on Windows
    entry["content_hash"] = hashlib.sha256(crlf_bytes).hexdigest()  # the old raw-bytes hash
    assert verify_file_hashes(manifest) == []
    entry["content_hash"] = "0" * 64
    assert verify_file_hashes(manifest) == [f"hash_mismatch: {path}"]


# -- a file git keeps CRLF keeps its CRLF ----------------------------------------------------------------


def test_a_cmd_or_bat_file_is_copied_as_bytes_so_its_crlf_survives(tmp_path: Path):
    """.gitattributes: `*.cmd text eol=crlf`, `*.bat text eol=crlf`. Folding them to LF would
    break them, so they are copied, not re-written from text."""
    from integrations.installer.claude_code_fileops import _collect_skill_dir_ops
    from integrations.installer.file_ops import atomic_copy, atomic_write

    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# s\n", encoding="utf-8")
    (skill / "run.cmd").write_bytes(b"@echo off\r\necho hi\r\n")
    (skill / "go.bat").write_bytes(b"@echo off\r\nexit /b 0\r\n")
    (skill / "notes.txt").write_bytes(b"line one\r\nline two\r\n")  # not a batch file: text
    out = tmp_path / "out"
    ops = {Path(op.target).name: op for op in _collect_skill_dir_ops(skill, out, "ds-x", tmp_path)}
    for name in ("run.cmd", "go.bat"):
        assert ops[name].source_content is None and ops[name].source_path is not None
        atomic_copy(ops[name].source_path, ops[name].target)
        assert ops[name].target.read_bytes() == (skill / name).read_bytes()
        assert ops[name].source_hash == hashlib.sha256(ops[name].target.read_bytes()).hexdigest()
    assert ops["notes.txt"].source_content == "line one\nline two\n"
    atomic_write(ops["notes.txt"].target, ops["notes.txt"].source_content)
    assert ops["notes.txt"].target.read_bytes() == b"line one\nline two\n"


def test_the_recorded_hash_is_the_hash_of_what_is_written_not_of_the_checkout(tmp_path: Path):
    """The manifest hash of a text op is the hash of its projected text: it does not change
    when the working tree's newline conversion does."""
    from integrations.installer.claude_code_fileops import _collect_skill_dir_ops

    for newline in (b"\n", b"\r\n"):
        skill = tmp_path / f"skill{len(newline)}"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# s\n", encoding="utf-8")
        (skill / "t.j2").write_bytes(b"a" + newline + b"b" + newline)
        ops = {
            Path(op.target).name: op
            for op in _collect_skill_dir_ops(skill, tmp_path / "o", "ds-x", tmp_path)
        }
        assert ops["t.j2"].source_hash == hashlib.sha256(b"a\nb\n").hexdigest()
