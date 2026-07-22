"""ds learn validate/disambiguate — retroactive validation and collision resolution.

Split from interfaces/cli/ds_learn.py (WO-GF-CLI-split).

No module-level ``import json`` here: ``cmd_disambiguate``'s JSON use is all
function-local (``import json as _json`` / ``import json as _j``) — a
module-level import would be unused (F401) since nothing in this file
references a bare ``json`` name.
"""

from __future__ import annotations

import sys


def cmd_validate(args) -> int:
    """Retroactive validation for compiled extensions (19.5)."""
    from core.expansion.validation import RetroactiveValidator
    from core.config.database import get_connection

    db_path = getattr(args, "db_path", None)
    extension_id = getattr(args, "extension_id", None)
    all_proposed = getattr(args, "all_proposed", False)
    force = getattr(args, "force", False)

    conn = get_connection() if db_path is None else __import__("sqlite3").connect(str(db_path))
    conn.row_factory = __import__("sqlite3").Row
    validator = RetroactiveValidator(conn, db_path=db_path)

    try:
        if extension_id:
            results = [validator.validate(extension_id, force=force)]
        elif all_proposed:
            results = validator.validate_all_proposed()
        else:
            # List pending without running
            rows = conn.execute(
                "SELECT extension_id, skill_id, status, past_wo_count, "
                "current_eval_score, baseline_eval_score FROM ds_user_extensions "
                "WHERE status IN ('proposed', 'experimental') "
                "AND (content IS NOT NULL AND content != '' AND content != '{}') "
                "ORDER BY created_at"
            ).fetchall()
            if not rows:
                print("No extensions pending validation.")
                return 0
            print(f"\n{len(rows)} extension(s) available for validation:\n")
            for r in rows:
                score_info = ""
                if r["current_eval_score"] is not None:
                    score_info = f" | score={r['current_eval_score']:.3f}"
                print(
                    f"  {r['extension_id'][:8]}… {r['skill_id']} "
                    f"[{r['status']}] N={r['past_wo_count']}{score_info}"
                )
            print("\nRun: ds learn validate <id> OR ds learn validate --all-proposed")
            return 0
    finally:
        conn.close()

    # Report results
    # Phase 19.7: invalidate ExtensionLoader cache after validation
    # (extension statuses may have changed to 'active')
    try:
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()
    except Exception:
        pass

    for result in results:
        if not result.success:
            print(f"  ✗ {result.extension_id[:8]}… FAILED: {result.error}", file=sys.stderr)
            continue
        symbol = "✓" if result.verdict == "active" else "⚠"
        score_str = (
            f"  score={result.current_eval_score:.3f}"
            if result.current_eval_score is not None
            else ""
        )
        tokens_str = f" (~{result.tokens_estimated} tokens)" if result.tokens_estimated > 0 else ""
        print(
            f"  {symbol} {result.extension_id[:8]}… "
            f"→ {result.verdict}{score_str}  N={result.past_wo_count}"
            f"{tokens_str}\n    {result.verdict_reason}"
        )
    return 0


def cmd_disambiguate(args) -> int:
    """Resolve description collisions for extensions blocked by 19.6 gate."""
    from core.expansion.disambiguation import (
        check_extension_description,
        CRITICAL_THRESHOLD,
        WARNING_THRESHOLD,
    )
    from core.config.database import get_connection

    db_path = getattr(args, "db_path", None)
    extension_id = args.extension_id
    rewrite = getattr(args, "rewrite", None)
    accept_warning = getattr(args, "accept_warning", False)
    force_reason = getattr(args, "force", None)

    conn = get_connection() if db_path is None else __import__("sqlite3").connect(str(db_path))
    conn.row_factory = __import__("sqlite3").Row

    try:
        row = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
        ).fetchone()
        if row is None:
            print(f"Extension {extension_id!r} not found.", file=sys.stderr)
            return 1

        ext = dict(row)

        # Handle --rewrite: update description and re-run check
        if rewrite:
            import json as _json

            content = _json.loads(ext.get("content") or "{}")
            content["description"] = rewrite
            conn.execute(
                "UPDATE ds_user_extensions SET content = ? WHERE extension_id = ?",
                (_json.dumps(content), extension_id),
            )
            conn.commit()
            ext["content"] = _json.dumps(content)
            print("  Description updated.")

        # Run the check
        collision = check_extension_description(ext, conn=conn)

        if collision.status == "clean":
            print(f"  ✓ No collision detected (worst score below {WARNING_THRESHOLD}).")
            print(f"    Run 'ds learn validate {extension_id[:8]}' to complete activation.")
            return 0

        # Show collision details
        print(f"\n  ⚠ Collision detected: {collision.status.upper()}")
        print(f"  Candidate: {collision.candidate_description!r}")
        if collision.collisions:
            top = collision.collisions[0]
            print(f"  Collides with: {top.compared_id!r} (similarity: {top.similarity_score:.2f})")
            print(f"  Existing:  {top.compared_description!r}")
        print()

        # Handle --accept-warning (only for warning tier)
        if accept_warning:
            if collision.status == "critical":
                print(
                    f"  ✗ --accept-warning rejected: collision is CRITICAL (score ≥ {CRITICAL_THRESHOLD}). "
                    f'Use --force "<reason>" instead.',
                    file=sys.stderr,
                )
                return 1
            # Accept warning — promote to active with audit trail
            import json as _j

            detail_raw = ext.get("validation_detail")
            detail = _j.loads(detail_raw) if detail_raw else {}
            if "collision_check" in detail:
                detail["collision_check"]["accepted"] = True
            detail["verdict"] = "active"
            score = collision.collisions[0].similarity_score if collision.collisions else 0.0
            detail["verdict_reason"] = f"collision warning accepted by operator (score={score:.2f})"
            conn.execute(
                "UPDATE ds_user_extensions SET status='active', validation_detail=? WHERE extension_id=?",
                (_j.dumps(detail), extension_id),
            )
            conn.commit()
            print(f"  ✓ Warning accepted. Extension {extension_id[:8]}… → active")
            # Invalidate cache
            try:
                from core.expansion.loader import ExtensionLoader

                ExtensionLoader.invalidate_cache()
            except Exception:
                pass
            return 0

        # Handle --force (accepted for any tier)
        if force_reason:
            import json as _j

            detail_raw = ext.get("validation_detail")
            detail = _j.loads(detail_raw) if detail_raw else {}
            if "collision_check" in detail:
                detail["collision_check"]["accepted"] = True
                detail["collision_check"]["force_reason"] = force_reason
            detail["verdict"] = "active"
            detail["verdict_reason"] = f"collision force-overridden: {force_reason}"
            conn.execute(
                "UPDATE ds_user_extensions SET status='active', validation_detail=? WHERE extension_id=?",
                (_j.dumps(detail), extension_id),
            )
            conn.commit()
            print(f"  ✓ Force override accepted. Extension {extension_id[:8]}… → active")
            print(f"    Reason logged: {force_reason!r}")
            try:
                from core.expansion.loader import ExtensionLoader

                ExtensionLoader.invalidate_cache()
            except Exception:
                pass
            return 0

        # No action flags — just show the status
        print("  Actions:")
        if collision.status == "warning":
            print("    --accept-warning     accept the warning and activate")
        print('    --rewrite "..."       update description and re-check')
        print('    --force "reason"      force-activate with audit trail')
        return 1

    finally:
        conn.close()
