---
name: binary-scan
description: "Binary/executable analysis — checksec hardening, YARA malware signatures, PE/ELF metadata extraction. Trigger on binary-scan:, scan binary, analyze exe, checksec."
user_invocable: true
args: mode
argument-hint: "[setup | analyze | ingest | status] [--client <name>] [--target <name>]"
pack: security
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

## Storage
See `docs/security-storage-layout.md`. See skill-specific paths in layout doc.

## Templates
See `templates/security/README.md` for template registry.

## Client Profile
See `docs/client-profile-schema.md`. Required fields vary by mode.

---

## Client Profile Fields Used

Read from `~/.dream-studio/clients/{name}.yaml`:

| Profile field | Used by |
|---|---|
| `client.name` | All modes — identity |
| `targets.binaries[]` | All modes — target list |
| `targets.binaries[].artifact_source` | `setup`, `analyze` — where to get the binary |
| `targets.binaries[].artifact_repo` | `setup`, `analyze` — GitHub release source |
| `targets.binaries[].artifact_pattern` | `setup`, `analyze` — filename glob |
| `targets.binaries[].path` | `analyze` — local binary path |
| `targets.binaries[].platform` | `setup`, `analyze` — platform-specific tooling |
| `data.critical`, `data.sensitive`, `data.pii_patterns` | `setup` — YARA rule generation |

---

## Mode: `setup`

### Step S0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--target <name>` — optional. If absent, generate for all `targets.binaries`.

### Step S1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** with profile-not-found error.
3. Validate `targets.binaries` is present and non-empty.
4. If missing: **stop** with — "No binary targets defined in profile."

### Step S2: Generate YARA Rules

For each binary target:

1. Read `builds/dream-studio/templates/security/binary/yara-rules.yar.j2`.
2. Fill variables from client profile: `data.pii_patterns`, `data.critical` terms, `data.sensitive` terms.
3. Include hardcoded signature patterns for: hardcoded credentials, embedded URLs/IPs, known packer signatures.
4. Write to `~/.dream-studio/security/binary/{client}/{target.name}/yara-rules.yar`.

### Step S3: Generate checksec Config

1. Read `builds/dream-studio/templates/security/binary/checksec-config.yaml.j2`.
2. Configure checks based on `target.platform`:
   - Linux: NX, PIE, RELRO, Stack Canaries, FORTIFY, RUNPATH
   - Windows: DEP, ASLR, CFG, SafeSEH, Authenticode
   - macOS: PIE, Stack Canaries, ARC, Code Signing
3. Write to `~/.dream-studio/security/binary/{client}/{target.name}/checksec-config.yaml`.

### Step S4: Generate Analysis Script

1. Read `builds/dream-studio/templates/security/binary/analyze.sh.j2`.
2. Render platform-appropriate commands.
3. Write to `~/.dream-studio/security/binary/{client}/{target.name}/analyze.sh`.

### Step S5: Generate GitHub Actions Workflow

1. Read `builds/dream-studio/templates/security/github-actions/binary-scan.yml.j2`.
2. Fill variables from all binary targets.
3. Write to `~/.dream-studio/security/actions/{client}/binary-scan.yml`.

### Step S6: Present Output

Show: files generated, next steps for local analysis or CI setup.

---

## Mode: `analyze`

### Step A0: Parse Arguments

- `--client <name>` — required.
- `--target <name>` — optional.

### Step A1: Load Config and Validate

1. Read client profile. Validate `targets.binaries` is present.
2. Confirm analysis config exists for the target. If absent: **stop** — "Run `binary-scan setup` first."

### Step A2: Locate Binary

Based on `artifact_source`:
- `local-path`: verify file exists at `target.path`.
- `github-release`: download latest release artifact matching `target.artifact_pattern` from `target.artifact_repo` using `gh release download`.
- `ci-artifact`: download from latest CI run using `gh run download`.

If binary not found: **stop** with specific instructions.

### Step A3: Compute Binary Hash

```bash
sha256sum {binary_path}
```

Store the hash for inclusion in findings.

### Step A4: Run checksec

Detect platform and run appropriate tool:
- Linux: `checksec --output=json --file={binary_path}`
- Windows: `winchecksec {binary_path}` or via WSL: `wsl checksec --output=json --file={wsl_path}`

Store output as `checksec.json`.

