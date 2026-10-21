"""A pack manifest that does not load must not take `ds` down with it.

MEASURED. `--type choices=work_order_type_names()` ran while the argument parser was BUILT, which is
before every command. With `contributes.gates` declared (refused today, because nothing reads it),
`ds --help`, `version`, `status`, `doctor` and `project list` all exited 1 with a raw traceback, and
`ds doctor` is the command an operator reaches for to find out why.

The parser now builds whatever the manifest holds. Commands that read a work-order type fail with
ONE line naming the manifest and the pack, and `ds doctor` reports the manifest as a finding.

Each case runs `ds` in a subprocess with the running manifest pointed at a broken file, because the
failure was an uncaught exception at process start and only a process shows that.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BROKEN = (
    "schema_version: 2\n" "packs:\n" "  legal:\n" "    contributes:\n" "      gates: [anything]\n"
)

#: Points the running manifest at a file, as the registry would find it in a real install, then runs
#: ds. Patching the resolver, not the registry: the whole load path stays the real one.
_BOOT = (
    "import sys\n"
    "from pathlib import Path\n"
    "import core.work_orders.type_manifest as m\n"
    "target = Path(sys.argv.pop(1))\n"
    "m.default_manifest_path = lambda: target\n"
    "from interfaces.cli.ds import main\n"
    "sys.exit(main(sys.argv[1:]))\n"
)


@pytest.fixture
def broken_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "packs.yaml"
    path.write_text(BROKEN, encoding="utf-8")
    return path


def _ds(manifest: Path, *args: str, home: Path) -> subprocess.CompletedProcess:
    home.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("DREAM_STUDIO")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    return subprocess.run(
        [sys.executable, "-c", _BOOT, str(manifest), "--home", str(home), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(home),
        env=env,
        timeout=300,
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["version"],
        ["status"],
        ["work-order", "--help"],
        ["work-order", "create", "--help"],
    ],
    ids=["help", "version", "status", "work-order-help", "create-help"],
)
def test_the_parser_builds_and_these_commands_run_with_a_broken_manifest(
    broken_manifest, tmp_path, args
):
    proc = _ds(broken_manifest, *args, home=tmp_path / "home")
    assert "Traceback" not in proc.stderr, proc.stderr[-1500:]
    assert "PackManifestError" not in proc.stderr
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr[-800:])


def test_doctor_reports_the_broken_manifest_as_a_finding_not_a_crash(broken_manifest, tmp_path):
    proc = _ds(broken_manifest, "doctor", home=tmp_path / "home")
    assert "Traceback" not in proc.stderr, proc.stderr[-1500:]
    report = json.loads(proc.stdout)
    check = report["checks"]["pack_work_order_types"]
    assert check["ok"] is False
    assert str(broken_manifest) in check["error"] and "'legal'" in check["error"]
    assert "unsupported key" in check["error"]
    assert report["status"] in ("attention_required", "fail"), report["status"]


def test_a_command_that_reads_a_type_fails_in_one_line_naming_the_manifest(
    broken_manifest, tmp_path
):
    proc = _ds(
        broken_manifest,
        "work-order",
        "create",
        "p-1",
        "--milestone",
        "m-1",
        "--title",
        "A thing",
        "--description",
        "A description long enough to pass the prompt floor for a work order, easily.",
        "--module-boundary",
        "core/x",
        "--type",
        "documentation",
        home=tmp_path / "home",
    )
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1, lines
    assert lines[0].startswith("error: ") and str(broken_manifest) in lines[0]
    assert "'legal'" in lines[0] and "ds doctor" in lines[0]


def test_doctor_lists_what_a_loaded_pack_type_weakens(tmp_path):
    """For a manifest that loads, the doctor shows the governance profile of each pack type: the
    operator's chance to see what they are trusting."""
    manifest = tmp_path / "packs.yaml"
    manifest.write_text(
        "schema_version: 2\n"
        "packs:\n"
        "  legal:\n"
        "    contributes:\n"
        "      work_order_types:\n"
        "        - {name: contract_review, artifact_class: document, description: A contract,"
        " ui_bearing: false, exempt_from_verification: false}\n",
        encoding="utf-8",
    )
    proc = _ds(manifest, "doctor", home=tmp_path / "home")
    check = json.loads(proc.stdout)["checks"]["pack_work_order_types"]
    assert check["ok"] is True
    (profile,) = check["pack_types"]
    assert profile["type"] == "contract_review" and profile["declared_by"] == "legal"
    assert profile["review_rules"] == 5 and profile["independent_review_at_close"] is True


def test_the_help_still_lists_the_declared_types_when_the_manifest_is_fine():
    from interfaces.cli.ds import build_parser

    sub = next(a for a in build_parser()._actions if a.dest == "command")
    wo = sub.choices["work-order"]
    wo_sub = next(a for a in wo._actions if getattr(a, "choices", None) and "create" in a.choices)
    type_action = next(a for a in wo_sub.choices["create"]._actions if a.dest == "work_order_type")
    assert type_action.choices is not None and "documentation" in type_action.choices
