# Dream-Studio Analytics Platform

Enterprise-grade analytics and real-time monitoring for the dream-studio AI agent platform.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Real-Time Monitoring](#real-time-monitoring)
  - [WebSocket Streaming](#websocket-streaming)
  - [Alert Rules](#alert-rules)
  - [SLA Tracking](#sla-tracking)
  - [Notifications](#notifications)
- [REST API](#rest-api)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

The analytics platform provides comprehensive tracking, analysis, and real-time monitoring for dream-studio operations:

- **Data Collection**: Automated collectors for sessions, skills, workflows, tokens, and models
- **Analysis**: Anomaly detection, trend analysis, performance insights, and predictions
- **Real-Time Monitoring**: WebSocket streaming, alerts, SLA tracking, and notifications
- **REST API**: Full CRUD operations for metrics, insights, reports, and alerts
- **Power BI Integration**: Enterprise-ready dashboards with scheduled refresh

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT APPLICATIONS                       │
│  (Web UI, Power BI, Monitoring Tools, Automation Scripts)      │
└────────────┬────────────────────────────────────┬───────────────┘
             │                                    │
             │ HTTP/REST                          │ WebSocket
             │                                    │
┌────────────▼────────────────┐      ┌───────────▼──────────────┐
│     REST API (FastAPI)      │      │  WebSocket Streaming     │
│  - Metrics   - Insights     │      │  - Real-time metrics     │
│  - Reports   - Exports      │      │  - Subscribe/Unsubscribe │
│  - Alerts    - SLA tracking │      │  - Connection mgmt       │
└────────────┬────────────────┘      └───────────┬──────────────┘
             │                                    │
             └────────────────┬───────────────────┘
                              │
              ┌───────────────▼──────────────────┐
              │       CORE ANALYTICS ENGINE       │
              │                                   │
              │  ┌─────────────────────────────┐ │
              │  │     Data Collectors         │ │
              │  │  Sessions, Skills, Tokens,  │ │
              │  │  Models, Workflows, Lessons │ │
              │  └──────────┬──────────────────┘ │
              │             │                     │
              │  ┌──────────▼──────────────────┐ │
              │  │       Analyzers             │ │
              │  │  Anomaly, Trends, Perf,     │ │
              │  │  Predictions, Root Cause    │ │
              │  └──────────┬──────────────────┘ │
              │             │                     │
              │  ┌──────────▼──────────────────┐ │
              │  │   Real-Time Components      │ │
              │  │  - Metric Streamer          │ │
              │  │  - Alert Evaluator          │ │
              │  │  - SLA Tracker              │ │
              │  │  - Notification Dispatcher  │ │
              │  └──────────┬──────────────────┘ │
              └─────────────┼────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │   SQLite Database          │
              │   ~/.dream-studio/state/   │
              │   - Metrics history        │
              │   - Alert rules/history    │
              │   - SLA definitions        │
              │   - Raw telemetry          │
              └────────────────────────────┘
```

---

## Real-Time Monitoring

### WebSocket Streaming

Connect to the WebSocket endpoint to receive real-time metric updates.

#### Connection

```javascript
// JavaScript/Node.js example
const ws = new WebSocket('ws://localhost:8000/api/v1/stream/metrics');

ws.onopen = () => {
    console.log('Connected to analytics stream');
    
    // Subscribe to specific metrics
    ws.send(JSON.stringify({
        type: 'subscribe',
        metrics: ['sessions', 'tokens', 'skills']
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
    
    if (data.type === 'metric_update') {
        // Handle metric update
        console.log(`${data.metric}: ${data.value}`);
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected from analytics stream');
};
```

```python
# Python example using websockets library
import asyncio
import json
import websockets

async def stream_metrics():
    uri = "ws://localhost:8000/api/v1/stream/metrics"
    
    async with websockets.connect(uri) as websocket:
        # Wait for connection confirmation
        welcome = await websocket.recv()
        print(f"Connected: {welcome}")
        
        # Subscribe to metrics
        await websocket.send(json.dumps({
            "type": "subscribe",
            "metrics": ["sessions", "tokens", "workflows"]
        }))
        
        # Receive acknowledgment
        ack = await websocket.recv()
        print(f"Subscribed: {ack}")
        
        # Stream metrics
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "metric_update":
                print(f"{data['metric']}: {data['value']}")

asyncio.run(stream_metrics())
```

#### Message Protocol

**Client → Server (Subscribe)**
```json
{
    "type": "subscribe",
    "metrics": ["sessions", "tokens", "skills"]
}
```

**Client → Server (Unsubscribe)**
```json
{
    "type": "unsubscribe",
    "metrics": ["sessions"]
}
```

**Server → Client (Acknowledgment)**
```json
{
    "type": "ack",
    "action": "subscribe",
    "metrics": ["sessions", "tokens", "skills"]
}
```

**Server → Client (Metric Update)**
```json
{
    "type": "metric_update",
    "metric": "sessions",
    "value": 127,
    "timestamp": "2026-05-01T12:34:56Z"
}
```

---

### Alert Rules

Create, manage, and monitor alert rules via the REST API.

#### Create Alert Rule

```bash
curl -X POST http://localhost:8000/api/v1/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "High Session Duration",
    "metric_path": "sessions_avg_duration",
    "condition": "gt",
    "threshold": 30.0,
    "severity": "warning",
    "enabled": true
  }'
```

```python
import requests

# Create alert rule
response = requests.post(
    "http://localhost:8000/api/v1/alerts/rules",
    json={
        "rule_name": "Low Skill Success Rate",
        "metric_path": "skills_success_rate",
        "condition": "lt",
        "threshold": 95.0,
        "severity": "critical",
        "enabled": True
    }
)

rule = response.json()
print(f"Created rule: {rule['rule_id']}")
```

#### Supported Conditions

- `gt`: Greater than
- `lt`: Less than
- `eq`: Equal to
- `gte`: Greater than or equal to
- `lte`: Less than or equal to

#### Severity Levels

- `info`: Informational alerts
- `warning`: Warning-level alerts
- `critical`: Critical alerts requiring immediate attention

#### List Alert Rules

```bash
curl http://localhost:8000/api/v1/alerts/rules
```

```python
import requests

response = requests.get("http://localhost:8000/api/v1/alerts/rules")
rules = response.json()

for rule in rules:
    print(f"{rule['rule_name']}: {rule['metric_path']} {rule['condition']} {rule['threshold']}")
```

#### Update Alert Rule

```bash
curl -X PUT http://localhost:8000/api/v1/alerts/rules/{rule_id} \
  -H "Content-Type: application/json" \
  -d '{
    "threshold": 35.0,
    "severity": "critical"
  }'
```

#### Delete Alert Rule

```bash
curl -X DELETE http://localhost:8000/api/v1/alerts/rules/{rule_id}
```

#### View Alert History

```bash
# Get last 100 alerts
curl http://localhost:8000/api/v1/alerts/history

# Filter by severity
curl http://localhost:8000/api/v1/alerts/history?severity=critical&limit=50
```

---

### SLA Tracking

Define Service Level Agreements (SLAs) and track compliance over time.

#### Define SLA

```python
from analytics.core.sla.tracker import SLATracker

tracker = SLATracker()

# Response time SLA: average session duration < 20 minutes
sla_id = tracker.define_sla(
    name="Session Duration SLA",
    metric="sessions_avg_duration",
    target=20.0,
    window=24,  # 24-hour window
    sla_type="response_time"  # Auto-inferred if omitted
)

# Success rate SLA: skill success rate > 98%
tracker.define_sla(
    name="Skill Success SLA",
    metric="skills_success_rate",
    target=98.0,
    window=12,  # 12-hour window
    sla_type="success_rate"
)
```

#### SLA Types

- **response_time**: Lower is better (avg duration, latency)
- **error_rate**: Lower is better (error percentage)
- **success_rate**: Higher is better (success percentage)
- **availability**: Higher is better (uptime percentage)

#### Check SLA Compliance

```python
from analytics.core.sla.tracker import SLATracker

tracker = SLATracker()
compliance = tracker.check_compliance()

print(f"Total SLAs: {compliance['summary']['total_slas']}")
print(f"Compliant: {compliance['summary']['compliant_count']}")
print(f"Breached: {compliance['summary']['breached_count']}")
print(f"Compliance: {compliance['summary']['compliance_percentage']}%")

# Check individual SLAs
for sla_id, status in compliance['slas'].items():
    print(f"\n{status['name']}:")
    print(f"  Target: {status['target']}")
    print(f"  Current: {status['current_value']:.2f}")
    print(f"  Compliant: {status['compliant']}")
    if not status['compliant']:
        print(f"  Breach: {status['breach_percentage']:.2f}%")
```

#### Generate SLA Report

```python
from analytics.core.sla.tracker import SLATracker

tracker = SLATracker()
report = tracker.get_sla_report()

# Critical breaches (>20% over target)
if report['summary']['critical_breaches']:
    print("CRITICAL BREACHES:")
    for breach in report['summary']['critical_breaches']:
        print(f"  - {breach['name']}: {breach['breach_percentage']:.2f}% over target")
```

---

### Notifications

Configure notification channels to receive alerts.

#### Setup Notification Channels

```python
from analytics.core.notifications.dispatcher import (
    NotificationDispatcher,
    ConsoleChannel,
    FileChannel,
    WebhookChannel
)

# Create dispatcher
dispatcher = NotificationDispatcher()

# Register console channel (stdout + logs)
dispatcher.register_channel(ConsoleChannel(name="console"))

# Register file channel (JSONL log)
dispatcher.register_channel(FileChannel(
    name="file",
    log_path="/path/to/notifications.jsonl"
))

# Register webhook channel (Slack, Teams, etc.)
dispatcher.register_channel(WebhookChannel(
    name="slack",
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    timeout=10
))

# Send notification
dispatcher.send({
    "alert_id": "alert_123",
    "severity": "critical",
    "message": "Skill success rate dropped below 95%",
    "metric_path": "skills_success_rate",
    "metric_value": 92.5,
    "threshold": 95.0
})
```

#### Channel Types

**ConsoleChannel**: Prints to stdout and logs
- Best for development and debugging
- No external dependencies

**FileChannel**: Appends to JSONL log file
- Persistent notification history
- Default path: `~/.dream-studio/logs/notifications.jsonl`
- One JSON object per line for easy parsing

**WebhookChannel**: HTTP POST to webhook URL
- Integration with Slack, Microsoft Teams, Discord, PagerDuty, etc.
- Sends notification as JSON payload
- Configurable timeout

#### Configuration via YAML

Enable notification channels in `analytics.yaml`:

```yaml
realtime:
  enabled: true
  notification_channels:
    - console
    - file
    - webhook
```

---

## REST API

Full REST API documentation available at: `http://localhost:8000/api/docs` (Swagger UI)

### Base URL

```
http://localhost:8000/api/v1
```

### Key Endpoints

#### Metrics
- `GET /metrics/summary` - Current metrics summary
- `GET /metrics/trends` - Historical trends

#### Insights
- `GET /insights` - AI-generated insights and recommendations
- `GET /insights/anomalies` - Detected anomalies

#### Reports
- `POST /reports/generate` - Generate custom reports
- `GET /reports/{report_id}` - Retrieve generated report

#### Alerts
- `GET /alerts/rules` - List all alert rules
- `POST /alerts/rules` - Create new alert rule
- `PUT /alerts/rules/{rule_id}` - Update alert rule
- `DELETE /alerts/rules/{rule_id}` - Delete alert rule
- `GET /alerts/history` - Alert history with filters

#### Real-Time
- `WS /stream/metrics` - WebSocket metrics stream
- `GET /connection-stats` - WebSocket connection statistics

#### Export
- `GET /export/powerbi` - Power BI dataset export
- `GET /export/csv` - CSV export

---

## Configuration

Configuration is managed via `analytics/config/analytics.yaml`.

### Real-Time Monitoring Settings

```yaml
realtime:
  # Enable/disable real-time monitoring features
  enabled: true
  
  # Polling interval for metric collection (seconds)
  # Lower values = more frequent updates, higher resource usage
  poll_interval: 60
  
  # Interval for checking alert conditions (seconds)
  # Should be <= poll_interval for timely alerts
  alert_check_interval: 60
  
  # Enabled notification channels
  # Available: console, file, webhook
  notification_channels:
    - console
    - file
    - webhook
  
  # SLA compliance window (hours)
  # Time window for calculating SLA metrics
  sla_window: 24
```

### Environment Variables

Override configuration with environment variables:

```bash
# Database path
export DREAM_STUDIO_DB_PATH="~/.dream-studio/state/studio.db"

# API server settings
export ANALYTICS_HOST="0.0.0.0"
export ANALYTICS_PORT="8000"

# Enable debug logging
export ANALYTICS_DEBUG="true"
```

---

## Troubleshooting

### WebSocket Connection Issues

**Problem**: Cannot connect to WebSocket endpoint

**Solutions**:
1. Verify API server is running:
   ```bash
   curl http://localhost:8000/api/health
   ```

2. Check firewall/proxy settings (WebSocket requires WS/WSS protocol support)

3. Enable debug logging:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

4. Test with simple client:
   ```bash
   # Using websocat (https://github.com/vi/websocat)
   websocat ws://localhost:8000/api/v1/stream/metrics
   ```

---

### Alert Rules Not Triggering

**Problem**: Alert rules created but no alerts generated

**Solutions**:
1. Check rule is enabled:
   ```bash
   curl http://localhost:8000/api/v1/alerts/rules | jq '.[] | select(.enabled == false)'
   ```

2. Verify metric path is correct:
   ```python
   from analytics.core.streaming.metric_streamer import MetricStreamer
   streamer = MetricStreamer()
   metrics = streamer.collect_metrics()
   print(metrics.keys())  # Show available metric paths
   ```

3. Check alert evaluation interval in `analytics.yaml`:
   ```yaml
   realtime:
     alert_check_interval: 60  # Ensure this is reasonable
   ```

4. Review logs for evaluation errors:
   ```bash
   tail -f ~/.dream-studio/logs/analytics.log | grep "AlertEvaluator"
   ```

---

### SLA Compliance Calculation Issues

**Problem**: SLA showing 0.0 or incorrect values

**Solutions**:
1. Verify sufficient data exists in time window:
   ```python
   tracker = SLATracker()
   # Reduce window for testing
   tracker.define_sla(name="Test", metric="sessions_avg_duration", 
                      target=20.0, window=1)  # 1-hour window
   ```

2. Check database tables exist:
   ```bash
   sqlite3 ~/.dream-studio/state/studio.db ".tables"
   # Should include: raw_sessions, raw_skill_telemetry, raw_workflow_runs
   ```

3. Verify metric calculation query:
   ```python
   import sqlite3
   conn = sqlite3.connect("~/.dream-studio/state/studio.db")
   cursor = conn.cursor()
   cursor.execute("SELECT COUNT(*) FROM raw_sessions")
   print(f"Sessions in database: {cursor.fetchone()[0]}")
   ```

4. Review SLA type inference:
   ```python
   tracker = SLATracker()
   # Explicitly specify sla_type to avoid inference errors
   tracker.define_sla(..., sla_type="response_time")
   ```

---

### Notification Channels Not Working

**Problem**: Alerts triggered but notifications not received

**Solutions**:

1. **Console channel not logging**:
   - Check logging configuration
   - Verify console output is not redirected

2. **File channel not writing**:
   - Check file permissions:
     ```bash
     ls -la ~/.dream-studio/logs/notifications.jsonl
     ```
   - Verify parent directory exists:
     ```bash
     mkdir -p ~/.dream-studio/logs
     ```

3. **Webhook channel failing**:
   - Test webhook URL manually:
     ```bash
     curl -X POST https://your-webhook-url \
       -H "Content-Type: application/json" \
       -d '{"test": "message"}'
     ```
   - Check network connectivity and SSL certificates
   - Review webhook service logs (Slack, Teams, etc.)

4. **Channels not registered**:
   ```python
   from analytics.core.notifications.dispatcher import NotificationDispatcher
   dispatcher = NotificationDispatcher()
   
   # Verify channels
   print(dispatcher.channels.keys())  # Should show registered channels
   ```

---

### API Server Won't Start

**Problem**: `python -m analytics.api.main` fails

**Solutions**:

1. Check port availability:
   ```bash
   # Windows
   netstat -ano | findstr :8000
   
   # Linux/Mac
   lsof -i :8000
   ```

2. Install missing dependencies:
   ```bash
   pip install fastapi uvicorn websockets
   ```

3. Verify Python version (3.9+ required):
   ```bash
   python --version
   ```

4. Check database file permissions:
   ```bash
   ls -la ~/.dream-studio/state/studio.db
   ```

---

### High Memory Usage

**Problem**: Analytics platform consuming excessive memory

**Solutions**:

1. Increase polling interval to reduce data collection frequency:
   ```yaml
   realtime:
     poll_interval: 300  # 5 minutes instead of 1 minute
   ```

2. Limit WebSocket connections:
   - Review active connections:
     ```bash
     curl http://localhost:8000/api/v1/connection-stats
     ```
   - Close idle connections
   - Implement connection limit in production

3. Prune old data from database:
   ```bash
   sqlite3 ~/.dream-studio/state/studio.db
   > DELETE FROM alert_history WHERE triggered_at < datetime('now', '-30 days');
   > VACUUM;
   ```

4. Reduce alert history retention:
   ```bash
   curl "http://localhost:8000/api/v1/alerts/history?limit=100"  # Lower limit
   ```

---

## Getting Started

### Quick Start

1. **Start the API server**:
   ```bash
   cd analytics
   python -m api.main
   ```

2. **Open API documentation**:
   ```
   http://localhost:8000/api/docs
   ```

3. **Create your first alert rule**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/alerts/rules \
     -H "Content-Type: application/json" \
     -d '{
       "rule_name": "Test Alert",
       "metric_path": "skills_success_rate",
       "condition": "lt",
       "threshold": 90.0,
       "severity": "warning"
     }'
   ```

4. **Connect to WebSocket stream**:
   ```bash
   # Using websocat
   websocat ws://localhost:8000/api/v1/stream/metrics
   
   # Then send:
   {"type": "subscribe", "metrics": ["sessions", "skills"]}
   ```

### Production Deployment

For production use:

1. Use a production WSGI server (gunicorn, hypercorn)
2. Configure HTTPS/WSS for WebSocket security
3. Set up proper CORS policies in `api/main.py`
4. Enable authentication/authorization
5. Configure external notification channels (Slack, PagerDuty)
6. Set up database backups
7. Monitor API performance and set resource limits

---

## Support

For issues, questions, or contributions:
- GitHub Issues: [dream-studio repository](https://github.com/your-org/dream-studio)
- Documentation: `analytics/docs/`
- API Docs: `http://localhost:8000/api/docs`
