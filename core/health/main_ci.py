"""Post-merge CI status for the default branch (WO-MAINRED-VISIBILITY).

The merge rule is satisfied by the 3-platform ``pr-smoke`` matrix, which runs a
focused subset (11 files). The FULL suite runs post-merge, ubuntu-only, in
``full-ci`` — so a merge can be correctly authorized and still break ``main``,
and until now no DS surface reported that. On 2026-08-19 main sat red across
eight merges before an operator noticed; twice more the same day a red was found
only because someone thought to look.

An unwatched signal is an invisible signal — the same class as the enforcement
bypasses this milestone already made visible. This module reads the status; the
doctor / project-state / close surfaces report it.

Read-only and advisory by design: a red ``main`` from anyone's merge must not
block unrelated work. The defect was invisibility, not permissiveness. Never
fabricates a verdict — an unavailable or unauthenticated ``gh`` yields
``status="unknown"`` with the reason.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_WORKFLOW = "Full CI"
_BRANCH = "main"
_TIMEOUT = 25

# ── Read-through cache (WO-MAINCI-CACHE) ────────────────────────────────────────
#
# `ds doctor` and `ds project state` call this on every invocation, and project
# state runs on every resume — so an advisory signal was charging a network round
# trip to commands that are otherwise local. Typical cost ~1s; worst case the full
# _TIMEOUT, which is what an offline or unauthenticated operator pays every single
# time. main's status changes on the order of tens of minutes, so a short TTL costs
# no meaningful freshness.
#
# CACHING IS OPT-IN, and the default is a live read. The first cut defaulted it ON
# and immediately broke ten existing tests — because they call this with no
# db_path, so they read the OPERATOR'S REAL authority DB and were served a row a
# previous real invocation had written. That is not a test-fixture problem: a
# default-on cache silently turns a stateless reader into one that consults shared
# global state, so any caller can be handed an answer produced by an unrelated
# earlier call it knows nothing about. The two high-frequency callers
# (``ds doctor``, ``ds project state``) ask for the cache explicitly; everything
# else — tests, ``close``, any future caller — reads live unless it says otherwise.
#
# ``close`` therefore needs no special casing, but passes 0 explicitly anyway:
# declaring work done must never be told about main by a cache, and stating it at
# the call site keeps that true if the default ever changes.
#
# A cached entry is never presented as live: every return carries ``as_of`` and
# ``age_seconds``, and the operator warning states its age. A verification surface
# that shows stale data as current is the defect class this milestone exists to
# remove — caching it silently would be a regression dressed as an optimisation.
CACHE_MAX_AGE_SECONDS = 300
_CACHE_KEY_PREFIX = "main_ci."


def _cache_key(repo_root: Path | None) -> str:
    """Cache key namespaced by repository.

    The repo is part of the key because this reader is repo-scoped: one shared row
    would serve repo A's CI status for repo B — a wrong answer indistinguishable
    from a right one, which is quality rule 7's class. The digest keeps the key
    stable and bounded; the basename keeps it readable in ``ds_config``.
    """
    if repo_root is None:
        target = "__default__"
    else:
        try:
            target = str(Path(repo_root).resolve())
        except OSError:
            target = str(repo_root)
    digest = hashlib.sha256(target.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{_CACHE_KEY_PREFIX}{Path(target).name or 'root'}.{digest}"


def _read_cache(
    repo_root: Path | None, max_age_seconds: int, db_path: Path | None
) -> dict[str, Any] | None:
    """Return a cached status still inside its TTL, else None.

    Every unusable shape — absent table, missing row, malformed payload,
    unparseable timestamp — is a MISS, never an exception: the cache is an
    optimisation and must not be able to change an answer or raise into a caller.
    A future-dated entry is a miss rather than infinitely fresh, so a clock
    adjustment cannot pin a stale verdict forever. (WO-MAINRED-GH-NONSTR's lesson,
    applied while writing this rather than after main goes red.)
    """
    if max_age_seconds <= 0:
        return None
    try:
        from core.runtime_state import db_read_runtime_state

        entry = db_read_runtime_state(_cache_key(repo_root), db_path=db_path)
    except Exception:
        return None
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    fetched_at = entry.get("fetched_at")
    if not isinstance(status, dict) or not isinstance(fetched_at, str):
        return None
    if "status" not in status or "red" not in status:
        return None  # not a status payload this module produced
    try:
        stamped = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - stamped).total_seconds()
    if age < 0 or age > max_age_seconds:
        return None
    cached = dict(status)
    cached["as_of"] = fetched_at
    cached["age_seconds"] = int(age)
    return cached


def _write_cache(status: dict[str, Any], repo_root: Path | None, db_path: Path | None) -> None:
    """Store a status with its fetch time. Best-effort and silent on failure — the
    caller already holds the fresh answer, so a cache write must never turn a good
    read into a failed one.

    ``unknown`` results are cached too, deliberately: an unreachable ``gh`` is the
    most expensive case (a full timeout) and the one repeated invocations most need
    to stop paying for.
    """
    try:
        from core.runtime_state import db_write_runtime_state

        db_write_runtime_state(
            _cache_key(repo_root),
            {"status": status, "fetched_at": datetime.now(UTC).isoformat()},
            db_path=db_path,
        )
    except Exception:
        pass


def clear_main_ci_cache(*, repo_root: Path | None = None, db_path: Path | None = None) -> bool:
    """Drop a repo's cached status — after a merge, or when an operator wants the
    next read to be live."""
    try:
        from core.runtime_state import db_clear_runtime_state

        return db_clear_runtime_state(_cache_key(repo_root), db_path=db_path)
    except Exception:
        return False


def _gh_json(args: list[str], cwd: Path | None) -> tuple[Any, str | None]:
    """Run a ``gh`` command expecting JSON. Returns ``(parsed, error)``."""
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "gh CLI not installed"
    except subprocess.TimeoutExpired:
        return None, f"gh timed out after {_TIMEOUT}s"
    except OSError as exc:
        return None, f"gh could not run: {exc}"

    # WO-MAINRED-GH-NONSTR: everything below reads two attributes off whatever
    # `subprocess.run` returned, and this reader's documented contract is that any
    # unusable reply becomes unknown-with-reason — never an exception, because it
    # is an ADVISORY check that must not be able to raise into a caller who was
    # asking about something else. A caller that patches subprocess.run (a
    # legitimate thing for a test about a DIFFERENT subprocess call to do) hands
    # back a mock whose .stdout is a truthy non-string, and `stdout or "[]"` fed
    # it straight to json.loads, which raises TypeError — not a subclass of
    # JSONDecodeError or ValueError, so the guard below never saw it. That took
    # main red for a full day. Normalise to text first, then parse.
    def _text(value: Any) -> str:
        return value if isinstance(value, str) else ""

    if not isinstance(result.returncode, int):
        return None, "gh returned no usable exit status"
    if result.returncode != 0:
        detail = (_text(result.stderr) or _text(result.stdout)).strip().splitlines()
        reason = detail[0][:200] if detail else f"gh exited {result.returncode}"
        return None, reason
    raw = _text(result.stdout)
    if not raw.strip():
        # No text at all is a real answer ("no runs yet"), not a parse failure —
        # but it must not be confused with output we simply could not read.
        if result.stdout is not None and not isinstance(result.stdout, str):
            return None, "gh returned non-text output"
        return [], None
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return None, f"gh returned non-JSON: {exc}"


def _local_head_includes(
    run_sha: str | None, repo_root: Path | None
) -> tuple[bool | None, str | None]:
    """Does the local HEAD contain ``run_sha``? Returns ``(answer, reason)``.

    Gap WO ebbd529c. "main is RED" is not actionable on its own: an operator needs
    to know whether the failing run includes their own merge or predates it, which
    is exactly the distinction the close-ceremony advisory ("its own merge has main
    red") leans on. Answered with ``merge-base --is-ancestor``, so a HEAD that is
    the run's commit or any descendant of it counts as including it.

    ``None`` with a reason for every case we cannot answer — no git, not a repo,
    unknown sha, a shallow clone that lacks the object. Same posture as the rest of
    this module: never guess, and never let an advisory read raise into a caller.
    """
    if not run_sha:
        return None, "run sha unknown"
    try:
        probe = subprocess.run(
            ["git", "merge-base", "--is-ancestor", run_sha, "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except FileNotFoundError:
        return None, "git not installed"
    except subprocess.TimeoutExpired:
        return None, "git merge-base timed out"
    except OSError as exc:
        return None, f"git could not run: {exc}"
    code = probe.returncode if isinstance(probe.returncode, int) else None
    if code == 0:
        return True, None
    if code == 1:
        return False, None
    # Any other exit is git declining to answer (unknown object in a shallow
    # clone, not a repository, bad sha) — not evidence either way.
    detail = (probe.stderr if isinstance(probe.stderr, str) else "").strip().splitlines()
    return None, (detail[0][:160] if detail else f"git merge-base exited {code}")


def main_ci_status(
    *,
    repo_root: Path | None = None,
    limit: int = 5,
    max_age_seconds: int = 0,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Latest ``full-ci`` conclusion for ``main``.

    Returns::

        {"status": "success" | "failure" | "running" | "unknown",
         "conclusion": str | None,       # raw gh conclusion when finished
         "head_sha": str | None,
         "run_url": str | None,
         "title": str | None,
         "red": bool,                    # True only on a definite failure
         "reason": str | None,           # why status is unknown
         "as_of": str,                   # ISO time the status was READ from gh
         "age_seconds": int,             # 0 when live, >0 when served from cache
         "local_head_includes_run": bool | None,   # is the run's commit in local HEAD?
         "local_head_reason": str | None}          # why that is None

    ``red`` is deliberately False when the status is unknown: an unreadable
    signal is reported as unreadable, never as a failure (nor as a pass).

    Caching is OPT-IN: ``max_age_seconds`` defaults to 0, meaning a live read and
    no cache write-back. Pass ``CACHE_MAX_AGE_SECONDS`` to accept a recent cached
    answer — ``ds doctor`` and ``ds project state`` do, because they run
    constantly; ``close`` does not, because declaring work done must not be told
    about main by a cache. Any cached return carries a non-zero ``age_seconds`` so
    no caller can mistake it for live.
    """
    cached = _read_cache(repo_root, max_age_seconds, db_path)
    if cached is not None:
        return cached

    runs, error = _gh_json(
        [
            "run",
            "list",
            "--branch",
            _BRANCH,
            "--workflow",
            _WORKFLOW,
            "--limit",
            str(limit),
            "--json",
            "conclusion,status,headSha,url,displayTitle",
        ],
        repo_root,
    )

    # One exit path so every result — including the unknowns — is stamped and
    # cached identically. Three separate returns each doing it themselves is how a
    # branch ends up as the only one that forgets.
    def _finish(payload: dict[str, Any]) -> dict[str, Any]:
        payload["as_of"] = datetime.now(UTC).isoformat()
        payload["age_seconds"] = 0
        # Gap WO ebbd529c: only worth asking when there IS a run to locate, and
        # only worth the subprocess when the answer changes what an operator does —
        # i.e. when main is red. A green or unknown main needs no "was it mine".
        if payload.get("red") and payload.get("head_sha"):
            includes, why = _local_head_includes(payload.get("head_sha"), repo_root)
        else:
            includes, why = None, None if not payload.get("head_sha") else "not applicable"
        payload["local_head_includes_run"] = includes
        payload["local_head_reason"] = why
        if max_age_seconds > 0:
            _write_cache(payload, repo_root, db_path)
        return payload

    if error is not None:
        return _finish(
            {
                "status": "unknown",
                "conclusion": None,
                "head_sha": None,
                "run_url": None,
                "title": None,
                "red": False,
                "reason": error,
            }
        )
    if not runs:
        return _finish(
            {
                "status": "unknown",
                "conclusion": None,
                "head_sha": None,
                "run_url": None,
                "title": None,
                "red": False,
                "reason": f"no {_WORKFLOW} runs found for {_BRANCH}",
            }
        )

    # Gap WO 094f3c12 (malformed_input, named by the falsification analyst and
    # confirmed by test): valid JSON is not the same as the shape we asked for. gh
    # can exit 0 with an API error object (`{"message": "Not Found"}`), and a caller
    # that blanket-patches subprocess.run can hand back another command's JSON
    # entirely — the exact trigger of WO-MAINRED-GH-NONSTR. `runs[0]` then raises
    # KeyError on a dict, TypeError on a scalar, and `latest.get` raises
    # AttributeError on a string or int. Parsing succeeded, so the guard in
    # _gh_json never saw any of it.
    latest = runs[0] if isinstance(runs, list) else None
    if not isinstance(latest, dict):
        return _finish(
            {
                "status": "unknown",
                "conclusion": None,
                "head_sha": None,
                "run_url": None,
                "title": None,
                "red": False,
                "reason": (
                    f"gh returned JSON that is not a list of {_WORKFLOW} runs "
                    f"({type(runs).__name__})"
                ),
            }
        )
    raw_status = (latest.get("status") or "").lower()
    conclusion = (latest.get("conclusion") or "").lower() or None
    if raw_status in ("queued", "in_progress", "waiting", "pending", "requested"):
        status = "running"
    elif conclusion == "success":
        status = "success"
    elif conclusion in ("failure", "timed_out", "startup_failure"):
        status = "failure"
    elif conclusion in ("cancelled", "skipped", "neutral", "stale", "action_required"):
        # Not a pass and not a defect — say so rather than guessing either way.
        status = "unknown"
    else:
        status = "unknown"

    return _finish(
        {
            "status": status,
            "conclusion": conclusion,
            "head_sha": latest.get("headSha"),
            "run_url": latest.get("url"),
            "title": latest.get("displayTitle"),
            "red": status == "failure",
            "reason": None if status in ("success", "failure", "running") else conclusion,
        }
    )


def _age_phrase(age_seconds: int) -> str:
    """Human phrasing for a cached status's age. Empty for a live read."""
    if age_seconds < 30:
        return ""
    if age_seconds < 120:
        return " (cached, under 2 min old)"
    return f" (cached, {age_seconds // 60} min old)"


def main_ci_warning(status: dict[str, Any] | None) -> str | None:
    """One-line operator-facing warning for a red ``main``, else None.

    Only a DEFINITE failure warns: 'running' and 'unknown' are not defects, and
    crying wolf on them would train operators to ignore the line that matters.

    A cached status says so, with its age. The whole point of this surface is that
    an operator can trust what it says about main; presenting a four-minute-old red
    as current would trade the latency win for a smaller version of the problem the
    surface exists to solve. A red that has since been fixed is exactly the case
    that must be distinguishable.

    It also says whether the failing run is IN the local HEAD (gap WO ebbd529c).
    "main is RED" prompts different action depending on whether the operator's own
    merge is in that run or predates it, and an advisory that cannot tell them
    which just adds noise to a close they were right to make. Unknown says
    unknown — the relationship is never guessed from the sha alone.
    """
    if not status or not status.get("red"):
        return None
    sha = (status.get("head_sha") or "")[:8]
    title = (status.get("title") or "").strip()
    url = status.get("run_url") or ""
    try:
        age = int(status.get("age_seconds") or 0)
    except (TypeError, ValueError):
        age = 0
    includes = status.get("local_head_includes_run")
    if includes is True:
        whose = " That run INCLUDES your local HEAD — your own work is in it."
    elif includes is False:
        whose = " That run PREDATES your local HEAD — it is not your change."
    else:
        reason = status.get("local_head_reason")
        whose = (
            f" Whether it includes your HEAD is unknown ({reason})."
            if isinstance(reason, str) and reason and reason != "not applicable"
            else ""
        )
    return (
        f"main is RED: the latest {_WORKFLOW} run failed at {sha}"
        f"{f' ({title[:70]})' if title else ''}.{_age_phrase(age)}{whose}"
        f"{f' See {url}' if url else ''}"
        " pr-smoke green is merge authorization, not proof main is green."
    )
