"""Integration test for on-meta-review."""

from __future__ import annotations

from datetime import datetime, timezone


def _make_session_context(path, themes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, theme in enumerate(themes):
        blocks.append(
            f"## Session End — 2026-04-1{i}T00:00:00Z\n"
            f"**Session:** sess-{i}\n"
            f"**Tokens used:** {100 + i * 10}\n"
            f"**Summary:** did some {theme} work\n"
        )
    path.write_text("\n---\n".join(blocks), encoding="utf-8")


def test_no_context_file_is_noop(isolated_home, handler):
    mod = handler("on-meta-review")
    mod.main()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert not (isolated_home / ".dream-studio" / "meta" / f"review-{date_str}.md").exists()


def test_generates_review_and_drafts_theme_lessons(isolated_home, handler):
    context_path = isolated_home / ".dream-studio" / "planning" / "session-context.md"
    _make_session_context(context_path, ["build", "build", "build", "fix"])

    mod = handler("on-meta-review")
    mod.main()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    review = (isolated_home / ".dream-studio" / "meta" / f"review-{date_str}.md").read_text(encoding="utf-8")
    assert "Weekly Meta-Review" in review
    assert "**build**" in review

    drafts = list((isolated_home / ".dream-studio" / "meta" / "draft-lessons").glob("theme-build-*.md"))
    assert len(drafts) == 1
