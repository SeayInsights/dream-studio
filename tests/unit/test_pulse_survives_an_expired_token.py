"""The pulse keeps reporting when its long-lived token lapses.

``GITHUB_PERSONAL_ACCESS_TOKEN`` is a long-lived string in the operator's environment, and
when it expires the pulse does not degrade quietly. It printed five ``HTTP Error 401`` lines
on every prompt and reported ``open_prs: 0`` and ``ci_status: unknown`` for an entire session
while **seven** pull requests were open and main was red -- so the surface that exists to say
what needs attention was the last thing to know anything was wrong.

A stale credential is worse than no credential: with none, ``gh_api`` returned ``[]`` quietly;
with a dead one it spent a request per endpoint to arrive at the same ``[]`` plus noise.

``gh`` is already a hard dependency of this project's workflow and refreshes its own token, so
it is the fallback. These drive the resolution and retry directly -- no network.
"""

from __future__ import annotations

import urllib.error

import pytest

from interfaces.cli import pulse_collector


@pytest.fixture(autouse=True)
def _clean_rejections(monkeypatch):
    """Rejections are process-scoped; no test inherits another's."""
    monkeypatch.setattr(pulse_collector, "_REJECTED_TOKENS", set())


def _no_gh_cli() -> str:
    return ""


def _gh_cli_gives(token: str):
    def _resolve() -> str:
        return token

    return _resolve


# --- which credentials get tried -------------------------------------------------


def test_the_env_token_is_preferred(monkeypatch):
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("gh-token"))
    assert pulse_collector._github_tokens() == ["env-token", "gh-token"]


def test_the_gh_cli_token_is_used_when_no_env_token_is_set(monkeypatch):
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("gh-token"))
    assert pulse_collector._github_tokens() == ["gh-token"]


def test_identical_tokens_are_not_tried_twice(monkeypatch):
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "same")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("same"))
    assert pulse_collector._github_tokens() == ["same"]


def test_no_credentials_at_all_is_not_an_error(monkeypatch):
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _no_gh_cli)
    assert pulse_collector._github_tokens() == []
    assert pulse_collector.gh_api("repos/x/y/pulls") == []


# --- what happens when the first credential is dead -------------------------------


def _urlopen_that(rejects: str, payload: bytes):
    """A urlopen stand-in: 401 for one token, the payload for anything else."""

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return payload

    def _open(req, timeout=None):
        if req.headers.get("Authorization") == f"Bearer {rejects}":
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return _Response()

    return _open


def test_an_expired_token_falls_through_to_the_working_one(monkeypatch):
    """The whole point: seven open pull requests must not read as zero."""
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "expired")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("good"))
    monkeypatch.setattr(
        pulse_collector.urllib.request,
        "urlopen",
        _urlopen_that("expired", b'[{"number": 741}, {"number": 742}]'),
    )
    assert pulse_collector.gh_api("repos/x/y/pulls") == [{"number": 741}, {"number": 742}]


def test_a_dead_token_is_retired_after_the_first_rejection(monkeypatch):
    """One dead credential costs one request, not one per endpoint the pulse reads."""
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "expired")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("good"))
    monkeypatch.setattr(pulse_collector.urllib.request, "urlopen", _urlopen_that("expired", b"[]"))
    pulse_collector.gh_api("repos/x/y/pulls")
    assert "expired" in pulse_collector._REJECTED_TOKENS
    assert pulse_collector._github_tokens() == ["good"]


def test_every_credential_rejected_reports_and_returns_empty(monkeypatch):
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "expired")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("also-expired"))

    def _always_401(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(pulse_collector.urllib.request, "urlopen", _always_401)
    assert pulse_collector.gh_api("repos/x/y/pulls") == []
    assert pulse_collector._REJECTED_TOKENS == {"expired", "also-expired"}


def test_a_non_auth_failure_does_not_burn_the_other_credential(monkeypatch):
    """A 404 is about the endpoint. Re-asking with a different token would fail the same way."""
    monkeypatch.setattr(pulse_collector, "GITHUB_TOKEN", "fine")
    monkeypatch.setattr(pulse_collector, "_gh_cli_token", _gh_cli_gives("also-fine"))

    calls: list[str] = []

    def _always_404(req, timeout=None):
        calls.append(req.headers.get("Authorization", ""))
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(pulse_collector.urllib.request, "urlopen", _always_404)
    assert pulse_collector.gh_api("repos/x/y/nope") == []
    assert len(calls) == 1, "a 404 must not be retried against the second credential"
    assert pulse_collector._REJECTED_TOKENS == set(), "a 404 says nothing about the token"
