"""Tests for WO-DASH-DEVDIAG-CONSOLIDATE — Developer Diagnostics tab consolidation.

ACs verified:
  test_no_tab_except_devdiag_has_the_three_blocks
      - hooks-invisible-tables div is gone
      - three list ids appear exactly once each
      - insertAdjacentHTML beforeend createDeveloperDiagnostics is absent from ensureBusinessStorySections
  test_devdiag_page_renders_three_sections
      - developer-diagnostics tab-content div exists and contains all three list ids
  test_security_first_section_is_security
      - security tab-content leads with security-total-findings before any devdiag marker
  test_end_to_end
      - nav item navigate('developer-diagnostics') present
      - tab-content section present
      - switchTab init block references developer-diagnostics
      - tabsInitialized includes 'developer-diagnostics'
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"


# ── test_no_tab_except_devdiag_has_the_three_blocks ──────────────────────────


def test_no_tab_except_devdiag_has_the_three_blocks():
    """The old hooks-invisible-tables div is gone; three list ids each appear exactly once;
    ensureBusinessStorySections no longer injects the per-page developer-diagnostics drawer."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # Old loose div must be completely removed
    assert "hooks-invisible-tables" not in text, (
        "id='hooks-invisible-tables' must be removed — the three cards now live in the "
        "dedicated Developer Diagnostics tab (devdiag-invisible-tables)."
    )

    # Each list id must appear exactly once (only in the new tab, not duplicated)
    tool_count = text.count('id="tool-activity-list"')
    assert tool_count == 1, f"id='tool-activity-list' must appear exactly once; found {tool_count}."

    val_count = text.count('id="validation-failures-list"')
    assert (
        val_count == 1
    ), f"id='validation-failures-list' must appear exactly once; found {val_count}."

    raw_count = text.count('id="raw-events-list"')
    assert raw_count == 1, f"id='raw-events-list' must appear exactly once; found {raw_count}."

    # ensureBusinessStorySections must no longer inject the per-page drawer
    assert "insertAdjacentHTML('beforeend', createDeveloperDiagnostics" not in text, (
        "ensureBusinessStorySections must not inject createDeveloperDiagnostics per-page — "
        "that line must be removed to eliminate cross-tab duplication."
    )


# ── test_devdiag_page_renders_three_sections ─────────────────────────────────


def test_devdiag_page_renders_three_sections():
    """The developer-diagnostics tab-content div exists and contains all three list ids."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    tab_marker = '<div id="developer-diagnostics" class="tab-content">'
    assert (
        tab_marker in text
    ), "A <div id='developer-diagnostics' class='tab-content'> element must exist."

    # Extract the section from the tab marker to the next tab-content or </main>
    start = text.index(tab_marker)
    next_tab = text.find('class="tab-content"', start + len(tab_marker))
    end_main = text.find("</main>", start)

    # Use the closer of next tab-content or </main> as the end boundary
    if next_tab == -1:
        end = end_main
    elif end_main == -1:
        end = next_tab
    else:
        end = min(next_tab, end_main)

    section = text[start:end]

    assert (
        'id="tool-activity-list"' in section
    ), "tool-activity-list must be inside the developer-diagnostics tab-content section."
    assert (
        'id="validation-failures-list"' in section
    ), "validation-failures-list must be inside the developer-diagnostics tab-content section."
    assert (
        'id="raw-events-list"' in section
    ), "raw-events-list must be inside the developer-diagnostics tab-content section."


# ── test_security_first_section_is_security ──────────────────────────────────


def test_security_first_section_is_security():
    """The security tab leads with security-total-findings before any devdiag markers."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    sec_marker = '<div id="security" class="tab-content">'
    assert sec_marker in text, "security tab-content div must exist."

    start = text.index(sec_marker)
    next_tab = text.find('class="tab-content"', start + len(sec_marker))
    end_main = text.find("</main>", start)

    if next_tab == -1:
        end = end_main
    elif end_main == -1:
        end = next_tab
    else:
        end = min(next_tab, end_main)

    section = text[start:end]

    assert (
        "security-total-findings" in section
    ), "security tab must contain security-total-findings summary card."

    # devdiag markers must NOT appear inside the security tab section
    assert "tool-activity-list" not in section, (
        "tool-activity-list must NOT appear inside the security tab-content section — "
        "it belongs only in the developer-diagnostics tab."
    )
    assert (
        "Developer diagnostics" not in section or "Developer Diagnostics" not in section
    ), "The per-page Developer diagnostics drawer must not appear inside the security tab."

    # Confirm security-total-findings appears before any devdiag content in the section
    findings_pos = section.find("security-total-findings")
    tool_pos = section.find("tool-activity-list")
    # tool_pos should be -1 (not found); if somehow present it must come after findings
    if tool_pos != -1:
        assert (
            findings_pos < tool_pos
        ), "security-total-findings must appear before any tool-activity-list in the security section."


# ── test_end_to_end ──────────────────────────────────────────────────────────


def test_end_to_end():
    """Nav item, tab-content, switchTab init block, and tabsInitialized entry all present."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # Nav item in sidebar
    assert (
        "navigate('developer-diagnostics')" in text
    ), "Sidebar nav item onclick='navigate(\"developer-diagnostics\")' must be present."

    # Tab-content section
    assert (
        '<div id="developer-diagnostics" class="tab-content">' in text
    ), "Tab-content div for developer-diagnostics must be present."

    # switchTab init block — the tabName check
    assert (
        "tabName === 'developer-diagnostics'" in text
    ), "switchTab must have an init block for tabName === 'developer-diagnostics'."

    # tabsInitialized object must include the entry
    assert (
        "'developer-diagnostics': false" in text
    ), "tabsInitialized must include 'developer-diagnostics': false."

    # loadInvisibleTables must reference devdiag-invisible-tables, not the old id
    assert (
        "devdiag-invisible-tables" in text
    ), "loadInvisibleTables must reference devdiag-invisible-tables container."
    assert (
        "hooks-invisible-tables" not in text
    ), "hooks-invisible-tables must be fully removed from the file."
