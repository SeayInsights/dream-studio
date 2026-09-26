//! PreToolUse edit enforcement, native.
//!
//! Ported because after this session's work 57 of the hook's 98 ms is Python
//! interpreter start plus stdlib import, and nothing heavy is left to remove:
//! the telemetry it used to write inline now goes to the append-only queue. It
//! blocks every Edit, Write and Bash, five or so times a turn, so what remains
//! is irreducibly the cost of being a Python program.
//!
//! The decision itself lives in `decision.rs` as pure functions checked against
//! the same contract table the Python implementation is checked against; the
//! orchestration (candidate extraction, the tier ladder, the authority lookups)
//! is `enforce.rs`. This file is deliberately thin: parse env/stdin, call
//! `enforce::enforce`, write telemetry, exit 0 -- ALWAYS exit 0. `panic =
//! "abort"` in Cargo.toml means a panic anywhere below main() terminates the
//! process with no cleanup and no guaranteed exit code, so nothing here may
//! panic: every fallible call is matched, not unwrapped.

mod db;
mod decision;
mod enforce;
mod paths;
mod queue;
mod session;

use std::io::Read;
use std::path::PathBuf;

fn ds_home() -> Option<PathBuf> {
    match std::env::var("DS_HOME") {
        Ok(h) if !h.is_empty() => Some(PathBuf::from(h)),
        _ => {
            let base = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")).ok()?;
            Some(PathBuf::from(base).join(".dream-studio"))
        }
    }
}

fn env() -> Option<enforce::Env> {
    let home = ds_home()?;
    Some(enforce::Env {
        authority_db: home.join("state").join("studio.db"),
        session_dir: home.join("state").join("enforce"),
        ds_home: home,
        temp_root: std::env::temp_dir(),
    })
}

fn read_stdin_payload() -> Result<serde_json::Value, ()> {
    let mut buf = Vec::new();
    if std::io::stdin().read_to_end(&mut buf).is_err() {
        return Err(());
    }
    let raw = String::from_utf8_lossy(&buf);
    let raw = raw.trim_start_matches('\u{feff}');
    if raw.trim().is_empty() {
        return Ok(serde_json::Value::Object(serde_json::Map::new()));
    }
    serde_json::from_str(raw).map_err(|_| ())
}

fn now_iso() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_default()
}

fn main() {
    let tier = match std::env::var("DS_ENFORCE") {
        Ok(v) => decision::resolve_tier(Some(&v), std::env::var("DS_ENFORCE_TIER").ok().as_deref()),
        Err(_) => decision::resolve_tier(None, std::env::var("DS_ENFORCE_TIER").ok().as_deref()),
    };

    if tier == decision::Tier::Off {
        // WO-BYPASS-TELEMETRY: the escape hatch still works, but it leaves a
        // mark -- every enforcement decision suppressed by DS_ENFORCE=0 is
        // recorded before the short-circuit.
        queue::record_bypass(
            "on_edit_enforce",
            "PreToolUse",
            "enforcement_disabled",
            "DS_ENFORCE=0 / DS_ENFORCE_TIER=off — edit enforcement short-circuited",
            None,
        );
        return;
    }

    let tier_str = match tier {
        decision::Tier::Observe => "observe",
        decision::Tier::Warn => "warn",
        decision::Tier::Enforce => "enforce",
        decision::Tier::Off => unreachable!("handled above"),
    };

    let started_at = now_iso();
    let start = std::time::Instant::now();

    let Some(env) = env() else {
        // DS_HOME cannot be resolved at all (no USERPROFILE/HOME either) --
        // fail open with no telemetry, matching the Python import-failure path
        // this has no direct equivalent of (nothing here can fail to import).
        return;
    };

    let (decision, session_id) = match read_stdin_payload() {
        Ok(payload) => enforce::enforce(&env, tier_str, &payload, &mut std::io::stdout()),
        Err(()) => (enforce::Decision::Noop, None),
    };

    let duration_ms = start.elapsed().as_millis().min(i64::MAX as u128) as i64;
    queue::log_hook_execution(
        "on_edit_enforce",
        "PreToolUse",
        &started_at,
        duration_ms,
        decision.as_str(),
        "success",
        None,
        session_id.as_deref(),
    );
}