### Step A5: Run YARA

```bash
yara -j ~/.dream-studio/security/binary/{client}/{target}/yara-rules.yar {binary_path} > yara-matches.json
```

Store output as `yara-matches.json`.

### Step A6: Run Strings Analysis

```bash
strings {binary_path} | grep -E '(https?://|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|password|secret|api.key|token)' > strings-findings.txt
```

Apply PII patterns from `data.pii_patterns` against strings output.

### Step A7: PE/ELF Header Analysis (if Python tools available)

```python
# For PE (Windows):
import pefile
pe = pefile.PE(binary_path)
# Check: unsigned, debug symbols, known vulnerable compiler

# For ELF (Linux):
from elftools.elf.elffile import ELFFile
# Check: interpreter, sections, symbols
```

### Step A8: Store Results

1. Create `~/.dream-studio/security/scans/{client}/{target}/{date}/`
2. Move all result files into the directory.
3. Write `scan-meta.json`:
   ```json
   {
     "schema_version": 1,
     "client": "{client}",
     "target": "{target}",
     "target_type": "binary",
     "date": "{YYYY-MM-DD}",
     "source": "local-analysis",
     "binary_hash": "{sha256}",
     "platform": "{platform}",
     "scanners": ["checksec", "yara", "strings"],
     "ingested_at": "{ISO-8601}"
   }
   ```

### Step A9: Present Summary

Show: binary analyzed, hash, checksec pass/fail summary, YARA matches count, strings findings count.

---

## Mode: `ingest`

### Step I0: Parse Arguments

- `--client <name>` — required.
- `--target <name>` — required.
- `--file <path>` — optional.

### Step I1: Locate Results

Find checksec.json, yara-matches.json, strings-findings.json in the scan directory.

### Step I2: Parse Results

Run parse_binary.py:
```bash
py -3.12 templates/security/etl/parse_binary.py --client {client} --scans-dir {scan_dir}
```

### Step I3: Present Summary

Show: findings by category (hardening failures, YARA matches, strings findings), severity breakdown.

---

## Mode: `status`

Same pattern as DAST status — coverage table for binary targets with last analysis date, staleness, finding counts.

---

## Binary-Specific Finding Fields

| Field | Description |
|---|---|
| `target_type` | `binary` |
| `target_name` | Binary target name from profile |
| `binary_name` | Executable filename |
| `binary_hash` | SHA256 of the analyzed file |
| `binary_section` | PE/ELF section where issue found |
| `function_name` | Function name (if from disassembly) |
| `hardening_check` | Which hardening property failed |
| `yara_rule` | YARA rule that matched |

## Scanner Details

**checksec** (binary hardening):
- Checks: NX (DEP), PIE/ASLR, RELRO, Stack Canaries, FORTIFY, CFI
- JSON output: pass/fail per check
- Linux: `checksec`, Windows: `winchecksec`

**YARA** (pattern matching):
- Custom rules from client data classifications
- JSON output: rule name, match offset, matched strings

**strings + grep** (quick analysis):
- Hardcoded URLs, IPs, credentials, API keys
- PII pattern matching from client profile

**PE/ELF analysis** (metadata):
- Python `pefile` / `pyelftools`
- Unsigned binaries, debug symbols, vulnerable compilers

**Rule ID patterns:** `BIN-chk-{check}`, `BIN-yar-{rule}`, `BIN-str-{N}`, `BIN-hdr-{N}`

---

## Anti-Patterns

- **Analyzing untrusted binaries without sandboxing** — YARA scanning is safe (read-only pattern matching), but strings extraction and header parsing should not execute the binary. Never run the binary itself.
- **Skipping platform detection** — checksec behavior differs by platform. Always detect OS and use the appropriate tool (checksec vs winchecksec vs codesign).
- **Missing binary hash** — every analysis result must include the SHA256 hash for traceability. If two analyses produce different results, the hash tells you if the binary changed.
- **Ingesting without scan-meta.json** — same as DAST/SAST: every scan directory must have `scan-meta.json` with `target_type: binary`.
- **Running on wrong platform** — a Windows PE analyzed on Linux may produce incomplete results (no winchecksec). Warn the user when the analysis platform doesn't match the target platform.
- **Ignoring Ghidra/IDA exports** — the `ingest` mode should accept manually-produced analysis exports. Not all binary analysis can be automated.
