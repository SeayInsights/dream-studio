"""Unit tests for real-time WebSocket streaming"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from analytics.api.websocket.connection_manager import ConnectionManager
from analytics.core.streaming.metric_streamer import MetricStreamer


# ============================================================================
# ConnectionManager Tests
# ============================================================================

@pytest.mark.asyncio
async def test_connection_manager_connect():
    """Test connecting a new client"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    await manager.connect(client_id, mock_websocket)

    # Verify websocket.accept() was called
    mock_websocket.accept.assert_called_once()

    # Verify client was added
    assert manager.active_connections_count == 1

    # Verify client ID is tracked
    stats = manager.get_connection_stats()
    assert client_id in stats["connected_clients"]


@pytest.mark.asyncio
async def test_connection_manager_disconnect():
    """Test disconnecting a client"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    # Connect first
    await manager.connect(client_id, mock_websocket)
    assert manager.active_connections_count == 1

    # Disconnect
    manager.disconnect(client_id)

    # Verify client was removed
    assert manager.active_connections_count == 0


@pytest.mark.asyncio
async def test_connection_manager_disconnect_cleans_subscriptions():
    """Test that disconnecting a client removes all their subscriptions"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    # Connect and subscribe
    await manager.connect(client_id, mock_websocket)
    manager.subscribe(client_id, ["sessions", "tokens"])

    # Verify subscriptions exist
    assert manager.active_subscriptions_count == 2
    assert client_id in manager.get_subscribers("sessions")

    # Disconnect
    manager.disconnect(client_id)

    # Verify subscriptions are cleaned up
    assert manager.active_subscriptions_count == 0
    assert client_id not in manager.get_subscribers("sessions")


@pytest.mark.asyncio
async def test_connection_manager_subscribe():
    """Test subscribing a client to metrics"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    await manager.connect(client_id, mock_websocket)

    # Subscribe to metrics
    metrics = ["sessions", "tokens", "skills"]
    manager.subscribe(client_id, metrics)

    # Verify subscriptions
    assert manager.active_subscriptions_count == 3
    for metric in metrics:
        subscribers = manager.get_subscribers(metric)
        assert client_id in subscribers


@pytest.mark.asyncio
async def test_connection_manager_subscribe_multiple_clients():
    """Test multiple clients subscribing to same metric"""
    manager = ConnectionManager()

    # Connect two clients
    client1 = "client-1"
    client2 = "client-2"
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await manager.connect(client1, ws1)
    await manager.connect(client2, ws2)

    # Both subscribe to same metric
    manager.subscribe(client1, ["sessions"])
    manager.subscribe(client2, ["sessions"])

    # Verify both are subscribed
    subscribers = manager.get_subscribers("sessions")
    assert len(subscribers) == 2
    assert client1 in subscribers
    assert client2 in subscribers


@pytest.mark.asyncio
async def test_connection_manager_unsubscribe():
    """Test unsubscribing a client from metrics"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    await manager.connect(client_id, mock_websocket)

    # Subscribe to multiple metrics
    manager.subscribe(client_id, ["sessions", "tokens", "skills"])
    assert manager.active_subscriptions_count == 3

    # Unsubscribe from one metric
    manager.unsubscribe(client_id, ["tokens"])

    # Verify subscription removed
    assert manager.active_subscriptions_count == 2
    assert client_id not in manager.get_subscribers("tokens")
    assert client_id in manager.get_subscribers("sessions")


@pytest.mark.asyncio
async def test_connection_manager_unsubscribe_cleans_empty_metrics():
    """Test that unsubscribing removes empty metric entries"""
    manager = ConnectionManager()
    mock_websocket = AsyncMock()
    client_id = "test-client-1"

    await manager.connect(client_id, mock_websocket)
    manager.subscribe(client_id, ["sessions"])

    # Unsubscribe - should remove the metric entry entirely
    manager.unsubscribe(client_id, ["sessions"])

    # Verify metric entry is cleaned up
    assert manager.active_subscriptions_count == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast():
    """Test broadcasting to all connected clients"""
    manager = ConnectionManager()

    # Connect three clients
    clients = ["client-1", "client-2", "client-3"]
    websockets = [AsyncMock() for _ in range(3)]

    for client_id, ws in zip(clients, websockets):
        await manager.connect(client_id, ws)

    # Broadcast event
    event = {"type": "test", "data": "hello"}
    await manager.broadcast(event)

    # Verify all clients received the event
    for ws in websockets:
        ws.send_json.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_connection_manager_broadcast_handles_disconnected_clients():
    """Test that broadcast removes disconnected clients"""
    manager = ConnectionManager()

    # Create clients - one will fail
    client1 = "client-1"
    client2 = "client-2"
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    # Make ws2 fail when sending
    ws2.send_json.side_effect = Exception("Connection closed")

    await manager.connect(client1, ws1)
    await manager.connect(client2, ws2)

    assert manager.active_connections_count == 2

    # Broadcast - should handle the failure
    await manager.broadcast({"type": "test"})

    # Verify failed client was disconnected
    assert manager.active_connections_count == 1
    stats = manager.get_connection_stats()
    assert client1 in stats["connected_clients"]
    assert client2 not in stats["connected_clients"]


