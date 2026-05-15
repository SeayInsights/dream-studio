from __future__ import annotations

import json
import re
from pathlib import Path

PACKET_DIR = Path("docs/demo/sanitized")
TEXT_FILES = [
    PACKET_DIR / "README.md",
    PACKET_DIR / "5-minute-script.md",
    PACKET_DIR / "15-minute-technical-walkthrough.md",
    PACKET_DIR / "fallback-plan.md",
    PACKET_DIR / "rehearsal-report.md",
    PACKET_DIR / "validation-manifest.json",
    PACKET_DIR / "screenshots/demo-screens.html",
]
SCREENSHOTS = [
    PACKET_DIR / "screenshots/observe-mode.png",
    PACKET_DIR / "screenshots/assist-mode.png",
    PACKET_DIR / "screenshots/operate-mode.png",
]
WINDOWS_USER_PATH_FORWARD = "C:" + "/Users/"
LIVE_BACKUP_ROOT = "Dream Studio " + "Live Backups"
PRIVATE_PATTERNS = [
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(re.escape(WINDOWS_USER_PATH_FORWARD), re.IGNORECASE),
    re.compile(r"\\.dream-studio\\", re.IGNORECASE),
    re.compile(re.escape(LIVE_BACKUP_ROOT), re.IGNORECASE),
    re.compile(r"api[_-]?key\\s*[:=]", re.IGNORECASE),
    re.compile(r"token\\s*[:=]\\s*[A-Za-z0-9_\\-]{16,}", re.IGNORECASE),
    re.compile(r"password\\s*[:=]", re.IGNORECASE),
]


def test_sanitized_demo_packet_contains_required_artifacts() -> None:
    for path in [*TEXT_FILES, *SCREENSHOTS]:
        assert path.exists(), path
        assert path.stat().st_size > 0, path


def test_sanitized_demo_manifest_declares_public_ready_boundaries() -> None:
    manifest = json.loads((PACKET_DIR / "validation-manifest.json").read_text())

    assert manifest["verdict"] == "public_demo_ready"
    assert manifest["demo_mode"] == "public_sanitized"
    assert manifest["screenshots_are_synthetic"] is True
    assert manifest["synthetic_data_live_operator_view"] is False
    assert manifest["live_sqlite_mutation_authorized"] is False
    assert manifest["external_project_mutation_authorized"] is False
    assert manifest["push_deploy_authorized"] is False
    assert set(manifest["demo_modes"]) == {"observe", "assist", "operate"}


def test_sanitized_demo_covers_observe_assist_operate() -> None:
    packet = "\n".join(path.read_text(encoding="utf-8") for path in TEXT_FILES)

    for phrase in (
        "Observe Mode",
        "Assist Mode",
        "Operate Mode",
        "context packet",
        "adapter result",
        "evidence capture",
        "attribution",
        "route decision",
        "Work Order",
        "validation",
        "approval boundary",
        "safe continuation",
    ):
        assert phrase.lower() in packet.lower()


def test_sanitized_demo_text_has_no_private_values_or_live_paths() -> None:
    packet = "\n".join(path.read_text(encoding="utf-8") for path in TEXT_FILES)

    for pattern in PRIVATE_PATTERNS:
        assert not pattern.search(packet), pattern.pattern
    assert "private_work_orders" in packet
    assert "local_runtime_paths" in packet


def test_sanitized_demo_screenshots_are_not_empty() -> None:
    from PIL import Image

    for path in SCREENSHOTS:
        image = Image.open(path)
        assert image.size == (1440, 900)
        colors = image.convert("RGB").getcolors(maxcolors=1_000_000)
        assert colors is not None
        assert len(colors) > 20
