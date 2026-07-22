"""ds learn review — interactive/batch review of pending classified signals.

Split from interfaces/cli/ds_learn.py (WO-GF-CLI-split).

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
