"""Doctor checks — composite health view used by `ds doctor`.

The pure read-only path is `run_doctor_checks(fix=False)`. The `--fix` path
remains driven from the CLI wrapper in `interfaces/cli/ds.py` because it
shells out to `ds integrate install`, `ds spool ingest`, and `ds update`
which are themselves CLI-bound; A2 will decompose those subprocess
re-invocations into direct calls.

WO-GF-CORE-HEALTH-SKILLS: implementation moved to doctor_{shared,skill_sync,
checks,main}.py; this module re-exports the public+private surface so
existing `from core.health.doctor import X` callers are unchanged.
"""

from __future__ import annotations

from .doctor_checks import (
    _check_agents_installed,
    _check_dispatcher_hooks,
    _check_failed_events,
    _check_handoff_spawner,
    _check_hook_freshness,
    _check_stale_dbs,
    _check_version_current,
)
from .doctor_main import run_doctor_checks
from .doctor_shared import (
    _CLI_REFERENCE_PATTERN,
    _ENTRY_HOOK_RELPATHS,
    _ROUTING_BEGIN,
    _ROUTING_END,
)
from .doctor_skill_sync import (
    _check_enforcement_block_no_cli,
    _check_pack_mode_coverage,
    _check_routing_trigger_coverage,
    _check_skill_freshness,
    _check_skills_installed,
    _compute_directory_hash,
    _get_expected_skill_ids,
    _installed_modes_dir,
    _resolve_canonical_skill_dir,
    _synthesized_skill_transform,
)

__all__ = [
    "_CLI_REFERENCE_PATTERN",
    "_ENTRY_HOOK_RELPATHS",
    "_ROUTING_BEGIN",
    "_ROUTING_END",
    "_check_agents_installed",
    "_check_dispatcher_hooks",
    "_check_enforcement_block_no_cli",
    "_check_failed_events",
    "_check_handoff_spawner",
    "_check_hook_freshness",
    "_check_pack_mode_coverage",
    "_check_routing_trigger_coverage",
    "_check_skill_freshness",
    "_check_skills_installed",
    "_check_stale_dbs",
    "_check_version_current",
    "_compute_directory_hash",
    "_get_expected_skill_ids",
    "_installed_modes_dir",
    "_resolve_canonical_skill_dir",
    "_synthesized_skill_transform",
    "run_doctor_checks",
]
