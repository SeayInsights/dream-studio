"""The materialized workflow-pattern queries answer exactly what the old ones did.

The old session CTE ran a correlated subquery per session over the canonical_events
UNION view, so each session re-read and re-JSON-parsed every boundary event: quadratic
in sessions, about 24 million json_extract calls on the operator's 3,365 sessions, and
still running after 10 minutes on a 102,000-event seed. The new form parses each event
once. A rewrite of a query is only a fix if it returns the same rows, so the previous
module is kept verbatim in tests/unit/fixtures/workflow_patterns_legacy.py as the
oracle and both are run over the same randomized data.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sqlite3
from pathlib import Path

import pytest

from projections.core.analyzers import workflow_patterns as new_mod

_LEGACY = Path(__file__).parent / "fixtures" / "workflow_patterns_legacy.py"


def _load_legacy():
    spec = importlib.util.spec_from_file_location("workflow_patterns_legacy", _LEGACY)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


legacy_mod = _load_legacy()

_PROJECTS = ["p1", "p2", "p3", None]  # None: no project_id key in the trace at all
_SKILLS = ["s1", "s2", "s3", "s4", "s5", None]  # None: no skill_specifier key


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # created_at is nullable here on purpose: a session with no timestamp is a path the
    # old subquery answered (NULL -> open session) and the window version must too.
    conn.execute(
        "CREATE TABLE canonical_events (event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,"
        " trace TEXT, created_at TEXT)"
    )
    return conn


def _stamp(rng: random.Random) -> str | None:
    """A timestamp on a coarse grid, so ties are common, in both separator styles: the
    boundary comparison is raw-string and the joins use datetime(), so they can disagree."""
    if rng.random() < 0.03:
        return None
    minute = rng.randrange(0, 90) * 5
    sep = "T" if rng.random() < 0.7 else " "
    return f"2026-06-01{sep}{minute // 60:02d}:{minute % 60:02d}:00"


def _trace(rng: random.Random, project, **extra) -> str:
    body = dict(extra)
    if project is not None:
        body["project_id"] = project
    return json.dumps(body)


def _seed(conn: sqlite3.Connection, seed: int, sessions: int) -> None:
    rng = random.Random(seed)
    rows = []
    n = 0

    def add(event_type, trace):
        nonlocal n
        n += 1
        rows.append((f"e{n}", event_type, trace, _stamp(rng)))

    for _ in range(sessions):
        project = rng.choice(_PROJECTS)
        add(new_mod.EVENT_SESSION_STARTED, _trace(rng, project))
        if rng.random() < 0.6:
            add(new_mod.EVENT_SESSION_CLOSED, _trace(rng, project))
        for _ in range(rng.randrange(0, 5)):
            skill = rng.choice(_SKILLS)
            extra = {} if skill is None else {"skill_specifier": skill}
            add(new_mod.EVENT_SKILL_INVOKED, _trace(rng, rng.choice(_PROJECTS), **extra))
        if rng.random() < 0.4:
            add(new_mod.EVENT_WO_CLOSED, _trace(rng, project))
    conn.executemany("INSERT INTO canonical_events VALUES (?, ?, ?, ?)", rows)


def _boundaries(conn, mod):
    sql = (
        f"WITH {mod._SESSION_CTE} SELECT session_id, project_id, session_start, session_end"
        " FROM session_boundaries ORDER BY session_id"
    )
    return [tuple(r) for r in conn.execute(sql)]


def _signals(conn, mod, detector, project_id=None):
    analyzer = mod.WorkflowPatternAnalyzer(conn)
    found = getattr(analyzer, detector)(project_id, 1, 0.0)
    return sorted(found, key=lambda s: s["pattern_id"])


@pytest.mark.parametrize("seed", range(25))
def test_session_boundaries_are_identical(seed):
    conn = _conn()
    _seed(conn, seed, sessions=40)
    assert _boundaries(conn, new_mod) == _boundaries(conn, legacy_mod)


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize(
    "detector", ["_detect_always_paired", "_detect_post_completion", "_detect_pre_close"]
)
def test_every_detector_returns_the_same_signals(seed, detector):
    conn = _conn()
    _seed(conn, seed, sessions=40)
    assert _signals(conn, new_mod, detector) == _signals(conn, legacy_mod, detector)


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("project", ["p1", "p2", "p3"])
def test_the_per_project_form_is_identical(seed, project):
    conn = _conn()
    _seed(conn, seed, sessions=40)
    assert _signals(conn, new_mod, "_detect_always_paired", project) == _signals(
        conn, legacy_mod, "_detect_always_paired", project
    )


def test_the_comparison_is_not_vacuous():
    """Equality of two empty results proves nothing. The seeded data must produce signals
    and boundaries for the equivalence tests above to mean anything."""
    conn = _conn()
    _seed(conn, 0, sessions=40)
    assert len(_boundaries(conn, new_mod)) > 20
    for detector in ("_detect_always_paired", "_detect_post_completion", "_detect_pre_close"):
        total = sum(len(_signals(_seeded(seed), new_mod, detector)) for seed in range(25))
        assert total > 0, f"no seed produced a {detector} signal; the oracle compares nothing"


def _seeded(seed: int) -> sqlite3.Connection:
    conn = _conn()
    _seed(conn, seed, sessions=40)
    return conn


# --- the cost is linear, not quadratic ---------------------------------------------


def _steps(mod, sessions: int) -> int:
    """SQLite VM instructions the three detectors execute: a deterministic stand-in for
    time, which would make a scaling test flaky on a slow runner."""
    conn = _conn()
    rows = []
    for i in range(sessions):
        stamp = f"2026-06-01T{(i // 60) % 24:02d}:{i % 60:02d}:00"
        rows.append((f"s{i}", mod.EVENT_SESSION_STARTED, json.dumps({"project_id": "p"}), stamp))
        rows.append((f"c{i}", mod.EVENT_SESSION_CLOSED, json.dumps({"project_id": "p"}), stamp))
        for k in range(2):
            trace = json.dumps({"project_id": "p", "skill_specifier": f"k{k}"})
            rows.append((f"k{i}-{k}", mod.EVENT_SKILL_INVOKED, trace, stamp))
    conn.executemany("INSERT INTO canonical_events VALUES (?, ?, ?, ?)", rows)
    counter = [0]

    def tick():
        counter[0] += 1
        return 0

    conn.set_progress_handler(tick, 100)
    analyzer = mod.WorkflowPatternAnalyzer(conn)
    for detector in ("_detect_always_paired", "_detect_post_completion", "_detect_pre_close"):
        getattr(analyzer, detector)(None, 1, 0.0)
    return counter[0]


def test_work_does_not_grow_cubically_with_sessions():
    """The old query was CUBIC in sessions: every doubling cost 8x (26 s at 400 sessions,
    roughly four hours at the operator's 3,365). The new one is quadratic, because the
    skill events are still range-joined to sessions with no index to seek on. Quadrupling
    the sessions costs ~16x when quadratic and ~64x when cubic; 24 separates them."""
    small, large = _steps(new_mod, 50), _steps(new_mod, 200)
    assert large / small < 24, f"work grew {large / small:.1f}x for 4x the sessions"


def test_the_guard_discriminates():
    """The same measurement on the old module must trip it, or this guard would pass for
    any implementation, including the one being replaced."""
    small, large = _steps(legacy_mod, 50), _steps(legacy_mod, 200)
    assert large / small > 24, f"old module grew only {large / small:.1f}x; the guard is blind"


def test_the_rewrite_is_orders_of_magnitude_cheaper_at_a_realistic_size():
    new, old = _steps(new_mod, 200), _steps(legacy_mod, 200)
    assert old / new > 30, f"only {old / new:.1f}x cheaper than the old query"
