#!/usr/bin/env python3
"""File-backed Work Order CLI for Phase 16B.

Commands in this file read/write only Work Order files. They do not inspect
target repos, open the native runtime DB, or emit runtime events.

WO-GF-CLI-split: this module is now a thin facade. It runs as a script
(``python interfaces/cli/ds_work_order.py``, no package context) as well as
an importable module, so it re-establishes its own REPO_ROOT/sys.path
bootstrap BEFORE importing its siblings — ``ds_work_order_core`` (create/
validate/status/render/record-result/report/regenerate-handoff/decision
commands + the shared safe-output-path helpers), ``ds_work_order_security``
(the three generate-security-*-handoff commands + YAML artifact loaders), and
``ds_work_order_parser`` (build_parser()/main()). Every public and private
name that used to live here is re-exported below so existing imports keep
working unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.work_orders import (  # noqa: E402
    SUPPORTED_RENDER_TARGETS,
    WorkOrderError,
    build_security_post_remediation_review_handoff_prompt,
    build_security_remediation_mutation_handoff_prompt,
    build_security_review_remediation_handoff_prompt,
    create_decision_request,
    decision_status,
    default_storage_root,
    evaluate_security_post_remediation_review_handoff_prompt,
    evaluate_security_remediation_mutation_handoff_prompt,
    evaluate_security_review_next_handoff_prompt,
    generate_report,
    load_work_order,
    load_work_order_file,
    record_operator_decision,
    record_result,
    regenerate_handoff_prompt,
    render_work_order,
    save_work_order,
    status_summary,
    validate_work_order,
)
from interfaces.cli.ds_work_order_core import (  # noqa: E402
    _assert_safe_handoff_output,
    _is_relative_to,
    _print_validation_errors,
    _safe_handoff_output_roots,
    _storage_root,
    cmd_create,
    cmd_decide,
    cmd_decision_request,
    cmd_record_result,
    cmd_regenerate_handoff,
    cmd_render,
    cmd_report,
    cmd_request_decision,
    cmd_status,
    cmd_validate,
)
from interfaces.cli.ds_work_order_parser import build_parser, main  # noqa: E402
from interfaces.cli.ds_work_order_security import (  # noqa: E402
    _load_yaml_dir,
    _load_yaml_mapping,
    cmd_generate_security_mutation_handoff,
    cmd_generate_security_next_handoff,
    cmd_generate_security_post_remediation_review_handoff,
)

__all__ = [
    "REPO_ROOT",
    # core.work_orders re-exports (kept for backward compatibility)
    "SUPPORTED_RENDER_TARGETS",
    "WorkOrderError",
    "build_security_post_remediation_review_handoff_prompt",
    "build_security_remediation_mutation_handoff_prompt",
    "build_security_review_remediation_handoff_prompt",
    "create_decision_request",
    "default_storage_root",
    "decision_status",
    "evaluate_security_post_remediation_review_handoff_prompt",
    "evaluate_security_remediation_mutation_handoff_prompt",
    "evaluate_security_review_next_handoff_prompt",
    "generate_report",
    "load_work_order",
    "load_work_order_file",
    "record_operator_decision",
    "record_result",
    "regenerate_handoff_prompt",
    "render_work_order",
    "save_work_order",
    "status_summary",
    "validate_work_order",
    # ds_work_order_core
    "_storage_root",
    "_print_validation_errors",
    "_is_relative_to",
    "_safe_handoff_output_roots",
    "_assert_safe_handoff_output",
    "cmd_create",
    "cmd_validate",
    "cmd_status",
    "cmd_render",
    "cmd_record_result",
    "cmd_report",
    "cmd_regenerate_handoff",
    "cmd_decision_request",
    "cmd_request_decision",
    "cmd_decide",
    # ds_work_order_security
    "_load_yaml_mapping",
    "_load_yaml_dir",
    "cmd_generate_security_next_handoff",
    "cmd_generate_security_mutation_handoff",
    "cmd_generate_security_post_remediation_review_handoff",
    # ds_work_order_parser
    "build_parser",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
