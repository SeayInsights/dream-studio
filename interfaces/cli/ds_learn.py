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
"""

from __future__ import annotations

import json
import sys


def _format_signal(sig: dict, index: int, total: int) -> str:
    ctx = {}
    try:
        ctx = json.loads(sig.get("context") or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    lines = [
        f"\n[{index}/{total}] Signal: {sig.get('signal_type', '?')}",
        f"  Skill:       {sig.get('skill_id', '?')}",
    ]
    if sig.get("rule_id"):
        lines.append(f"  Rule:        {sig['rule_id']}")
    lines.extend(
        [
            f"  Classified:  {sig.get('classified_as', '?')}  "
            f"(confidence: {sig.get('classification_confidence', '?'):.2f})",
            f"  Reason:      {sig.get('classification_reason', '?')}",
        ]
    )
    if ctx:
        occ = ctx.get("occurrence_count", "?")
        scans = ctx.get("distinct_scans", "?")
        lines.append(f"  Sample data: {occ} occurrences across {scans} sources")
    lines.append("  Actions:  c=confirm  s=skip  d=defer  q=quit")
    return "\n".join(lines)


def _get_classifier(db_path=None):
    from projections.core.analyzers.gap_classifier import GapClassifier
    from core.config.database import get_connection

    conn = get_connection() if db_path is None else __import__("sqlite3").connect(str(db_path))
    conn.row_factory = __import__("sqlite3").Row
    return GapClassifier(conn), conn


def cmd_review(args) -> int:
    """Interactive review of pending classified signals."""
    limit = getattr(args, "limit", 50) or 50
    batch = getattr(args, "batch", False)
    db_path = getattr(args, "db_path", None)

    classifier, conn = _get_classifier(db_path)

    try:
        signals = classifier.get_pending_review(limit=limit)
    except Exception as exc:
        print(f"Error loading signals: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_path is not None:
            conn.close()

    if not signals:
        print("No signals pending review.")
        return 0

    # Batch mode: print JSON and exit
    if batch:
        print(json.dumps(signals, indent=2))
        return 0

    # Interactive mode
    total = len(signals)
    print(f"\nds learn review — {total} signal(s) pending\n")

    acted = skipped = deferred = 0

    for i, sig in enumerate(signals, 1):
        print(_format_signal(sig, i, total))

        while True:
            try:
                choice = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n(interrupted)")
                choice = "q"

            if choice in ("c", "confirm"):
                try:
                    # Re-open connection for writes (batch opened for reads)
                    write_classifier, write_conn = _get_classifier(db_path)
                    try:
                        ext_id = write_classifier.confirm_signal(sig["signal_id"])
                        print(f"  ✓ Created extension {ext_id[:8]}… (status=proposed)")
                        acted += 1
                    finally:
                        write_conn.close()
                except Exception as exc:
                    print(f"  Error: {exc}", file=sys.stderr)
                break
            if choice in ("s", "skip"):
                try:
                    write_classifier, write_conn = _get_classifier(db_path)
                    try:
                        write_classifier.skip_signal(sig["signal_id"])
                        print("  → Skipped (won't resurface)")
                        skipped += 1
                    finally:
                        write_conn.close()
                except Exception as exc:
                    print(f"  Error: {exc}", file=sys.stderr)
                break
            if choice in ("d", "defer"):
                try:
                    write_classifier, write_conn = _get_classifier(db_path)
                    try:
                        write_classifier.defer_signal(sig["signal_id"])
                        print("  ⟳ Deferred (will reclassify next session)")
                        deferred += 1
                    finally:
                        write_conn.close()
                except Exception as exc:
                    print(f"  Error: {exc}", file=sys.stderr)
                break
            if choice in ("q", "quit", "exit"):
                print(f"\nStopped. {i - 1} reviewed.")
                _print_summary(acted, skipped, deferred)
                return 0
            print("  Invalid choice. Use: c=confirm  s=skip  d=defer  q=quit")

    # Phase 19.7: confirm/skip/defer all change extension state
    if acted + skipped + deferred > 0:
        try:
            from core.expansion.loader import ExtensionLoader

            ExtensionLoader.invalidate_cache()
        except Exception:
            pass

    print(f"\nAll {total} signals reviewed.")
    _print_summary(acted, skipped, deferred)
    return 0


def _print_summary(confirmed: int, skipped: int, deferred: int) -> None:
    print(
        f"Summary: {confirmed} confirmed (extensions proposed), "
        f"{skipped} skipped, {deferred} deferred."
    )


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


def add_learn_subcommand(subparsers) -> None:
    """Register the 'learn' subcommand group with ds CLI."""
    learn_parser = subparsers.add_parser(
        "learn",
        help="Operator learning and gap review workflows",
    )
    learn_sub = learn_parser.add_subparsers(dest="learn_command")

    # ds learn review
    review_parser = learn_sub.add_parser(
        "review",
        help="Review pending classified friction signals",
    )
    review_parser.add_argument("--limit", type=int, default=50)
    review_parser.add_argument("--batch", action="store_true")
    review_parser.set_defaults(func=cmd_review)

    # ds learn expand (19.4a — personalization only)
    expand_parser = learn_sub.add_parser(
        "expand",
        help="Compile personalization extensions from dismissal evidence (19.4a)",
    )
    expand_parser.add_argument(
        "extension_id",
        nargs="?",
        help="Compile a specific extension by ID (default: show all pending)",
    )
    expand_parser.add_argument("--all", action="store_true", help="Compile all pending")
    expand_parser.add_argument("--batch", action="store_true", help="JSON output, no interaction")
    expand_parser.add_argument(
        "--show-events",
        action="store_true",
        dest="show_events",
        help="Show cited event IDs for capability proposals",
    )
    expand_parser.set_defaults(func=cmd_expand)

    # ds learn validate (19.5 — retroactive validation)
    validate_parser = learn_sub.add_parser(
        "validate",
        help="Retroactive validation for compiled extensions (Decision 6)",
    )
    validate_parser.add_argument(
        "extension_id",
        nargs="?",
        help="Validate a specific extension (default: list pending)",
    )
    validate_parser.add_argument(
        "--all-proposed",
        action="store_true",
        dest="all_proposed",
        help="Validate all proposed/experimental extensions with sufficient WO history",
    )
    validate_parser.add_argument(
        "--force",
        action="store_true",
        help="Override the N≥5 minimum (requires explicit confirmation)",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # ds learn disambiguate (19.6 — description collision resolution)
    disambig_parser = learn_sub.add_parser(
        "disambiguate",
        help="Resolve description collisions for blocked extensions (19.6)",
    )
    disambig_parser.add_argument("extension_id", help="Extension to disambiguate")
    disambig_parser.add_argument(
        "--rewrite",
        metavar="DESCRIPTION",
        help="New description to use; re-runs collision check after update",
    )
    disambig_parser.add_argument(
        "--accept-warning",
        action="store_true",
        dest="accept_warning",
        help="Accept a warning-tier collision (0.70-0.85 similarity) and activate",
    )
    disambig_parser.add_argument(
        "--force",
        metavar="REASON",
        help="Force-activate despite critical collision (≥0.85); requires a reason",
    )
    disambig_parser.set_defaults(func=cmd_disambiguate)

    learn_parser.set_defaults(func=_learn_help)


def _learn_help(args) -> int:
    print("Usage: ds learn review [--limit N] [--batch]")
    print("       ds learn expand [extension_id] [--all] [--batch]")
    print("       ds learn validate [extension_id] [--all-proposed] [--force]")
    print(
        "       ds learn disambiguate <extension_id> [--rewrite DESC] [--accept-warning] [--force REASON]"
    )
    return 0
