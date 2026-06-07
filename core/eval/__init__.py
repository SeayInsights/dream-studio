"""Behavioral eval harness — session-level skill correctness measurement.

Scoring is 100% deterministic: event pattern matching only, no LLM judge (WO-N2).

Usage:
    from core.eval.runner import EvalRunner
    runner = EvalRunner()
    results = runner.run_all()
"""
