"""Profile layer (migration 159): a switchable operating-context identity.

A PROJECT is what work is being done; a PROFILE is which real-world engagement/identity
it is being done as (today: SeayInsights, Fulcrum -- more to come). Both are
independently "active" -- switching the active project does not touch the active
profile and vice versa. Every profile belongs to a client (core/clients), the existing
attribution layer this sits on top of; a client may have zero, one, or several profiles.

  - mutations.py — create_profile / switch_active_profile. Mirrors
    core.projects.mutations_activation.set_active_project's shape: a direct SQL dual-write
    (so the row is correct for a synchronous caller on return) plus a best-effort
    canonical event emission (profile.created / profile.activated / profile.deactivated)
    for the audit trail. There is no ProfileProjection in this change set -- nothing
    replays these events to rebuild business_profiles; the direct write is the only
    writer, the same as set_active_project before any replay path existed for it.
  - queries.py — list_profiles / active_profile / get_profile, read directly off
    business_profiles.

claude_config_dir and mcp_client_name are stored, inert columns in this change set. Two
follow-ups are deliberately NOT done here (see migration 159's own comment and the
module docstrings below):
  1. Wiring core.config.paths.claude_config_root() to prefer the active profile's
     claude_config_dir over the CLAUDE_CONFIG_DIR env var / default ~/.claude.
  2. An MCP client identity registry keyed by mcp_client_name.
"""
