//! Telemetry emission, matching `runtime/lib/enforcement.py`'s
//! `record_observation`/`record_bypass`/`log_hook_execution` (queued path
//! only -- their `db_path`-override branch is never exercised by
//! `on-edit-enforce.py`'s own call sites, which never pass it).
//!
//! Appends to the SAME `hookq.jsonl` the already-shipped `ds-enqueue` binary
//! and `runtime/hooks/enqueue.py` write, via the shared `ds_enqueue` crate --
//! not a fourth hand-copied implementation of the path/framing rules.
//!
//! Every function here is best-effort: a failure to write telemetry must
//! never affect the enforcement decision, matching the Python `except
//! Exception: pass` around every one of these call sites.

use serde_json::{Map, Value};

use ds_enqueue::{append_line, escape_json, queue_path};

fn now_iso() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_default()
}

/// Mirror `_enqueue_hook_execution`: wrap `record` as `{"event":"hook.execution",
/// "ts":<unix seconds>,"payload":"<record, JSON-encoded as a STRING>"}` and
/// append one line. The inner `record` is serialized compactly rather than
/// with Python's default `, `/`: ` separators -- a format-only difference
/// nothing downstream can observe, since every reader parses `payload` back
/// into a value rather than comparing its bytes.
fn enqueue_hook_execution(record: &Value) {
    let Some(path) = queue_path() else { return };
    let payload = serde_json::to_string(record).unwrap_or_default();
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    let mut line = String::with_capacity(payload.len() + 64);
    line.push_str("{\"event\":\"hook.execution\",\"ts\":");
    line.push_str(&format!("{ts}"));
    line.push_str(",\"payload\":\"");
    escape_json(&payload, &mut line);
    line.push_str("\"}\n");

    append_line(&path, &line);
}

fn opt_str(s: Option<&str>) -> Value {
    s.map(|v| Value::String(v.to_string())).unwrap_or(Value::Null)
}

/// Mirror `record_observation` (queued path): a would-have-denied action at
/// the observe/warn tier, carrying the SAME reason string `enforce` would
/// have used.
pub fn record_observation(hook_name: &str, hook_type: &str, rule: &str, reason: &str, tier: &str, session_id: Option<&str>) {
    let mut trigger_context = Map::new();
    trigger_context.insert("decision".into(), Value::String("observe".into()));
    trigger_context.insert("tier".into(), Value::String(tier.into()));
    trigger_context.insert("rule".into(), Value::String(rule.into()));
    trigger_context.insert("would_deny_reason".into(), Value::String(reason.into()));

    let mut record = Map::new();
    record.insert("hook_name".into(), Value::String(hook_name.into()));
    record.insert("hook_type".into(), Value::String(hook_type.into()));
    record.insert("trigger_context".into(), Value::Object(trigger_context));
    record.insert("started_at".into(), Value::String(now_iso()));
    record.insert("completed_at".into(), Value::String(now_iso()));
    record.insert("duration_ms".into(), Value::Number(0.into()));
    record.insert("exit_code".into(), Value::Number(0.into()));
    record.insert("status".into(), Value::String("success".into()));
    record.insert("session_id".into(), opt_str(session_id));

    enqueue_hook_execution(&Value::Object(record));
}

/// Mirror `record_bypass`: an enforcement bypass or fail-open, on the same
/// `HOOK_EXECUTION_LOGGED` event `record_observation` uses (`decision ==
/// "bypass"` is what tells the two apart downstream).
pub fn record_bypass(hook_name: &str, hook_type: &str, rule: &str, detail: &str, session_id: Option<&str>) {
    let mut trigger_context = Map::new();
    trigger_context.insert("decision".into(), Value::String("bypass".into()));
    trigger_context.insert("rule".into(), Value::String(rule.into()));
    trigger_context.insert("detail".into(), Value::String(detail.into()));

    let mut record = Map::new();
    record.insert("hook_name".into(), Value::String(hook_name.into()));
    record.insert("hook_type".into(), Value::String(hook_type.into()));
    record.insert("trigger_context".into(), Value::Object(trigger_context));
    record.insert("started_at".into(), Value::String(now_iso()));
    record.insert("completed_at".into(), Value::String(now_iso()));
    record.insert("duration_ms".into(), Value::Number(0.into()));
    record.insert("exit_code".into(), Value::Number(0.into()));
    record.insert("status".into(), Value::String("success".into()));
    record.insert("session_id".into(), opt_str(session_id));

    enqueue_hook_execution(&Value::Object(record));
}

