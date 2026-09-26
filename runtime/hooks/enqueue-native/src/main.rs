//! Append-only Dream Studio hook entry point: record the event, exit.
//!
//! This is a native rewrite of `runtime/hooks/enqueue.py`, which is itself a
//! rewrite of "import the whole platform to write one telemetry row".
//!
//! Measured on the operator's machine, 2026-09-21, per hook invocation:
//!
//!     the original dispatcher ...............  283 ms
//!     enqueue.py (Python, no DS imports) ....   55 ms
//!     this binary ...........................   see tests/bench in the PR
//!
//! The first jump was architectural and is where most of the win lives: the
//! old hook cold-loaded pydantic, jsonschema and the event store so it could
//! append a line. The second jump is the language, and it is worth taking only
//! because PostToolUse fires on every single tool call -- 92,315 runs against
//! 19,787 prompts in one timing log. At that frequency the ~33 ms Python
//! interpreter floor is itself the remaining cost.
//!
//! Behaviour is intentionally identical to enqueue.py, including the failure
//! mode: THIS MUST NEVER FAIL THE TOOL CALL IT OBSERVES. Every error path here
//! ends in exit code 0. A dropped telemetry record costs a row in a chart; a
//! non-zero exit costs the user their work.

use std::env;
use std::io::Read;
use std::time::{SystemTime, UNIX_EPOCH};

use ds_enqueue::{append_line, escape_json, queue_path};

/// Matches `_MAX_PAYLOAD` in enqueue.py. A hook payload larger than this is a
/// bug upstream, and truncating beats spooling megabytes per tool call.
const MAX_PAYLOAD: usize = 64 * 1024;

fn run() -> Option<()> {
    let event = env::args().nth(1).unwrap_or_default();

    // Read at most MAX_PAYLOAD. take() bounds it without allocating for a
    // pathological writer, and a lossy conversion keeps a non-UTF-8 payload
    // from turning into a dropped record.
    let mut buf = Vec::with_capacity(4096);
    std::io::stdin()
        .take(MAX_PAYLOAD as u64)
        .read_to_end(&mut buf)
        .ok()?;
    let payload = String::from_utf8_lossy(&buf);

    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    let mut line = String::with_capacity(buf.len() + 128);
    line.push_str("{\"event\":\"");
    escape_json(&event, &mut line);
    line.push_str("\",\"ts\":");
    line.push_str(&format!("{ts}"));
    line.push_str(",\"payload\":\"");
    escape_json(&payload, &mut line);
    line.push_str("\"}\n");

    let path = queue_path()?;
    append_line(&path, &line)
}

fn main() {
    // Deliberately ignores the result. See the module docs: every failure path
    // exits 0, because this process observes the user's work and must never be
    // able to interrupt it.
    let _ = run();
}
