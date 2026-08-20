"""WO-MAINCI-CACHE: main's CI status is cached briefly, and never looks live.

`ds doctor` and `ds project state` read main's post-merge status on every
invocation, and project state runs on every resume — so an advisory signal was
charging a network round trip (typical ~1s, worst case the full 25s timeout, paid
on EVERY call when gh is unreachable) to commands that are otherwise local.

The cache is the easy half. The half that matters is that a cached answer stays
distinguishable from a live one, and that no malformed cache entry can change an
answer or raise into a caller — the exact failure WO-MAINRED-GH-NONSTR turned
main red with, applied here while writing the code instead of afterwards.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.health.main_ci import (
    CACHE_MAX_AGE_SECONDS,
    _cache_key,
    clear_main_ci_cache,
    main_ci_status,
    main_ci_warning,
)

_RED_RUN = {
    "conclusion": "failure",
    "status": "completed",
    "headSha": "4d7fa6e8beef",
    "url": "https://github.com/x/y/actions/runs/1",
    "displayTitle": "fix(health): non-text gh output",
}
_GREEN_RUN = {**_RED_RUN, "conclusion": "success", "headSha": "0000green00"}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _gh(runs: list[dict]) -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps(runs)
    proc.stderr = ""
    return proc


def _seed(db: Path, repo: Path, payload: dict, *, age_seconds: float) -> None:
    """Write a cache row directly, aged by ``age_seconds`` (negative = future)."""
    stamped = (datetime.now(UTC) - timedelta(seconds=age_seconds)).isoformat()
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO ds_config (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (
            f"runtime.{_cache_key(repo)}",
            json.dumps({"status": payload, "fetched_at": stamped}),
            stamped,
        ),
    )
    conn.commit()
    conn.close()


# ── Caching is opt-in ──────────────────────────────────────────────────────────


def test_caching_is_opt_in_so_a_bare_call_never_consults_shared_state(db, tmp_path):
    """The first cut of this feature defaulted the cache ON and broke ten existing
    tests — because they call main_ci_status with no db_path, so they read the
    OPERATOR'S REAL authority DB and were served a row an earlier real invocation
    had written.

    That was not a fixture problem. A default-on cache turns a stateless reader
    into one that silently consults shared global state, so any caller can be
    handed an answer produced by an unrelated earlier call it knows nothing about.
    This test pins the default so it cannot drift back.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # Prime a cache row that a default call must NOT see.
    _seed(db, repo, {"status": "failure", "red": True, "head_sha": "cached01"}, age_seconds=1)

    with patch("subprocess.run", return_value=_gh([_GREEN_RUN])) as run:
        status = main_ci_status(repo_root=repo, db_path=db)  # no max_age_seconds
    assert run.call_count == 1, "the default must read live, not from the cache"
    assert status["status"] == "success"
    assert status["age_seconds"] == 0

    # A live-by-default read must also not write back, or it would seed a cache
    # for a caller that never asked for one.
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT value FROM ds_config WHERE key = ?", (f"runtime.{_cache_key(repo)}",)
    ).fetchone()
    conn.close()
    assert row is not None, "the primed row should still be there"
    assert "cached01" in row[0], "a live read must not overwrite the cache it ignored"


# ── The cache does its job ──────────────────────────────────────────────────────


