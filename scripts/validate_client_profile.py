#!/usr/bin/env python3
"""
validate_client_profile.py — dream-studio client profile validator
Usage: py -3.12 scripts/validate_client_profile.py <profile.yaml>
Exits 0 on success, 1 on validation failure.
"""

import sys
import os

# ── PyYAML guard ────────────────────────────────────────────────────────────
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    print("  On this machine try: py -3.12 -m pip install pyyaml")
    sys.exit(1)


# ── Enum definitions ─────────────────────────────────────────────────────────
VALID_ENGAGEMENT_TYPES = {"vendor", "internal", "consulting"}
VALID_ISOLATION_MODELS = {"multi-tenant", "single-tenant", "none"}
VALID_PROXY_TYPES      = {"zscaler", "bluecoat", "palo-alto", "none"}
VALID_SCAN_SCHEDULES   = {"nightly", "weekly", "on-push-only"}
VALID_DASHBOARD_TOOLS  = {"powerbi", "none"}


# ── Validation rules ─────────────────────────────────────────────────────────
def validate(data: dict) -> list[str]:
    """
    Run all validation checks against a profile dict.
    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    # ── schema_version ───────────────────────────────────────────────────────
    sv = data.get("schema_version")
    if sv is None:
        errors.append("MISSING schema_version (expected: 1)")
    elif sv != 1:
        errors.append(f"INVALID schema_version '{sv}' (expected: 1)")

    # ── client block ─────────────────────────────────────────────────────────
    client = data.get("client")
    if not isinstance(client, dict):
        errors.append("MISSING or invalid 'client' block")
    else:
        for field in ("name", "contact", "github_org", "engagement_type"):
            if not client.get(field):
                errors.append(f"MISSING required field: client.{field}")

        et = client.get("engagement_type")
        if et and isinstance(et, str) and et not in VALID_ENGAGEMENT_TYPES:
            errors.append(
                f"INVALID client.engagement_type '{et}' "
                f"(valid: {sorted(VALID_ENGAGEMENT_TYPES)})"
            )
        elif et and not isinstance(et, str):
            errors.append(
                f"INVALID client.engagement_type: expected string, got {type(et).__name__}"
            )

    # ── data block ───────────────────────────────────────────────────────────
    if not isinstance(data.get("data"), dict):
        errors.append("MISSING or invalid 'data' block")

    # ── isolation block ──────────────────────────────────────────────────────
    isolation = data.get("isolation")
    if not isinstance(isolation, dict):
        errors.append("MISSING or invalid 'isolation' block")
    else:
        model = isolation.get("model")
        if not model:
            errors.append("MISSING required field: isolation.model")
        elif not isinstance(model, str):
            errors.append(f"INVALID isolation.model: expected string, got {type(model).__name__}")
            model = None  # prevent further checks on bad type
        elif model not in VALID_ISOLATION_MODELS:
            errors.append(
                f"INVALID isolation.model '{model}' "
                f"(valid: {sorted(VALID_ISOLATION_MODELS)})"
            )
        # Cross-reference: multi-tenant requires tenant_key
        if model == "multi-tenant" and not isolation.get("tenant_key"):
            errors.append(
                "CROSS-REF: isolation.model is 'multi-tenant' but "
                "isolation.tenant_key is missing or empty (required)"
            )

    # ── network block ────────────────────────────────────────────────────────
    network = data.get("network")
    if not isinstance(network, dict):
        errors.append("MISSING or invalid 'network' block")
    else:
        proxy = network.get("proxy")
        if not isinstance(proxy, dict):
            errors.append("MISSING or invalid 'network.proxy' block")
        else:
            proxy_type = proxy.get("type")
            if not proxy_type:
                errors.append("MISSING required field: network.proxy.type")
            elif not isinstance(proxy_type, str):
                errors.append(f"INVALID network.proxy.type: expected string, got {type(proxy_type).__name__}")
                proxy_type = None
            elif proxy_type not in VALID_PROXY_TYPES:
                errors.append(
                    f"INVALID network.proxy.type '{proxy_type}' "
                    f"(valid: {sorted(VALID_PROXY_TYPES)})"
                )

            # Cross-reference: non-none proxy requires ssl_inspection + custom_ca
            if proxy_type and isinstance(proxy_type, str) and proxy_type != "none":
                if proxy.get("ssl_inspection") is None:
                    errors.append(
                        f"CROSS-REF: network.proxy.type is '{proxy_type}' but "
                        "network.proxy.ssl_inspection is missing (required)"
                    )
                if proxy.get("custom_ca") is None:
                    errors.append(
                        f"CROSS-REF: network.proxy.type is '{proxy_type}' but "
                        "network.proxy.custom_ca is missing (required)"
                    )

    # ── stack block ──────────────────────────────────────────────────────────
    stack = data.get("stack")
    if not isinstance(stack, dict):
        errors.append("MISSING or invalid 'stack' block")
    else:
        langs = stack.get("languages")
        if not langs or not isinstance(langs, list):
            errors.append("MISSING required field: stack.languages (must be a non-empty list)")

    # ── compliance block ─────────────────────────────────────────────────────
    compliance = data.get("compliance")
    if not isinstance(compliance, dict):
        errors.append("MISSING or invalid 'compliance' block")
    else:
        frameworks = compliance.get("frameworks")
        if not frameworks or not isinstance(frameworks, list):
            errors.append("MISSING required field: compliance.frameworks (must be a non-empty list)")

    # ── scan block ───────────────────────────────────────────────────────────
    scan = data.get("scan")
    if not isinstance(scan, dict):
        errors.append("MISSING or invalid 'scan' block")
    else:
        schedule = scan.get("schedule")
        if not schedule:
            errors.append("MISSING required field: scan.schedule")
        elif not isinstance(schedule, str):
            errors.append(f"INVALID scan.schedule: expected string, got {type(schedule).__name__}")
        elif schedule not in VALID_SCAN_SCHEDULES:
            errors.append(
                f"INVALID scan.schedule '{schedule}' "
                f"(valid: {sorted(VALID_SCAN_SCHEDULES)})"
            )

    # ── dashboard block ──────────────────────────────────────────────────────
    dashboard = data.get("dashboard")
    if not isinstance(dashboard, dict):
        errors.append("MISSING or invalid 'dashboard' block")
    else:
        tool = dashboard.get("tool")
        if not tool:
            errors.append("MISSING required field: dashboard.tool")
        elif not isinstance(tool, str):
            errors.append(f"INVALID dashboard.tool: expected string, got {type(tool).__name__}")
        elif tool not in VALID_DASHBOARD_TOOLS:
            errors.append(
                f"INVALID dashboard.tool '{tool}' "
                f"(valid: {sorted(VALID_DASHBOARD_TOOLS)})"
            )

        # Validate org_score thresholds if present
        org_score = dashboard.get("org_score")
        if isinstance(org_score, dict):
            green = org_score.get("green_threshold")
            yellow = org_score.get("yellow_threshold")
            if green is not None and yellow is not None:
                if not isinstance(green, (int, float)):
                    errors.append("INVALID dashboard.org_score.green_threshold: must be a number")
                if not isinstance(yellow, (int, float)):
                    errors.append("INVALID dashboard.org_score.yellow_threshold: must be a number")
                if (isinstance(green, (int, float)) and isinstance(yellow, (int, float))
                        and yellow >= green):
                    errors.append(
                        f"INVALID thresholds: dashboard.org_score.yellow_threshold ({yellow}) "
                        f"must be less than green_threshold ({green})"
                    )

    return errors


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: py -3.12 scripts/validate_client_profile.py <profile.yaml>")
        return 1

    path = sys.argv[1]
    # Expand ~ so callers can pass ~/.dream-studio/... paths
    path = os.path.expanduser(path)

    if not os.path.isfile(path):
        print(f"ERROR: File not found: {path}")
        return 1

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"ERROR: Failed to parse YAML: {exc}")
        return 1

    if not isinstance(data, dict):
        print("ERROR: Profile must be a YAML mapping (dict), got:", type(data).__name__)
        return 1

    errors = validate(data)

    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s) in: {path}")
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}")
        return 1

    print(f"OK — profile is valid: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
