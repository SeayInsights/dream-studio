# Publication Boundary

Dream Studio is public source plus private local authority. The public GitHub repository should accurately represent the current product without publishing private operational history.

## Public Allowlist

The public repo may contain:

- product source code;
- public documentation;
- schema migrations and tests;
- examples, templates, and synthetic fixtures;
- adapter projection templates;
- sanitized demos;
- sanitized release notes;
- public license, security, and contribution guidance.

## Private By Default

Keep these out of Git unless separately sanitized and approved:

- `.dream-studio/` runtime state;
- SQLite DB files, WAL/SHM files, dumps, and backups;
- local Work Orders, handoffs, continuation packets, approval artifacts, and operator decisions;
- raw telemetry, raw logs, hook traces, dashboard runtime logs, and token traces;
- cutover, cleanup, rollback, dogfood, release, and local audit evidence;
- generated prompts and private context packets;
- external-project details not intentionally public;
- secret, credential, token, or private data values.

## Current Repo Hygiene

`.gitignore` excludes local runtime state, database files, backups, logs, and local evidence exports. If a private file has been committed in the past, remove it from current tracking without deleting the local copy, then classify whether history rewrite is required.

Repo publication readiness is checked through the repo-owned command:

```powershell
python interfaces\cli\repo_publication_readiness.py --strict
```

The command audits tracked file paths, ignored/untracked boundaries, Git history
path names, Apache-2.0 references, README/PRD product framing, and
private-content/secret-pattern rules without printing matched secret values.
Use `--execute --output-dir docs\publication` only when intentionally
refreshing public publication evidence artifacts.

## Git History Policy

- Non-secret historical product docs can usually remain in history after current-state cleanup.
- Private local DB backups, raw logs, local evidence, or sensitive operator state in history require a history rewrite risk assessment.
- Secrets, credentials, tokens, or sensitive private data in history require immediate operator approval before any rewrite and should trigger rotation guidance.
- Never force-push or rewrite remote history without explicit operator approval.

## Documentation Rule

Public docs should describe Dream Studio as a local-first AI orchestration and operational intelligence platform. Adapter-specific docs may describe Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP, shell, or local-model surfaces, but must not frame any adapter as the product itself.

## Contract Atlas Export Rule

The Contract Atlas is private/local by default. Public atlas exports are allowed
only when sanitized: local paths, live runtime state, local adapter config
contents, private evidence paths, backups, raw telemetry, and operator-specific
metadata must be removed or replaced with non-sensitive placeholders.

`ds contract-atlas-refresh --output-dir <dir> --execute` is the supported export
refresh surface. It writes the public sanitized atlas and freshness manifest to
an explicit directory, and writes a private/internal atlas only when
`--include-private` is supplied. Private/internal exports are not repo-safe and
must remain in operator-local runtime or review locations.
