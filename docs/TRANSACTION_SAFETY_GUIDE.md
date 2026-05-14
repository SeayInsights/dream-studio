# Transaction Safety Migration Guide

**Created:** 2026-05-07  
**Phase:** 2 - Runtime Stabilization

---

## Problem

Transaction audit identified **249 unsafe write operations** across the codebase. These writes are not properly wrapped in transactions, which can lead to:

- **Data corruption** if process crashes mid-write
- **Inconsistent state** if multi-statement operations partially fail
- **Race conditions** in concurrent writes
- **Loss of atomicity** for related operations

---

## Solution Pattern

### Before (Unsafe):
```python
import sqlite3

conn = sqlite3.connect(db_path)
conn.execute("INSERT INTO table1 VALUES (?)", [value1])
conn.execute("INSERT INTO table2 VALUES (?)", [value2])
conn.commit()
conn.close()
```

**Problems:**
- Manual commit/rollback management
- Connection not closed on exception
- No automatic rollback on error

### After (Safe):
```python
from core.config.database import transaction

with transaction() as conn:
    conn.execute("INSERT INTO table1 VALUES (?)", [value1])
    conn.execute("INSERT INTO table2 VALUES (?)", [value2])
# Auto-commits on success, auto-rollbacks on exception
```

**Benefits:**
- ✅ Automatic commit on success
- ✅ Automatic rollback on error
- ✅ Connection properly closed
- ✅ WAL mode enabled by default
- ✅ Foreign keys enforced

---

## Migration Checklist

### 1. Replace Direct Connections

**Find:**
```python
import sqlite3
conn = sqlite3.connect(db_path)
```

**Replace with:**
```python
from core.config.database import transaction
# (no connection creation needed)
```

### 2. Wrap Write Operations

**Find:**
```python
def save_data(value):
    conn = get_connection()
    conn.execute("INSERT INTO table VALUES (?)", [value])
    conn.commit()
    conn.close()
```

**Replace with:**
```python
def save_data(value):
    with transaction() as conn:
        conn.execute("INSERT INTO table VALUES (?)", [value])
```

### 3. Handle Read-Only Operations

**For reads, use DatabaseContext:**
```python
from core.config.database import DatabaseContext

with DatabaseContext(read_only=True) as conn:
    rows = conn.execute("SELECT * FROM table").fetchall()
```

### 4. Immediate Transactions for Writes

**For write-heavy operations, use immediate mode:**
```python
with transaction(immediate=True) as conn:
    # BEGIN IMMEDIATE locks database for writing
    conn.execute("UPDATE large_table SET ...")
```

---

## Critical Files by Priority

### Priority 1: Core Infrastructure (67 unsafe writes)
1. **core/event_store/studio_db.py** (54 writes)
   - Main event/activity storage
   - High write volume
   - Critical for system integrity

2. **core/security/project_resolver.py** (6 writes)
   - Security finding linkage
   - Foreign key relationships

3. **projections/api/routes/alerts.py** (4 writes)
   - API endpoints
   - User-facing operations

4. **scripts/security_scan_production.py** (4 writes)
   - Production security scans
   - Large batch operations

### Priority 2: Control Layer (34 unsafe writes)
5. **control/analysis/engine.py** (21 writes)
   - Analysis results storage
   - Multi-table updates

6. **control/research/memory.py** (13 writes)
   - Research state persistence
   - Consistency critical

### Priority 3: Other (148 unsafe writes)
- Tests: 17+ files with unsafe writes (acceptable in tests)
- Migrations: 6 files (one-time scripts, safe to leave)
- CLI tools: 20+ files (consider migrating high-use tools)

---

## Implementation Pattern

### Single-Table Writes
```python
def create_finding(finding_data: dict):
    """Create a security finding."""
    with transaction() as conn:
        conn.execute("""
            INSERT INTO sec_findings (
                finding_id, scan_id, severity, title, description
            ) VALUES (?, ?, ?, ?, ?)
        """, [
            finding_data['id'],
            finding_data['scan_id'],
            finding_data['severity'],
            finding_data['title'],
            finding_data['description']
        ])
```

