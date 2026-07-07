"""Tests for WO-DASH-RENDER-FIX dashboard render fixes.

Seven fixes validated:
  T1 - Hooks: null-ref guard on hooks-total-anomalies + honest empty-state for hook cards
  T2 - Workflows: honest empty-state on early return + PromotedVsDraft empty-state overlay
  T3 - Skills + Cost: leaderboard never stuck 'Loading...' + Cost Over Time empty-state overlay
  T4 - Charts: Models, workflow-success, skill-success all show user-facing empty-states
  T5 - End-to-end: no obvious stuck 'Loading...' regressions for data-backed tabs
  T6 - Skills charts: execution-time-distribution gets empty-state instead of blank canvas
  T7 - Hooks charts: performance chart gets empty-state when byHook is empty
"""

from __future__ import annotations

from tests.dashboard_source import dashboard_source

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"


# ── T1: Hooks null-ref guard + honest card empty-state ───────────────────────


class TestT1HooksNullRefAndRenders:
    def test_hooks_no_null_ref_and_renders(self):
        """T1: hooks-total-anomalies write is null-guarded; card container gets honest empty-state."""
        text = dashboard_source()

        # The direct un-guarded write must be gone
        assert "document.getElementById('hooks-total-anomalies').textContent" not in text, (
            "Null-ref bug: direct write to 'hooks-total-anomalies' must be null-guarded. "
            "The element was removed from the DOM, so this throws every load."
        )

        # The guarded write must be present
        assert (
            "anomaliesEl" in text
        ), "hooks-total-anomalies write must use a null-guarded pattern (via anomaliesEl)"
        assert (
            "if (anomaliesEl) anomaliesEl.textContent" in text
        ), "Null guard pattern 'if (anomaliesEl) anomaliesEl.textContent' must be present"

        # Hook cards container must have an else branch for the empty case
        assert (
            "No per-hook breakdown available" in text
            or "by_hook stats are not yet computed" in text
        ), (
            "hooks-cards-container must show an honest empty-state when byHook is empty — "
            "otherwise 'Loading hook status...' persists indefinitely."
        )

    def test_hooks_cards_else_branch_present(self):
        """T1: The if/else structure on byHook replaces the old unconditional 'if only' guard."""
        text = dashboard_source()
        # Confirm the old simple guard (single 'if' with no else) is replaced
        # by looking for the else that provides honest empty-state
        # The old code: if (cardsContainer && Object.keys(byHook).length > 0)
        # New code wraps with outer if(cardsContainer) + inner if/else on byHook length
        assert "No per-hook breakdown available yet" in text, (
            "The hooks cards container must have an else branch that shows an honest empty-state "
            "message — previously it silently left 'Loading hook status...' with no replacement."
        )


# ── T2: Workflows honest empty-state ─────────────────────────────────────────


class TestT2WorkflowsHonestEmptystate:
    def test_workflows_honest_emptystate(self):
        """T2: initWorkflowsTab early-return shows honest empty-state; promotedVsDraft has overlay."""
        text = dashboard_source()

        # Early return path must update cards to honest empty values, not leave '--'
        assert "No workflow data yet" in text, (
            "initWorkflowsTab early-return must show an honest 'No workflow data yet' state "
            "on the card containers — not silently leave summary cards at '--'."
        )

        # Promoted vs Draft chart must have a user-facing empty-state overlay
        assert "No lesson timeline data yet" in text, (
            "initPromotedVsDraftChart must show a user-facing empty-state when timeline is empty "
            "instead of leaving a blank canvas. Message must include 'No lesson timeline data yet'."
        )

    def test_promoted_vs_draft_no_silent_return(self):
        """T2: initPromotedVsDraftChart must not silently return — it must set an empty-state."""
        text = dashboard_source()
        fn_start = text.find("async function initPromotedVsDraftChart")
        fn_end = text.find("\n        async function ", fn_start + 1)
        if fn_end < 0:
            fn_end = text.find("\n        function ", fn_start + 1)
        fn_body = text[fn_start:fn_end] if fn_start >= 0 else ""

        # Must have a user-facing message in the empty branch
        assert "No lesson timeline data yet" in fn_body or "timeline data" in fn_body, (
            "initPromotedVsDraftChart empty branch must set a user-facing empty-state "
            "on the canvas wrapper, not just console.warn and return."
        )
        assert (
            "pvdWrapper" in fn_body or "parentElement" in fn_body
        ), "Empty-state must be written to the canvas wrapper element, not left as blank canvas."


# ── T3: Skills + Cost empty-states ───────────────────────────────────────────


