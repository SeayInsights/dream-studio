"""Each config root's integration backups live in their own directory, uniquely named.

Backups for every root went to <home>/backups/claude_code/<relative path>.<second>.bak:
two roots' settings.json, backed up in the same second, wrote one file.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.installer.file_ops import backup_before_write
from integrations.manifest import config_root_key


def test_two_roots_keep_separate_backups(tmp_path):
    home = tmp_path / "home"
    roots = [tmp_path / "root-a", tmp_path / "root-b"]
    for i, root in enumerate(roots):
        root.mkdir()
        (root / "settings.json").write_text(json.dumps({"mine": i}), encoding="utf-8")
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        for root in roots:
            ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    for i, root in enumerate(roots):
        own = home / "backups" / "claude_code" / config_root_key(root)
        copies = list(own.rglob("settings.json.*.bak"))
        assert copies, f"no settings.json backup under {own}"
        assert json.loads(copies[0].read_text(encoding="utf-8")) == {"mine": i}


def test_two_backups_of_one_file_in_one_second_are_both_kept(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("one", encoding="utf-8")
    first = backup_before_write(target, tmp_path / "b")
    target.write_text("two", encoding="utf-8")
    second = backup_before_write(target, tmp_path / "b")
    assert first != second
    assert (
        first.read_text(encoding="utf-8") == "one" and second.read_text(encoding="utf-8") == "two"
    )
