from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "interfaces" / "cli" / "ds_work_order.py"


def _work_order(target_path: Path, *, work_order_id: str = "wo-cli-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "CLI Test",
        "target_path": str(target_path),
        "objective": "Observe target readiness without changing files.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "observe-only",
        "forbidden_actions": [
            "no edits, writes, patches, formats, or moves",
            "no commits, staging, or pushes",
            "no deletes or removes",
            "no schema changes",
            "no dependency or package changes",
            "no external actions, network calls, publishing, deploys, or cloud actions",
            "no target repo mutation",
        ],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["status evidence"],
        "stop_conditions": ["target changes"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "draft",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _env(fake_home: Path, storage_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["DREAM_STUDIO_WORK_ORDER_ROOT"] = str(storage_root)
    return env


def _run(args: list[str], *, fake_home: Path, storage_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(REPO_ROOT),
        env=_env(fake_home, storage_root),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_cli_create_validate_status_with_fake_home_storage(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("target before\n", encoding="utf-8")
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    source = tmp_path / "work_order.yaml"
    source.write_text(yaml.safe_dump(_work_order(target)), encoding="utf-8")
    before = _snapshot(target)

    create = _run(
        ["create", "--from-file", str(source)],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    validate = _run(
        ["validate", "--id", "wo-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    status = _run(
        ["status", "--id", "wo-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert create.returncode == 0, create.stderr
    assert validate.returncode == 0, validate.stderr
    assert status.returncode == 0, status.stderr
    assert "created: wo-cli-001" in create.stdout
    assert "valid: wo-cli-001" in validate.stdout
    assert "status: draft" in status.stdout
    assert "approval_mode: observe_only" in status.stdout
    assert "next_required_action: run validate" in status.stdout
    assert (storage_root / "wo-cli-001" / "work_order.json").is_file()
    assert _snapshot(target) == before
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_cli_render_writes_packet_and_eval_artifacts_without_target_mutation(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("target before\n", encoding="utf-8")
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    source = tmp_path / "work_order.yaml"
    source.write_text(
        yaml.safe_dump(_work_order(target, work_order_id="wo-render-cli-001")),
        encoding="utf-8",
    )
    before = _snapshot(target)

    create = _run(
        ["create", "--from-file", str(source)],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    render = _run(
        ["render", "--id", "wo-render-cli-001", "--target", "codex"],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    status = _run(
        ["status", "--id", "wo-render-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert create.returncode == 0, create.stderr
    assert render.returncode == 0, render.stderr
    assert status.returncode == 0, status.stderr
    assert "rendered: wo-render-cli-001" in render.stdout
    assert "target: codex" in render.stdout
    assert "status: rendered" in status.stdout
    # WO-FILESDB-C3/C5: the rendered packet + evals live in the authority-free packet
    # store (packets.db), not loose rendered/*.md or evals/*.json, and never studio.db.
    from core.work_orders.packet_store import get_packet_artifact

    assert not (storage_root / "wo-render-cli-001" / "rendered").exists()
    assert (
        get_packet_artifact(
            "wo-render-cli-001", "packet", instance_key="codex", storage_root=storage_root
        )
        is not None
    )
    assert not (storage_root / "wo-render-cli-001" / "evals").exists()
    assert (
        get_packet_artifact(
            "wo-render-cli-001",
            "eval",
            instance_key="work_order_render_completeness",
            storage_root=storage_root,
        )
        is not None
    )
    assert (
        get_packet_artifact(
            "wo-render-cli-001",
            "eval",
            instance_key="skill_identifier_safety",
            storage_root=storage_root,
        )
        is not None
    )
    assert _snapshot(target) == before
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_cli_record_result_and_report_write_file_backed_artifacts(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("target before\n", encoding="utf-8")
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    source = tmp_path / "work_order.yaml"
    source.write_text(
        yaml.safe_dump(_work_order(target, work_order_id="wo-report-cli-001")),
        encoding="utf-8",
    )
    result_source = tmp_path / "result.md"
    result_source.write_text(
        "\n".join(
            [
                "Summary: CLI result recorded.",
                "Files inspected: README.md",
                "Files changed: none",
                "Commands: not run",
                "Forbidden actions: complied",
                "Target mutation: no",
                "Warnings: none",
                "Risks: none",
                "Next Work Order: Objective: review report; Risk: low; Approval: observe_only; Non-goals: mutation; Validation: static checks.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    before = _snapshot(target)

    create = _run(
        ["create", "--from-file", str(source)],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    record = _run(
        ["record-result", "--id", "wo-report-cli-001", "--from-file", str(result_source)],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    report = _run(
        ["report", "--id", "wo-report-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    status = _run(
        ["status", "--id", "wo-report-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert create.returncode == 0, create.stderr
    assert record.returncode == 0, record.stderr
    assert report.returncode == 0, report.stderr
    assert status.returncode == 0, status.stderr
    assert "result_recorded: wo-report-cli-001" in record.stdout
    assert "report: wo-report-cli-001" in report.stdout
    assert "result_present: true" in report.stdout
    assert "status: reported" in status.stdout
    # WO-FILESDB-C5: results + report live in the packet store, not results/*.{md,json}
    # or report.md on disk.
    from core.work_orders.packet_store import get_packet_artifact

    assert not (storage_root / "wo-report-cli-001" / "results").exists()
    assert not (storage_root / "wo-report-cli-001" / "report.md").exists()
    assert get_packet_artifact("wo-report-cli-001", "result", storage_root=storage_root) is not None
    assert (
        get_packet_artifact("wo-report-cli-001", "result_meta", storage_root=storage_root)
        is not None
    )
    assert get_packet_artifact("wo-report-cli-001", "report", storage_root=storage_root) is not None
    # Evals live in the packet store too.
    assert not (storage_root / "wo-report-cli-001" / "evals").exists()
    assert (
        get_packet_artifact(
            "wo-report-cli-001",
            "eval",
            instance_key="observe_only_compliance",
            storage_root=storage_root,
        )
        is not None
    )
    assert (
        get_packet_artifact(
            "wo-report-cli-001",
            "eval",
            instance_key="result_report_completeness",
            storage_root=storage_root,
        )
        is not None
    )
    assert _snapshot(target) == before
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_cli_create_allows_missing_target_only_when_flagged(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    missing_target = tmp_path / "missing"
    source = tmp_path / "work_order.yaml"
    source.write_text(
        yaml.safe_dump(_work_order(missing_target, work_order_id="wo-missing-001")),
        encoding="utf-8",
    )

    rejected = _run(
        ["create", "--from-file", str(source)],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    accepted = _run(
        ["create", "--from-file", str(source), "--allow-missing-target"],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    validate = _run(
        ["validate", "--id", "wo-missing-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert rejected.returncode == 2
    assert "target_path: does not exist" in rejected.stderr
    assert accepted.returncode == 0, accepted.stderr
    assert validate.returncode == 2
    assert "target_path: does not exist" in validate.stderr
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_cli_regenerate_handoff_writes_audit_artifact_without_target_mutation(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("target before\n", encoding="utf-8")
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    audit_path = fake_home / ".dream-studio" / "meta" / "audit" / "phase17v.md"
    source = tmp_path / "stale-handoff.md"
    source.write_text(
        "\n".join(
            [
                "# Handoff Packet",
                "",
                "## Phase Name",
                "Phase 17V - DreamySuite Background Parity Post-Push Retrospective Planning",
                "",
                "## Handoff Type",
                "normal_next_work_order",
                "",
                "## Phase Type",
                "product_closeout",
                "",
                "## Required Decision Taxonomy",
                "- READY_FOR_HUMAN_REVIEW",
                "- READY_FOR_COMMIT_PLANNING",
                "- NEEDS_ONE_MORE_FIX",
                "- HOLD",
                "- FAIL",
                "",
                "## Final Decision",
                "HOLD",
                "",
                "## Decision Rationale",
                "This post-push follow-up starts at HOLD.",
                "",
                "## Fresh-Session Rule",
                "Assume you have no prior conversation context. Use only this prompt and referenced artifacts.",
                "",
                "## Source Work Order ID",
                "wo-dreamysuite-019-background-parity-approved-push-execution",
                "",
                "## Next Work Order ID",
                "wo-dreamysuite-020-background-parity-post-push-retrospective-planning",
                "",
                "## Dream Studio Repo Path",
                str(REPO_ROOT),
                "",
                "## Target Repo Path",
                str(target),
                "",
                "## Baseline Dream Studio Branch/HEAD",
                "Branch: integration/phase3-plus-phase1-phase2",
                "",
                "## Baseline Target Repo Branch/HEAD",
                "Branch: fix/drag-and-selection-scaling",
                "",
                "## Objective",
                "Review the completed background parity push and decide whether to produce a retrospective or case-study planning artifact.",
                "",
                "## Capability Boundary",
                "This is observe-only planning.",
                "",
                "## Approval Mode",
                "observe_only",
                "",
                "## Risk Level",
                "medium",
                "",
                "## Scope Include",
                "- Phase 17U report",
                "",
                "## Scope Exclude",
                "- push execution",
                "",
                "## Approved Files If Mutation-Gated",
                "not applicable",
                "",
                "## Forbidden Files",
                "- any DreamySuite file",
                "",
                "## Allowed Actions",
                "- inspect Phase 17U report",
                "",
                "## Forbidden Actions",
                "- push",
                "- edit files",
                "- stage files",
                "- commit files",
                "",
                "## Approval Artifact Requirement",
                "not applicable for observe_only planning",
                "",
                "## Before/After Evidence Requirements",
                "Capture read-only Dream Studio and DreamySuite status before and after review.",
                "",
                "## Validation Commands",
                "No validation commands are approved for this planning phase.",
                "",
                "## Eval Requirements",
                "- handoff_prompt_completeness",
                "",
                "## Report Path",
                str(fake_home / ".dream-studio" / "meta" / "audit" / "phase17v-report.md"),
                "",
                "## Stop Conditions",
                "- Handoff Understanding Report is missing",
                "",
                "## Handoff Understanding Report Requirement",
                "Before taking action, produce a Handoff Understanding Report with objective, repositories involved, source Work Order ID, next Work Order ID, approval mode, risk level, approved files, forbidden files, allowed commands/actions, forbidden commands/actions, evidence required, validation required, eval requirements, stop conditions, first safe action, and missing context.",
                "",
                "## First Safe Action",
                "Read the Phase 17U report, then produce the Handoff Understanding Report before touching any repository.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    before = _snapshot(target)

    result = _run(
        ["regenerate-handoff", "--from-file", str(source), "--to-file", str(audit_path)],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert result.returncode == 0, result.stderr
    assert "handoff_regenerated:" in result.stdout
    assert "target_repo_mutation: no" in result.stdout
    regenerated = audit_path.read_text(encoding="utf-8")
    assert "## Readiness Rules" in regenerated
    assert "## Expected Verdict" in regenerated
    assert "any target repo file" in regenerated
    assert "inspect referenced source report" in regenerated
    assert _snapshot(target) == before
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_cli_generate_security_next_handoff_from_file_backed_artifacts(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    audit_path = fake_home / ".dream-studio" / "meta" / "audit" / "phase18s12.md"
    source_report = tmp_path / "phase18s11-report.md"
    source_report.write_text(
        "Bill Stack target: C:\\Users\\Example User\\builds\\family-bill-organizer\n",
        encoding="utf-8",
    )
    security_report = tmp_path / "review_report.yaml"
    security_report.write_text(
        yaml.safe_dump(
            {
                "source_work_order_id": "wo-dream-studio-018s11-first-observe-only-tier0-security-review-bill-stack",
                "target_id": "bill-stack",
                "verdict": "PASS WITH RISKS",
                "next_work_order_recommendation": {
                    "recommended_work_order_id": "wo-dream-studio-018s12-bill-stack-tier0-security-remediation-planning",
                    "recommended_phase_name": "Phase 18S.12 - Bill Stack Tier 0 Security Remediation Planning",
                    "recommended_handoff_type": "normal_next_work_order",
                    "recommended_phase_type": "normal_next_work_order",
                    "decision_taxonomy": [
                        "CONTINUE_TO_NEXT_WORK_ORDER",
                        "REQUEST_HUMAN_APPROVAL",
                        "HOLD",
                        "FAIL",
                    ],
                    "recommended_decision": "HOLD",
                },
            }
        ),
        encoding="utf-8",
    )
    release_gate = tmp_path / "release_gate.yaml"
    release_gate.write_text(
        yaml.safe_dump({"decision": "REMEDIATE_BEFORE_RELEASE"}),
        encoding="utf-8",
    )
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()
    finding_ids = [
        "revenuecat_webhook_unsigned",
        "household_invite_code_exposure",
        "browser_token_exposure_window",
        "server_password_policy_gap",
        "in_memory_auth_state",
        "dependency_reproducibility_gap",
    ]
    for finding_id in finding_ids:
        (findings_dir / f"{finding_id}.yaml").write_text(
            yaml.safe_dump({"finding_id": f"sec.finding.bill_stack.{finding_id}"}),
            encoding="utf-8",
        )
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "baseline.yaml").write_text(
        yaml.safe_dump(
            {
                "evidence_id": "sec.evidence.bill_stack.baseline",
                "branch_head": {
                    "target_branch": "master",
                    "target_head": "e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
                },
                "before_status": "\n".join(
                    [
                        "## master...origin/master",
                        "?? billstack-api/migrate_direct.py",
                        "?? billstack-web/dev-dist/",
                    ]
                ),
            }
        ),
        encoding="utf-8",
    )
    dashboard_projection = tmp_path / "projection_inputs.yaml"
    dashboard_projection.write_text("artifact_kind: DashboardProjectionInputs\n", encoding="utf-8")

    result = _run(
        [
            "generate-security-next-handoff",
            "--source-report",
            str(source_report),
            "--security-report",
            str(security_report),
            "--release-gate",
            str(release_gate),
            "--findings-dir",
            str(findings_dir),
            "--evidence-dir",
            str(evidence_dir),
            "--dashboard-projection",
            str(dashboard_projection),
            "--to-file",
            str(audit_path),
            "--output-report-path",
            str(fake_home / ".dream-studio" / "meta" / "audit" / "phase18s12-report.md"),
            "--expected-untracked-entry",
            "billstack-api/migrate_direct.py",
            "--expected-untracked-entry",
            "billstack-web/dev-dist/",
            *[
                item
                for finding_id in finding_ids
                for item in ("--expected-finding-id", f"sec.finding.bill_stack.{finding_id}")
            ],
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert result.returncode == 0, result.stderr
    assert "security_handoff_generated:" in result.stdout
    assert "security_handoff_evals: pass" in result.stdout
    generated = audit_path.read_text(encoding="utf-8")
    assert "## Target Baseline Constraints" in generated
    assert "## Release-Gate Decision Rules" in generated
    assert "REMEDIATE_BEFORE_RELEASE" in generated
    assert "sec.finding.bill_stack.revenuecat_webhook_unsigned" in generated


def test_cli_generate_security_mutation_handoff_forbids_commit_authority(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    audit_path = fake_home / ".dream-studio" / "meta" / "audit" / "phase18s13.md"
    planning_report = tmp_path / "phase18s12-report.md"
    planning_report.write_text(
        "\n".join(
            [
                "# Phase 18S.12",
                "Target Repo Path",
                "C:\\Users\\Example User\\builds\\family-bill-organizer",
            ]
        ),
        encoding="utf-8",
    )
    security_report = tmp_path / "review_report.yaml"
    security_report.write_text(
        yaml.safe_dump(
            {
                "source_work_order_id": "wo-dream-studio-018s11-first-observe-only-tier0-security-review-bill-stack",
                "target_id": "bill-stack",
                "verdict": "PASS WITH RISKS",
            }
        ),
        encoding="utf-8",
    )
    release_gate = tmp_path / "release_gate.yaml"
    release_gate.write_text(
        yaml.safe_dump({"decision": "REMEDIATE_BEFORE_RELEASE"}),
        encoding="utf-8",
    )
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()
    finding_ids = [
        "revenuecat_webhook_unsigned",
        "household_invite_code_exposure",
        "browser_token_exposure_window",
        "server_password_policy_gap",
        "in_memory_auth_state",
        "dependency_reproducibility_gap",
    ]
    for finding_id in finding_ids:
        (findings_dir / f"{finding_id}.yaml").write_text(
            yaml.safe_dump(
                {
                    "finding_id": f"sec.finding.bill_stack.{finding_id}",
                    "title": finding_id.replace("_", " "),
                    "affected_assets": ["billstack-api/app/routers/purchases.py"],
                }
            ),
            encoding="utf-8",
        )
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "baseline.yaml").write_text(
        yaml.safe_dump(
            {
                "evidence_id": "sec.evidence.bill_stack.baseline",
                "branch_head": {
                    "target_branch": "master",
                    "target_head": "e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
                },
                "before_status": "\n".join(
                    [
                        "## master...origin/master",
                        "?? billstack-api/migrate_direct.py",
                        "?? billstack-web/dev-dist/",
                    ]
                ),
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        [
            "generate-security-mutation-handoff",
            "--planning-report",
            str(planning_report),
            "--security-report",
            str(security_report),
            "--release-gate",
            str(release_gate),
            "--findings-dir",
            str(findings_dir),
            "--evidence-dir",
            str(evidence_dir),
            "--to-file",
            str(audit_path),
            "--output-report-path",
            str(fake_home / ".dream-studio" / "meta" / "audit" / "phase18s13-report.md"),
            "--included-finding-id",
            "revenuecat_webhook_unsigned",
            "--included-finding-id",
            "household_invite_code_exposure",
            "--included-finding-id",
            "server_password_policy_gap",
            "--expected-untracked-entry",
            "billstack-api/migrate_direct.py",
            "--expected-untracked-entry",
            "billstack-web/dev-dist/",
            *[
                item
                for finding_id in finding_ids
                for item in ("--expected-finding-id", f"sec.finding.bill_stack.{finding_id}")
            ],
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert result.returncode == 0, result.stderr
    assert "security_mutation_handoff_generated:" in result.stdout
    assert "security_mutation_handoff_evals: pass" in result.stdout
    generated = audit_path.read_text(encoding="utf-8")
    assert "## Handoff Type\napproved_mutation_execution" in generated
    assert "Do not stage, commit, or push." in generated
    assert "Commit planning must occur in a later separate Work Order" in generated
    assert "Commit only scoped" not in generated
    assert "REMEDIATE_BEFORE_RELEASE" in generated


def test_cli_generate_security_post_remediation_review_handoff(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    audit_path = fake_home / ".dream-studio" / "meta" / "audit" / "phase18s14.md"
    mutation_report = tmp_path / "phase18s13-report.md"
    mutation_report.write_text("# Phase 18S.13\nMUTATION_COMPLETE", encoding="utf-8")
    mutation_evidence = tmp_path / "mutation_validation_evidence.yaml"
    changed_files = [
        "billstack-api/.env.example",
        "billstack-api/app/routers/auth.py",
        "billstack-api/app/routers/household.py",
        "billstack-api/app/routers/purchases.py",
        "billstack-api/app/schemas/schemas.py",
        "billstack-api/tests/test_security_remediation.py",
    ]
    mutation_evidence.write_text(
        yaml.safe_dump(
            {
                "work_order_id": "wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation",
                "target_id": "bill-stack",
                "target_path": "C:\\Users\\Example User\\builds\\family-bill-organizer",
                "target_branch": "master",
                "target_head": "e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
                "release_gate_after": "REMEDIATE_BEFORE_RELEASE",
                "included_findings": [
                    "sec.finding.bill_stack.revenuecat_webhook_unsigned",
                    "sec.finding.bill_stack.household_invite_code_exposure",
                    "sec.finding.bill_stack.server_password_policy_gap",
                ],
                "files_changed": changed_files,
                "focused_validation": [
                    {
                        "command": "python -B -m unittest tests.test_security_remediation -v",
                        "result": "passed",
                    }
                ],
                "preserved_untracked_entries": [
                    "billstack-api/migrate_direct.py",
                    "billstack-web/dev-dist/",
                ],
            }
        ),
        encoding="utf-8",
    )
    paused_work = tmp_path / "paused_work.yaml"
    paused_work.write_text("current_status: completed\n", encoding="utf-8")
    security_report = tmp_path / "review_report.yaml"
    security_report.write_text(
        yaml.safe_dump({"target_id": "bill-stack", "verdict": "PASS WITH RISKS"}),
        encoding="utf-8",
    )
    release_gate = tmp_path / "release_gate.yaml"
    release_gate.write_text(
        yaml.safe_dump({"decision": "REMEDIATE_BEFORE_RELEASE"}),
        encoding="utf-8",
    )
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()
    finding_ids = [
        "revenuecat_webhook_unsigned",
        "household_invite_code_exposure",
        "server_password_policy_gap",
    ]
    for finding_id in finding_ids:
        (findings_dir / f"{finding_id}.yaml").write_text(
            yaml.safe_dump(
                {
                    "finding_id": f"sec.finding.bill_stack.{finding_id}",
                    "title": finding_id.replace("_", " "),
                }
            ),
            encoding="utf-8",
        )

    result = _run(
        [
            "generate-security-post-remediation-review-handoff",
            "--mutation-report",
            str(mutation_report),
            "--mutation-evidence",
            str(mutation_evidence),
            "--paused-work",
            str(paused_work),
            "--security-report",
            str(security_report),
            "--release-gate",
            str(release_gate),
            "--findings-dir",
            str(findings_dir),
            "--to-file",
            str(audit_path),
            "--output-report-path",
            str(fake_home / ".dream-studio" / "meta" / "audit" / "phase18s14-report.md"),
            "--expected-untracked-entry",
            "billstack-api/migrate_direct.py",
            "--expected-untracked-entry",
            "billstack-web/dev-dist/",
            "--expected-validation-term",
            "python -B -m unittest tests.test_security_remediation -v",
            *[
                item
                for changed_file in changed_files
                for item in ("--expected-changed-file", changed_file)
            ],
            *[
                item
                for finding_id in finding_ids
                for item in ("--expected-finding-id", f"sec.finding.bill_stack.{finding_id}")
            ],
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert result.returncode == 0, result.stderr
    assert "security_post_remediation_handoff_generated:" in result.stdout
    assert "security_post_remediation_handoff_evals: pass" in result.stdout
    generated = audit_path.read_text(encoding="utf-8")
    assert "Phase 18S.14 - Bill Stack Post-Remediation Security Review" in generated
    assert "observe-only post-remediation security review" in generated
    assert "REMEDIATE_BEFORE_RELEASE" in generated
    assert "RUN_ADDITIONAL_SECURITY_REVIEW" in generated
    assert "Do not mutate Bill Stack." in generated
    assert "Do not stage, commit, or push." in generated
