"""WO 653187b6: the domain skills' external tech facts match what upstream actually says.

These skills assert vendor versions, feature graduation and store policies as settled fact.
Nothing re-checked them, so they decayed silently while the skill kept advising with full
confidence -- a five-domain audit on 2026-09-17 found errors in every skill it checked,
including an ``actions/checkout`` SHA that does not exist upstream sitting inside the pattern
that teaches SHA-pinning as a supply-chain control.

What these tests pin is deliberately narrow: the specific wrong claims that were corrected,
so a revert or a careless re-edit fails loudly. They are NOT a freshness gate -- no offline
test can know that Google moved the target-API deadline again. That question is open
(see the "Skill Content Accuracy" milestone); this file only guarantees the corrections stay
corrected, and that canonical and the shipped projection never disagree about them.

Everything here is offline by construction. The upstream-resolution check that produced the
verified SHAs needs the network and belongs in the audit, not in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "canonical" / "skills" / "domains"
# data-engineering split out of domains into its own data pack, 2026-09-24 (pack-split).
CANONICAL_DATA = REPO_ROOT / "canonical" / "skills" / "data"
DIST_DATA = REPO_ROOT / "dist" / "plugin" / "skills" / "ds-data"
# devops, kubernetes, terraform split out of domains into their own infra pack, 2026-09-24
# (pack-split).
CANONICAL_INFRA = REPO_ROOT / "canonical" / "skills" / "infra"
DIST_INFRA = REPO_ROOT / "dist" / "plugin" / "skills" / "ds-infra"
# saas-build, mobile, game-dev, mcp-build split out of domains into their own apps pack,
# 2026-09-24 (pack-split).
CANONICAL_APPS = REPO_ROOT / "canonical" / "skills" / "apps"
DIST_APPS = REPO_ROOT / "dist" / "plugin" / "skills" / "ds-apps"

# The fabricated pin. It shares its first 32 hex characters with the real v4.1.6 commit
# (a5ac7e51b41094c92402da3b24376905380afc29) and differs only in the last 8, which is why
# it read as plausible and nobody resolved it.
_FABRICATED_CHECKOUT_SHA = "a5ac7e51b41094c92402da3b24376905139b7f7d"

_SHA_PIN_RE = re.compile(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})")

# Resolved with `git ls-remote` on 2026-09-17. Recorded rather than re-fetched so CI stays
# offline and deterministic; refresh alongside the pins when these actions are next bumped.
_VERIFIED_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
    "aws-actions/configure-aws-credentials": "e1253824e5c10ff9df46874f81ed3ec929e19cfd",
}


def test_no_action_is_pinned_to_the_fabricated_sha() -> None:
    """The originating symptom: a pin that resolves to nothing, in the SHA-pinning example."""
    hits = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in list(CANONICAL.rglob("*.yml")) + list(CANONICAL.rglob("*.md"))
        if _FABRICATED_CHECKOUT_SHA in p.read_text(encoding="utf-8")
    ]
    assert hits == [], (
        f"{_FABRICATED_CHECKOUT_SHA} does not exist in actions/checkout upstream. "
        f"A workflow copying it fails at 'Set up job'. Found in: {hits}"
    )


def test_every_pinned_action_sha_is_one_that_was_resolved_upstream() -> None:
    """Any 40-hex pin must be a SHA someone actually resolved, not a plausible-looking value.

    This is the guard the fabricated SHA slipped past: the pin LOOKED like a real commit.
    Adding a new pin means adding it to _VERIFIED_PINS, which means resolving it first.
    """
    unverified: list[str] = []
    for path in CANONICAL.rglob("*.yml"):
        for repo, sha in _SHA_PIN_RE.findall(path.read_text(encoding="utf-8")):
            if _VERIFIED_PINS.get(repo) != sha:
                unverified.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {repo}@{sha}")
    assert unverified == [], (
        "Pinned SHAs that were never resolved against upstream:\n  "
        + "\n  ".join(unverified)
        + "\nResolve with `git ls-remote <repo> <tag>` and record it in _VERIFIED_PINS."
    )


def test_mobile_states_the_current_store_submission_requirements() -> None:
    """Play target API and Apple's SDK minimum were both rejection-causing as written."""
    text = (CANONICAL_APPS / "modes" / "mobile" / "SKILL.md").read_text(encoding="utf-8")
    assert "Target API 34 required" not in text, (
        "Play has required API 36 for new apps and updates since 2026-08-31; "
        "API 34 guidance gets a submission rejected."
    )
    assert "API 36 (Android 16) since 2026-08-31" in text
    assert (
        "Xcode 26 / iOS 26 SDK" in text
    ), "App Store Connect has required the iOS 26 SDK since 2026-04-28."
    assert "Xcode 15+ required for iOS 17 SDK" not in text


def test_kubernetes_states_one_correct_ga_version_per_feature() -> None:
    """Sidecars went alpha 1.28 / beta 1.29 / GA 1.33, and the file contradicted itself on HPA."""
    text = (CANONICAL_INFRA / "modes" / "kubernetes" / "SKILL.md").read_text(encoding="utf-8")
    assert (
        "feature stable in 1.29" not in text
    ), "Native sidecars reached GA in 1.33, not 1.29 (1.29 was beta)."
    assert "GA in 1.33" in text
    # The old text claimed autoscaling/v2 went GA in 1.27 on one line and 1.23 on another.
    assert "HPA v2 is GA" not in text, "The 1.27 GA claim contradicted the correct 1.23 line."


