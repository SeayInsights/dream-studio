"""The append-only hook queue: two writers, one reader, one framing.

PostToolUse fires on every tool call. It used to cold-load pydantic, jsonschema
and the event store to append one telemetry row -- 283 ms per tool call, of
which 196 ms was import. It now appends a line and exits.

That splits one hook into two programs in two languages (enqueue.py and the
Rust ds-enqueue), writing the same file, read by a third (hookq.drain). These
tests exist because that is three chances to disagree about framing, and they
already disagreed once: Python's text-mode open silently wrote \\r\\n on Windows
while the native binary wrote \\n, so a byte-level read of a file both had
touched would not parse.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import hookq, paths

REPO = Path(__file__).resolve().parents[2]
ENQUEUE_PY = REPO / "runtime" / "hooks" / "enqueue.py"
ENQUEUE_EXE = (
    REPO / "runtime" / "hooks" / "enqueue-native" / "target" / "release" / "ds-enqueue.exe"
)

#: Payloads that have historically broken one framing or another.
NASTY = [
    '{"tool_name":"Read"}',
    '{"q":"he said \\"hi\\""}',
    '{"nl":"line1\nline2"}',  # a raw newline MUST NOT split the record
    '{"crlf":"a\r\nb"}',  # nor a carriage return
    '{"tab":"x\ty"}',
    '{"uni":"é✓\U0001f600"}',
    '{"ctrl":"\x01\x02"}',
    "{}",
    "not json at all",
]


@pytest.fixture
def ds_home(tmp_path, monkeypatch):
    home = tmp_path / ".dream-studio"
    (home / "state").mkdir(parents=True)
    monkeypatch.setenv("DS_HOME", str(home))
    monkeypatch.setattr(paths, "user_data_dir", lambda: home)
    monkeypatch.setattr(paths, "state_dir", lambda: home / "state")
    return home


def _enqueue_py(payload: str, event: str = "PostToolUse") -> None:
    subprocess.run(
        [sys.executable, str(ENQUEUE_PY), event],
        input=payload.encode("utf-8"),
        check=True,
        capture_output=True,
    )


def _enqueue_native(payload: str, event: str = "PostToolUse") -> None:
    subprocess.run(
        [str(ENQUEUE_EXE), event],
        input=payload.encode("utf-8"),
        check=True,
        capture_output=True,
    )


native = pytest.mark.skipif(
    not ENQUEUE_EXE.is_file(),
    reason="native enqueuer not built (cargo build --release in runtime/hooks/enqueue-native)",
)


# --- the contract that keeps the two writers interchangeable ----------------


def test_python_and_native_resolve_the_same_queue_path(ds_home):
    """Three copies of one path rule. They must agree or records go missing."""
    _enqueue_py('{"tool_name":"A"}')
    assert hookq.queue_path().is_file(), "enqueue.py wrote somewhere hookq does not read"


@native
def test_native_writes_where_hookq_reads(ds_home):
    _enqueue_native('{"tool_name":"A"}')
    assert hookq.queue_path().is_file(), "the native binary wrote somewhere hookq does not read"


@native
def test_both_writers_use_one_framing(ds_home):
    """The \\r\\n regression: mixed framing in one file is unparseable as bytes."""
    _enqueue_py('{"tool_name":"py"}')
    _enqueue_native('{"tool_name":"native"}')
    raw = hookq.queue_path().read_bytes()
    assert b"\r" not in raw, "a writer is emitting CRLF; the other is not"
    lines = [ln for ln in raw.split(b"\n") if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln.decode("utf-8"))  # raises if framing broke


@pytest.mark.parametrize("payload", NASTY)
def test_python_writer_survives_nasty_payloads(ds_home, payload):
    _enqueue_py(payload)
    raw = hookq.queue_path().read_bytes()
    lines = [ln for ln in raw.split(b"\n") if ln.strip()]
    assert len(lines) == 1, "payload broke the one-record-per-line contract"
    assert json.loads(lines[0].decode("utf-8"))["payload"] == payload


@native
@pytest.mark.parametrize("payload", NASTY)
def test_native_writer_survives_nasty_payloads(ds_home, payload):
    _enqueue_native(payload)
    raw = hookq.queue_path().read_bytes()
    lines = [ln for ln in raw.split(b"\n") if ln.strip()]
    assert len(lines) == 1, "payload broke the one-record-per-line contract"
    assert json.loads(lines[0].decode("utf-8"))["payload"] == payload


# --- drain ------------------------------------------------------------------


def test_drain_replays_every_record_in_order(ds_home):
    for i in range(5):
        _enqueue_py(json.dumps({"n": i}))
    seen: list[tuple[str, str]] = []
    assert hookq.drain(lambda e, p: seen.append((e, p))) == 5
    assert [json.loads(p)["n"] for _, p in seen] == [0, 1, 2, 3, 4]
    assert all(e == "PostToolUse" for e, _ in seen)


def test_drain_consumes_the_queue(ds_home):
    _enqueue_py('{"tool_name":"A"}')
    assert hookq.drain(lambda e, p: None) == 1
    assert hookq.drain(lambda e, p: None) == 0, "a second drain must find nothing"


def test_drain_of_an_empty_queue_is_free(ds_home):
    assert hookq.drain(lambda e, p: None) == 0


def test_a_handler_that_raises_does_not_strand_the_queue(ds_home):
    """One poisonous record must not block every record behind it."""
    for i in range(4):
        _enqueue_py(json.dumps({"n": i}))
    ok: list[int] = []

    def handler(event, payload):
        n = json.loads(payload)["n"]
        if n == 1:
            raise RuntimeError("boom")
        ok.append(n)

    assert hookq.drain(handler) == 4
    assert ok == [0, 2, 3], "records after the failure must still be processed"


def test_a_torn_line_does_not_strand_the_file(ds_home):
    """A writer killed mid-append leaves a partial line.

    The honest guarantee is narrower than "lose only itself": an append-only log
    has no delimiter before the tear, so the next record is glued to the
    fragment and both are unreadable. What must hold is that the damage stops
    there -- records already on disk still drain, and the file is not abandoned.
    """
    _enqueue_py('{"tool_name":"A"}')
    with hookq.queue_path().open("a", encoding="utf-8", newline="") as fh:
        fh.write('{"event":"PostToolUse","payl')  # no newline: a torn write
    _enqueue_py('{"tool_name":"B"}')  # glued to the fragment; lost with it

    seen: list[str] = []
    hookq.drain(lambda e, p: seen.append(p))

    tools = [json.loads(p)["tool_name"] for p in seen if p.strip().startswith("{")]
    assert "A" in tools, "a complete record written before the tear must survive"
    assert hookq.pending_count() == 0, "the file must be consumed, not abandoned"


def test_drain_is_capped_between_files(ds_home, monkeypatch):
    """A drain must not become the new long pole; the queue is durable on disk."""
    monkeypatch.setattr(hookq, "MAX_RECORDS_PER_DRAIN", 3)
    state = ds_home / "state"
    for f in range(3):  # three rotated files, two records each
        lines = [
            json.dumps({"event": "PostToolUse", "ts": 0, "payload": json.dumps({"n": f * 2 + i})})
            for i in range(2)
        ]
        (state / f"hookq.{f}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline=""
        )

    processed = hookq.drain(lambda e, p: None)
    assert processed == 4, "files are finished, so the budget overshoots by at most one file"
    assert hookq.pending_count() == 2, "the untouched file waits for the next drain"


def test_the_cap_never_redelivers(ds_home, monkeypatch):
    """The bug this replaced: a mid-file stop re-ran everything already handled."""
    monkeypatch.setattr(hookq, "MAX_RECORDS_PER_DRAIN", 3)
    state = ds_home / "state"
    for f in range(3):
        lines = [
            json.dumps({"event": "PostToolUse", "ts": 0, "payload": json.dumps({"n": f * 2 + i})})
            for i in range(2)
        ]
        (state / f"hookq.{f}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline=""
        )

    seen: list[int] = []
    hookq.drain(lambda e, p: seen.append(json.loads(p)["n"]))
    hookq.drain(lambda e, p: seen.append(json.loads(p)["n"]))

    assert sorted(seen) == [0, 1, 2, 3, 4, 5], "every record exactly once across both drains"
    assert len(seen) == len(set(seen)), "no record may be delivered twice"


def test_an_interrupted_drain_is_recovered(ds_home):
    """Drain rotates before reading, so a crash leaves a file, not a hole."""
    for i in range(3):
        _enqueue_py(json.dumps({"n": i}))

    def die(event, payload):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        hookq.drain(die)

    # The rotated file is still on disk; a later drain must pick it up.
    seen: list[str] = []
    assert hookq.drain(lambda e, p: seen.append(p)) == 3
    assert len(seen) == 3


def test_pending_count_does_not_consume(ds_home):
    for i in range(3):
        _enqueue_py(json.dumps({"n": i}))
    assert hookq.pending_count() == 3
    assert hookq.pending_count() == 3, "counting must not drain"
    assert hookq.drain(lambda e, p: None) == 3
