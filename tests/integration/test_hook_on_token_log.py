"""Integration test for on-token-log."""

from __future__ import annotations

import json


def test_appends_row_with_explicit_tokens(isolated_home, handler, capsys):
    mod = handler("on-token-log")
    mod.main(
        {
            "session_name": "sess-1",
            "model": "claude-opus",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "timestamp": "2026-04-16T00:00:00+00:00",
        }
    )

    log = isolated_home / ".dream-studio" / "meta" / "token-log.md"
    text = log.read_text(encoding="utf-8")
    assert "sess-1" in text
    assert "claude-opus" in text
    assert "150" in text

    out = capsys.readouterr().out
    result = json.loads(out.strip())
    assert result["status"] == "ok"
    assert result["total_tokens"] == 150


def test_parses_transcript_when_tokens_missing(isolated_home, handler):
    transcript = isolated_home / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"model": "claude-sonnet", "usage": {"input_tokens": 10, "output_tokens": 4}}) + "\n"
        + json.dumps({"usage": {"input_tokens": 5, "output_tokens": 2}}) + "\n",
        encoding="utf-8",
    )

    mod = handler("on-token-log")
    mod.main({"session_name": "sess-2", "transcript_path": str(transcript)})

    log = (isolated_home / ".dream-studio" / "meta" / "token-log.md").read_text(encoding="utf-8")
    assert "claude-sonnet" in log
    # 15 input + 6 output = 21 total
    assert "| 15 | 6 | 21 |" in log
