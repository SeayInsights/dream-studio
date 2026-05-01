---
name: binary-scan
model_tier: opus
description: "Binary/executable analysis — checksec hardening, YARA malware signatures, PE/ELF metadata extraction. Trigger on binary-scan:, scan binary, analyze exe, checksec."
user_invocable: true
args: mode
argument-hint: "[setup | analyze | ingest | status] [--client <name>] [--target <name>]"
pack: security
chain_suggests:
  - condition: "findings_found"
    next: "mitigate"
    prompt: "Binary findings — run mitigate?"
---

# Binary Scan — Executable Analysis

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`binary-scan:`, `scan binary`, `analyze exe`, `checksec`, `/binary-scan`

## Purpose
Orchestrate binary and executable security analysis against binary targets defined in the client profile. The skill generates YARA rules, checksec configurations, and analysis scripts; executes binary analysis locally; and ingests results into the unified findings store for downstream skills (mitigate, comply, security-dashboard).

## Modes
- `setup` — Generate YARA rules, checksec config, and analysis scripts for each binary target.
- `analyze` — Execute binary analysis locally (checksec, YARA, strings extraction, PE/ELF parsing).
- `ingest` — Parse checksec + YARA + strings results into unified findings with `target_type: binary`.
- `status` — Show binary analysis coverage: which binaries are analyzed, staleness.

---

## Anti-Patterns

- **Analyzing untrusted binaries without sandboxing** — YARA scanning is safe (read-only pattern matching), but strings extraction and header parsing should not execute the binary. Never run the binary itself.
- **Skipping platform detection** — checksec behavior differs by platform. Always detect OS and use the appropriate tool (checksec vs winchecksec vs codesign).
- **Missing binary hash** — every analysis result must include the SHA256 hash for traceability. If two analyses produce different results, the hash tells you if the binary changed.
- **Ingesting without scan-meta.json** — same as DAST/SAST: every scan directory must have `scan-meta.json` with `target_type: binary`.
- **Running on wrong platform** — a Windows PE analyzed on Linux may produce incomplete results (no winchecksec). Warn the user when the analysis platform doesn't match the target platform.
- **Ignoring Ghidra/IDA exports** — the `ingest` mode should accept manually-produced analysis exports. Not all binary analysis can be automated.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