@pytest.mark.asyncio
async def test_connection_manager_send_to_client():
    """Test sending to a specific client"""
    manager = ConnectionManager()

    # Connect two clients
    client1 = "client-1"
    client2 = "client-2"
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await manager.connect(client1, ws1)
    await manager.connect(client2, ws2)

    # Send to specific client
    event = {"type": "test", "message": "hello"}
    await manager.send_to_client(client1, event)

    # Verify only target client received it
    ws1.send_json.assert_called_once_with(event)
    ws2.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_connection_manager_send_to_nonexistent_client():
    """Test sending to a client that doesn't exist"""
    manager = ConnectionManager()

    # Try sending to non-existent client (should not raise error)
    await manager.send_to_client("ghost-client", {"type": "test"})

    # Should complete without error


@pytest.mark.asyncio
async def test_connection_manager_send_to_client_handles_error():
    """Test that send_to_client disconnects on error"""
    manager = ConnectionManager()

    client_id = "client-1"
    ws = AsyncMock()
    ws.send_json.side_effect = Exception("Connection failed")

    await manager.connect(client_id, ws)
    assert manager.active_connections_count == 1

    # Send - should handle error and disconnect
    await manager.send_to_client(client_id, {"type": "test"})

    # Verify client was disconnected
    assert manager.active_connections_count == 0


@pytest.mark.asyncio
async def test_connection_manager_send_to_subscribers():
    """Test sending to all subscribers of a metric"""
    manager = ConnectionManager()

    # Connect three clients
    client1 = "client-1"
    client2 = "client-2"
    client3 = "client-3"
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    ws3 = AsyncMock()

    await manager.connect(client1, ws1)
    await manager.connect(client2, ws2)
    await manager.connect(client3, ws3)

    # Subscribe only client1 and client2 to "sessions"
    manager.subscribe(client1, ["sessions"])
    manager.subscribe(client2, ["sessions"])
    manager.subscribe(client3, ["tokens"])

    # Send to subscribers
    event = {"type": "metric_update", "metric": "sessions", "value": 100}
    await manager.send_to_subscribers("sessions", event)

    # Verify only subscribed clients received it
    ws1.send_json.assert_called_once_with(event)
    ws2.send_json.assert_called_once_with(event)
    ws3.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_connection_manager_send_to_subscribers_no_subscribers():
    """Test sending to metric with no subscribers"""
    manager = ConnectionManager()

    # Should complete without error
    await manager.send_to_subscribers("ghost-metric", {"type": "test"})


@pytest.mark.asyncio
async def test_connection_manager_get_connection_stats():
    """Test getting connection statistics"""
    manager = ConnectionManager()

    # Connect clients
    await manager.connect("client-1", AsyncMock())
    await manager.connect("client-2", AsyncMock())

    # Subscribe
    manager.subscribe("client-1", ["sessions", "tokens"])
    manager.subscribe("client-2", ["sessions"])

    # Get stats
    stats = manager.get_connection_stats()

    # Verify stats
    assert stats["total_connections"] == 2
    assert stats["total_subscriptions"] == 2
    assert stats["total_subscribers"] == 3  # client-1 has 2, client-2 has 1
    assert len(stats["connected_clients"]) == 2
    assert set(stats["subscribed_metrics"]) == {"sessions", "tokens"}


@pytest.mark.asyncio
async def test_connection_manager_thread_safety():
    """Test that connection manager is thread-safe"""
    manager = ConnectionManager()

    # Simulate concurrent connections
    tasks = []
    for i in range(10):
        client_id = f"client-{i}"
        ws = AsyncMock()
        tasks.append(manager.connect(client_id, ws))

    await asyncio.gather(*tasks)

    # Verify all connections registered
    assert manager.active_connections_count == 10


# ============================================================================
# WebSocket Endpoint Tests
# ============================================================================

