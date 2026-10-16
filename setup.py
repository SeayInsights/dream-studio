"""Build hook: ship the runtime data that lives outside every package.

All project metadata lives in pyproject.toml. This file exists for one reason:
setuptools can only ship files that sit inside a package directory, and Dream
Studio's runtime reads a handful of files from the repository root (VERSION,
packs.yaml, config.yml, the canonical event schemas under docs/canonical, ...).
A wheel built without them installs a `ds` that cannot validate an event or
read its own version.

The list is pyproject.toml's [tool.dream-studio] shipped-root-data. Each match is
copied into the build tree at the SAME relative path, so the installed code root
(core.config.paths.code_root(): the directory holding the `core` package) has the
layout a checkout has. tests/unit/test_wheel_runs_without_checkout.py builds a
wheel and proves every entry lands.
"""

from __future__ import annotations

import glob
import os
import tomllib

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

_HERE = os.path.dirname(os.path.abspath(__file__))


def shipped_root_data(root: str = _HERE) -> list[str]:
    """Repo-relative POSIX paths of every root-level data file the wheel must carry."""
    with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
        patterns = tomllib.load(fh)["tool"]["dream-studio"]["shipped-root-data"]
    found: list[str] = []
    for pattern in patterns:
        matches = [
            m
            for m in glob.glob(os.path.join(root, pattern), recursive=True)
            if os.path.isfile(m) and "__pycache__" not in m
        ]
        if not matches:
            raise RuntimeError(f"shipped-root-data entry {pattern!r} matched no file")
        found.extend(os.path.relpath(m, root).replace(os.sep, "/") for m in sorted(matches))
    return found


class build_py(_build_py):
    """build_py that also copies shipped-root-data into the build tree."""

    def run(self) -> None:
        super().run()
        if getattr(self, "editable_mode", False):
            # An editable install imports from the checkout, which already has the files.
            return
        for rel in shipped_root_data():
            dest = os.path.join(self.build_lib, *rel.split("/"))
            self.mkpath(os.path.dirname(dest))
            self.copy_file(os.path.join(_HERE, *rel.split("/")), dest)


if __name__ == "__main__":
    # setuptools' build backend executes this file as __main__; importing it (the wheel
    # test reads shipped_root_data) must not start a build.
    setup(cmdclass={"build_py": build_py})
