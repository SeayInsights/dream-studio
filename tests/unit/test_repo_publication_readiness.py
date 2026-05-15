from __future__ import annotations

from pathlib import Path

from core.release.repo_publication_readiness import (
    build_repo_publication_readiness,
    validate_repo_publication_readiness,
)


def test_publication_readiness_accepts_current_repo_public_boundary() -> None:
    packet = build_repo_publication_readiness(Path(__file__).resolve().parents[2])

    assert packet["current_tracked_tree_publication_safe"] is True
    assert packet["git_history_publication_safe"] is True
    assert packet["secret_scan_findings"] == 0
    assert packet["apache_2_license_consistent"] is True
    assert packet["readme_current_product_framing"] is True
    assert packet["prd_current_product_authority"] is True
    assert validate_repo_publication_readiness(packet) == []


def test_publication_readiness_blocks_legacy_runtime_artifact_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "Apache-2.0 local-first AI orchestration adapter surfaces "
        "SQLite-backed authority Contract Atlas Publication Boundary",
        encoding="utf-8",
    )
    prd = repo / "docs" / "product" / "dream-studio-prd.md"
    prd.parent.mkdir(parents=True)
    prd.write_text(
        "Status: current public product authority\n"
        "local-first AI orchestration\n"
        "Authority Model\n"
        "Secure Production Readiness\n"
        "Contract Atlas\n"
        "Publication Boundary\n"
        "Human Approval Boundaries\n",
        encoding="utf-8",
    )

    packet = build_repo_publication_readiness(
        repo,
        tracked_files=["core/app.py", ".dream-studio/state/studio.db"],
        history_paths=["backups/studio.db.2026-05-06.bak"],
        ignored_status={
            "schema": "dream_studio.repo_publication.ignored_file_audit.v1",
            "untracked_file_count": 0,
            "untracked_publication_risk": False,
            "untracked_publication_risk_findings": [],
            "ignored_boundary_ok": True,
        },
    )

    assert packet["current_tracked_tree_publication_safe"] is False
    assert packet["git_history_publication_safe"] is False
    assert "current_tracked_tree_not_publication_safe" in validate_repo_publication_readiness(
        packet
    )
    assert "git_history_not_publication_safe" in validate_repo_publication_readiness(packet)


def test_publication_readiness_reports_secret_rule_without_value(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "Apache-2.0 local-first AI orchestration adapter surfaces "
        "SQLite-backed authority Contract Atlas Publication Boundary",
        encoding="utf-8",
    )
    prd = repo / "docs" / "product" / "dream-studio-prd.md"
    prd.parent.mkdir(parents=True)
    prd.write_text(
        "Status: current public product authority\n"
        "local-first AI orchestration\n"
        "Authority Model\n"
        "Secure Production Readiness\n"
        "Contract Atlas\n"
        "Publication Boundary\n"
        "Human Approval Boundaries\n",
        encoding="utf-8",
    )
    secret_file = repo / "example.env"
    secret_file.write_text("OPENAI_API_KEY=sk-" + ("a" * 24), encoding="utf-8")

    packet = build_repo_publication_readiness(
        repo,
        tracked_files=["README.md", "LICENSE", "docs/product/dream-studio-prd.md", "example.env"],
        history_paths=[],
        ignored_status={
            "schema": "dream_studio.repo_publication.ignored_file_audit.v1",
            "untracked_file_count": 0,
            "untracked_publication_risk": False,
            "untracked_publication_risk_findings": [],
            "ignored_boundary_ok": True,
        },
    )

    assert packet["secret_scan_findings"] == 1
    assert packet["secret_scan_finding_refs"][0]["rule"] == "openai_api_key"
    assert packet["secret_scan_finding_refs"][0]["value_printed"] is False