def test_websocket_connection_endpoint():
    """Test basic WebSocket connection"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Should receive welcome message
            data = websocket.receive_json()

            assert data["type"] == "connected"
            assert "client_id" in data
            assert data["message"] == "Connected to dream-studio analytics stream"


def test_websocket_subscribe_message():
    """Test subscribe message handling"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Receive welcome
            websocket.receive_json()

            # Send subscribe message
            websocket.send_json({
                "type": "subscribe",
                "metrics": ["sessions", "tokens"]
            })

            # Should receive acknowledgment
            ack = websocket.receive_json()
            assert ack["type"] == "ack"
            assert ack["action"] == "subscribe"
            assert set(ack["metrics"]) == {"sessions", "tokens"}


def test_websocket_unsubscribe_message():
    """Test unsubscribe message handling"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Receive welcome
            websocket.receive_json()

            # Subscribe first
            websocket.send_json({
                "type": "subscribe",
                "metrics": ["sessions", "tokens"]
            })
            websocket.receive_json()  # ack

            # Unsubscribe
            websocket.send_json({
                "type": "unsubscribe",
                "metrics": ["sessions"]
            })

            # Should receive acknowledgment
            ack = websocket.receive_json()
            assert ack["type"] == "ack"
            assert ack["action"] == "unsubscribe"
            assert ack["metrics"] == ["sessions"]


def test_websocket_invalid_subscribe_message():
    """Test error handling for invalid subscribe message"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Receive welcome
            websocket.receive_json()

            # Send invalid subscribe (no metrics)
            websocket.send_json({
                "type": "subscribe",
                "metrics": []
            })

            # Should receive error
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert "Invalid subscribe request" in error["message"]


def test_websocket_invalid_unsubscribe_message():
    """Test error handling for invalid unsubscribe message"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Receive welcome
            websocket.receive_json()

            # Send invalid unsubscribe (metrics not a list)
            websocket.send_json({
                "type": "unsubscribe",
                "metrics": "not-a-list"
            })

            # Should receive error
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert "Invalid unsubscribe request" in error["message"]


def test_websocket_unknown_message_type():
    """Test error handling for unknown message type"""
    from analytics.api.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/stream/metrics") as websocket:
            # Receive welcome
            websocket.receive_json()

            # Send unknown message type
            websocket.send_json({
                "type": "unknown_type",
                "data": "test"
            })

            # Should receive error
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert "Unknown message type" in error["message"]


def test_websocket_connection_stats_endpoint():
    """Test connection stats HTTP endpoint"""
    from analytics.api.main import app

    client = TestClient(app)

    # Get stats (should work even with no connections)
    response = client.get("/api/v1/connection-stats")
    assert response.status_code == 200

    data = response.json()
    assert "total_connections" in data
    assert "total_subscriptions" in data
    assert "connected_clients" in data


# ============================================================================
# MetricStreamer Tests
# ============================================================================

@pytest.mark.asyncio
async def test_metric_streamer_init():
    """Test MetricStreamer initialization"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=30,
        db_path=":memory:"
    )

    assert streamer.connection_manager is manager
    assert streamer.poll_interval == 30
    assert streamer.db_path == ":memory:"
    assert streamer._running is False


@pytest.mark.asyncio
async def test_metric_streamer_start():
    """Test starting the metric streamer"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=1,
        db_path=":memory:"
    )

    await streamer.start()

    assert streamer._running is True
    assert streamer._task is not None

    # Clean up
    await streamer.stop()


@pytest.mark.asyncio
async def test_metric_streamer_stop():
    """Test stopping the metric streamer"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=1,
        db_path=":memory:"
    )

    await streamer.start()
    assert streamer._running is True

    await streamer.stop()

    assert streamer._running is False


@pytest.mark.asyncio
async def test_metric_streamer_start_already_running():
    """Test starting when already running"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=1,
        db_path=":memory:"
    )

    await streamer.start()

    # Try starting again (should not raise error)
    await streamer.start()

    assert streamer._running is True

    # Clean up
    await streamer.stop()


@pytest.mark.asyncio
async def test_metric_streamer_stop_not_running():
    """Test stopping when not running"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=1,
        db_path=":memory:"
    )

    # Stop without starting (should not raise error)
    await streamer.stop()

    assert streamer._running is False


