"""C4 — Guardrail enforcement evals.

Exercises the pure text detectors in ``guardrails/enforcement.py``. Domain-
isolated from ``guardrails/evaluator.py`` (which is activity_log-driven).

  eval_placeholder_clean_text          — no placeholders → []
  eval_placeholder_bracket_tbd         — "[TBD]" detected
  eval_placeholder_bracket_your_field  — "[your email]" detected
  eval_placeholder_bare_word           — bare "TBD" / "TODO" detected
  eval_placeholder_phrase              — "define later" / "as needed" detected
  eval_placeholder_ignores_citations   — "[1]" / "[docs]" not flagged
  eval_placeholder_returns_all         — multiple placeholders in one body
  eval_multi_question_single           — one "?" → False
  eval_multi_question_two              — two "?" → True
  eval_multi_question_none             — zero "?" → False
  eval_multi_question_ignores_url      — "?" in URL not counted
  eval_multi_question_ignores_code     — "?" inside fenced code not counted
  eval_multi_question_ignores_inline   — "?" inside inline backticks not counted
"""

from __future__ import annotations

from guardrails.enforcement import detect_multi_question, detect_placeholders


def test_placeholder_clean_text_returns_empty():
    assert detect_placeholders("Build the dashboard exactly as described.") == []


def test_placeholder_empty_text_returns_empty():
    assert detect_placeholders("") == []


def test_placeholder_bracket_tbd_detected():
    findings = detect_placeholders("Milestone 1: [TBD]")
    assert findings == ["[TBD]"]


def test_placeholder_bracket_your_field_detected():
    findings = detect_placeholders("Contact us at [your email] for support.")
    assert findings == ["[your email]"]


def test_placeholder_bracket_fill_in_detected():
    findings = detect_placeholders("Section: [fill in later]")
    assert findings == ["[fill in later]"]


def test_placeholder_bare_word_tbd_detected():
    findings = detect_placeholders("Decide on TBD before shipping.")
    assert findings == ["TBD"]


def test_placeholder_bare_word_todo_detected():
    findings = detect_placeholders("TODO: wire the API contract.")
    assert findings == ["TODO"]


def test_placeholder_phrase_define_later_detected():
    findings = detect_placeholders("We will define later once specs land.")
    assert findings == ["define later"]


def test_placeholder_phrase_as_needed_detected():
    findings = detect_placeholders("Retry as needed if the call fails.")
    assert findings == ["as needed"]


def test_placeholder_ignores_numeric_citations():
    assert detect_placeholders("See [1] and [42] for background.") == []


def test_placeholder_ignores_link_labels():
    assert detect_placeholders("Read the [docs] and the [spec].") == []


def test_placeholder_returns_all_findings():
    text = (
        "Milestone 1: [TBD]. Owner: [your name]. "
        "Steps: TODO write the script. Cleanup as needed."
    )
    findings = detect_placeholders(text)
    assert findings == ["[TBD]", "[your name]", "TODO", "as needed"]


def test_multi_question_single_returns_false():
    assert detect_multi_question("What is the next milestone?") is False


def test_multi_question_two_returns_true():
    assert detect_multi_question("Which path should we take? What about timing?") is True


def test_multi_question_none_returns_false():
    assert detect_multi_question("There are no questions in this sentence.") is False


def test_multi_question_empty_returns_false():
    assert detect_multi_question("") is False


def test_multi_question_ignores_url_query_string():
    text = "See https://example.com/search?q=cat&page=2 — does that work?"
    assert detect_multi_question(text) is False


def test_multi_question_ignores_fenced_code():
    text = (
        "Run this:\n"
        "```\n"
        "GET /users?id=1\n"
        "GET /users?id=2\n"
        "```\n"
        "Does that match your expectation?"
    )
    assert detect_multi_question(text) is False


def test_multi_question_ignores_inline_code():
    text = "Use `GET /users?id=1` and `POST /users?dry_run=true`. Make sense?"
    assert detect_multi_question(text) is False


def test_multi_question_counts_prose_questions_only():
    text = "URL `GET /search?q=foo` returns 200. " "Should we retry? Or surface the error?"
    assert detect_multi_question(text) is True