def test_terraform_attributes_the_s3_split_to_the_provider_version_that_shipped_it() -> None:
    """The split was v4.0.0 (Feb 2022); v5.0 only removed the fallbacks v4.9 had restored.

    Asserted across the whole terraform skill because the claim lived in three places and a
    fix to SKILL.md alone would leave gotchas.yml as a stale contradicting copy.
    """
    stale = []
    for path in (CANONICAL_INFRA / "modes" / "terraform").rglob("*"):
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        if "v4->v5" in body or "AWS provider v5 (2023)" in body:
            stale.append(path.relative_to(REPO_ROOT).as_posix())
    assert stale == [], f"S3 split still attributed to v5 in: {stale}"
    assert "AWS provider v4.0 (Feb 2022)" in (
        CANONICAL_INFRA / "modes" / "terraform" / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_terraform_teaches_native_s3_locking_not_dynamodb() -> None:
    """use_lockfile went GA in 1.11, which deprecated the DynamoDB arguments."""
    body = (CANONICAL_INFRA / "infra" / "terraform.yml").read_text(encoding="utf-8")
    example_start = body.index("id: remote-state-with-locking")
    example_end = body.index("- id:", example_start + 10)
    example = body[example_start:example_end]
    assert "use_lockfile = true" in example
    assert (
        "dynamodb_table =" not in example
    ), "The headline backend example should not add a DynamoDB lock table to a new backend."


def test_data_engineering_snippets_use_apis_that_still_exist() -> None:
    """Each of these fails outright when pasted: removed param, wrong param, invented function."""
    dag = (CANONICAL_DATA / "data" / "pipelines.yml").read_text(encoding="utf-8")
    assert "schedule_interval=" not in dag, "Removed in Airflow 3.0; the DAG does not parse."

    skill = (CANONICAL_DATA / "modes" / "data-engineering" / "SKILL.md").read_text(encoding="utf-8")
    assert (
        "daterange_start =>" not in skill
    ), "Snowflake QUERY_HISTORY takes END_TIME_RANGE_START; daterange_start is not a parameter."
    assert "END_TIME_RANGE_START" in skill
    assert (
        "`config(version=2)`" not in skill
    ), "dbt model versioning is YAML-only; there is no config(version=...) function."


def test_devops_does_not_assert_an_artifact_size_limit_that_does_not_exist() -> None:
    """'500MB public / 2GB private per run' was never a thing -- those are monthly plan quotas."""
    for rel in ("modes/devops/SKILL.md", "modes/devops/gotchas.yml", "infra/devops.yml"):
        body = (CANONICAL_INFRA / rel).read_text(encoding="utf-8")
        assert "500MB public" not in body, f"{rel} states a per-run limit that does not exist"
        assert (
            "silently truncates" not in body
        ), f"{rel} asserts an upload-truncation failure mode no GitHub source documents"


@pytest.mark.parametrize(
    "rel",
    [
        "modes/mobile/SKILL.md",
        "modes/mobile/gotchas.yml",
        "mobile/patterns.yml",
    ],
)
def test_the_shipped_apps_pack_projection_carries_the_same_corrected_text(rel: str) -> None:
    """Same as the other packs' projection-parity tests, for the apps pack (saas-build,
    mobile, game-dev, mcp-build split out of domains, 2026-09-24 -- pack-split)."""
    canonical_body = (CANONICAL_APPS / rel).read_text(encoding="utf-8")
    dist_path = DIST_APPS / rel
    assert dist_path.exists(), f"dist/plugin is missing {rel} -- rebuild it from canonical"
    dist_body = dist_path.read_text(encoding="utf-8")
    assert canonical_body == dist_body or canonical_body in dist_body, (
        f"dist/plugin copy of {rel} has drifted from canonical -- "
        "rebuild with integrations.marketplace.plugin_dist.build_plugin_dist"
    )


@pytest.mark.parametrize(
    "rel",
    [
        "modes/data-engineering/SKILL.md",
        "data/pipelines.yml",
    ],
)
def test_the_shipped_data_pack_projection_carries_the_same_corrected_text(rel: str) -> None:
    """Same as test_the_shipped_projection_carries_the_same_corrected_text, for the data
    pack (data-engineering split out of domains, 2026-09-24 -- pack-split)."""
    canonical_body = (CANONICAL_DATA / rel).read_text(encoding="utf-8")
    dist_path = DIST_DATA / rel
    assert dist_path.exists(), f"dist/plugin is missing {rel} -- rebuild it from canonical"
    dist_body = dist_path.read_text(encoding="utf-8")
    assert canonical_body == dist_body or canonical_body in dist_body, (
        f"dist/plugin copy of {rel} has drifted from canonical -- "
        "rebuild with integrations.marketplace.plugin_dist.build_plugin_dist"
    )


@pytest.mark.parametrize(
    "rel",
    [
        "modes/kubernetes/SKILL.md",
        "infra/kubernetes.yml",
        "modes/terraform/SKILL.md",
        "modes/terraform/gotchas.yml",
        "infra/terraform.yml",
        "modes/devops/SKILL.md",
        "modes/devops/gotchas.yml",
        "infra/devops.yml",
        "devops/REFERENCES.md",
    ],
)
def test_the_shipped_infra_pack_projection_carries_the_same_corrected_text(rel: str) -> None:
    """Same as test_the_shipped_projection_carries_the_same_corrected_text, for the infra
    pack (devops/kubernetes/terraform split out of domains, 2026-09-24 -- pack-split)."""
    canonical_body = (CANONICAL_INFRA / rel).read_text(encoding="utf-8")
    dist_path = DIST_INFRA / rel
    assert dist_path.exists(), f"dist/plugin is missing {rel} -- rebuild it from canonical"
    dist_body = dist_path.read_text(encoding="utf-8")
    assert canonical_body == dist_body or canonical_body in dist_body, (
        f"dist/plugin copy of {rel} has drifted from canonical -- "
        "rebuild with integrations.marketplace.plugin_dist.build_plugin_dist"
    )
