from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.manifest import (
    MANIFEST_SCHEMA_VERSION,
    build_manifest,
    compute_hash,
    get_manifest_path,
    read_manifest,
    verify_file_hashes,
    write_manifest,
)


def test_get_manifest_path_uses_ds_home(ds_home):
    path = get_manifest_path("claude_code", ds_home)
    assert path == ds_home / "integrations" / "claude_code" / "manifest.json"


def test_manifest_round_trip(ds_home):
    manifest = build_manifest(
        tool="claude_code",
        scope="user",
        ds_version="migration-47",
        files=[{"path": "/tmp/test.md", "operation": "create", "content_hash": "abc", "backup_path": None}],
    )
    write_manifest("claude_code", manifest, ds_home)
    loaded = read_manifest("claude_code", ds_home)
    assert loaded is not None
    assert loaded["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert loaded["tool"] == "claude_code"
    assert loaded["scope"] == "user"
    assert loaded["ds_version"] == "migration-47"
    assert len(loaded["files"]) == 1


def test_read_manifest_returns_none_when_missing(ds_home):
    result = read_manifest("claude_code", ds_home)
    assert result is None


def test_read_manifest_returns_none_on_corrupt_json(ds_home):
    path = get_manifest_path("claude_code", ds_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    result = read_manifest("claude_code", ds_home)
    assert result is None


def test_installed_at_is_iso8601(ds_home):
    manifest = build_manifest(tool="t", scope="user", ds_version="v1", files=[])
    assert "T" in manifest["installed_at"]
    assert manifest["installed_at"].endswith("+00:00") or manifest["installed_at"].endswith("Z") or "+" in manifest["installed_at"]


def test_compute_hash_is_sha256():
    h = compute_hash("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_hash_bytes_vs_str_consistent():
    assert compute_hash("hello") == compute_hash(b"hello")


def test_verify_file_hashes_all_match(tmp_path, ds_home):
    f = tmp_path / "test.md"
    f.write_text("content", encoding="utf-8")
    manifest = {
        "files": [{"path": str(f), "operation": "create", "content_hash": compute_hash("content")}]
    }
    assert verify_file_hashes(manifest) == []


def test_verify_file_hashes_detects_drift(tmp_path, ds_home):
    f = tmp_path / "test.md"
    f.write_text("changed content", encoding="utf-8")
    manifest = {
        "files": [{"path": str(f), "operation": "create", "content_hash": compute_hash("original content")}]
    }
    drifted = verify_file_hashes(manifest)
    assert any("hash_mismatch" in d for d in drifted)


def test_verify_file_hashes_missing_file(tmp_path, ds_home):
    manifest = {
        "files": [{"path": str(tmp_path / "nonexistent.md"), "operation": "create", "content_hash": "abc"}]
    }
    drifted = verify_file_hashes(manifest)
    assert any("missing" in d for d in drifted)


def test_verify_file_hashes_skips_skip_operations(tmp_path, ds_home):
    manifest = {
        "files": [{"path": str(tmp_path / "local.json"), "operation": "skip", "content_hash": ""}]
    }
    assert verify_file_hashes(manifest) == []
