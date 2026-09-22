//! PreToolUse edit enforcement, native.
//!
//! Ported because after this session's work 57 of the hook's 98 ms is Python
//! interpreter start plus stdlib import, and nothing heavy is left to remove:
//! the telemetry it used to write inline now goes to the append-only queue. It
//! blocks every Edit, Write and Bash, five or so times a turn, so what remains
//! is irreducibly the cost of being a Python program.
//!
//! The decision itself lives in `decision.rs` as pure functions checked against
//! the same contract table the Python implementation is checked against.

mod decision;

fn main() {
    // Scaffold only: the decision module is complete and under test. Wiring it
    // to stdin, the authority and the queue is the remaining work, and it is
    // deliberately not half-done here -- a blocking hook that is partly wired is
    // a hook that denies real edits for reasons nobody can read.
    std::process::exit(0);
}
