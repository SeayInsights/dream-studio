"""Integration test for on-agent-correction."""

from __future__ import annotations

CORRECTIONS_TEMPLATE = (
    "# Corrections file\n\n"
    "## Corrections\n\n"
    "- Session: 2026-04-01\n"
    "- DCL command: build feature\n"
    "- My routing: engineering\n"
    "- Correct routing: game\n"
    "- Reason: feature is game-related\n"
    "- Pattern to apply: route game builds to game agent\n"
)


def _write_corrections(path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = ["# Corrections file\n\n## Corrections\n"]
    for i in range(count):
        blocks.append(
            f"\n- Session: 2026-04-{i+1:02d}\n"
            f"- DCL command: build feature\n"
            f"- My routing: engineering\n"
            f"- Correct routing: game\n"
            f"- Reason: {i}\n"
            f"- Pattern to apply: route game builds to game agent\n"
        )
    path.write_text("".join(blocks), encoding="utf-8")


def test_writes_correction_log(isolated_home, monkeypatch, handler):
    target = isolated_home / ".dream-studio" / "planning" / "director-corrections.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CORRECTIONS_TEMPLATE, encoding="utf-8")

    monkeypatch.setenv("CLAUDE_FILE_PATH", str(target))
    mod = handler("on-agent-correction")
    mod.main()

    log = isolated_home / ".dream-studio" / "meta" / "corrections.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "2026-04-01" in text
    assert "route game builds to game agent" in text


def test_non_target_file_is_ignored(isolated_home, monkeypatch, handler):
    other = isolated_home / "unrelated.md"
    other.write_text("## Corrections\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_FILE_PATH", str(other))

    mod = handler("on-agent-correction")
    mod.main()

    assert not (isolated_home / ".dream-studio" / "meta" / "corrections.log").exists()


def test_pattern_accumulation_drafts_lesson(isolated_home, monkeypatch, handler):
    target = isolated_home / ".dream-studio" / "planning" / "director-corrections.md"
    _write_corrections(target, count=3)
    monkeypatch.setenv("CLAUDE_FILE_PATH", str(target))

    mod = handler("on-agent-correction")
    # pre-populate the log so the current write is the 3rd entry
    log = isolated_home / ".dream-studio" / "meta" / "corrections.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "2026-04-01T00:00:00+00:00\tsess-1\troute game builds to game agent\n"
        "2026-04-02T00:00:00+00:00\tsess-2\troute game builds to game agent\n",
        encoding="utf-8",
    )

    mod.main()

    drafts = list((isolated_home / ".dream-studio" / "meta" / "draft-lessons").glob("correction-pattern-*.md"))
    assert len(drafts) == 1
    assert "route game builds to game agent" in drafts[0].read_text(encoding="utf-8")
