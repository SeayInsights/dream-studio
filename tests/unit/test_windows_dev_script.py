import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_SCRIPT = REPO_ROOT / "scripts" / "dev.ps1"
DOCKER_DOC = REPO_ROOT / "docs" / "operations" / "docker-clean-room.md"
WINDOWS_DOC = REPO_ROOT / "docs" / "operations" / "windows-dev-commands.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_windows_dev_script_exists_with_core_targets() -> None:
    source = _read(DEV_SCRIPT)

    for target in (
        '"test"',
        '"lint"',
        '"typecheck"',
        '"verify"',
        '"run-api"',
        '"run-ui"',
        '"clean"',
        '"docker-runtime-check"',
    ):
        assert target in source


def test_windows_dev_script_keeps_native_readiness_targets_without_make() -> None:
    source = _read(DEV_SCRIPT)

    for target in (
        '"verify"',
        '"verify-guarded"',
        '"runtime-check"',
        '"setup-check"',
        '"dashboard-check"',
        '"test"',
        '"test-guarded"',
    ):
        assert target in source
    assert re.search(r"\bmake\b", source, flags=re.IGNORECASE) is None


def test_windows_dev_script_exposes_guarded_validation_targets() -> None:
    source = _read(DEV_SCRIPT)

    assert "function Invoke-GuardedPython" in source
    assert "scripts/runtime_state_hash_guard.py" in source
    assert '"verify-guarded"' in source
    assert '"test-guarded"' in source
    assert "schema_migrations" in source
    assert "runtime_reliability" in source
    assert "hook_runtime_reliability" in source
    assert "powershell_test" in source


def test_windows_dev_script_mirrors_docker_target_without_make() -> None:
    source = _read(DEV_SCRIPT)

    assert "Dockerfile.runtime-check" in source
    assert "dream-studio-runtime-check" in source
    assert "--network" in source
    assert "none" in source
    assert "DREAM_STUDIO_HOME=/tmp/dream-studio-home" in source
    assert "HOME=/tmp/dream-studio-user" in source


def test_windows_dev_script_does_not_mount_host_runtime_state() -> None:
    source = _read(DEV_SCRIPT)

    forbidden = (
        "--volume",
        "--mount",
        "C:\\Users\\Example User",
        "~/.dream-studio",
        "studio.db",
    )
    for token in forbidden:
        assert token not in source


def test_windows_docs_do_not_require_make() -> None:
    docker_doc = _read(DOCKER_DOC)
    windows_doc = _read(WINDOWS_DOC)
    contributing = _read(CONTRIBUTING)

    assert "scripts/dev.ps1 docker-runtime-check" in docker_doc
    assert "make is not required" in windows_doc.lower()
    assert "scripts/dev.ps1 test" in contributing
