"""WO-README-SUBSTANTIATE: the `ds prove` transcript pasted in the README must not drift from
what the command actually emits. Volatile parts (scratch paths, UUIDs, content hashes) are
ignored; the STABLE structure — the four claim titles, the PASS verdicts, and the RESULT
line — is asserted against a live run, so a renamed claim, a PASS→FAIL, or a changed count
fails this test and forces the README to be updated.
"""

from __future__ import annotations

import re
from pathlib import Path

from interfaces.cli.commands.prove import prove_main

REPO_ROOT = Path(__file__).resolve().parents[2]


def _readme_prove_block() -> str:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # The fenced ```text block that contains the ds prove transcript.
    for block in re.findall(r"```text\n(.*?)```", text, re.DOTALL):
        if "ds prove" in block and "RESULT:" in block:
            return block
    raise AssertionError("no `ds prove` transcript block found in README.md")


def test_readme_transcript_matches_live_prove(capsys):
    import json

    rc = prove_main(as_json=True)
    live = json.loads(capsys.readouterr().out)
    block = _readme_prove_block()

    # Every claim title the command emits must appear verbatim in the pasted transcript.
    for claim in live["claims"]:
        assert claim["title"] in block, (
            f"README transcript is stale: claim {claim['claim']} title "
            f"{claim['title']!r} is not in the pasted block"
        )

    # The PASS/FAIL verdict count must match: all live claims pass → the block shows the same.
    live_passing = sum(1 for c in live["claims"] if c["passed"])
    block_pass = len(re.findall(r"→ PASS", block))
    assert rc == 0 and live["ok"] is True
    assert (
        block_pass == live_passing
    ), f"README shows {block_pass} PASS lines but a live run has {live_passing}"

    # The RESULT line must reflect the same count.
    total = len(live["claims"])
    assert f"RESULT: {live_passing}/{total} claims passed" in block
