"""WO-AUTOACT-B — UserPromptSubmit routing handler (on-prompt-route).

When a prompt carries an explicit Dream Studio trigger, the handler injects a
<dream-studio-routing> block naming the Skill to invoke. When it doesn't, the
handler stays silent. Triggers are derived from packs.yaml + mode metadata.yml,
longest-first so a specific trigger wins over a shorter prefix of another.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_HANDLER = REPO / "runtime" / "hooks" / "meta" / "on-prompt-route.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("on_prompt_route_under_test", _HANDLER)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


route = _load_module()


def test_trigger_map_is_populated_and_longest_first():
    entries = route._load_trigger_map(REPO)
    assert entries, "expected a non-empty trigger map from packs.yaml"
    lengths = [len(t) for t, _, _ in entries]
    assert lengths == sorted(lengths, reverse=True), "entries must be longest-trigger-first"


def test_matches_known_triggers_to_the_right_skill():
    entries = route._load_trigger_map(REPO)

    m = route._match("debug: my test keeps failing", entries)
    assert m is not None and m[1] == "ds-quality", m

    m2 = route._match("resume: where was I", entries)
    assert m2 is not None and m2[1] == "ds-project", m2


def test_no_match_for_a_plain_prompt():
    entries = route._load_trigger_map(REPO)
    assert route._match("please refactor this small function for me", entries) is None


def test_main_emits_routing_block_on_trigger(monkeypatch, capsys):
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    route.main({"prompt": "resume: pick up where I left off"})
    out = capsys.readouterr().out
    assert "<dream-studio-routing>" in out
    assert 'Skill(skill="ds-project"' in out


def test_main_stays_silent_without_trigger(monkeypatch, capsys):
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    route.main({"prompt": "just a normal request with no trigger at all"})
    assert capsys.readouterr().out.strip() == ""
