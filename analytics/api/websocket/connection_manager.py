"""WebSocket connection manager for real-time analytics streaming"""
import logging
from typing import Dict, List, Set
from fastapi import WebSocket
from threading import Lock

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and client subscriptions for real-time analytics.

    Thread-safe manager that tracks active connections, handles client subscriptions
    to specific metrics, and provides broadcast and targeted messaging capabilities.
    """

    def __init__(self):
        """Initialize the connection manager."""
        # Active WebSocket connections mapped by client_id
        self._connections: Dict[str, WebSocket] = {}

        # Client subscriptions: metric_name -> set of client_ids
        self._subscriptions: Dict[str, Set[str]] = {}

        # Thread-safety locks
        self._connection_lock = Lock()
        self._subscription_lock = Lock()

        logger.info("ConnectionManager initialized")

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        """
        Register a new client WebSocket connection.

        Args:
            client_id: Unique identifier for the client
            websocket: FastAPI WebSocket instance
        """
        await websocket.accept()

        with self._connection_lock:
            self._connections[client_id] = websocket

        logger.info(f"Client {client_id} connected. Total connections: {len(self._connections)}")

    def disconnect(self, client_id: str) -> None:
        """
        Remove a client connection and clean up all subscriptions.

        Args:
            client_id: Unique identifier for the client to disconnect
        """
        # Remove connection
        with self._connection_lock:
            if client_id in self._connections:
                del self._connections[client_id]

        # Clean up all subscriptions for this client
        with self._subscription_lock:
            metrics_to_clean = []
            for metric, subscribers in self._subscriptions.items():
                if client_id in subscribers:
                    subscribers.discard(client_id)
                    # Mark empty subscription lists for cleanup
                    if not subscribers:
                        metrics_to_clean.append(metric)

            # Remove empty subscription entries
            for metric in metrics_to_clean:
                del self._subscriptions[metric]

        logger.info(f"Client {client_id} disconnected. Total connections: {len(self._connections)}")

    def subscribe(self, client_id: str, metrics: List[str]) -> None:
        """
        Subscribe a client to specific metrics.

        Args:
            client_id: Unique identifier for the client
            metrics: List of metric names to subscribe to
        """
        with self._subscription_lock:
            for metric in metrics:
                if metric not in self._subscriptions:
                    self._subscriptions[metric] = set()
                self._subscriptions[metric].add(client_id)

        logger.info(f"Client {client_id} subscribed to {len(metrics)} metrics: {metrics}")

    def unsubscribe(self, client_id: str, metrics: List[str]) -> None:
        """
        Unsubscribe a client from specific metrics.

        Args:
            client_id: Unique identifier for the client
            metrics: List of metric names to unsubscribe from
        """
        with self._subscription_lock:
            for metric in metrics:
                if metric in self._subscriptions:
                    self._subscriptions[metric].discard(client_id)
                    # Clean up empty subscription entries
                    if not self._subscriptions[metric]:
                        del self._subscriptions[metric]

        logger.info(f"Client {client_id} unsubscribed from {len(metrics)} metrics: {metrics}")

    async def broadcast(self, event: dict) -> None:
        """
        Send an event to all connected clients.

        Args:
            event: Event data to broadcast (will be JSON serialized)
        """
        disconnected_clients = []

        with self._connection_lock:
            connections = list(self._connections.items())

        # Send to all clients (outside lock to avoid blocking)
        for client_id, websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.error(f"Failed to send to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

        logger.debug(f"Broadcast event to {len(connections)} clients")

    async def send_to_client(self, client_id: str, event: dict) -> None:
        """
        Send an event to a specific client.

        Args:
            client_id: Unique identifier for the target client
            event: Event data to send (will be JSON serialized)
        """
        with self._connection_lock:
            websocket = self._connections.get(client_id)

        if websocket is None:
            logger.warning(f"Cannot send to client {client_id}: not connected")
            return

        try:
            await websocket.send_json(event)
            logger.debug(f"Sent event to client {client_id}")
        except Exception as e:
            logger.error(f"Failed to send to client {client_id}: {e}")
            self.disconnect(client_id)

    def get_subscribers(self, metric: str) -> List[str]:
        """
        Get list of client IDs subscribed to a specific metric.

        Args:
            metric: Metric name to query

        Returns:
            List of client IDs subscribed to the metric
        """
        with self._subscription_lock:
            subscribers = self._subscriptions.get(metric, set())
            return list(subscribers)

    async def send_to_subscribers(self, metric: str, event: dict) -> None:
        """
        Send an event to all clients subscribed to a specific metric.

        This is a helper method not in the spec but useful for sending
        metric-specific updates efficiently.

        Args:
            metric: Metric name to send to
            event: Event data to send (will be JSON serialized)
        """
        subscribers = self.get_subscribers(metric)

        if not subscribers:
            logger.debug(f"No subscribers for metric {metric}")
            return

        disconnected_clients = []

        # Get websockets for subscribers
        with self._connection_lock:
            connections = [(cid, self._connections.get(cid)) for cid in subscribers]

        # Send to all subscribers
        for client_id, websocket in connections:
            if websocket is None:
                continue

            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.error(f"Failed to send to subscriber {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

        logger.debug(f"Sent event to {len(subscribers)} subscribers of {metric}")

    @property
    def active_connections_count(self) -> int:
        """Get count of active connections."""
        with self._connection_lock:
            return len(self._connections)

    @property
    def active_subscriptions_count(self) -> int:
        """Get count of active metric subscriptions."""
        with self._subscription_lock:
            return len(self._subscriptions)

    def get_connection_stats(self) -> dict:
        """
        Get connection statistics.

        Returns:
            Dictionary with connection and subscription stats
        """
        with self._connection_lock:
            total_connections = len(self._connections)
            client_ids = list(self._connections.keys())

        with self._subscription_lock:
            total_subscriptions = len(self._subscriptions)
            metrics = list(self._subscriptions.keys())
            total_subscribers = sum(len(subs) for subs in self._subscriptions.values())

        return {
            "total_connections": total_connections,
            "total_subscriptions": total_subscriptions,
            "total_subscribers": total_subscribers,
            "connected_clients": client_ids,
            "subscribed_metrics": metrics
        }
