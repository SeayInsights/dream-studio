"""A managed-region merge keeps the newline the operator's own file uses.

WHY (#925). The installer writes the files it projects as LF on every OS (so an installed
file is the committed file, byte for byte). But CLAUDE.md and settings.json are the
OPERATOR's files: the installer only merges a managed region into them. An operator's CRLF
CLAUDE.md came back LF after an install that changed the managed region, and so did a CRLF
settings.json (content preserved, recoverable from the backup, but every line of a file the
operator owns changed). The old code flipped LF files to CRLF the same way. A merge keeps the
file's own newline: CRLF stays CRLF, LF stays LF; a file that does not exist yet is LF.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.installer.file_ops import atomic_write, file_newline

REPO_ROOT = Path(__file__).resolve().parents[3]


def _install(tmp_path: Path, files: dict[str, bytes]) -> Path:
    config_root = tmp_path / "claude_config"
    config_root.mkdir()
    for name, data in files.items():
        (config_root / name).write_bytes(data)
    ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=tmp_path / "ds_home",
    ).install("execute")
    return config_root


def _newlines(data: bytes) -> tuple[int, int]:
    """(CRLF count, bare LF count)."""
    crlf = data.count(b"\r\n")
    return crlf, data.count(b"\n") - crlf


OPERATOR_MD = (
    "# My own notes\n\nKeep answers short.\n\n"
    "<!-- BEGIN AUTO-ROUTING -->\nstale routing from an older install\n<!-- END AUTO-ROUTING -->\n"
    "\n- one\n- two\n"
)
OPERATOR_SETTINGS = '{\n  "permissions": {\n    "allow": ["Bash(ls:*)"]\n  }\n}\n'


@pytest.mark.parametrize("newline", ["\r\n", "\n"])
def test_claude_md_keeps_its_own_newline_after_a_managed_region_merge(tmp_path: Path, newline: str):
    original = OPERATOR_MD.replace("\n", newline).encode("utf-8")
    config_root = _install(tmp_path, {"CLAUDE.md": original})
    merged = (config_root / "CLAUDE.md").read_bytes()
    assert merged != original  # the managed region was merged in
    crlf, lf = _newlines(merged)
    assert (crlf, lf) == ((crlf, 0) if newline == "\r\n" else (0, lf)), (crlf, lf)
    assert merged.replace(b"\r\n", b"\n").startswith(b"# My own notes\n")  # the operator's text


@pytest.mark.parametrize("newline", ["\r\n", "\n"])
def test_settings_json_keeps_its_own_newline_after_a_merge(tmp_path: Path, newline: str):
    original = OPERATOR_SETTINGS.replace("\n", newline).encode("utf-8")
    config_root = _install(tmp_path, {"settings.json": original})
    merged = (config_root / "settings.json").read_bytes()
    crlf, lf = _newlines(merged)
    assert (crlf, lf) == ((crlf, 0) if newline == "\r\n" else (0, lf)), (crlf, lf)
    data = json.loads(merged.decode("utf-8"))
    assert data["permissions"]["allow"] == ["Bash(ls:*)"]  # the operator's own setting survives
    assert "hooks" in data


def test_a_new_claude_md_and_settings_are_lf(tmp_path: Path):
    config_root = _install(tmp_path, {})
    for name in ("CLAUDE.md", "settings.json"):
        crlf, lf = _newlines((config_root / name).read_bytes())
        assert crlf == 0 and lf > 0, name


def test_a_file_with_mostly_crlf_stays_crlf(tmp_path: Path):
    mixed = OPERATOR_MD.replace("\n", "\r\n").encode("utf-8") + b"a stray lf line\n"
    config_root = _install(tmp_path, {"CLAUDE.md": mixed})
    crlf, lf = _newlines((config_root / "CLAUDE.md").read_bytes())
    assert crlf > 0 and lf == 0  # one style, the file's majority


def test_a_second_install_changes_nothing(tmp_path: Path):
    original = OPERATOR_MD.replace("\n", "\r\n").encode("utf-8")
    config_root = _install(tmp_path, {"CLAUDE.md": original})
    first = (config_root / "CLAUDE.md").read_bytes()
    ClaudeCodeInstaller(
        config_root, "user", canonical_root=REPO_ROOT / "canonical", ds_home=tmp_path / "ds_home"
    ).install("execute")
    assert (config_root / "CLAUDE.md").read_bytes() == first


def test_projected_skill_files_stay_lf_even_next_to_crlf_operator_files(tmp_path: Path):
    config_root = _install(tmp_path, {"CLAUDE.md": OPERATOR_MD.replace("\n", "\r\n").encode()})
    skill = (config_root / "skills" / "ds-security" / "SKILL.md").read_bytes()
    assert b"\r\n" not in skill


def test_a_projected_file_that_changed_is_rewritten_as_lf_whatever_it_held(tmp_path: Path):
    """The newline of the operator's own files is theirs to keep; a file the installer
    projects is its own, and comes back as the committed LF even over an edited CRLF copy."""
    config_root = _install(tmp_path, {})
    skill = config_root / "skills" / "ds-security" / "templates" / "security" / "README.md"
    skill.write_bytes(b"edited by someone\r\nwith windows line ends\r\n")
    ClaudeCodeInstaller(
        config_root, "user", canonical_root=REPO_ROOT / "canonical", ds_home=tmp_path / "ds_home"
    ).install("execute")
    data = skill.read_bytes()
    assert b"edited by someone" not in data and b"\r\n" not in data


# -- the helper ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"a\r\nb\r\n", "\r\n"),
        (b"a\nb\n", "\n"),
        (b"a\r\nb\nc\r\n", "\r\n"),
        (b"a\nb\r\nc\n", "\n"),
        (b"a\r\nb\n", "\n"),  # a tie goes to LF
        (b"no newline at all", None),
        (b"", None),
        (b"lone\rcr\r", None),
    ],
)
def test_file_newline(tmp_path: Path, data: bytes, expected):
    path = tmp_path / "f.txt"
    path.write_bytes(data)
    assert file_newline(path) == expected


def test_file_newline_of_a_missing_file_is_none(tmp_path: Path):
    assert file_newline(tmp_path / "absent") is None


def test_atomic_write_defaults_to_lf_and_honours_an_explicit_newline(tmp_path: Path):
    target = tmp_path / "t.txt"
    atomic_write(target, "a\nb\n")
    assert target.read_bytes() == b"a\nb\n"
    atomic_write(target, "a\nb\n", newline="\r\n")
    assert target.read_bytes() == b"a\r\nb\r\n"