### Multi-Table Writes (Atomic)
```python
def create_scan_with_findings(scan_data: dict, findings: list):
    """Create scan and all findings atomically."""
    with transaction() as conn:
        # Insert scan
        conn.execute("""
            INSERT INTO sec_scans (scan_id, node_id, scan_type, tool_name)
            VALUES (?, ?, ?, ?)
        """, [scan_data['id'], scan_data['node_id'], scan_data['type'], scan_data['tool']])

        # Insert all findings
        for finding in findings:
            conn.execute("""
                INSERT INTO sec_findings (finding_id, scan_id, severity, title)
                VALUES (?, ?, ?, ?)
            """, [finding['id'], scan_data['id'], finding['severity'], finding['title']])

    # If any statement fails, entire transaction is rolled back
```

### Batch Operations
```python
def batch_insert_events(events: list):
    """Insert multiple events efficiently."""
    with transaction(immediate=True) as conn:
        conn.executemany("""
            INSERT INTO events (event_id, event_type, event_data)
            VALUES (?, ?, ?)
        """, [(e['id'], e['type'], e['data']) for e in events])
```

### Error Handling
```python
def update_with_retry(data: dict):
    """Update with automatic retry on lock."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with transaction() as conn:
                conn.execute("UPDATE table SET value = ? WHERE id = ?", 
                           [data['value'], data['id']])
            return  # Success
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                continue
            raise
```

---

## Testing Migration

### Before Migration - Capture Baseline
```bash
python scripts/audit_transactions.py > before.txt
```

### After Migration - Verify Improvement
```bash
python scripts/audit_transactions.py > after.txt
diff before.txt after.txt
```

### Verify WAL Mode
```python
from core.config.database import health_check
print(health_check())
# Should show: wal_mode: True
```

---

## Rollback Procedure

If migration causes issues:

1. **Revert code changes** via git
2. **Check database integrity:**
   ```python
   from core.config.database import health_check
   health = health_check()
   assert health['integrity'] == 'ok'
   ```

3. **Backup database before major migrations:**
   ```bash
   cp ~/.dream-studio/state/dream-studio.db ~/.dream-studio/state/dream-studio.db.backup
   ```

---

## Success Criteria

- [ ] Unsafe writes reduced from 249 to <50
- [ ] All Priority 1 files migrated
- [ ] All Priority 2 files migrated
- [ ] Transaction audit passes
- [ ] All tests pass
- [ ] WAL mode enabled on all databases
- [ ] No degradation in performance

---

## Common Pitfalls

### ❌ Don't: Nest transactions
```python
# WRONG - nested transactions
with transaction() as conn1:
    conn1.execute("INSERT ...")
    with transaction() as conn2:  # Creates new connection!
        conn2.execute("INSERT ...")
```

### ✅ Do: Use single transaction
```python
# CORRECT - single transaction scope
with transaction() as conn:
    conn.execute("INSERT INTO table1 ...")
    conn.execute("INSERT INTO table2 ...")
```

### ❌ Don't: Mix old and new patterns
```python
# WRONG - mixing patterns
conn = sqlite3.connect(db_path)
with transaction() as trans_conn:
    trans_conn.execute("INSERT ...")
conn.execute("INSERT ...")  # Not in transaction!
```

### ✅ Do: Use consistent pattern
```python
# CORRECT - all writes in transaction
with transaction() as conn:
    conn.execute("INSERT INTO table1 ...")
    conn.execute("INSERT INTO table2 ...")
```

---

## Next Steps

1. **Prioritize by impact:** Start with core/event_store/studio_db.py
2. **Migrate incrementally:** One file at a time, test between changes
3. **Run audit after each file:** Verify unsafe write count decreases
4. **Update tests:** Ensure tests use transaction() pattern
5. **Document exceptions:** Some tools (migrations, one-off scripts) can stay as-is

---

**Created by:** Execution OS Convergence - Phase 2  
**Last Updated:** 2026-05-07