def test_second_call_is_served_from_cache_without_a_subprocess(db, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with patch("subprocess.run", return_value=_gh([_RED_RUN])) as run:
        first = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert first["status"] == "failure"
    assert first["age_seconds"] == 0, "a live read is age 0"
    # Count gh calls specifically: a RED status also probes git for the local-HEAD
    # relationship (gap WO ebbd529c), so a bare call_count would pin an unrelated
    # implementation detail and break the next time a probe is added.
    gh_calls = [c for c in run.call_args_list if c.args and c.args[0] and c.args[0][0] == "gh"]
    assert len(gh_calls) == 1

    # Second call: no subprocess at all. A patch that would EXPLODE if called
    # proves the network was not touched, rather than merely counting calls.
    with patch("subprocess.run", side_effect=AssertionError("gh must not be invoked")):
        second = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert second["status"] == "failure"
    assert second["head_sha"] == first["head_sha"]


def test_expired_entry_triggers_a_live_read(db, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed(db, repo, {"status": "failure", "red": True, "head_sha": "stale123"}, age_seconds=9999)
    with patch("subprocess.run", return_value=_gh([_GREEN_RUN])):
        fresh = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=300)
    assert fresh["status"] == "success", "an expired entry must not shadow the live answer"
    assert fresh["age_seconds"] == 0


def test_unknown_results_are_cached_too(db, tmp_path):
    """Deliberate: an unreachable gh is the MOST expensive case (a full timeout)
    and the one repeated invocations most need to stop paying for."""
    repo = tmp_path / "repo"
    repo.mkdir()
    with patch("subprocess.run", side_effect=FileNotFoundError("gh")):
        first = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert first["status"] == "unknown" and first["reason"]

    with patch("subprocess.run", side_effect=AssertionError("gh must not be invoked")):
        second = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert second["status"] == "unknown"
    assert second["reason"] == first["reason"]


# ── A cached answer never looks live ───────────────────────────────────────────


def test_cached_result_reports_its_age(db, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed(
        db,
        repo,
        {"status": "failure", "red": True, "head_sha": "abc12345", "title": "t", "run_url": "u"},
        age_seconds=240,
    )
    with patch("subprocess.run", side_effect=AssertionError("gh must not be invoked")):
        status = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert 235 <= status["age_seconds"] <= 245
    assert status["as_of"], "a cached status must say when it was actually read"


def test_warning_states_the_age_when_served_from_cache(db, tmp_path):
    """A four-minute-old red presented as current would trade the latency win for
    a smaller version of the problem this surface exists to solve."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed(
        db,
        repo,
        {"status": "failure", "red": True, "head_sha": "abc12345", "title": "t", "run_url": "u"},
        age_seconds=240,
    )
    with patch("subprocess.run", side_effect=AssertionError("gh must not be invoked")):
        status = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    warning = main_ci_warning(status)
    assert warning and "main is RED" in warning
    assert "cached" in warning and "4 min old" in warning

    # A live read says nothing about caching — no noise on the common path.
    with patch("subprocess.run", return_value=_gh([_RED_RUN])):
        live = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=0)
    live_warning = main_ci_warning(live)
    assert live_warning and "cached" not in live_warning


def test_warning_survives_a_malformed_age(db):
    """main_ci_warning is advisory and must not raise on a junk age field."""
    for bad in ("not-a-number", None, [], {}):
        status = {
            "red": True,
            "head_sha": "a" * 12,
            "title": "t",
            "run_url": "u",
            "age_seconds": bad,
        }
        assert "main is RED" in (main_ci_warning(status) or "")


# ── Wrong-answer hazards ───────────────────────────────────────────────────────


def test_a_different_repo_is_a_cache_miss(db, tmp_path):
    """One shared row would serve repo A's CI status for repo B — a wrong answer
    indistinguishable from a right one, which is quality rule 7's class."""
    repo_a, repo_b = tmp_path / "alpha", tmp_path / "beta"
    repo_a.mkdir()
    repo_b.mkdir()
    assert _cache_key(repo_a) != _cache_key(repo_b)

    with patch("subprocess.run", return_value=_gh([_RED_RUN])):
        assert (
            main_ci_status(repo_root=repo_a, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)[
                "status"
            ]
            == "failure"
        )
    # repo_b must go to the network rather than inherit alpha's red.
    with patch("subprocess.run", return_value=_gh([_GREEN_RUN])) as run_b:
        status_b = main_ci_status(
            repo_root=repo_b, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS
        )
    assert run_b.call_count == 1
    assert status_b["status"] == "success"


def test_unusable_cache_entries_are_misses_not_errors(db, tmp_path):
    """Absent row, malformed payload, wrong types, and a non-status dict each fall
    through to a live read. The cache is an optimisation; it must never be able to
    change an answer or raise into a caller."""
    repo = tmp_path / "repo"
    repo.mkdir()
    key = f"runtime.{_cache_key(repo)}"
    junk_values = [
        "not json at all",
        json.dumps("a bare string"),
        json.dumps({"status": "not a dict", "fetched_at": datetime.now(UTC).isoformat()}),
        json.dumps({"status": {"status": "failure", "red": True}}),  # no fetched_at
        json.dumps({"status": {"status": "failure", "red": True}, "fetched_at": 12345}),
        json.dumps(
            {"status": {"unrelated": "payload"}, "fetched_at": datetime.now(UTC).isoformat()}
        ),
        json.dumps({"status": {"status": "f", "red": True}, "fetched_at": "not-a-timestamp"}),
    ]
    for value in junk_values:
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO ds_config (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        conn.close()
        with patch("subprocess.run", return_value=_gh([_GREEN_RUN])) as run:
            status = main_ci_status(
                repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS
            )  # must not raise
        assert status["status"] == "success", value
        assert run.call_count == 1, f"a junk entry must not be served: {value}"


def test_future_dated_entry_is_not_treated_as_fresh(db, tmp_path):
    """A clock adjustment must not pin a stale verdict forever."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed(db, repo, {"status": "failure", "red": True}, age_seconds=-86400)
    with patch("subprocess.run", return_value=_gh([_GREEN_RUN])) as run:
        status = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert run.call_count == 1
    assert status["status"] == "success"


def test_an_unavailable_db_still_returns_a_live_answer(tmp_path):
    """No authority DB (or an unwritable one) degrades to uncached reads, never to
    an error — the same fail-open posture as the rest of this module."""
    repo = tmp_path / "repo"
    repo.mkdir()
    missing = tmp_path / "nope" / "studio.db"
    with patch("subprocess.run", return_value=_gh([_RED_RUN])):
        status = main_ci_status(repo_root=repo, db_path=missing)
    assert status["status"] == "failure"
    assert status["age_seconds"] == 0


def test_clear_cache_forces_the_next_read_live(db, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with patch("subprocess.run", return_value=_gh([_RED_RUN])):
        main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert clear_main_ci_cache(repo_root=repo, db_path=db) is True
    with patch("subprocess.run", return_value=_gh([_GREEN_RUN])) as run:
        status = main_ci_status(repo_root=repo, db_path=db, max_age_seconds=CACHE_MAX_AGE_SECONDS)
    assert run.call_count == 1 and status["status"] == "success"


# ── close reads live ───────────────────────────────────────────────────────────


def test_close_bypasses_the_cache(db, tmp_path):
    """Declaring work done is the one low-frequency, high-consequence moment that
    must not be told about main by a cache. Asserted by driving the real close and
    inspecting the call it makes — not by reading the source for a literal."""
    from core.work_orders.close import close_work_order

    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-19T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','cleanup','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    live = {
        "status": "failure",
        "red": True,
        "head_sha": "abc12345",
        "run_url": "u",
        "title": "t",
        "as_of": now,
        "age_seconds": 0,
    }
    with patch("core.health.main_ci.main_ci_status", return_value=live) as reader:
        close_work_order(
            work_order_id=wo_id,
            force=True,  # gates are not under test here; the read freshness is
            source_root=tmp_path,
            dream_studio_home=tmp_path,
        )

    assert reader.call_count >= 1, "close must consult main's CI status"
    assert reader.call_args.kwargs.get("max_age_seconds") == 0, (
        "close must read LIVE — a cached answer is acceptable for doctor and "
        "project state, never for declaring work done"
    )
