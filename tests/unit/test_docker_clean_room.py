"""Phase 8F Docker clean-room authority tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_docker_runtime_files_exist():
    assert (REPO_ROOT / "Dockerfile.runtime-check").is_file()
    assert (REPO_ROOT / ".dockerignore").is_file()
    assert (REPO_ROOT / "scripts" / "docker_runtime_check.py").is_file()


def test_dockerfile_uses_isolated_runtime_home():
    source = _read("Dockerfile.runtime-check")

    assert "HOME=/tmp/dream-studio-user" in source
    assert "DREAM_STUDIO_HOME=/tmp/dream-studio-home" in source
    assert 'CMD ["python", "scripts/docker_runtime_check.py"]' in source
    assert "VOLUME" not in source
    assert "~/.dream-studio" not in source
    assert "C:\\Users\\Example User" not in source
    assert "studio.db" not in source


def test_make_target_does_not_mount_host_state():
    source = _read("Makefile")
    match = re.search(r"docker-runtime-check:\n(?P<body>(?:\t.*\n?)+)", source)

    assert match is not None
    body = match.group("body")
    assert "docker build -f Dockerfile.runtime-check" in body
    assert "docker run --rm --network none" in body
    assert "-e HOME=/tmp/dream-studio-user" in body
    assert "-e DREAM_STUDIO_HOME=/tmp/dream-studio-home" in body
    assert " -v " not in body
    assert "--volume" not in body
    assert "--mount" not in body
    assert ".dream-studio" not in body
    assert "studio.db" not in body


def test_dockerignore_excludes_local_runtime_state():
    source = _read(".dockerignore")

    assert ".dream-studio/" in source
    assert "**/.dream-studio/" in source
    assert "**/studio.db" in source
    assert "**/studio.db.bak" in source
    assert "**/studio.db.pre-restore.bak" in source


def test_clean_room_script_runs_expected_validation_commands():
    source = _read("scripts/docker_runtime_check.py")

    assert "interfaces/cli/runtime_preflight.py" in source
    assert "interfaces/cli/runtime_recovery.py" in source
    assert "tests/integration/test_schema_migrations.py" in source
    assert "runtime_reliability" in source
    assert "host_runtime_state_mounted=false" in source
    assert "HOME" in source
    assert "DREAM_STUDIO_HOME" in source
    assert "C:\\Users\\Example User" not in source
    assert ".dream-studio\\state\\studio.db" not in source


def test_no_docker_compose_file_introduced():
    compose_names = {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
    existing = {path.name for path in REPO_ROOT.iterdir() if path.name in compose_names}

    assert existing == set()


def test_docker_docs_keep_harness_optional_and_non_authoritative():
    source = _read("docs/operations/docker-clean-room.md")

    assert "optional validation harness" in source
    assert "not a runtime authority" in source
    assert "does not mount the host `~/.dream-studio`" in source
    assert "Native preflight remains authoritative" in source
    assert "Docker must not be used to hide" in source
