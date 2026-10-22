"""The operator's pack-trust file is the one in the home the command runs against.

MEASURED. `build_parser()` reads the work-order type registry (for `--type`'s choices) before
`--home` has been applied, and a successful load is cached for the process. With an ambient
`DREAM_STUDIO_HOME=H1` whose trust file allows the legal pack, `ds --home H0 doctor` (H0 has no
trust file) accepted the pack's exemption: the allowance of one home was spent in another.
`ds mcp serve --home H0` went through the same ordering.

A load that leaned on the trust file is validated again when the home changes, so the home the
command names is the home whose allowance counts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.work_orders import type_manifest, type_registry
from core.work_orders.type_registry import PackManifestError, work_order_type_names

REPO_ROOT = Path(__file__).resolve().parents[2]

EXEMPT_MANIFEST = (
    "schema_version: 2\n"
    "packs:\n"
    "  legal:\n"
    "    contributes:\n"
    "      work_order_types:\n"
    "        - {name: contract_review, artifact_class: document, description: A contract,"
    " ui_bearing: false, exempt_from_verification: true}\n"
)

_BOOT = (
    "import sys\n"
    "from pathlib import Path\n"
    "import core.work_orders.type_manifest as m\n"
    "target = Path(sys.argv.pop(1))\n"
    "m.default_manifest_path = lambda: target\n"
    "from interfaces.cli.ds import main\n"
    "sys.exit(main(sys.argv[1:]))\n"
)


def _home(tmp_path: Path, name: str, *, trusts: bool) -> Path:
    home = tmp_path / name
    home.mkdir()
    if trusts:
        (home / "pack-trust.yaml").write_text(
            "exempt_from_verification: [legal]\n", encoding="utf-8"
        )
    return home


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "packs.yaml"
    path.write_text(EXEMPT_MANIFEST, encoding="utf-8")
    return path


def _doctor(manifest: Path, ambient: Path, *argv: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DREAM_STUDIO")}
    env.update(PYTHONPATH=str(REPO_ROOT), PYTHONIOENCODING="utf-8", DREAM_STUDIO_HOME=str(ambient))
    proc = subprocess.run(
        [sys.executable, "-c", _BOOT, str(manifest), *argv, "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ambient),
        env=env,
        timeout=300,
    )
    assert "Traceback" not in proc.stderr, proc.stderr[-1500:]
    return json.loads(proc.stdout)["checks"]["pack_work_order_types"]


def test_ds_home_decides_whose_trust_file_counts_not_the_ambient_home(manifest, tmp_path):
    trusting = _home(tmp_path, "h1", trusts=True)
    bare = _home(tmp_path, "h0", trusts=False)

    refused = _doctor(manifest, trusting, "--home", str(bare))
    assert refused["ok"] is False, "the ambient home's allowance was spent under --home"
    assert "exempt_from_verification: true" in refused["error"] and "'legal'" in refused["error"]

    assert _doctor(manifest, trusting, "--home", str(trusting))["ok"] is True
    assert _doctor(manifest, trusting)["ok"] is True, "no --home: the ambient home is the home"
    # The flag wins over an ambient home that does not allow it.
    assert _doctor(manifest, bare, "--home", str(trusting))["ok"] is True
    assert _doctor(manifest, bare)["ok"] is False


@pytest.fixture
def unloaded(monkeypatch, manifest):
    builtins = {
        n: t
        for n, t in type_registry._REGISTRY.items()
        if n in type_registry.builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: manifest)


def _serve_under(monkeypatch, ambient: Path, home: Path):
    """Run `ds --home <home> mcp serve` in-process with the server stubbed out, and report what
    the registry says from inside it: the type names, or the error it raised."""
    from interfaces.cli.ds import main

    seen: dict[str, object] = {}

    def fake_run(app, host, port):
        try:
            seen["names"] = work_order_type_names()
        except PackManifestError as exc:
            seen["error"] = str(exc)

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(ambient))
    assert main(["--home", str(home), "mcp", "serve"]) == 0
    return seen


def test_mcp_serve_home_decides_whose_trust_file_counts(unloaded, tmp_path, monkeypatch):
    trusting = _home(tmp_path, "h1", trusts=True)
    bare = _home(tmp_path, "h0", trusts=False)

    seen = _serve_under(monkeypatch, ambient=trusting, home=bare)
    assert "error" in seen and "exempt_from_verification: true" in str(seen["error"]), seen


def test_mcp_serve_under_a_home_that_allows_it_serves_the_pack_types(
    unloaded, tmp_path, monkeypatch
):
    trusting = _home(tmp_path, "h1", trusts=True)
    bare = _home(tmp_path, "h0", trusts=False)

    seen = _serve_under(monkeypatch, ambient=bare, home=trusting)
    assert "contract_review" in seen.get("names", ()), seen
