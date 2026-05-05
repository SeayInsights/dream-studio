"""Token optimization system for dream-studio project-intelligence (Wave 6)."""
from __future__ import annotations
from datetime import datetime, timezone

from .document_store import DocumentStore


def track_token_usage(operation: str, tokens: int, context: dict) -> None:
    """
    Track high-cost operations (>50k tokens).

    Args:
        operation: Operation name (e.g., 'analyze_project', 'full_audit')
        tokens: Token count
        context: Additional context (project_id, session_id, etc.)

    Stores in ds_documents table with doc_type='token-usage'.
    """
    if tokens < 50000:
        return

    # Create timestamp
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build content summary
    content = f"""# Token Usage Report

**Operation**: {operation}
**Tokens**: {tokens:,}
**Timestamp**: {timestamp}

## Context
"""
    for key, value in context.items():
        content += f"- **{key}**: {value}\n"

    # Build metadata
    metadata = {
        "operation": operation,
        "tokens": tokens,
        "timestamp": timestamp,
        **context,
    }

    # Extract project_id and session_id for FK fields (if present)
    # Only pass them if they exist in context; DocumentStore will handle None
    project_id = context.get("project_id")
    session_id = context.get("session_id")

    # Store in document store
    # Note: If project_id/session_id are provided but don't exist in DB,
    # this will raise a foreign key constraint error
    DocumentStore.create(
        doc_type="token-usage",
        title=f"{operation} - {tokens:,} tokens",
        content=content,
        project_id=project_id,
        session_id=session_id,
        format="markdown",
        metadata=metadata,
        tags=["high-cost", "token-tracking"],
        keywords=f"{operation} tokens {tokens}",
    )


def suggest_optimizations(operation: str, usage_history: list[dict]) -> list[str]:
    """
    Suggest token reduction strategies based on usage patterns.

    Args:
        operation: Operation name
        usage_history: List of usage records with 'operation', 'tokens', 'context' keys

    Returns:
        List of actionable optimization suggestions
    """
    suggestions = []

    # Filter to this operation
    op_history = [h for h in usage_history if h.get("operation") == operation]

    if not op_history:
        return [
            "No historical data available for this operation.",
            "Consider tracking usage over multiple runs to identify patterns.",
        ]

    # Calculate average token usage
    avg_tokens = sum(h.get("tokens", 0) for h in op_history) / len(op_history)

    # Check for repeated patterns
    models_used = [h.get("context", {}).get("model") for h in op_history if h.get("context", {}).get("model")]
    model_counts = {}
    for model in models_used:
        model_counts[model] = model_counts.get(model, 0) + 1

    # Suggestion 1: Model selection
    if "sonnet" in str(models_used).lower() or "opus" in str(models_used).lower():
        suggestions.append(
            "Switch to Haiku model for exploration/search tasks (70% cost reduction)"
        )

    # Suggestion 2: Caching for repeated queries
    if len(op_history) >= 3:
        # Check for similar operations
        recent_ops = [h.get("context", {}).get("query") for h in op_history[-3:]]
        if len(set(filter(None, recent_ops))) < len(recent_ops):
            suggestions.append(
                "Use caching for repeated queries (60% token reduction)"
            )

    # Suggestion 3: Progressive loading
    if avg_tokens > 100000:
        suggestions.append(
            "Use progressive loading with Context7 (40% token reduction)"
        )

    # Suggestion 4: Targeted search
    if "analyze" in operation.lower() or "audit" in operation.lower():
        suggestions.append(
            "Use targeted grep/glob searches instead of full file reads (50% token reduction)"
        )

    # Suggestion 5: Batch operations
    if len(op_history) >= 5:
        time_diffs = []
        sorted_history = sorted(op_history, key=lambda h: h.get("timestamp", ""))
        for i in range(1, len(sorted_history)):
            try:
                t1 = datetime.fromisoformat(sorted_history[i-1].get("timestamp", ""))
                t2 = datetime.fromisoformat(sorted_history[i].get("timestamp", ""))
                time_diffs.append((t2 - t1).total_seconds())
            except (ValueError, TypeError):
                continue

        if time_diffs:
            avg_time_diff = sum(time_diffs) / len(time_diffs)
            if avg_time_diff < 300:  # Less than 5 minutes between operations
                suggestions.append(
                    "Batch similar operations together to reduce context switching (30% token reduction)"
                )

    # Suggestion 6: Use subagents
    if avg_tokens > 150000:
        suggestions.append(
            "Delegate subtasks to lightweight subagents (Haiku) instead of full analysis (65% token reduction)"
        )

    # Return at least 2 suggestions
    if not suggestions:
        suggestions = [
            "Operation is already well-optimized.",
            "Monitor for usage patterns over time to identify further optimizations.",
        ]

    return suggestions[:6]  # Cap at 6 suggestions


def auto_compact_check(current_tokens: int, max_tokens: int = 400000) -> bool:
    """
    Check if /compact should trigger.

    Args:
        current_tokens: Current token count in session
        max_tokens: Maximum token limit (default 400k)

    Returns:
        True if /compact should be triggered (at 75% of max)
    """
    threshold = int(max_tokens * 0.75)
    return current_tokens >= threshold
