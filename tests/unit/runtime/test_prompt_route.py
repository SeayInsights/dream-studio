"""WO-AUTOACT-B — UserPromptSubmit routing handler (on-prompt-route).

When a prompt carries an explicit Dream Studio trigger, the handler injects a
<dream-studio-routing> block naming the Skill to invoke. When it doesn't, the
handler stays silent. Triggers are derived from packs.yaml + mode metadata.yml,
longest-first so a specific trigger wins over a shorter prefix of another.
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import json
import sys
from pathlib import Path

import pytest

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
    lengths = [len(entry[0]) for entry in entries]
    assert lengths == sorted(lengths, reverse=True), "entries must be longest-trigger-first"


def test_matches_known_triggers_to_the_right_skill():
    entries = route._load_trigger_map(REPO)

    m = route._match("debug: my test keeps failing", entries)
    assert m is not None and m[1] == "ds-code-health", m

    # `resume:` reaches a COMMAND, not a skill. The ds-project pack was dissolved --
    # every operation it narrated was already a `ds project ...` command -- and the
    # eleven phrases that used to reach its resume mode now reach `ds project state`
    # through a command trigger declared in packs.yaml.
    m2 = route._match("resume: where was I", entries)
    assert m2 is not None, "resume: routed nowhere"
    assert m2[1] == "ds project state", m2
    assert m2[3] == "command", m2


def test_no_match_for_a_plain_prompt():
    entries = route._load_trigger_map(REPO)
    assert route._match("please refactor this small function for me", entries) is None


def test_route_emits_routing_block_on_trigger(monkeypatch, capsys):
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    route._route({"prompt": "resume: pick up where I left off"})
    out = capsys.readouterr().out
    assert "<dream-studio-routing>" in out
    # A command directive, not a Skill() call. Naming a skill that no longer exists would
    # be worse than silence: the model would go looking for it.
    assert "ds project state" in out
    assert "Skill(skill=" not in out


def test_route_stays_silent_without_trigger(monkeypatch, capsys):
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    route._route({"prompt": "just a normal request with no trigger at all"})
    assert capsys.readouterr().out.strip() == ""


# ---------------------------------------------------------------------------
# The regression that mattered.
#
# The tests above used to call route.main({...}) directly. The production
# dispatcher (control/execution/dispatch_tracking.py) assigns the payload to
# sys.stdin and calls mod.main() with ZERO arguments. Because main() declared a
# required `payload` parameter, every real dispatch raised TypeError — 8,767
# out of 8,767 between 2026-07-19 and 2026-09-17 — while these unit tests
# stayed green, because they never used the calling convention that production
# uses. The tests below exercise that convention.
# ---------------------------------------------------------------------------


def test_main_takes_no_arguments():
    """The dispatcher calls mod.main() with no args; main must accept that."""
    sig = inspect.signature(route.main)
    required = [
        p
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    assert not required, (
        f"main() must take no required arguments — dispatch_tracking.py calls "
        f"mod.main() with zero args. Found required: {[p.name for p in required]}"
    )


def test_main_reads_the_payload_from_stdin_like_the_dispatcher_does(monkeypatch, capsys):
    """End-to-end through the real convention: set sys.stdin, then main()."""
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"prompt": "resume: pick up where I left off"}))
    )
    route.main()
    out = capsys.readouterr().out
    assert (
        "<dream-studio-routing>" in out
    ), "main() produced no routing block when driven the way production drives it"
    assert "ds project state" in out


@pytest.mark.parametrize("raw", ["", "   ", "not json at all", "[1, 2, 3]", "null"], ids=repr)
def test_main_survives_a_malformed_payload(monkeypatch, capsys, raw):
    """A hook that raises is swallowed and recorded as failed — so don't raise."""
    monkeypatch.setattr(route, "_PLUGIN_ROOT", REPO)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    route.main()
    assert capsys.readouterr().out.strip() == ""