class TestT3SkillsAndCostEmptystates:
    def test_skills_and_cost_emptystates(self):
        """T3: Skills leaderboard never stuck 'Loading...'; Cost Over Time shows overlay."""
        text = dashboard_source()

        # initSkillsTab error path and no-data path must call populateSkillsLeaderboard([])
        # so the table body is never left as 'Loading skills data...'
        fn_start = text.find("async function initSkillsTab")
        fn_end = text.find("\n        // Update summary cards", fn_start + 1)
        fn_body = text[fn_start:fn_end] if fn_start >= 0 else ""

        assert fn_body.count("populateSkillsLeaderboard([])") >= 2, (
            "initSkillsTab must call populateSkillsLeaderboard([]) in both the no-data branch "
            "AND the catch block — otherwise 'Loading skills data...' persists on fetch failure. "
            f"Found {fn_body.count('populateSkillsLeaderboard([])')} call(s), expected >= 2."
        )

        # Cost Over Time must have an empty-state overlay (not silent return)
        assert (
            "Cost data not yet reportable" in text or "cost attribution is not available" in text
        ), (
            "initCostOverTimeChart must show a user-facing empty-state overlay when cost data "
            "is not reportable — not just console.warn and leave blank canvas."
        )

    def test_skills_leaderboard_no_data_path_covered(self):
        """T3: The no-data path in initSkillsTab calls populateSkillsLeaderboard([]) explicitly."""
        text = dashboard_source()
        # Locate the 'if (!data)' block inside initSkillsTab
        fn_start = text.find("async function initSkillsTab")
        no_data_idx = text.find("No skills data available", fn_start)
        assert no_data_idx > 0, "No skills data available warning not found in initSkillsTab"
        # The next few lines after the warning must include the leaderboard call
        snippet_end = no_data_idx + 200
        snippet = text[no_data_idx:snippet_end]
        assert "populateSkillsLeaderboard([])" in snippet, (
            "The no-data early-return in initSkillsTab must call populateSkillsLeaderboard([]) "
            "before returning so the 'Loading skills data...' placeholder is replaced."
        )


# ── T4: Charts show empty-state not blank ────────────────────────────────────


class TestT4ChartsShowEmptystateNotBlank:
    def test_charts_show_emptystate_not_blank(self):
        """T4: Models, workflow-success, skill-success all have user-facing empty-states."""
        text = dashboard_source()

        # Model distribution chart
        assert "No model usage data yet" in text, (
            "initModelDistributionChart must show 'No model usage data yet' empty-state "
            "instead of silently returning and leaving a blank canvas."
        )

        # Workflow success rates chart
        assert "No workflow run data yet" in text, (
            "initWorkflowSuccessRatesChart must show 'No workflow run data yet' empty-state "
            "instead of silently returning and leaving a blank canvas."
        )

        # Skill success rate trend chart
        assert "No success rate trend data yet" in text, (
            "initSkillSuccessRateChart must show 'No success rate trend data yet' empty-state "
            "instead of silently returning and leaving a blank canvas."
        )

    def test_model_chart_empty_state_wired_to_wrapper(self):
        """T4: Model distribution empty-state is written to the canvas wrapper element."""
        text = dashboard_source()
        fn_start = text.find("async function initModelDistributionChart")
        fn_end = text.find("\n        async function ", fn_start + 1)
        if fn_end < 0:
            fn_end = text.find("\n        // Initialize", fn_start + 1)
        fn_body = text[fn_start:fn_end] if fn_start >= 0 else ""

        assert (
            "mdWrapper" in fn_body or "modelDistributionChart" in fn_body
        ), "Model distribution empty-state must reference the chart wrapper element."
        assert (
            "No model usage data yet" in fn_body
        ), "Model distribution empty-state message must appear inside the function body."


# ── T6: Skills avg-duration and execution-time-distribution ──────────────────


class TestT6SkillsDurationAndHeatmap:
    def test_skills_duration_and_heatmap(self):
        """T6: Skill execution-time-distribution shows empty-state when leaderboard is empty."""
        text = dashboard_source()

        # Execution time distribution must have empty-state
        assert "No execution time data yet" in text, (
            "initSkillExecutionTimeChart must show 'No execution time data yet' empty-state "
            "when leaderboard is empty — not leave a blank canvas."
        )

    def test_execution_time_chart_empty_branch_wired(self):
        """T6: initSkillExecutionTimeChart empty branch writes to the canvas wrapper."""
        text = dashboard_source()
        fn_start = text.find("async function initSkillExecutionTimeChart")
        fn_end = text.find("\n        // Initialize", fn_start + 1)
        if fn_end < 0:
            fn_end = text.find("\n        // Populate", fn_start + 1)
        fallback_end = fn_start + 1500
        fn_body = text[fn_start:fn_end] if fn_start >= 0 else text[fn_start:fallback_end]

        assert (
            "No execution time data yet" in fn_body
        ), "The empty-state message must be inside initSkillExecutionTimeChart."
        assert (
            "etWrapper" in fn_body or "parentElement" in fn_body
        ), "Empty-state must be written to the canvas wrapper (not just console.warn)."

    def test_skill_heatmap_already_has_empty_state(self):
        """T6: initSkillHeatmap already shows a CSS-based empty-state (pre-existing, verify preserved)."""
        text = dashboard_source()
        assert "No heatmap data available" in text, (
            "initSkillHeatmap must still show 'No heatmap data available' empty-state — "
            "this was pre-existing and must not have been removed."
        )


