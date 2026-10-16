"""A main-CI failure reason is cut at a word, not in the middle of one."""

from core.health.main_ci import _clip


def test_a_long_reason_is_cut_at_a_word_boundary():
    text = "gh: could not resolve the repository because authentication failed " * 5
    clipped = _clip(text, 60)
    assert len(clipped) <= 60 and clipped.endswith("...")
    assert text.startswith(clipped[:-3]) and text[len(clipped) - 3] == " "


def test_a_short_reason_is_untouched():
    assert _clip("gh exited 1", 200) == "gh exited 1"