@pytest.mark.asyncio
async def test_metric_streamer_collect_metrics():
    """Test collecting metrics from all collectors"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=60,
        db_path=":memory:"
    )

    # Mock collectors to avoid DB dependency
    with patch.object(streamer.session_collector, 'collect', return_value={
        "total_sessions": 10,
        "by_project": {},
        "timeline": [],
        "day_of_week": {},
        "outcomes": {},
        "avg_duration_minutes": 45.0
    }), \
    patch.object(streamer.skill_collector, 'collect', return_value={
        "total_invocations": 50,
        "by_skill": {},
        "success_rate_overall": 0.95,
        "failures": [],
        "top_skills": []
    }), \
    patch.object(streamer.token_collector, 'collect', return_value={
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "total_tokens": 1500,
        "total_cost_usd": 0.05,
        "by_model": {},
        "by_project": {},
        "by_skill": {},
        "daily_average": 100
    }), \
    patch.object(streamer.model_collector, 'collect', return_value={
        "by_model": {},
        "distribution": {},
        "performance_rank": [],
        "token_efficiency": {}
    }), \
    patch.object(streamer.lesson_collector, 'collect', return_value={
        "total_lessons": 5,
        "by_source": {},
        "by_status": {},
        "by_confidence": {},
        "capture_rate": 0.8,
        "promoted_count": 2,
        "recent_lessons": []
    }), \
    patch.object(streamer.workflow_collector, 'collect', return_value={
        "total_runs": 15,
        "by_workflow": {},
        "by_status": {},
        "success_rate": 0.9,
        "avg_completion_time_minutes": 30.0,
        "total_nodes_executed": 100
    }):
        metrics = await streamer._collect_metrics()

    # Verify metrics were collected
    assert "sessions_total" in metrics
    assert metrics["sessions_total"] == 10
    assert "skills_total_invocations" in metrics
    assert metrics["skills_total_invocations"] == 50
    assert "tokens_total" in metrics
    assert metrics["tokens_total"] == 1500
    assert "_timestamp" in metrics
    assert "_poll_interval" in metrics


@pytest.mark.asyncio
async def test_metric_streamer_emit_metric_update():
    """Test emitting metric updates to subscribers"""
    manager = ConnectionManager()

    # Connect and subscribe a client
    client_id = "test-client"
    ws = AsyncMock()
    await manager.connect(client_id, ws)
    manager.subscribe(client_id, ["sessions_total"])

    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=60,
        db_path=":memory:"
    )

    # Emit metric update
    await streamer._emit_metric_update("sessions_total", 100)

    # Verify client received the update
    ws.send_json.assert_called_once()
    call_args = ws.send_json.call_args[0][0]

    assert call_args["type"] == "metric_update"
    assert call_args["metric"] == "sessions_total"
    assert call_args["value"] == 100
    assert "timestamp" in call_args


@pytest.mark.asyncio
async def test_metric_streamer_handles_collector_errors():
    """Test that streamer handles collector errors gracefully"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=60,
        db_path=":memory:"
    )

    # Mock one collector to fail
    with patch.object(streamer.session_collector, 'collect', side_effect=Exception("DB error")), \
    patch.object(streamer.skill_collector, 'collect', return_value={
        "total_invocations": 50,
        "by_skill": {},
        "success_rate_overall": 0.95,
        "failures": [],
        "top_skills": []
    }), \
    patch.object(streamer.token_collector, 'collect', return_value={
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "total_tokens": 1500,
        "total_cost_usd": 0.05,
        "by_model": {},
        "by_project": {},
        "by_skill": {},
        "daily_average": 100
    }), \
    patch.object(streamer.model_collector, 'collect', return_value={
        "by_model": {},
        "distribution": {},
        "performance_rank": [],
        "token_efficiency": {}
    }), \
    patch.object(streamer.lesson_collector, 'collect', return_value={
        "total_lessons": 5,
        "by_source": {},
        "by_status": {},
        "by_confidence": {},
        "capture_rate": 0.8,
        "promoted_count": 2,
        "recent_lessons": []
    }), \
    patch.object(streamer.workflow_collector, 'collect', return_value={
        "total_runs": 15,
        "by_workflow": {},
        "by_status": {},
        "success_rate": 0.9,
        "avg_completion_time_minutes": 30.0,
        "total_nodes_executed": 100
    }):
        metrics = await streamer._collect_metrics()

    # Should still return metrics from successful collectors
    assert "skills_total_invocations" in metrics
    # Session metrics should be missing due to error
    assert "sessions_total" not in metrics


