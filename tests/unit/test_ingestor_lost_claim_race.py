"""WO 00d223a8: losing a spool claim race was recorded as a failure.

``ingest`` globs the spool directory, then ``_process_one`` claims each file with
``os.replace``. Overlapping runs are routine — the pulse hooks and
``ds doctor --fix`` both ingest — so two runs regularly glob the same file and
one loses the rename with ``FileNotFoundError``.

The generic ``except Exception`` handler recorded that as a FAILURE. It is not
one: the winner is processing the event and nothing is lost. Worse, the record
could never drain, because ``_move_to_failed`` cannot move a file that is already
gone. The phantoms accumulated past the threshold ``ds doctor`` treats as
critical, so a healthy install reported ``fail`` — the loose failed count climbed
from 892 to 970 inside a single session.

The second test is the one that matters for safety: widening an exception handler
is exactly how a real failure gets silently reclassified as a skip, so a genuinely
malformed event still has to land in ``failed`` with a reason.
"""

from __future__ import annotations

import json
from pathlib import Path

from spool.ingestor import ingest
from spool.states import ensure_dirs


def _spool_a_file(root: Path, name: str, body: str) -> Path:
    ensure_dirs(root)
    p = root / "spool" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _reason_files(root: Path) -> list[Path]:
    return list((root / "failed" / "reasons").glob("*.reason.json"))


def test_lost_claim_race_counts_as_skipped_not_failed(tmp_path, monkeypatch) -> None:
    """A rename that loses the race is a skip and leaves no trace behind."""
    from spool import ingestor

    _spool_a_file(tmp_path, "evt-race.json", json.dumps({"event_id": "evt-race"}))

    def _claimed_by_someone_else(src, dst):
        raise FileNotFoundError(2, "The system cannot find the file specified", str(src))

    # Patch at the real claim site rather than stubbing _process_one, so this
    # exercises the same call that loses the race in production.
    monkeypatch.setattr(ingestor.os, "replace", _claimed_by_someone_else)

    result = ingest(root=tmp_path, db_path=tmp_path / "t.db")

    assert result.skipped == 1
    assert result.failed == 0
    assert _reason_files(tmp_path) == []


def test_a_real_failure_is_still_recorded(tmp_path) -> None:
    """Widening the handler must not reclassify genuine failures as skips."""
    _spool_a_file(tmp_path, "evt-broken.json", "{ this is not json")

    result = ingest(root=tmp_path, db_path=tmp_path / "t.db")

    assert result.failed == 1
    assert result.skipped == 0

    reasons = _reason_files(tmp_path)
    assert len(reasons) == 1
    assert "parse_error" in json.loads(reasons[0].read_text(encoding="utf-8"))["reason"]