/// Mirror `log_hook_execution`: this directly-wired hook's own execution
/// record, so it appears in the DuckDB `hook_executions` view the same way a
/// dispatched hook's does.
pub fn log_hook_execution(
    hook_name: &str,
    hook_type: &str,
    started_at: &str,
    duration_ms: i64,
    decision: &str,
    status: &str,
    error_message: Option<&str>,
    session_id: Option<&str>,
) {
    let mut trigger_context = Map::new();
    trigger_context.insert("decision".into(), Value::String(decision.into()));

    let mut record = Map::new();
    record.insert("hook_name".into(), Value::String(hook_name.into()));
    record.insert("hook_type".into(), Value::String(hook_type.into()));
    record.insert("trigger_context".into(), Value::Object(trigger_context));
    record.insert("started_at".into(), Value::String(started_at.into()));
    record.insert("completed_at".into(), Value::String(now_iso()));
    record.insert("duration_ms".into(), Value::Number(duration_ms.into()));
    record.insert("exit_code".into(), Value::Number(0.into()));
    record.insert("status".into(), Value::String(status.into()));
    record.insert("error_message".into(), opt_str(error_message));
    record.insert("session_id".into(), opt_str(session_id));

    enqueue_hook_execution(&Value::Object(record));
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::sync::Mutex;

    // DS_HOME is process-global state, and cargo test runs these in parallel
    // threads within ONE process -- without this, two tests race on the same
    // env var (whichever set it last wins for both) even with distinct
    // directories.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn with_ds_home<F: FnOnce()>(name: &str, f: F) -> std::path::PathBuf {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let dir = std::env::temp_dir().join(format!("ds-enforce-queue-test-{name}-{}", std::process::id()));
        std::fs::remove_dir_all(&dir).ok();
        std::fs::create_dir_all(&dir).unwrap();
        std::env::set_var("DS_HOME", &dir);
        f();
        std::env::remove_var("DS_HOME");
        dir
    }

    fn read_queue(dir: &std::path::Path) -> String {
        let mut s = String::new();
        std::fs::File::open(dir.join("state").join("hookq.jsonl")).unwrap().read_to_string(&mut s).unwrap();
        s
    }

    #[test]
    fn record_observation_writes_a_parseable_line_with_the_reason() {
        let dir = with_ds_home("observation", || {
            record_observation(
                "on_edit_enforce",
                "PreToolUse",
                "authority_source_edit",
                "no work order",
                "observe",
                Some("sess1"),
            );
        });
        let raw = read_queue(&dir);
        let outer: Value = serde_json::from_str(raw.trim_end()).unwrap();
        assert_eq!(outer["event"], "hook.execution");
        let inner: Value = serde_json::from_str(outer["payload"].as_str().unwrap()).unwrap();
        assert_eq!(inner["trigger_context"]["decision"], "observe");
        assert_eq!(inner["trigger_context"]["would_deny_reason"], "no work order");
        assert_eq!(inner["session_id"], "sess1");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn record_bypass_marks_decision_bypass() {
        let dir = with_ds_home("bypass", || {
            record_bypass("enforcement_lib", "PreToolUse", "fail_open_authority_db", "db missing", None);
        });
        let raw = read_queue(&dir);
        let outer: Value = serde_json::from_str(raw.trim_end()).unwrap();
        let inner: Value = serde_json::from_str(outer["payload"].as_str().unwrap()).unwrap();
        assert_eq!(inner["trigger_context"]["decision"], "bypass");
        assert_eq!(inner["session_id"], Value::Null);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn log_hook_execution_carries_the_decision_and_error() {
        let dir = with_ds_home("log-hook-execution", || {
            log_hook_execution(
                "on_edit_enforce",
                "PreToolUse",
                "2026-09-26T00:00:00Z",
                12,
                "deny",
                "failed",
                Some("boom"),
                Some("sess2"),
            );
        });
        let raw = read_queue(&dir);
        let outer: Value = serde_json::from_str(raw.trim_end()).unwrap();
        let inner: Value = serde_json::from_str(outer["payload"].as_str().unwrap()).unwrap();
        assert_eq!(inner["trigger_context"]["decision"], "deny");
        assert_eq!(inner["status"], "failed");
        assert_eq!(inner["error_message"], "boom");
        assert_eq!(inner["duration_ms"], 12);
        std::fs::remove_dir_all(&dir).ok();
    }
}
