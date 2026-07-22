"""ds learn expand — compile personalization/capability/onboarding extensions.

Split from interfaces/cli/ds_learn.py (WO-GF-CLI-split).

No module-level ``import json`` here: every JSON use inside ``cmd_expand`` is
a function-local ``import json as _json`` (batch-mode dump and the compiled
content preview) — a module-level import would be unused (F401) since
nothing in this file references a bare ``json`` name.
"""

from __future__ import annotations

import sys


def _get_compiler(classified_as: str, conn):
    """Return the appropriate compiler for the classification type."""
    if classified_as == "capability":
        from core.expansion.capability import CapabilityCompiler

        return CapabilityCompiler(conn)
    if classified_as == "onboarding":
        from core.expansion.onboarding import OnboardingCompiler

        return OnboardingCompiler(conn)
    from core.expansion.personalization import PersonalizationCompiler

    return PersonalizationCompiler(conn)


def cmd_expand(args) -> int:
    """Compile extensions — personalization (19.4a), capability (19.4b), onboarding (19.4c)."""
    from core.expansion.personalization import PersonalizationCompiler
    from core.expansion.capability import CapabilityCompiler
    from core.expansion.onboarding import OnboardingCompiler
    from core.config.database import get_connection

    db_path = getattr(args, "db_path", None)
    extension_id = getattr(args, "extension_id", None)
    batch = getattr(args, "batch", False)
    show_events = getattr(args, "show_events", False)

    conn = get_connection() if db_path is None else __import__("sqlite3").connect(str(db_path))
    conn.row_factory = __import__("sqlite3").Row

    try:
        p_pending = PersonalizationCompiler(conn).get_pending_compilation()
        c_pending = CapabilityCompiler(conn).get_pending_compilation()
        o_pending = OnboardingCompiler(conn).get_pending_compilation()
    finally:
        conn.close()

    # Tag each item with its type so the CLI can route to the right compiler
    for item in p_pending:
        item["_compiler_type"] = "personalization"
    for item in c_pending:
        item["_compiler_type"] = "capability"
    for item in o_pending:
        item["_compiler_type"] = "onboarding"

    pending = p_pending + c_pending + o_pending

    if not pending:
        print("No extensions pending compilation.")
        return 0

    if batch:
        import json as _json

        print(_json.dumps(pending, indent=2))
        return 0

    # Filter to one extension if specified
    if extension_id:
        pending = [p for p in pending if p["extension_id"] == extension_id]
        if not pending:
            print(f"Extension {extension_id!r} not found or not eligible.", file=sys.stderr)
            return 1

    total = len(pending)
    print(f"\nds learn expand — {total} extension(s) pending compilation\n")
    accepted = rejected = failed = 0

    for i, item in enumerate(pending, 1):
        compiler_type = item.get("_compiler_type", "personalization")
        print(f"\n[{i}/{total}] Extension: {item['extension_id'][:8]}…  [{compiler_type}]")
        print(f"  Skill:    {item['skill_id']}")
        print(f"  Rule:     {item.get('rule_id') or 'N/A'}")
        print(f"  Reason:   {item.get('classification_reason') or '?'}")
        actions = "c=compile+accept  r=reject  q=quit"
        if compiler_type == "capability" and show_events:
            actions += "  (--show-events active)"
        print(f"  Actions:  {actions}")

        while True:
            try:
                choice = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ("c", "compile", "accept"):
                conn2 = (
                    get_connection()
                    if db_path is None
                    else __import__("sqlite3").connect(str(db_path))
                )
                conn2.row_factory = __import__("sqlite3").Row
                try:
                    compiler_inst = _get_compiler(compiler_type, conn2)
                    result = compiler_inst.compile_one(item["extension_id"])
                finally:
                    conn2.close()
                if result.success:
                    import json as _json

                    cited = getattr(result, "finding_ids_cited", None) or getattr(
                        result, "event_ids_cited", []
                    )
                    tokens = getattr(result, "tokens_estimated", 0)
                    cited_label = "findings" if compiler_type == "personalization" else "events"
                    print(
                        f"  ✓ Compiled ({len(cited)} {cited_label} cited{', ~' + str(tokens) + ' tokens' if tokens else ''})"
                    )
                    print(f"    Content preview: {_json.dumps(result.content)[:120]}…")
                    accepted += 1
                else:
                    print(f"  ✗ Compilation failed: {result.error}", file=sys.stderr)
                    if result.signal_deferred:
                        print("    (signal returned to deferred state)")
                    failed += 1
                break
            if choice in ("r", "reject"):
                conn3 = (
                    get_connection()
                    if db_path is None
                    else __import__("sqlite3").connect(str(db_path))
                )
                conn3.row_factory = __import__("sqlite3").Row
                try:
                    conn3.execute(
                        "DELETE FROM ds_user_extensions WHERE extension_id = ?",
                        (item["extension_id"],),
                    )
                    conn3.execute(
                        "UPDATE ds_friction_signals SET extension_id = NULL WHERE extension_id = ?",
                        (item["extension_id"],),
                    )
                    conn3.commit()
                finally:
                    conn3.close()
                print("  → Rejected (extension row removed)")
                rejected += 1
                break
            if choice in ("q", "quit"):
                print(f"\nStopped. {i - 1} processed.")
                print(f"Summary: {accepted} compiled, {rejected} rejected, {failed} failed.")
                return 0
            print("  Invalid. Use: c=compile+accept  r=reject  q=quit")

    # Phase 19.7: invalidate cache after any accept/reject (extension state changed)
    if accepted + rejected > 0:
        try:
            from core.expansion.loader import ExtensionLoader

            ExtensionLoader.invalidate_cache()
        except Exception:
            pass

    print(f"\nAll {total} extensions processed.")
    print(f"Summary: {accepted} compiled, {rejected} rejected, {failed} failed.")
    return 0
