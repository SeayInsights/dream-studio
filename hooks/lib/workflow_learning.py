"""Workflow learning system for dream-studio project intelligence.

Tracks which skill chains (workflows) succeed most often and recommends
optimal workflows based on historical performance.
"""

from __future__ import annotations

import json
import hashlib
from typing import Any
from datetime import datetime, timezone

from . import studio_db


def _generate_workflow_id(workflow_chain: list[str]) -> str:
    """Generate a unique ID for a workflow chain."""
    chain_str = json.dumps(workflow_chain, sort_keys=True)
    return hashlib.sha256(chain_str.encode()).hexdigest()[:16]


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def track_workflow_success(workflow_chain: list[str], outcome: str) -> None:
    """
    Track workflow chain success/failure.

    Args:
        workflow_chain: List of skill calls, e.g., ['dream-studio:core think',
                       'dream-studio:core plan', 'dream-studio:core build']
        outcome: 'success' or 'failure'

    Stores in existing reg_workflows table.
    """
    if not workflow_chain:
        return

    if outcome not in ('success', 'failure'):
        raise ValueError(f"outcome must be 'success' or 'failure', got '{outcome}'")

    workflow_id = _generate_workflow_id(workflow_chain)
    chain_json = json.dumps(workflow_chain)

    # Get or create workflow record
    conn = studio_db._connect()
    try:
        # Check if workflow exists
        row = conn.execute(
            "SELECT success_count, total_count FROM reg_workflows WHERE workflow_id=?",
            (workflow_id,)
        ).fetchone()

        if row:
            # Update existing workflow
            success_count = row["success_count"] or 0
            total_count = row["total_count"] or 0

            if outcome == 'success':
                success_count += 1
            total_count += 1

            conn.execute(
                """UPDATE reg_workflows
                   SET success_count=?, total_count=?, updated_at=?
                   WHERE workflow_id=?""",
                (success_count, total_count, _now(), workflow_id)
            )
        else:
            # Create new workflow
            success_count = 1 if outcome == 'success' else 0
            total_count = 1

            # Extract category from first skill
            category = "unknown"
            if workflow_chain:
                first_skill = workflow_chain[0]
                if ':' in first_skill:
                    pack = first_skill.split(':')[1].split()[0]
                    category = pack

            conn.execute(
                """INSERT INTO reg_workflows
                   (workflow_id, yaml_path, description, chain, success_count,
                    total_count, category, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, '', f"Auto-tracked workflow: {' → '.join(workflow_chain[:3])}",
                 chain_json, success_count, total_count, category, _now(), _now())
            )

        conn.commit()
    finally:
        conn.close()


def calculate_workflow_success_rate(workflow_id: str) -> float:
    """
    Calculate success rate for a workflow.

    Returns: success_count / total_count
    """
    conn = studio_db._connect()
    try:
        row = conn.execute(
            "SELECT success_count, total_count FROM reg_workflows WHERE workflow_id=?",
            (workflow_id,)
        ).fetchone()

        if not row:
            return 0.0

        success_count = row["success_count"] or 0
        total_count = row["total_count"] or 0

        if total_count == 0:
            return 0.0

        return success_count / total_count
    finally:
        conn.close()


def get_recommended_workflows(context: dict[str, Any] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get top workflows by success rate.

    Args:
        context: Current context (can filter by project type, skill pack, etc.)
                 Supported keys:
                 - category: Filter by workflow category (e.g., 'core', 'quality')
                 - min_executions: Minimum number of executions (default: 3)
        limit: Number of recommendations to return

    Returns: List of workflows sorted by success_rate DESC, each with:
        - workflow_chain: list[str]
        - success_rate: float
        - total_executions: int
    """
    context = context or {}
    category = context.get('category')
    min_executions = context.get('min_executions', 3)

    conn = studio_db._connect()
    try:
        # Build query
        query = """
            SELECT workflow_id, chain, success_count, total_count, category
            FROM reg_workflows
            WHERE total_count >= ?
        """
        params: list[Any] = [min_executions]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY (CAST(success_count AS REAL) / total_count) DESC, total_count DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            workflow_chain = json.loads(row["chain"]) if row["chain"] else []
            success_count = row["success_count"] or 0
            total_count = row["total_count"] or 0
            success_rate = success_count / total_count if total_count > 0 else 0.0

            results.append({
                'workflow_chain': workflow_chain,
                'success_rate': success_rate,
                'total_executions': total_count,
                'category': row["category"]
            })

        return results
    finally:
        conn.close()


def get_workflow_stats(workflow_id: str) -> dict[str, Any] | None:
    """
    Get detailed statistics for a specific workflow.

    Returns: Dict with workflow details or None if not found.
    """
    conn = studio_db._connect()
    try:
        row = conn.execute(
            """SELECT workflow_id, chain, success_count, total_count,
                      category, created_at, updated_at
               FROM reg_workflows WHERE workflow_id=?""",
            (workflow_id,)
        ).fetchone()

        if not row:
            return None

        workflow_chain = json.loads(row["chain"]) if row["chain"] else []
        success_count = row["success_count"] or 0
        total_count = row["total_count"] or 0

        return {
            'workflow_id': row["workflow_id"],
            'workflow_chain': workflow_chain,
            'success_count': success_count,
            'failure_count': total_count - success_count,
            'total_executions': total_count,
            'success_rate': success_count / total_count if total_count > 0 else 0.0,
            'category': row["category"],
            'created_at': row["created_at"],
            'updated_at': row["updated_at"]
        }
    finally:
        conn.close()
