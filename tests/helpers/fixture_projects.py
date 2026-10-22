"""Small projects, built in a temporary directory, with the shape a rule looks for.

The pre-launch rules decide what a project IS from what is on disk (a ``src/app`` web
tree or a migration that stores an email address is a consumer service; an
``interfaces/cli`` directory is a developer tool). Their tests used to point at a
sibling repository on the author's machine (``~/builds/dreamysuite``) and skip when it
was absent. That tested the sibling's current state, not the rule: it changed whenever
that project did, and on CI it never ran. Each helper here makes exactly the signals
the rule reads, so a test says which signal it relies on and can also remove it.
"""

from __future__ import annotations

from pathlib import Path

from tests.helpers.git_repo import commit, init_repo, tag


def consumer_service(
    root: Path,
    *,
    legal_documents: bool = False,
    tags: tuple[str, ...] = (),
    web_ui: bool = True,
    stores_email: bool = True,
) -> Path:
    """A consumer-facing service: a web UI plus a schema that stores an email address.

    Either signal alone makes the service a consumer one (``web_ui=False`` leaves only the
    schema; ``stores_email=False`` leaves a schema with no personal data), so a test can say
    which one it relies on. ``legal_documents`` adds the terms of service and privacy policy the
    consumer rules (pl-001, pl-002) look for. ``tags`` are release tags on the single commit.
    """
    column = "email text not null" if stores_email else "label text not null"
    files = {
        "supabase/migrations/001_users.sql": (
            f"create table users (id uuid primary key, {column});\n"
        ),
        "README.md": "A small consumer service.\n",
    }
    if web_ui:
        files["src/app/page.tsx"] = "export default function Home() { return null }\n"
    if legal_documents:
        files["TERMS.md"] = "# Terms of Service\n"
        files["PRIVACY.md"] = "# Privacy Policy\n"
    init_repo(root)
    commit(root, "initial", files=files)
    if tags:
        tag(root, *tags)
    return root


def developer_tool(root: Path, *, tags: tuple[str, ...] = ()) -> Path:
    """A command-line tool: it has an ``interfaces/cli`` directory and no web UI."""
    init_repo(root)
    commit(
        root,
        "initial",
        files={
            "interfaces/cli/main.py": "def main() -> int:\n    return 0\n",
            "pyproject.toml": '[project]\nname = "tool"\nversion = "0.1.0"\n',
        },
    )
    if tags:
        tag(root, *tags)
    return root
