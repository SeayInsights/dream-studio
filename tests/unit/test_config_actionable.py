"""WO-DASH-ACTIONABILITY T2: the config tab explains its settings, or is removed.

Operator: config gave "no idea what this shows". Each ds_config key must be
explained (what it does), or the tab removed.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections/frontend/dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_config_explains_or_removed():
    html = _html()

    tab_present = 'id="config"' in html and 'id="ds-config-body"' in html
    if not tab_present:
        # Acceptable outcome: the non-actionable tab was cut.
        assert 'id="ds-config-body"' not in html
        return

    # Kept → it must explain what the settings control.
    assert "ds_config" in html, "config tab must name the ds_config source"
    assert "What it does" in html, "config table must have a 'What it does' column"

    fn_start = html.find("function dsConfigDescription")
    assert fn_start != -1, "a per-key description helper must exist"
    assert "DS_CONFIG_DESCRIPTIONS" in html, "known-key descriptions must be defined"
    # At least one concrete, meaningful key description (not just a generic fallback).
    assert "friction_threshold" in html, "known keys must carry concrete descriptions"

    _cfg = html.find("async function loadDsConfig")
    load_fn = html[_cfg : _cfg + 1400]  # noqa: E203
    assert "dsConfigDescription(row.key)" in load_fn, "each row must render its description"
    # Honest empty-state explains defaults rather than a bare 'none'.
    assert "all defaults apply" in load_fn, "empty config must explain defaults + how to set a key"