@pytest.mark.asyncio
async def test_metric_streamer_poll_loop():
    """Test the polling loop executes and emits metrics"""
    manager = ConnectionManager()

    # Connect and subscribe a client
    client_id = "test-client"
    ws = AsyncMock()
    await manager.connect(client_id, ws)
    manager.subscribe(client_id, ["sessions_total"])

    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=0.1,  # Fast poll for testing
        db_path=":memory:"
    )

    # Mock collectors
    with patch.object(streamer.session_collector, 'collect', return_value={
        "total_sessions": 10,
        "by_project": {},
        "timeline": [],
        "day_of_week": {},
        "outcomes": {},
        "avg_duration_minutes": 45.0
    }), \
    patch.object(streamer.skill_collector, 'collect', return_value={
        "total_invocations": 50,
        "by_skill": {},
        "success_rate_overall": 0.95,
        "failures": [],
        "top_skills": []
    }), \
    patch.object(streamer.token_collector, 'collect', return_value={
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "total_tokens": 1500,
        "total_cost_usd": 0.05,
        "by_model": {},
        "by_project": {},
        "by_skill": {},
        "daily_average": 100
    }), \
    patch.object(streamer.model_collector, 'collect', return_value={
        "by_model": {},
        "distribution": {},
        "performance_rank": [],
        "token_efficiency": {}
    }), \
    patch.object(streamer.lesson_collector, 'collect', return_value={
        "total_lessons": 5,
        "by_source": {},
        "by_status": {},
        "by_confidence": {},
        "capture_rate": 0.8,
        "promoted_count": 2,
        "recent_lessons": []
    }), \
    patch.object(streamer.workflow_collector, 'collect', return_value={
        "total_runs": 15,
        "by_workflow": {},
        "by_status": {},
        "success_rate": 0.9,
        "avg_completion_time_minutes": 30.0,
        "total_nodes_executed": 100
    }):
        # Start streamer
        await streamer.start()

        # Wait for at least one poll cycle
        await asyncio.sleep(0.3)

        # Stop streamer
        await streamer.stop()

    # Verify client received metric updates
    assert ws.send_json.call_count > 0


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_streaming_flow():
    """Test complete flow: connect -> subscribe -> receive updates"""
    manager = ConnectionManager()

    # Connect client
    client_id = "test-client"
    ws = AsyncMock()
    await manager.connect(client_id, ws)

    # Subscribe to metrics
    manager.subscribe(client_id, ["sessions_total", "tokens_total"])

    # Create streamer
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=60,
        db_path=":memory:"
    )

    # Manually emit some metrics (simulating poll)
    await streamer._emit_metric_update("sessions_total", 100)
    await streamer._emit_metric_update("tokens_total", 50000)

    # Verify client received both updates
    assert ws.send_json.call_count == 2

    # Verify message format
    calls = ws.send_json.call_args_list
    msg1 = calls[0][0][0]
    msg2 = calls[1][0][0]

    assert msg1["type"] == "metric_update"
    assert msg1["metric"] == "sessions_total"
    assert msg1["value"] == 100

    assert msg2["type"] == "metric_update"
    assert msg2["metric"] == "tokens_total"
    assert msg2["value"] == 50000


def test_multiple_clients_different_subscriptions():
    """Test multiple clients with different metric subscriptions"""
    from analytics.api.main import app

    with TestClient(app) as client:
        # Connect first client
        with client.websocket_connect("/api/v1/stream/metrics") as ws1:
            ws1.receive_json()  # welcome

            # Subscribe to sessions
            ws1.send_json({
                "type": "subscribe",
                "metrics": ["sessions"]
            })
            ws1.receive_json()  # ack

            # Connect second client
            with client.websocket_connect("/api/v1/stream/metrics") as ws2:
                ws2.receive_json()  # welcome

                # Subscribe to different metrics
                ws2.send_json({
                    "type": "subscribe",
                    "metrics": ["tokens", "skills"]
                })
                ws2.receive_json()  # ack

                # Get connection stats
                response = client.get("/api/v1/connection-stats")
                assert response.status_code == 200

                stats = response.json()
                assert stats["total_connections"] == 2
                assert stats["total_subscriptions"] == 3  # sessions, tokens, skills


@pytest.mark.asyncio
async def test_metric_update_format():
    """Test that metric updates have correct format"""
    manager = ConnectionManager()
    streamer = MetricStreamer(
        connection_manager=manager,
        poll_interval=60,
        db_path=":memory:"
    )

    # Connect and subscribe
    client_id = "test-client"
    ws = AsyncMock()
    await manager.connect(client_id, ws)
    manager.subscribe(client_id, ["test_metric"])

    # Emit metric
    test_value = {"count": 100, "average": 45.5}
    await streamer._emit_metric_update("test_metric", test_value)

    # Verify format
    ws.send_json.assert_called_once()
    event = ws.send_json.call_args[0][0]

    assert event["type"] == "metric_update"
    assert event["metric"] == "test_metric"
    assert event["value"] == test_value
    assert "timestamp" in event

    # Verify timestamp is ISO format
    from datetime import datetime
    try:
        datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))
    except ValueError:
        pytest.fail("Timestamp is not in valid ISO format")
