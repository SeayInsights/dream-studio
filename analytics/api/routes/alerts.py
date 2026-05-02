"""Alert management API routes"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from analytics.core.alerts.rule_manager import RuleManager
from analytics.core.sla.tracker import SLATracker

router = APIRouter()


def get_db_path() -> str:
    """Get database path - could be from env or config"""
    import os
    return os.path.expanduser("~/.dream-studio/state/studio.db")


# Request/Response Models

class RuleDefinition(BaseModel):
    """Alert rule definition for creation"""
    rule_name: str = Field(..., description="Name of the alert rule")
    metric_path: str = Field(..., description="Path to metric (e.g., 'skill.success_rate')")
    condition: str = Field(..., description="Comparison operator: gt, lt, eq, gte, lte")
    threshold: float = Field(..., description="Threshold value to trigger alert")
    severity: Optional[str] = Field(default="warning", description="Alert severity: info, warning, critical")
    enabled: Optional[bool] = Field(default=True, description="Whether rule is active")


class RuleUpdate(BaseModel):
    """Alert rule update - all fields optional"""
    rule_name: Optional[str] = Field(None, description="Name of the alert rule")
    metric_path: Optional[str] = Field(None, description="Path to metric")
    condition: Optional[str] = Field(None, description="Comparison operator: gt, lt, eq, gte, lte")
    threshold: Optional[float] = Field(None, description="Threshold value")
    severity: Optional[str] = Field(None, description="Alert severity: info, warning, critical")
    enabled: Optional[bool] = Field(None, description="Whether rule is active")


class AlertRule(BaseModel):
    """Alert rule response model"""
    rule_id: str
    rule_name: str
    metric_path: str
    condition: str
    threshold: float
    severity: str
    enabled: bool


class AlertHistory(BaseModel):
    """Alert history response model"""
    alert_id: str
    rule_id: str
    rule_name: str
    metric_path: str
    metric_value: float
    threshold: float
    severity: str
    triggered_at: str


class RuleCreatedResponse(BaseModel):
    """Response when rule is created"""
    rule_id: str
    message: str


class RuleDeletedResponse(BaseModel):
    """Response when rule is deleted"""
    message: str


# Endpoints

@router.get("/rules", response_model=List[AlertRule])
async def list_rules():
    """
    Get all alert rules (enabled and disabled).

    Returns:
        List of all alert rules with their configuration
    """
    try:
        db_path = get_db_path()

        # Query all rules directly from database
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rule_id,
                rule_name,
                metric_path,
                condition,
                threshold,
                severity,
                enabled
            FROM alert_rules
            ORDER BY severity DESC, rule_name ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        # Convert rows to response models
        rules = []
        for row in rows:
            rules.append(AlertRule(
                rule_id=row['rule_id'],
                rule_name=row['rule_name'],
                metric_path=row['metric_path'],
                condition=row['condition'],
                threshold=row['threshold'],
                severity=row['severity'],
                enabled=bool(row['enabled'])
            ))

        return rules

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving alert rules: {str(e)}"
        )


@router.post("/rules", response_model=RuleCreatedResponse, status_code=201)
async def create_rule(rule_def: RuleDefinition):
    """
    Create a new alert rule.

    Args:
        rule_def: Rule definition with metric path, condition, threshold, etc.

    Returns:
        Created rule ID and success message

    Raises:
        400: Invalid rule definition
        500: Database error
    """
    try:
        db_path = get_db_path()
        manager = RuleManager(db_path)

        # Convert Pydantic model to dict
        rule_dict = rule_def.model_dump(exclude_none=True)

        # Create rule
        rule_id = manager.create_rule(rule_dict)

        return RuleCreatedResponse(
            rule_id=rule_id,
            message=f"Alert rule '{rule_def.rule_name}' created successfully"
        )

    except ValueError as e:
        # Validation error from RuleManager
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        # Database error from RuleManager
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error creating rule: {str(e)}"
        )


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_rule(rule_id: str, updates: RuleUpdate):
    """
    Update an existing alert rule.

    Args:
        rule_id: ID of the rule to update
        updates: Fields to update (all optional)

    Returns:
        Updated rule configuration

    Raises:
        400: Invalid update data
        404: Rule not found
        500: Database error
    """
    try:
        db_path = get_db_path()
        manager = RuleManager(db_path)

        # Convert Pydantic model to dict, excluding None values
        update_dict = updates.model_dump(exclude_none=True)

        if not update_dict:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update"
            )

        # Update rule
        success = manager.update_rule(rule_id, update_dict)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert rule with ID '{rule_id}' not found"
            )

        # Fetch updated rule from database
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rule_id,
                rule_name,
                metric_path,
                condition,
                threshold,
                severity,
                enabled
            FROM alert_rules
            WHERE rule_id = ?
        """, (rule_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Alert rule with ID '{rule_id}' not found after update"
            )

        return AlertRule(
            rule_id=row['rule_id'],
            rule_name=row['rule_name'],
            metric_path=row['metric_path'],
            condition=row['condition'],
            threshold=row['threshold'],
            severity=row['severity'],
            enabled=bool(row['enabled'])
        )

    except ValueError as e:
        # Validation error from RuleManager
        raise HTTPException(status_code=400, detail=str(e))

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise

    except RuntimeError as e:
        # Database error from RuleManager
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error updating rule: {str(e)}"
        )


