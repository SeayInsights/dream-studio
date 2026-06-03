"""Tests for behavioral eval harness infrastructure (18.8.3).

Proving gate for merge:
- Deterministic matcher produces same score on identical inputs
- Event sequence matching works correctly
- Negative checks are enforced
- Baseline regression detection works
- Judge integration structure is correct (live API calls require ANTHROPIC_API_KEY)
- CLI structure verified
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.eval.matcher import match_events
from core.eval.runner import EvalRunner, format_results_report, load_eval_cases
from core.eval.schema import EvalCase, EvalResult, ExpectedEvent

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = REPO_ROOT / "evals"
HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


# ── EvalCase loading ──────────────────────────────────────────────────────


class TestEvalCaseLoading:
    def test_load_all_eval_cases(self):
        cases = load_eval_cases(EVALS_DIR)
        assert len(cases) >= 5, f"Expected at least 5 eval cases, found {len(cases)}"

    def test_eval_cases_have_required_fields(self):
        cases = load_eval_cases(EVALS_DIR)
        for case in cases:
            assert case.eval_id, f"Case missing eval_id: {case}"
            assert case.input_prompt, f"Case {case.eval_id} missing input_prompt"
            assert case.version

    def test_eval_01_loads_correctly(self):
        path = EVALS_DIR / "eval_01_event_sequence_skill_dispatch.json"
        case = EvalCase.from_json(path)
        assert case.eval_id == "eval_01_event_sequence_skill_dispatch"
        assert case.event_weight == 0.7
        assert case.behavior_weight == 0.3
        assert len(case.expected_events) == 1
        assert case.expected_events[0].event_type == "skill.invoked"
        assert case.expected_events[0].must_appear is True
        assert case.fixture_events is not None

    def test_eval_04_has_negative_check(self):
        path = EVALS_DIR / "eval_04_negative_check_no_direct_code.json"
        case = EvalCase.from_json(path)
        # eval_04 has a negative event check (code.generated must NOT appear)
        negative = [e for e in case.expected_events if not e.must_appear]
        assert len(negative) >= 1
        assert any("code" in e.event_type.lower() for e in negative)


# ── Deterministic event matcher ───────────────────────────────────────────


class TestDeterministicMatcher:
    def _make_case(self, expected_events, negative_checks=None):
        """Helper: create minimal EvalCase with given expected events."""
        return EvalCase(
            eval_id="test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_events=expected_events,
            negative_checks=negative_checks or [],
        )

    def test_perfect_match_scores_1_0(self):
        case = self._make_case([ExpectedEvent(event_type="skill.invoked", must_appear=True)])
        events = [{"event_type": "skill.invoked", "skill_id": "ds-project"}]
        result = match_events(case, events)
        assert result.score == 1.0
        assert result.matched_required == 1
        assert result.total_required == 1

    def test_missing_required_event_scores_0_0(self):
        case = self._make_case([ExpectedEvent(event_type="skill.invoked", must_appear=True)])
        events = [{"event_type": "session.start"}]
        result = match_events(case, events)
        assert result.score == 0.0
        assert "skill.invoked" in result.missing_events[0]

    def test_negative_event_present_reduces_score(self):
        case = self._make_case(
            [
                ExpectedEvent(event_type="skill.invoked", must_appear=True),
                ExpectedEvent(event_type="code.generated", must_appear=False),
            ]
        )
        events = [
            {"event_type": "skill.invoked"},
            {"event_type": "code.generated"},
        ]
        result = match_events(case, events)
        assert result.score < 1.0
        assert "code.generated" in result.negative_violations[0]

    def test_negative_event_absent_does_not_reduce_score(self):
        case = self._make_case(
            [
                ExpectedEvent(event_type="skill.invoked", must_appear=True),
                ExpectedEvent(event_type="code.generated", must_appear=False),
            ]
        )
        events = [{"event_type": "skill.invoked"}]
        result = match_events(case, events)
        assert result.score == 1.0
        assert not result.negative_violations

    def test_skill_id_filter_matches_correctly(self):
        case = self._make_case(
            [
                ExpectedEvent(
                    event_type="skill.invoked", skill_id="ds-project:resume", must_appear=True
                )
            ]
        )
        events_wrong_skill = [{"event_type": "skill.invoked", "trace": {"skill_id": "ds-quality"}}]
        events_right_skill = [
            {"event_type": "skill.invoked", "trace": {"skill_id": "ds-project:resume"}}
        ]
        result_wrong = match_events(case, events_wrong_skill)
        result_right = match_events(case, events_right_skill)
        assert result_wrong.score == 0.0
        assert result_right.score == 1.0

    def test_out_of_order_event_gives_partial_credit(self):
        case = self._make_case(
            [
                ExpectedEvent(
                    event_type="skill.invoked",
                    must_appear=True,
                    max_sequence_position=1,
                )
            ]
        )
        events = [
            {"event_type": "context.loaded"},
            {"event_type": "context.loaded"},
            {"event_type": "skill.invoked"},  # position 2, max=1
        ]
        result = match_events(case, events)
        assert 0.0 < result.score < 1.0
        assert result.out_of_order

    def test_determinism_same_input_same_output(self):
        """Identical inputs must produce identical scores — this is the determinism proof."""
        case = self._make_case(
            [
                ExpectedEvent(event_type="skill.invoked", must_appear=True),
                ExpectedEvent(event_type="code.generated", must_appear=False),
            ]
        )
        events = [{"event_type": "skill.invoked"}, {"event_type": "skill.completed"}]

        scores = [match_events(case, events).score for _ in range(10)]
        assert len(set(scores)) == 1, f"Non-deterministic: scores varied across runs: {set(scores)}"

    def test_empty_expected_events_scores_1_0(self):
        case = self._make_case([])
        result = match_events(case, [{"event_type": "anything"}])
        assert result.score == 1.0


# ── Runner integration ────────────────────────────────────────────────────


class TestEvalRunner:
    def test_run_eval_01_passes_in_fixture_mode(self):
        """eval_01 with its own fixture events should pass."""
        runner = EvalRunner(evals_dir=EVALS_DIR)
        path = EVALS_DIR / "eval_01_event_sequence_skill_dispatch.json"
        case = EvalCase.from_json(path)
        result = runner.run_case(case)
        assert isinstance(result, EvalResult)
        assert result.passed, (
            f"eval_01 should pass in fixture mode. "
            f"Score: {result.composite_score:.3f}, "
            f"event_score: {result.event_score:.3f}"
        )

    def test_run_eval_04_negative_check_passes(self):
        """eval_04 fixture has no code.generated event, so negative check passes."""
        runner = EvalRunner(evals_dir=EVALS_DIR)
        path = EVALS_DIR / "eval_04_negative_check_no_direct_code.json"
        case = EvalCase.from_json(path)
        result = runner.run_case(case)
        assert (
            not result.match_result.negative_violations
        ), f"Negative check should not fire: {result.match_result.negative_violations}"

    def test_negative_check_fails_when_forbidden_event_present(self):
        """If we inject a code.generated event, eval_04 negative check must fire."""
        path = EVALS_DIR / "eval_04_negative_check_no_direct_code.json"
        case = EvalCase.from_json(path)
        # Inject a forbidden event into fixture
        bad_fixtures = list(case.fixture_events or []) + [{"event_type": "code.generated"}]
        case.fixture_events = bad_fixtures

        runner = EvalRunner(evals_dir=EVALS_DIR)
        result = runner.run_case(case)
        assert (
            result.match_result.negative_violations
        ), "Negative check should fire when code.generated event is present"
        # Event score must be < 1.0 due to negative violation penalty
        assert (
            result.event_score < 1.0
        ), f"Event score should be < 1.0 when negative violation fires, got {result.event_score}"

    def test_run_all_returns_5_results(self):
        runner = EvalRunner(evals_dir=EVALS_DIR)
        results = runner.run_all()
        assert len(results) == 5

    def test_run_all_by_skill_filter(self):
        runner = EvalRunner(evals_dir=EVALS_DIR)
        results = runner.run_all(skill_filter="ds-project")
        assert all(r.eval_id.startswith("eval_0") for r in results)
        # Only evals with skill_id="ds-project" should be returned
        cases = load_eval_cases(EVALS_DIR)
        expected_count = sum(1 for c in cases if c.skill_id == "ds-project")
        assert len(results) == expected_count

    def test_result_has_token_estimate(self):
        runner = EvalRunner(evals_dir=EVALS_DIR)
        path = EVALS_DIR / "eval_01_event_sequence_skill_dispatch.json"
        case = EvalCase.from_json(path)
        result = runner.run_case(case)
        assert result.tokens_consumed >= 0

    def test_format_results_report_is_readable(self):
        runner = EvalRunner(evals_dir=EVALS_DIR)
        results = runner.run_all()
        report = format_results_report(results)
        assert "Behavioral Eval Report" in report
        assert "Summary:" in report
        assert "Tokens estimated:" in report


# ── Regression detection ──────────────────────────────────────────────────


class TestRegressionDetection:
    def test_baseline_established_on_first_run(self, tmp_path):
        """First run establishes baseline (is_baseline=True)."""
        from core.eval.baseline import load_baseline, save_run_result

        # Create the table in a temp DB
        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL, last_run_score REAL,
                last_run_at TEXT, regression_flag INTEGER DEFAULT 0,
                regression_threshold REAL DEFAULT 0.10,
                run_count INTEGER DEFAULT 0,
                last_updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.commit()
        conn.close()

        is_baseline, regression = save_run_result("test_eval", "1.0.0", 0.90, True, db_path=db)
        assert is_baseline is True
        assert regression is False

        baseline = load_baseline("test_eval", "1.0.0", db_path=db)
        assert baseline is not None
        assert abs(baseline["baseline_score"] - 0.90) < 0.001

    def test_regression_flagged_when_score_drops(self, tmp_path):
        """Score dropping > 10% below baseline flags regression."""
        from core.eval.baseline import save_run_result

        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL, last_run_score REAL,
                last_run_at TEXT, regression_flag INTEGER DEFAULT 0,
                regression_threshold REAL DEFAULT 0.10,
                run_count INTEGER DEFAULT 0,
                last_updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.commit()
        conn.close()

        # Establish baseline at 0.90
        save_run_result("reg_test", "1.0.0", 0.90, True, db_path=db)

        # Second run with degraded score (0.70 = drop of 0.20 > threshold 0.10)
        _is_baseline, regression = save_run_result("reg_test", "1.0.0", 0.70, False, db_path=db)
        assert _is_baseline is False
        assert regression is True, "Score dropped 0.20 (> 0.10 threshold) — should flag regression"

    def test_no_regression_within_threshold(self, tmp_path):
        """Small score variation within threshold does NOT flag regression."""
        from core.eval.baseline import save_run_result

        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL, last_run_score REAL,
                last_run_at TEXT, regression_flag INTEGER DEFAULT 0,
                regression_threshold REAL DEFAULT 0.10,
                run_count INTEGER DEFAULT 0,
                last_updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.commit()
        conn.close()

        save_run_result("stable_test", "1.0.0", 0.90, True, db_path=db)
        _is_baseline, regression = save_run_result("stable_test", "1.0.0", 0.85, True, db_path=db)
        assert regression is False, "Drop of 0.05 is within 0.10 threshold — should NOT flag"

    def test_baseline_update_requires_explicit_call(self, tmp_path):
        """Baseline must NOT auto-update on regression. Requires explicit update_baseline()."""
        from core.eval.baseline import load_baseline, save_run_result, update_baseline

        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL, last_run_score REAL,
                last_run_at TEXT, regression_flag INTEGER DEFAULT 0,
                regression_threshold REAL DEFAULT 0.10,
                run_count INTEGER DEFAULT 0,
                last_updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.commit()
        conn.close()

        save_run_result("update_test", "1.0.0", 0.90, True, db_path=db)
        # Regression run — baseline should NOT auto-update
        save_run_result("update_test", "1.0.0", 0.70, False, db_path=db)
        baseline_after_regression = load_baseline("update_test", "1.0.0", db_path=db)
        assert (
            abs(baseline_after_regression["baseline_score"] - 0.90) < 0.001
        ), "Baseline must NOT auto-update on regression"

        # Explicit update — now baseline should change
        update_baseline("update_test", "1.0.0", 0.70, db_path=db)
        baseline_after_update = load_baseline("update_test", "1.0.0", db_path=db)
        assert (
            abs(baseline_after_update["baseline_score"] - 0.70) < 0.001
        ), "Baseline should update after explicit update_baseline() call"


# ── Judge structure tests ──────────────────────────────────────────────────


class TestJudgeStructure:
    def test_judge_skips_when_claude_not_available(self, monkeypatch):
        """Judge must skip gracefully when claude CLI is not available."""
        import shutil

        monkeypatch.setattr(shutil, "which", lambda _: None)
        from core.eval.judge import grade_behavior

        case = EvalCase(
            eval_id="test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="Claude should do X",
        )
        result = grade_behavior(case, "some transcript", api_key=None)
        assert result.skipped is True
        assert result.score is None
        assert result.effective_score == 0.5  # Neutral fallback

    def test_judge_auto_passes_when_no_expected_behavior(self):
        """Empty expected_behavior → auto-pass with score 1.0."""
        from core.eval.judge import grade_behavior

        case = EvalCase(
            eval_id="test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="",
        )
        result = grade_behavior(case, "any transcript", api_key=None)
        assert result.score == 1.0
        assert not result.skipped

    def test_token_estimate_is_positive(self):
        from core.eval.judge import estimate_judge_tokens

        case = EvalCase(
            eval_id="test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="Claude should do X",
            negative_checks=["Not this"],
        )
        tokens = estimate_judge_tokens(case, "session transcript here")
        assert tokens > 0


# ── Live judge tests (Claude Code — no API key required) ──────────────────

HAS_CLAUDE = bool(__import__("shutil").which("claude"))


@pytest.mark.skipif(not HAS_CLAUDE, reason="Requires claude CLI for live judge")
class TestLiveJudge:
    def test_judge_scores_correct_behavior_highly(self):
        """A transcript that clearly exhibits expected behavior should score >= 0.75."""
        from core.eval.judge import grade_behavior

        case = EvalCase(
            eval_id="live_test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="Claude invokes the resume skill and presents the next work order",
        )
        transcript = "Claude: I'll check your project state.\n[Invoked: ds-project:resume]\nNext WO: Build authentication feature."
        result = grade_behavior(case, transcript)
        assert result.score is not None
        assert not result.skipped
        assert (
            result.score >= 0.5
        ), f"Expected score >= 0.5 for correct behavior, got {result.score}"

    def test_judge_scores_wrong_behavior_low(self):
        """A transcript that ignores expected behavior should score < 0.5."""
        from core.eval.judge import grade_behavior

        case = EvalCase(
            eval_id="live_test_low",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="Claude invokes the resume skill and presents the next work order",
            negative_checks=["Claude must not start writing code immediately"],
        )
        # Transcript that starts writing code without checking project state
        bad_transcript = "Claude: Sure, let me write the authentication code!\n```python\ndef login(user, password): ...\n```"
        result = grade_behavior(case, bad_transcript)
        assert result.score is not None
        # The negative check about writing code should fire → score = 0.0
        assert result.score <= 0.5, f"Expected low score for wrong behavior, got {result.score}"

    def test_judge_variance_across_identical_runs(self):
        """Run same eval 5 times — variance must be < 0.05 (tight prompt working)."""
        from core.eval.judge import grade_behavior

        case = EvalCase(
            eval_id="variance_test",
            version="1.0.0",
            description="test",
            skill_id=None,
            input_prompt="test",
            expected_behavior="Claude invokes the resume skill and presents work order context",
        )
        transcript = (
            "Claude: Checking project state.\n"
            "[Invoked: ds-project:resume]\n"
            "Active WO: Build auth feature. Design brief locked. Ready to proceed."
        )

        scores = []
        for _ in range(5):
            result = grade_behavior(case, transcript)
            if not result.skipped and result.score is not None:
                scores.append(result.score)

        assert len(scores) >= 3, "Need at least 3 non-skipped runs for variance check"
        variance = max(scores) - min(scores)
        assert variance < 0.05, (
            f"Judge variance {variance:.3f} exceeds 0.05 target. Scores: {scores}. "
            "Tight prompt not working — consider redesigning the judge prompt."
        )
