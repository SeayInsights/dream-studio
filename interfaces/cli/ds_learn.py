"""ds learn — Phase 19.3 operator review CLI.

Usage:
    ds learn review               — interactive review of pending classified signals
    ds learn review --limit N     — show up to N signals
    ds learn review --batch       — batch mode: show JSON, no interaction

Review is intentional ceremony, not constant pestering. Only call it when
you want to act on what the classifier has found.

Per-signal actions:
    c / confirm  — create ds_user_extensions row (status=proposed); signal won't resurface
    s / skip     — mark classification_skipped=1; signal permanently removed from review
    d / defer    — reset classification to NULL; will be reclassified next session
    q / quit     — exit without acting on remaining signals

WO-GF-CLI-split: this module is now a thin facade. The command set is
partitioned into three content siblings — ``ds_learn_review`` (`review`),
``ds_learn_expand`` (`expand`), and ``ds_learn_activation`` (`validate`/
`disambiguate`) — wired together by ``ds_learn_dispatch.add_learn_subcommand``
(there is no ``dispatch()``; routing is via ``set_defaults(func=cmd_X)``, with
``_learn_help`` as the bare `ds learn` group default). Every public and
private name that used to live here is re-exported below so existing imports
(``interfaces.cli.ds_learn.<name>``) keep working unchanged.
"""

from __future__ import annotations

from interfaces.cli.ds_learn_activation import cmd_disambiguate, cmd_validate
from interfaces.cli.ds_learn_dispatch import _learn_help, add_learn_subcommand
from interfaces.cli.ds_learn_expand import _get_compiler, cmd_expand
from interfaces.cli.ds_learn_review import (
    _format_signal,
    _get_classifier,
    _print_summary,
    cmd_review,
)

__all__ = [
    # Registration
    "add_learn_subcommand",
    "_learn_help",
    # ds_learn_review
    "_format_signal",
    "_get_classifier",
    "cmd_review",
    "_print_summary",
    # ds_learn_expand
    "_get_compiler",
    "cmd_expand",
    # ds_learn_activation
    "cmd_validate",
    "cmd_disambiguate",
]