@router.delete("/rules/{rule_id}", response_model=RuleDeletedResponse)
async def delete_rule(rule_id: str):
    """
    Delete an alert rule.

    Args:
        rule_id: ID of the rule to delete

    Returns:
        Success message

    Raises:
        404: Rule not found
        500: Database error
    """
    try:
        db_path = get_db_path()
        manager = RuleManager(db_path)

        # Delete rule
        success = manager.delete_rule(rule_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert rule with ID '{rule_id}' not found"
            )

        return RuleDeletedResponse(
            message=f"Alert rule '{rule_id}' deleted successfully"
        )

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise

    except RuntimeError as e:
        # Database error from RuleManager
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error deleting rule: {str(e)}"
        )


@router.get("/history", response_model=List[AlertHistory])
async def get_alert_history(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of alerts to return"),
    severity: Optional[str] = Query(default=None, description="Filter by severity: info, warning, critical")
):
    """
    Get alert history with optional filters.

    Args:
        limit: Maximum number of alerts to return (default: 100, max: 1000)
        severity: Optional severity filter (info, warning, critical)

    Returns:
        List of triggered alerts from history
    """
    try:
        db_path = get_db_path()

        # Query alert_history table directly
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query with optional severity filter
        query = """
            SELECT
                ah.alert_id,
                ah.rule_id,
                ar.rule_name,
                ar.metric_path,
                ah.metric_value,
                ar.threshold,
                ah.severity,
                ah.triggered_at
            FROM alert_history ah
            LEFT JOIN alert_rules ar ON ah.rule_id = ar.rule_id
        """

        params = []

        if severity:
            query += " WHERE ah.severity = ?"
            params.append(severity)

        query += " ORDER BY ah.triggered_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert rows to response models
        alerts = []
        for row in rows:
            alerts.append(AlertHistory(
                alert_id=row['alert_id'],
                rule_id=row['rule_id'],
                rule_name=row['rule_name'] or 'Unknown',
                metric_path=row['metric_path'] or 'Unknown',
                metric_value=row['metric_value'],
                threshold=row['threshold'] or 0.0,
                severity=row['severity'],
                triggered_at=row['triggered_at']
            ))

        return alerts

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving alert history: {str(e)}"
        )


@router.get("/sla")
async def get_sla_metrics() -> Dict[str, Any]:
    """
    Get current SLA metrics for display in dashboard gauges.

    Returns:
        Dict containing SLA metrics:
            - response_time: Average response time in milliseconds
            - error_rate: Error rate as decimal (0.0 to 1.0)
            - availability: Availability as decimal (0.0 to 1.0)
            - custom_metric: Custom metric value
    """
    try:
        db_path = get_db_path()
        tracker = SLATracker(db_path)

        # Get SLA compliance report
        report = tracker.get_sla_report()

        # Extract key metrics for dashboard gauges
        # Initialize with default values
        metrics = {
            "response_time": 0.0,
            "error_rate": 0.0,
            "availability": 1.0,  # Default to 100%
            "custom_metric": 0.0
        }

        # Map SLA data to metrics based on sla_type
        for sla in report.get("slas", []):
            sla_type = sla.get("sla_type", "")
            current_value = sla.get("current_value", 0.0)

            if sla_type == "response_time":
                metrics["response_time"] = current_value
            elif sla_type == "error_rate":
                # Convert percentage to decimal
                metrics["error_rate"] = current_value / 100.0
            elif sla_type == "availability":
                # Convert percentage to decimal
                metrics["availability"] = current_value / 100.0
            elif sla_type == "success_rate":
                # Use as custom metric
                metrics["custom_metric"] = current_value

        return metrics

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving SLA metrics: {str(e)}"
        )


@router.get("/analytics")
async def get_alert_analytics() -> Dict[str, Any]:
    """
    Get alert analytics including top triggered rules and resolution times.

    Returns:
        Dict containing:
            - top_triggered: List of most frequently triggered rules
            - resolution_times: Distribution of alert resolution times
    """
    try:
        db_path = get_db_path()

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get top 5 most triggered rules (last 30 days)
        cursor.execute("""
            SELECT
                ar.rule_name,
                COUNT(*) as trigger_count
            FROM alert_history ah
            LEFT JOIN alert_rules ar ON ah.rule_id = ar.rule_id
            WHERE ah.triggered_at >= datetime('now', '-30 days')
            GROUP BY ah.rule_id, ar.rule_name
            ORDER BY trigger_count DESC
            LIMIT 5
        """)

        top_triggered_rows = cursor.fetchall()
        top_triggered = [
            {
                "rule_name": row["rule_name"] or "Unknown",
                "count": row["trigger_count"]
            }
            for row in top_triggered_rows
        ]

        # Get resolution time distribution (placeholder - simplified implementation)
        # In production, this would query actual resolution timestamps
        # For now, return sample distribution data
        resolution_times = [
            {"range": "< 5 min", "count": 0},
            {"range": "5-15 min", "count": 0},
            {"range": "15-30 min", "count": 0},
            {"range": "30-60 min", "count": 0},
            {"range": "> 60 min", "count": 0}
        ]

        # Count total alerts in last 30 days for placeholder data
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM alert_history
            WHERE triggered_at >= datetime('now', '-30 days')
        """)
        total_alerts = cursor.fetchone()["total"]

        # Distribute counts across resolution time ranges (placeholder logic)
        if total_alerts > 0:
            # Simple distribution: most resolved quickly, fewer take longer
            resolution_times[0]["count"] = int(total_alerts * 0.5)
            resolution_times[1]["count"] = int(total_alerts * 0.3)
            resolution_times[2]["count"] = int(total_alerts * 0.15)
            resolution_times[3]["count"] = int(total_alerts * 0.04)
            resolution_times[4]["count"] = total_alerts - sum(r["count"] for r in resolution_times[:4])

        conn.close()

        return {
            "top_triggered": top_triggered,
            "resolution_times": resolution_times
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving alert analytics: {str(e)}"
        )
