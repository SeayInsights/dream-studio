"""MetricStreamer - Polls Phase 1 collectors and streams metrics to WebSocket clients"""
import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from analytics.api.websocket.connection_manager import ConnectionManager
from analytics.core.collectors.session_collector import SessionCollector
from analytics.core.collectors.skill_collector import SkillCollector
from analytics.core.collectors.token_collector import TokenCollector
from analytics.core.collectors.model_collector import ModelCollector
from analytics.core.collectors.lesson_collector import LessonCollector
from analytics.core.collectors.workflow_collector import WorkflowCollector

logger = logging.getLogger(__name__)


class MetricStreamer:
    """
    Streams real-time metrics to WebSocket clients by polling Phase 1 collectors.

    Polls all 6 Phase 1 collectors at configured intervals and emits metric updates
    to subscribed WebSocket clients via ConnectionManager. Runs in background
    using asyncio.
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        poll_interval: int = 60,
        db_path: Optional[str] = None
    ):
        """
        Initialize MetricStreamer.

        Args:
            connection_manager: ConnectionManager instance for WebSocket communication
            poll_interval: Polling interval in seconds (default: 60)
            db_path: Optional path to studio.db (if None, collectors use default)
        """
        self.connection_manager = connection_manager
        self.poll_interval = poll_interval
        self.db_path = db_path

        # Initialize collectors
        self.session_collector = SessionCollector(db_path=db_path)
        self.skill_collector = SkillCollector(db_path=db_path)
        self.token_collector = TokenCollector(db_path=db_path)
        self.model_collector = ModelCollector(db_path=db_path)
        self.lesson_collector = LessonCollector(db_path=db_path)
        self.workflow_collector = WorkflowCollector(db_path=db_path)

        # Background task tracking
        self._task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"MetricStreamer initialized with {poll_interval}s poll interval"
        )

    async def start(self) -> None:
        """
        Start polling collectors and streaming metrics.

        Launches background task that polls collectors at configured interval
        and emits updates to WebSocket clients.
        """
        if self._running:
            logger.warning("MetricStreamer already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("MetricStreamer started")

    async def stop(self) -> None:
        """
        Stop streaming and cancel background task.

        Gracefully shuts down the polling loop and waits for task completion.
        """
        if not self._running:
            logger.warning("MetricStreamer not running")
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("MetricStreamer stopped")

    async def _poll_loop(self) -> None:
        """
        Background polling loop.

        Continuously polls collectors at configured interval and emits updates
        until stopped. Handles errors gracefully to avoid crashing the loop.
        """
        while self._running:
            try:
                # Collect metrics from all collectors
                metrics = await self._collect_metrics()

                # Emit each metric to subscribed clients
                for metric_name, value in metrics.items():
                    await self._emit_metric_update(metric_name, value)

                logger.debug(f"Polled and emitted {len(metrics)} metrics")

            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                # Continue polling despite errors

            # Wait for next poll interval
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info("Polling loop cancelled")
                break

    async def _collect_metrics(self) -> Dict[str, Any]:
        """
        Poll all Phase 1 collectors and aggregate results.

        Runs all collectors in parallel using asyncio.gather to avoid blocking.
        Handles individual collector errors gracefully by logging and continuing.

        Returns:
            Dictionary of metric name -> value pairs from all collectors
        """
        # Use asyncio to run collectors concurrently (they're blocking but fast)
        # Wrap in run_in_executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        results = {}

        # Session metrics
        try:
            session_metrics = await loop.run_in_executor(
                None, self.session_collector.collect, 90
            )
            results["sessions_total"] = session_metrics["total_sessions"]
            results["sessions_by_project"] = session_metrics["by_project"]
            results["sessions_timeline"] = session_metrics["timeline"]
            results["sessions_day_of_week"] = session_metrics["day_of_week"]
            results["sessions_outcomes"] = session_metrics["outcomes"]
            results["sessions_avg_duration"] = session_metrics["avg_duration_minutes"]
        except Exception as e:
            logger.error(f"SessionCollector error: {e}", exc_info=True)

        # Skill metrics
        try:
            skill_metrics = await loop.run_in_executor(
                None, self.skill_collector.collect, 90
            )
            results["skills_total_invocations"] = skill_metrics["total_invocations"]
            results["skills_by_skill"] = skill_metrics["by_skill"]
            results["skills_success_rate"] = skill_metrics["success_rate_overall"]
            results["skills_failures"] = skill_metrics["failures"]
            results["skills_top_skills"] = skill_metrics["top_skills"]
        except Exception as e:
            logger.error(f"SkillCollector error: {e}", exc_info=True)

        # Token metrics
        try:
            token_metrics = await loop.run_in_executor(
                None, self.token_collector.collect, 90
            )
            results["tokens_total_input"] = token_metrics["total_input_tokens"]
            results["tokens_total_output"] = token_metrics["total_output_tokens"]
            results["tokens_total"] = token_metrics["total_tokens"]
            results["tokens_total_cost"] = token_metrics["total_cost_usd"]
            results["tokens_by_model"] = token_metrics["by_model"]
            results["tokens_by_project"] = token_metrics["by_project"]
            results["tokens_by_skill"] = token_metrics["by_skill"]
            results["tokens_daily_average"] = token_metrics["daily_average"]
        except Exception as e:
            logger.error(f"TokenCollector error: {e}", exc_info=True)

        # Model metrics
        try:
            model_metrics = await loop.run_in_executor(
                None, self.model_collector.collect, 90
            )
            results["models_by_model"] = model_metrics["by_model"]
            results["models_distribution"] = model_metrics["distribution"]
            results["models_performance_rank"] = model_metrics["performance_rank"]
            results["models_token_efficiency"] = model_metrics["token_efficiency"]
        except Exception as e:
            logger.error(f"ModelCollector error: {e}", exc_info=True)

        # Lesson metrics
        try:
            lesson_metrics = await loop.run_in_executor(
                None, self.lesson_collector.collect, 90
            )
            results["lessons_total"] = lesson_metrics["total_lessons"]
            results["lessons_by_source"] = lesson_metrics["by_source"]
            results["lessons_by_status"] = lesson_metrics["by_status"]
            results["lessons_by_confidence"] = lesson_metrics["by_confidence"]
            results["lessons_capture_rate"] = lesson_metrics["capture_rate"]
            results["lessons_promoted_count"] = lesson_metrics["promoted_count"]
            results["lessons_recent"] = lesson_metrics["recent_lessons"]
        except Exception as e:
            logger.error(f"LessonCollector error: {e}", exc_info=True)

        # Workflow metrics
        try:
            workflow_metrics = await loop.run_in_executor(
                None, self.workflow_collector.collect, 90
            )
            results["workflows_total_runs"] = workflow_metrics["total_runs"]
            results["workflows_by_workflow"] = workflow_metrics["by_workflow"]
            results["workflows_by_status"] = workflow_metrics["by_status"]
            results["workflows_success_rate"] = workflow_metrics["success_rate"]
            results["workflows_avg_completion_time"] = workflow_metrics["avg_completion_time_minutes"]
            results["workflows_total_nodes"] = workflow_metrics["total_nodes_executed"]
        except Exception as e:
            logger.error(f"WorkflowCollector error: {e}", exc_info=True)

        # Add metadata
        results["_timestamp"] = datetime.now(timezone.utc).isoformat()
        results["_poll_interval"] = self.poll_interval

        return results

    async def _emit_metric_update(self, metric_name: str, value: Any) -> None:
        """
        Send metric update to subscribed clients via ConnectionManager.

        Args:
            metric_name: Name of the metric (e.g., "sessions_total")
            value: Metric value (any JSON-serializable type)
        """
        # Build event payload
        event = {
            "type": "metric_update",
            "metric": metric_name,
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Send to all clients subscribed to this metric
        await self.connection_manager.send_to_subscribers(metric_name, event)
