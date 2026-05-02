"""Real-time WebSocket routes for streaming analytics"""
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any

from ..websocket.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection manager instance
connection_manager = ConnectionManager()


@router.websocket("/stream/metrics")
async def websocket_metrics_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time metrics streaming.

    Clients can subscribe to specific metrics and receive real-time updates.

    Message protocol:
    - Subscribe: {"type": "subscribe", "metrics": ["sessions", "tokens"]}
    - Unsubscribe: {"type": "unsubscribe", "metrics": ["sessions"]}
    - Server acknowledgment: {"type": "ack", "action": "subscribe", "metrics": [...]}
    """
    # Generate unique client ID
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await connection_manager.connect(client_id, websocket)

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "message": "Connected to dream-studio analytics stream"
        })

        # Handle incoming messages
        while True:
            try:
                # Receive message from client
                message = await websocket.receive_json()

                # Extract message type
                message_type = message.get("type")

                if message_type == "subscribe":
                    # Handle subscription request
                    metrics = message.get("metrics", [])

                    if not metrics or not isinstance(metrics, list):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid subscribe request: 'metrics' must be a non-empty list"
                        })
                        continue

                    # Subscribe client to metrics
                    connection_manager.subscribe(client_id, metrics)

                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "ack",
                        "action": "subscribe",
                        "metrics": metrics
                    })

                elif message_type == "unsubscribe":
                    # Handle unsubscription request
                    metrics = message.get("metrics", [])

                    if not metrics or not isinstance(metrics, list):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid unsubscribe request: 'metrics' must be a non-empty list"
                        })
                        continue

                    # Unsubscribe client from metrics
                    connection_manager.unsubscribe(client_id, metrics)

                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "ack",
                        "action": "unsubscribe",
                        "metrics": metrics
                    })

                else:
                    # Unknown message type
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message_type}"
                    })

            except ValueError as e:
                # JSON parsing error
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        # Client disconnected normally
        logger.info(f"Client {client_id} disconnected normally")

    except Exception as e:
        # Unexpected error
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        # Clean up connection
        connection_manager.disconnect(client_id)


@router.get("/connection-stats")
async def get_connection_stats() -> Dict[str, Any]:
    """
    Get current WebSocket connection statistics.

    Returns connection count, subscription count, and other stats.
    """
    return connection_manager.get_connection_stats()
