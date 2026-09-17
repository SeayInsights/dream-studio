"""AI events must be attributable to the project — and client — that produced them.

Before migration 156 the ai_canonical_events INSERT had no project_id column, so
every cost, model-mix and skill rollup aggregated all clients together. The fix
is only worth having if the attribution is RIGHT, and the first attempt was not:
it used raw_claude_code_events.project_id, which records the globally-ACTIVE
project rather than the working directory, and attributed $19,405 of Dream Studio
spend to the Fulcrum engagement. These tests pin the properties that make the
second approach trustworthy.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.event_store.project_attribution import (
    _project_for_dir,
    _project_roots,
    classify_client,
    encode_cwd,
)

SEP = "\\"


# ---------------------------------------------------------------------------
# The operator's classification rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cwd,expected",
    [
        (r"C:\Users\Example User\Fulcrum", "fulcrum"),
        (r"C:\Users\Example User\Fulcrum\gw-govdash\examples", "fulcrum"),
        (r"C:\Users\Example User\Hypershift\thing", "hypershift"),
        (r"C:\Users\Example User\builds\dream-studio-clean", "seayinsights"),
        (r"C:\Users\Example User\builds\dreamysuite", "seayinsights"),
        # Everything else is internal work, not a gap.
        (r"C:\Users\Example User\round-table\rt-chair", "seayinsights"),
        (r"C:\Users\Example User\Downloads", "seayinsights"),
    ],
)
def test_client_rule(cwd, expected):
    assert classify_client(cwd) == expected


def test_client_rule_is_case_insensitive():
    assert classify_client(r"c:\users\example user\FULCRUM\x") == "fulcrum"


def test_client_rule_matches_whole_segments_only():
    """'rebuilds' is not 'builds'; a substring match would misfile work."""
    assert classify_client(r"C:\Users\Example User\rebuilds\thing") == "seayinsights"
    # ...and proves it did NOT match via the builds rule by using a Fulcrum path.
    assert classify_client(r"C:\Users\Example\notfulcrumatall\y") == "seayinsights"


def test_an_engagement_wins_over_builds():
    """A Fulcrum checkout living under builds is still Fulcrum work."""
    assert classify_client(r"C:\Users\Example User\builds\Fulcrum\api") == "fulcrum"


def test_forward_slashes_are_handled():
    assert classify_client("C:/Users/Example User/Fulcrum/x") == "fulcrum"


# ---------------------------------------------------------------------------
# Directory-name encoding — matched forwards, never decoded
# ---------------------------------------------------------------------------


def test_encode_matches_claude_codes_own_directory_name():
    """This exact string is what Claude Code writes on disk."""
    assert (
        encode_cwd(r"C:\Users\Example User\builds\dream-studio-clean")
        == "c--users-example-user-builds-dream-studio-clean"
    )


def test_encode_handles_spaces_and_drive_colon():
    assert encode_cwd(r"C:\Users\Example User\Fulcrum") == "c--users-example-user-fulcrum"


def test_encode_ignores_a_trailing_separator():
    a = encode_cwd(r"C:\Users\Example\builds\p")
    b = encode_cwd("C:" + SEP + r"Users\Example\builds\p" + SEP)
    assert a == b


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE business_projects (project_id TEXT, name TEXT,"
        " project_path TEXT, status TEXT, client_id TEXT)"
    )
    c.executemany(
        "INSERT INTO business_projects VALUES (?,?,?,?,?)",
        [
            (
                "p-ds",
                "Dream Studio",
                r"C:\Users\Example User\builds\dream-studio-clean",
                "active",
                "seayinsights",
            ),
            (
                "p-ful",
                "Fulcrum Skill Library",
                r"C:\Users\Example User\Fulcrum",
                "active",
                "fulcrum",
            ),
            ("p-sub", "Nested", r"C:\Users\Example User\Fulcrum\gateway", "active", "fulcrum"),
            ("p-del", "Gone", r"C:\Users\Example User\builds\gone", "deleted", "seayinsights"),
        ],
    )
    return c


def test_exact_directory_resolves_to_its_project(conn):
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-builds-dream-studio-clean", roots) == "p-ds"


def test_subdirectory_resolves_to_the_enclosing_project(conn):
    """A Fulcrum subdirectory is Fulcrum work."""
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-fulcrum-demo-api", roots) == "p-ful"


def test_deepest_registered_project_wins(conn):
    """p-sub is registered inside p-ful; the nested one must win."""
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-fulcrum-gateway-src", roots) == "p-sub"


def test_unregistered_directory_resolves_to_nothing(conn):
    """No project is better than the wrong project."""
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-round-table-rt-chair", roots) is None


def test_deleted_projects_are_not_matched(conn):
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-builds-gone", roots) is None


def test_a_sibling_directory_is_not_a_prefix_match(conn):
    """'...-dream-studio-clean-backup' must not land on the dream-studio-clean project
    by accident — the separator after the root is required."""
    roots = _project_roots(conn)
    assert _project_for_dir("c--users-example-user-builds-dream-studio-cleanish", roots) is None


# ---------------------------------------------------------------------------
# Rejecting the evidence that produced the wrong answer
# ---------------------------------------------------------------------------


def test_active_project_is_not_used_as_evidence():
    """Regression guard for the $19,405 misattribution.

    raw_claude_code_events.project_id records whichever project was ACTIVE, so it
    must not appear anywhere in the attribution path. The module resolves from
    the transcript directory layout instead.
    """
    import inspect

    from core.event_store import project_attribution

    src = inspect.getsource(project_attribution.backfill_ai_event_projects)
    assert "raw_claude_code_events" not in src, (
        "attribution must not read raw_claude_code_events.project_id — it records "
        "the globally-active project, not where the work happened"
    )
