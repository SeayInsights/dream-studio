"""
SQLite Write Operation Tracer

Provides structured logging for database write operations to enable
runtime verification and breakpoint identification.

Usage:
    from core.observability.trace_logger import trace

    trace.log('INFO', 'TRIGGER', {'function': 'emit_event', 'event_type': 'foo'})
    trace.log('INFO', 'EXECUTE', {'rowcount': 1, 'lastrowid': 123})
    trace.log('INFO', 'COMMIT', {'success': True})
    trace.log('INFO', 'VERIFY', {'persisted': True, 'row_id': 123})
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from enum import Enum


class Stage(str, Enum):
    """Write operation stages"""

    TRIGGER = "TRIGGER"  # Function called
    VALIDATE = "VALIDATE"  # Input validation
    PREPARE = "PREPARE"  # SQL preparation
    EXECUTE = "EXECUTE"  # Query execution
    COMMIT = "COMMIT"  # Transaction commit
    VERIFY = "VERIFY"  # Persistence verification
    ROLLBACK = "ROLLBACK"  # Transaction rollback
    ERROR = "ERROR"  # Error occurred


class TraceLogger:
    """SQLite write operation tracer with structured logging."""

    def __init__(self, trace_file: Optional[Path] = None, console: bool = True):
        """
        Initialize trace logger.

        Args:
            trace_file: Path to trace log file (default: sqlite_trace.jsonl in cwd)
            console: Whether to print to console (default: True)
        """
        self.trace_file = trace_file or Path.cwd() / "sqlite_trace.jsonl"
        self.console = console

        # Create trace file parent directory if needed
        self.trace_file.parent.mkdir(parents=True, exist_ok=True)

        # Stage emoji mapping (use ASCII fallbacks for Windows compatibility)
        self._stage_icons = {
            Stage.TRIGGER: "[TRIGGER]",
            Stage.VALIDATE: "[VALIDATE]",
            Stage.PREPARE: "[PREPARE]",
            Stage.EXECUTE: "[EXECUTE]",
            Stage.COMMIT: "[COMMIT]",
            Stage.VERIFY: "[VERIFY]",
            Stage.ROLLBACK: "[ROLLBACK]",
            Stage.ERROR: "[ERROR]",
        }

    def log(self, level: str, stage: str, data: Dict[str, Any], context: Optional[Dict] = None):
        """
        Log a write operation stage.

        Args:
            level: Log level (DEBUG|INFO|WARN|ERROR)
            stage: Operation stage (TRIGGER|VALIDATE|PREPARE|EXECUTE|COMMIT|VERIFY|ERROR)
            data: Stage-specific data to log
            context: Optional additional context
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        log_entry = {"timestamp": timestamp, "level": level, "stage": stage, "data": data}

        if context:
            log_entry["context"] = context

        # Console output
        if self.console:
            icon = self._stage_icons.get(stage, "[INFO]")
            data_str = json.dumps(data, default=str)
            print(f"{icon} {data_str}", file=sys.stderr)

        # File output for analysis
        try:
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, default=str) + "\n")
        except Exception as e:
            print(f"[TRACE-ERROR] Failed to write trace: {e}", file=sys.stderr)

    def trigger(self, function: str, **kwargs):
        """Log function trigger."""
        data = {"function": function}
        data.update(kwargs)
        self.log("INFO", Stage.TRIGGER, data)

    def validate(self, **kwargs):
        """Log validation stage."""
        self.log("INFO", Stage.VALIDATE, kwargs)

    def prepare(self, table: str, operation: str, **kwargs):
        """Log SQL preparation."""
        data = {"table": table, "operation": operation}
        data.update(kwargs)
        self.log("INFO", Stage.PREPARE, data)

    def execute(self, rowcount: Optional[int] = None, lastrowid: Optional[int] = None, **kwargs):
        """Log query execution."""
        data = {}
        if rowcount is not None:
            data["rowcount"] = rowcount
        if lastrowid is not None:
            data["lastrowid"] = lastrowid
        data.update(kwargs)
        self.log("INFO", Stage.EXECUTE, data)

    def commit(self, success: bool = True, **kwargs):
        """Log transaction commit."""
        data = {"success": success}
        data.update(kwargs)
        self.log("INFO", Stage.COMMIT, data)

    def verify(self, persisted: bool, **kwargs):
        """Log persistence verification."""
        data = {"persisted": persisted}
        data.update(kwargs)
        self.log("INFO", Stage.VERIFY, data)

    def rollback(self, reason: str, **kwargs):
        """Log transaction rollback."""
        data = {"reason": reason}
        data.update(kwargs)
        self.log("WARN", Stage.ROLLBACK, data)

    def error(self, error: str, error_type: Optional[str] = None, **kwargs):
        """Log error."""
        data = {"error": str(error)}
        if error_type:
            data["error_type"] = error_type
        data.update(kwargs)
        self.log("ERROR", Stage.ERROR, data)

    def clear(self):
        """Clear trace log file."""
        if self.trace_file.exists():
            self.trace_file.unlink()

    def get_traces(self) -> list:
        """Read all traces from log file."""
        if not self.trace_file.exists():
            return []

        traces = []
        with open(self.trace_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        traces.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return traces

    def analyze(self):
        """Analyze trace log for issues."""
        traces = self.get_traces()

        if not traces:
            print("No traces found.")
            return

        print(f"\n{'='*60}")
        print(f"TRACE ANALYSIS")
        print(f"{'='*60}")
        print(f"Total entries: {len(traces)}")

        # Count by stage
        stage_counts = {}
        for trace in traces:
            stage = trace["stage"]
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        print(f"\nStage counts:")
        for stage, count in sorted(stage_counts.items()):
            print(f"  {stage}: {count}")

        # Find broken flows (EXECUTE without COMMIT)
        executes = stage_counts.get(Stage.EXECUTE, 0)
        commits = stage_counts.get(Stage.COMMIT, 0)
        verifies = stage_counts.get(Stage.VERIFY, 0)
        errors = stage_counts.get(Stage.ERROR, 0)

        print(f"\n{'='*60}")
        print(f"FLOW ANALYSIS")
        print(f"{'='*60}")

        if executes > commits:
            print(f"[WARNING] {executes - commits} executes without commits")

        if commits > verifies:
            print(f"[WARNING] {commits - verifies} commits without verification")

        if errors > 0:
            print(f"[ERROR] {errors} errors occurred")
            print(f"\nError details:")
            for trace in traces:
                if trace["stage"] == Stage.ERROR:
                    print(
                        f"  - {trace['data'].get('function', 'unknown')}: {trace['data'].get('error')}"
                    )

        if executes == commits == verifies and errors == 0:
            print("[OK] All write operations completed successfully")


# Global trace logger instance
trace = TraceLogger()


# Context manager for traced operations
class TracedOperation:
    """Context manager for traced database operations."""

    def __init__(self, function: str, table: str, operation: str):
        self.function = function
        self.table = table
        self.operation = operation
        self.lastrowid = None

    def __enter__(self):
        trace.trigger(self.function, table=self.table, operation=self.operation)
        trace.prepare(self.table, self.operation)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            trace.error(str(exc_val), error_type=exc_type.__name__, function=self.function)
            return False
        return True

    def executed(self, rowcount: int, lastrowid: int):
        """Call after execute()."""
        self.lastrowid = lastrowid
        trace.execute(rowcount=rowcount, lastrowid=lastrowid, table=self.table)

    def committed(self):
        """Call after commit()."""
        trace.commit(success=True, lastrowid=self.lastrowid)

    def verified(self, conn, table: str):
        """Verify row was persisted."""
        if self.lastrowid:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE rowid = ?", (self.lastrowid,)
            )
            persisted = cursor.fetchone()[0] > 0
            trace.verify(persisted=persisted, lastrowid=self.lastrowid, table=table)
            return persisted
        return False


# Decorator for traced functions
def traced_write(table: str, operation: str):
    """Decorator to trace database write operations."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            with TracedOperation(func.__name__, table, operation) as op:
                result = func(*args, **kwargs)
                return result

        return wrapper

    return decorator
