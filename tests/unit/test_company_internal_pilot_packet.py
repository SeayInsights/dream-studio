from __future__ import annotations

import json
import re
from pathlib import Path

PACKET_DIR = Path("docs/pilot/company-internal-pilot")
DEMO_DIR = Path("docs/demo/sanitized")

TEXT_FILES = [
    PACKET_DIR / "README.md",
    PACKET_DIR / "executive-summary.md",
    PACKET_DIR / "technical-appendix.md",
    PACKET_DIR / "feedback-template.md",
    PACKET_DIR / "validation-manifest.json",
]

WINDOWS_USER_PATH_FORWARD = "C:" + "/Users/"
LIVE_BACKUP_ROOT = "Dream Studio " + "Live Backups"
PRIVATE_PATTERNS = [
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(re.escape(WINDOWS_USER_PATH_FORWARD), re.IGNORECASE),
    re.compile(r"\.dream-studio", re.IGNORECASE),
    re.compile(re.escape(LIVE_BACKUP_ROOT), re.IGNORECASE),
    re.compile(r"api[_-]?key\s*[:=]", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"password\s*[:=]", re.IGNORECASE),
]


def _packet_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in TEXT_FILES)


def test_company_internal_pilot_packet_contains_required_artifacts() -> None:
    for path in TEXT_FILES:
        assert path.exists(), path
        assert path.stat().st_size > 0, path

    for path in (
        DEMO_DIR / "README.md",
        DEMO_DIR / "5-minute-script.md",
        DEMO_DIR / "15-minute-technical-walkthrough.md",
        DEMO_DIR / "fallback-plan.md",
        DEMO_DIR / "screenshots/observe-mode.png",
        DEMO_DIR / "screenshots/assist-mode.png",
        DEMO_DIR / "screenshots/operate-mode.png",
    ):
        assert path.exists(), path


def test_company_internal_pilot_manifest_declares_safe_boundaries() -> None:
    manifest = json.loads((PACKET_DIR / "validation-manifest.json").read_text())

    assert manifest["status"] == "pilot_packet_ready"
    assert manifest["recommended_pilot_mode"] == "analytics_only_observe"
    assert manifest["public_materials_use_sanitized_packet"] is True
    assert manifest["live_dashboard_private_only_without_separate_sanitization"] is True
    assert manifest["requires_push"] is False
    assert manifest["requires_deploy"] is False
    assert manifest["requires_cloud_hosting"] is False
    assert manifest["requires_docker"] is False
    assert manifest["requires_external_project_mutation"] is False
    assert manifest["requires_secret_access"] is False
    assert manifest["requires_ai_provider_api_keys"] is False
    assert "analytics_only" in manifest["enabled_modules"]
    assert "career_ops" in manifest["disabled_by_default"]


def test_company_internal_pilot_packet_covers_required_sections() -> None:
    packet = _packet_text().lower()

    for phrase in (
        "target audience",
        "pilot goals",
        "pilot non-goals",
        "recommended mode",
        "enabled modules",
        "disabled modules",
        "allowed data sources",
        "forbidden data sources",
        "privacy and security boundaries",
        "install and setup checklist",
        "demo script",
        "optional private-live walkthrough",
        "success metrics",
        "risk register",
        "rollback and offboarding",
        "support and troubleshooting",
        "feedback collection",
        "executive summary",
        "technical appendix",
    ):
        assert phrase in packet


def test_company_internal_pilot_packet_has_no_private_values_or_live_paths() -> None:
    packet = _packet_text()

    for pattern in PRIVATE_PATTERNS:
        assert not pattern.search(packet), pattern.pattern

    assert "private Work Orders" in packet
    assert "live dashboard review is private-only" in packet.lower()
    assert "without hooks, agents, workflows, Claude, Codex, Docker" in packet
