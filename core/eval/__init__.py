"""Behavioral eval harness — session-level skill correctness measurement.

Phase 1 (18.8.3): Core infrastructure — schema, matcher, judge, baseline, runner.
Phase 2: Per-skill corpus build-out.
Phase 3: Phase 19 gate integration.

Usage:
    from core.eval.runner import EvalRunner
    runner = EvalRunner()
    results = runner.run_all()
"""
