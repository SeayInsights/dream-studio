"""
Helper to resolve project (PRD node) from any execution graph node.
Ensures security findings always link back to the project root.
"""

from typing import Optional, Dict, List
from pathlib import Path

from core.config.database import get_connection


class ProjectResolver:
    """Resolves project (PRD) from any node in execution graph."""

    def get_prd_for_node(self, node_id: str) -> Optional[str]:
        """
        Walk up execution graph to find PRD node.

        Args:
            node_id: Any node ID in execution graph

        Returns:
            PRD node ID, or None if not found
        """
        conn = get_connection()

        try:
            current_id = node_id
            max_depth = 10  # Prevent infinite loops

            for _ in range(max_depth):
                cursor = conn.execute(
                    """
                    SELECT node_type, parent_id FROM execution_nodes WHERE node_id = ?
                """,
                    (current_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                node_type, parent_id = row["node_type"], row["parent_id"]

                # Found PRD
                if node_type == "prd":
                    return current_id

                # No parent - reached top without finding PRD
                if not parent_id:
                    return None

                # Move up to parent
                current_id = parent_id

            # Exceeded max depth
            return None

        finally:
            conn.close()

    def get_project_hierarchy(self, prd_id: str) -> Dict:
        """
        Get full project hierarchy from PRD.

        Args:
            prd_id: PRD node ID

        Returns:
            {
                'prd': {...},
                'plans': [...],
                'phases': [...],
                'waves': [...],
                'tasks': [...]
            }
        """
        conn = get_connection()

        try:
            # Recursive CTE to get all descendants
            cursor = conn.execute(
                """
                WITH RECURSIVE hierarchy AS (
                    -- Start with PRD
                    SELECT node_id, node_type, title, parent_id, 0 as depth
                    FROM execution_nodes
                    WHERE node_id = ?

                    UNION ALL

                    -- Recursively get children
                    SELECT e.node_id, e.node_type, e.title, e.parent_id, h.depth + 1
                    FROM execution_nodes e
                    JOIN hierarchy h ON e.parent_id = h.node_id
                )
                SELECT * FROM hierarchy
                ORDER BY depth, node_type
            """,
                (prd_id,),
            )

            nodes = [dict(row) for row in cursor.fetchall()]

            # Group by type
            hierarchy = {"prd": None, "plans": [], "phases": [], "waves": [], "tasks": []}

            for node in nodes:
                node_type = node["node_type"]
                if node_type == "prd":
                    hierarchy["prd"] = node
                elif node_type == "plan":
                    hierarchy["plans"].append(node)
                elif node_type == "phase":
                    hierarchy["phases"].append(node)
                elif node_type == "wave":
                    hierarchy["waves"].append(node)
                elif node_type == "task":
                    hierarchy["tasks"].append(node)

            return hierarchy

        finally:
            conn.close()

    def validate_prd_node(self, node_id: str) -> bool:
        """
        Verify that a node is actually a PRD.

        Args:
            node_id: Node ID to check

        Returns:
            True if node is a PRD, False otherwise
        """
        conn = get_connection()

        try:
            cursor = conn.execute(
                """
                SELECT node_type FROM execution_nodes WHERE node_id = ?
            """,
                (node_id,),
            )

            row = cursor.fetchone()
            return row and row["node_type"] == "prd"

        finally:
            conn.close()

    def get_project_path(self, node_id: str) -> Optional[Path]:
        """
        Get project path from node metadata.

        Args:
            node_id: Node ID (any level)

        Returns:
            Path to project, or None if not found
        """
        # First resolve to PRD
        prd_id = self.get_prd_for_node(node_id)
        if not prd_id:
            return None

        conn = get_connection()

        try:
            cursor = conn.execute(
                """
                SELECT metadata FROM execution_nodes WHERE node_id = ?
            """,
                (prd_id,),
            )

            row = cursor.fetchone()
            if not row or not row["metadata"]:
                return None

            import json

            metadata = json.loads(row["metadata"])

            # Try various metadata keys
            path_keys = ["project_path", "path", "file_path", "repo_path"]
            for key in path_keys:
                if key in metadata:
                    return Path(metadata[key])

            return None

        finally:
            conn.close()

    def list_all_projects(self) -> List[Dict]:
        """
        List all PRD nodes with their security status.

        Returns:
            List of projects with security summary
        """
        conn = get_connection()

        try:
            cursor = conn.execute("""
                SELECT
                    e.node_id,
                    e.title,
                    e.created_at,
                    COUNT(DISTINCT s.id) as scan_count,
                    COUNT(DISTINCT f.id) as finding_count,
                    SUM(CASE WHEN f.severity = 'CRITICAL' AND f.status = 'open' THEN 1 ELSE 0 END) as critical_open,
                    SUM(CASE WHEN f.severity = 'HIGH' AND f.status = 'open' THEN 1 ELSE 0 END) as high_open,
                    MAX(s.started_at) as last_scan
                FROM execution_nodes e
                LEFT JOIN sec_scans s ON e.node_id = s.node_id
                LEFT JOIN sec_findings f ON s.id = f.scan_id
                WHERE e.node_type = 'prd'
                GROUP BY e.node_id
                ORDER BY e.created_at DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_affected_nodes_for_finding(self, finding_id: str) -> List[Dict]:
        """
        Get all nodes affected by a finding (walk down hierarchy).

        Args:
            finding_id: Finding ID

        Returns:
            List of affected nodes
        """
        conn = get_connection()

        try:
            # Get finding's affected_node_id
            cursor = conn.execute(
                """
                SELECT affected_node_id FROM sec_findings WHERE id = ?
            """,
                (finding_id,),
            )

            row = cursor.fetchone()
            if not row or not row["affected_node_id"]:
                return []

            affected_id = row["affected_node_id"]

            # Get all descendant nodes
            cursor = conn.execute(
                """
                WITH RECURSIVE descendants AS (
                    -- Start with affected node
                    SELECT node_id, node_type, title, parent_id
                    FROM execution_nodes
                    WHERE node_id = ?

                    UNION ALL

                    -- Recursively get children
                    SELECT e.node_id, e.node_type, e.title, e.parent_id
                    FROM execution_nodes e
                    JOIN descendants d ON e.parent_id = d.node_id
                )
                SELECT * FROM descendants
            """,
                (affected_id,),
            )

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()
