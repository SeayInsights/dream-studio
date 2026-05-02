"""LessonCollector - Collects lesson capture metrics from studio.db"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


class LessonCollector:
    """Collects and aggregates lesson metrics from raw_lessons table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize LessonCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect lesson metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_lessons: int
                - by_source: Dict[source -> count]
                - by_status: Dict[status -> count]
                - by_confidence: Dict[confidence -> count]
                - capture_rate: float (lessons per day)
                - promoted_count: int
                - recent_lessons: List[Dict] (10 most recent)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            # Total lessons
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM raw_lessons
                WHERE created_at >= ?
            """, (cutoff_date,))
            total_lessons = cursor.fetchone()["total"]

            # By source
            cursor.execute("""
                SELECT source, COUNT(*) as count
                FROM raw_lessons
                WHERE created_at >= ?
                GROUP BY source
                ORDER BY count DESC
            """, (cutoff_date,))
            by_source = {row["source"]: row["count"] for row in cursor.fetchall()}

            # By status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM raw_lessons
                WHERE created_at >= ?
                GROUP BY status
                ORDER BY count DESC
            """, (cutoff_date,))
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

            # By confidence
            cursor.execute("""
                SELECT confidence, COUNT(*) as count
                FROM raw_lessons
                WHERE created_at >= ?
                GROUP BY confidence
                ORDER BY count DESC
            """, (cutoff_date,))
            by_confidence = {row["confidence"]: row["count"] for row in cursor.fetchall()}

            # Capture rate (lessons per day)
            capture_rate = total_lessons / days if days > 0 else 0.0

            # Promoted lessons
            cursor.execute("""
                SELECT COUNT(*) as promoted
                FROM raw_lessons
                WHERE created_at >= ?
                AND promoted_to IS NOT NULL
            """, (cutoff_date,))
            promoted_count = cursor.fetchone()["promoted"]

            # Recent lessons
            cursor.execute("""
                SELECT
                    lesson_id,
                    source,
                    status,
                    confidence,
                    title,
                    created_at
                FROM raw_lessons
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (cutoff_date,))
            recent_lessons = [dict(row) for row in cursor.fetchall()]

            return {
                "total_lessons": total_lessons,
                "by_source": by_source,
                "by_status": by_status,
                "by_confidence": by_confidence,
                "capture_rate": round(capture_rate, 2),
                "promoted_count": promoted_count,
                "recent_lessons": recent_lessons
            }

        finally:
            conn.close()

    def get_timeline(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily lesson capture timeline

        Args:
            days: Number of days of history

        Returns:
            List of dicts with date, count, sources
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            cursor.execute("""
                SELECT
                    DATE(created_at) as date,
                    COUNT(*) as count,
                    GROUP_CONCAT(DISTINCT source) as sources
                FROM raw_lessons
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """, (cutoff_date,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_source_quality(self) -> List[Dict[str, Any]]:
        """
        Analyze quality metrics by source

        Returns:
            List of dicts with source, count, promoted_rate, avg_confidence_score
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    source,
                    COUNT(*) as count,
                    SUM(CASE WHEN promoted_to IS NOT NULL THEN 1 ELSE 0 END) as promoted,
                    confidence
                FROM raw_lessons
                GROUP BY source, confidence
            """)

            # Aggregate by source
            sources = {}
            for row in cursor.fetchall():
                source = row["source"]
                if source not in sources:
                    sources[source] = {
                        "source": source,
                        "count": 0,
                        "promoted": 0,
                        "confidence_scores": []
                    }

                sources[source]["count"] += row["count"]
                sources[source]["promoted"] += row["promoted"]

                # Map confidence to numeric score
                confidence_map = {"high": 3, "medium": 2, "low": 1}
                score = confidence_map.get(row["confidence"], 2)
                sources[source]["confidence_scores"].extend([score] * row["count"])

            # Calculate metrics
            result = []
            for source_data in sources.values():
                promoted_rate = (source_data["promoted"] / source_data["count"] * 100) if source_data["count"] > 0 else 0.0
                avg_confidence = sum(source_data["confidence_scores"]) / len(source_data["confidence_scores"]) if source_data["confidence_scores"] else 0.0

                result.append({
                    "source": source_data["source"],
                    "count": source_data["count"],
                    "promoted_rate": round(promoted_rate, 1),
                    "avg_confidence_score": round(avg_confidence, 2)
                })

            return sorted(result, key=lambda x: x["count"], reverse=True)

        finally:
            conn.close()