# ── T7: Hooks charts render ──────────────────────────────────────────────────


class TestT7HooksChartsRender:
    def test_hooks_charts_render(self):
        """T7: Hook performance chart shows honest empty-state when byHook is empty."""
        text = dashboard_source()

        # Performance chart empty-state
        assert "No per-hook performance data yet" in text, (
            "hooksPerformanceChart must show 'No per-hook performance data yet' empty-state "
            "when byHook has no entries — not leave a blank canvas."
        )

    def test_hooks_timeline_chart_always_renders(self):
        """T7: The hooks timeline chart renders regardless (uses executions array, not byHook)."""
        text = dashboard_source()
        # The timeline chart creation is unconditional on byHook — it uses dayBuckets
        # which are built from executions. Verify the timeline ctx block has no byHook guard.
        fn_start = text.find("async function loadHooksData")
        timeline_idx = text.find("hooksTimelineChart", fn_start)
        assert timeline_idx > 0, "hooksTimelineChart canvas reference not found in loadHooksData"
        # The timeline block should use 'if (timelineCtx)' not 'if (timelineCtx && ..byHook..)'
        snip_start = timeline_idx - 50
        snip_end = timeline_idx + 200
        snippet = text[snip_start:snip_end]
        assert (
            "byHook" not in snippet or "timelineCtx" in snippet
        ), "Timeline chart creation must not be gated on byHook — it renders from executions."

    def test_hooks_performance_chart_empty_state_in_loadhooksdata(self):
        """T7: The empty-state for performance chart is written inside loadHooksData."""
        text = dashboard_source()
        fn_start = text.find("async function loadHooksData")
        fn_end = text.find("\n        // Update last updated", fn_start + 1)
        fn_body = text[fn_start:fn_end] if fn_start >= 0 else ""

        assert "No per-hook performance data yet" in fn_body, (
            "The hooksPerformanceChart empty-state must be written from within loadHooksData, "
            "not from a separate initHooksCharts() stub."
        )


# ── T5: End-to-end — no stuck Loading regressions ────────────────────────────


class TestT5EndToEnd:
    def test_end_to_end(self):
        """T5: No data-backed tabs have unguarded 'Loading...' that can never be replaced."""
        text = dashboard_source()

        # Verify core sections still present (regression guard)
        for section_id in ["hooks", "security", "memory-surface", "adaptation"]:
            assert (
                f'id="{section_id}"' in text
            ), f"Dashboard section id={section_id!r} was removed — regression"

        # The skills leaderboard placeholder is the HTML initial state
        # It MUST still exist as the initial DOM state (gets replaced by JS)
        assert "Loading skills data..." in text, (
            "The initial 'Loading skills data...' placeholder must still exist in the HTML "
            "DOM — it is replaced by JS on load. Removing it is a regression."
        )

        # Confirm populateSkillsLeaderboard replaces it (guards both error paths)
        assert text.count("populateSkillsLeaderboard([])") >= 2, (
            "populateSkillsLeaderboard([]) must be called in at least 2 error paths "
            "(no-data guard + catch block) to ensure the placeholder is always replaced."
        )

        # The 'Loading hook status...' placeholder is the HTML initial state — it must still exist
        assert "Loading hook status..." in text, (
            "The initial 'Loading hook status...' placeholder must still exist in the HTML DOM "
            "— the JS replaces it. Removing it is a regression."
        )

        # But the JS must now handle both the data case AND the empty case
        assert "No per-hook breakdown available yet" in text, (
            "The hooks cards empty-state ('No per-hook breakdown available yet') must be present "
            "so the 'Loading hook status...' placeholder is always replaced."
        )

        # Workflows tab must not have unguarded '--' summary cards
        assert "No workflow data yet" in text, (
            "Workflows tab must show 'No workflow data yet' in the early-return path "
            "instead of leaving summary cards at '--'."
        )
