"""Unit tests for WO-EVALS-RENDER: Evals tab render elements in dashboard.html.

Validates that the Evals tab has:
- A baselines table with tbody populated by JS
- A recent runs table with tbody populated by JS
- Honest empty-state messages for both sections
- The initEvalsTab() function wired to fetch /api/v1/evals/health
"""

from __future__ import annotations

from tests.dashboard_source import dashboard_source

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections" / "frontend" / "dashboard.html"


def test_evals_tab_shows_baselines_and_runs() -> None:
    """Evals tab has render elements and JS for baselines + recent runs + empty-state."""
    text = dashboard_source()

    # --- DOM elements present ---
    assert 'id="evals"' in text, "Evals tab container (id=evals) must be present in dashboard.html"

    assert (
        'id="evals-baselines-body"' in text
    ), "Baselines tbody (id=evals-baselines-body) must be present for JS to populate"
    assert (
        'id="evals-runs-body"' in text
    ), "Runs tbody (id=evals-runs-body) must be present for JS to populate"

    assert 'id="evals-total"' in text, "evals-total summary card element must be present"
    assert 'id="evals-pass-rate"' in text, "evals-pass-rate summary card element must be present"
    assert (
        'id="evals-recent-count"' in text
    ), "evals-recent-count summary card element must be present"

    # --- JS fetch wired to /api/v1/evals/health ---
    assert (
        "/api/v1/evals/health" in text
    ), "initEvalsTab() must fetch from /api/v1/evals/health to populate the Evals tab"

    # --- initEvalsTab function present ---
    assert (
        "function initEvalsTab" in text
    ), "initEvalsTab() function must be defined in dashboard.html"

    # --- Baselines render logic ---
    assert (
        "evals-baselines-body" in text
    ), "JS must reference evals-baselines-body to render baseline rows"
    assert (
        "d.baselines" in text
    ), "JS must iterate d.baselines from the API response to render the baselines table"

    # --- Recent runs render logic ---
    assert "evals-runs-body" in text, "JS must reference evals-runs-body to render recent run rows"
    assert (
        "d.recent_runs" in text
    ), "JS must iterate d.recent_runs from the API response to render the runs table"

    # --- Honest empty-states for both sections ---
    assert "No baselines recorded yet" in text, (
        "Evals tab must show 'No baselines recorded yet' empty-state "
        "when the baselines array is empty — not leave 'Loading baselines...'"
    )
    assert "No runs recorded yet" in text, (
        "Evals tab must show 'No runs recorded yet' empty-state "
        "when the recent_runs array is empty — not leave 'Loading runs...'"
    )

    # --- initEvalsTab is triggered when navigating to the evals tab ---
    assert (
        "initEvalsTab" in text
    ), "initEvalsTab must be called from the tab navigation logic to load evals data on demand"

    # --- Error fallback is present ---
    assert "Eval Health tab error" in text or "Failed to load" in text, (
        "initEvalsTab must have a catch block that writes a user-facing error message "
        "instead of leaving the tab blank on fetch failure"
    )

    # --- Fake-cost gate: forbidden substrings must not be present ---
    forbidden = [
        "_estimate_cost",
        "PRICING =",
        "input_tokens * 0.003",
        "output_tokens * 0.015",
        "$0.00/session",
        "Estimated cost",
        "Estimated USD",
    ]
    for marker in forbidden:
        assert (
            marker not in text
        ), f"dashboard.html must not contain fake-cost substring: {marker!r}"
