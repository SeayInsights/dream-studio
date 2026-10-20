# binary-scan -- Detailed Reference

Extracted from SKILL.md to reduce context injection size.

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

1. Read `builds/dream-studio-clean/templates/security/binary/yara-rules.yar.j2`.
2. Fill variables from client profile: `data.pii_patterns`, `data.critical` terms, `data.sensitive` terms.
3. Include hardcoded signature patterns for: hardcoded credentials, embedded URLs/IPs, known packer signatures.
4. Write to `~/.dream-studio/security/binary/{client}/{target.name}/yara-rules.yar`.

### Step S3: Generate checksec Config

1. Read `builds/dream-studio-clean/templates/security/binary/checksec-config.yaml.j2`.
2. Configure checks based on `target.platform`:
   - Linux: NX, PIE, RELRO, Stack Canaries, FORTIFY, RUNPATH
   - Windows: DEP, ASLR, CFG, SafeSEH, Authenticode
   - macOS: PIE, Stack Canaries, ARC, Code Signing
3. Write to `~/.dream-studio/security/binary/{client}/{target.name}/checksec-config.yaml`.

### Step S4: Generate Analysis Script

1. Read `builds/dream-studio-clean/templates/security/binary/analyze.sh.j2`.
2. Render platform-appropriate commands.
3. Write to `~/.dream-studio/security/binary/{client}/{target.name}/analyze.sh`.

### Step S5: Generate GitHub Actions Workflow

1. Read `builds/dream-studio-clean/templates/security/github-actions/binary-scan.yml.j2`.
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

### Run record (applies to A4-A7)

The analysis has four steps: `checksec` (A4), `yara` (A5), `strings` (A6) and
`header_analysis` (A7). Keep a run record as you go: for each one, `ran`, `skipped` (its
tool is not available, or A7 has no Python library for the format) or `failed` (it ran
and errored), with the `tool` actually used (required for `ran`) and, when it did not
run, the `reason`. Record `failed`, not `ran`, when a tool is installed but errors or
leaves no usable output. One entry per step. A step never leaves the record, because
Step A8 writes it to `scan-meta.json` and the ingest step reads it back to mark the scan
`complete`, `partial` or `unknown`.

Every step that ran must also leave its result file in the scan directory (A4
`checksec.json`, A5 `yara-matches.json`, A6 `strings-findings.txt`, A7
`header-analysis.json`). Ingest marks a scan `complete` only when it read a result for
each step; a step recorded `ran` whose file is missing, empty or unparseable reads
`partial`.

### Step A4: Run checksec

Detect platform and run appropriate tool:
- Linux: `checksec --output=json --file={binary_path}`
- Windows: `winchecksec {binary_path}` or via WSL: `wsl checksec --output=json --file={wsl_path}`

Store output as `checksec.json`. If no checksec variant is available for the platform,
record `checksec` as `skipped` with the reason (for example "winchecksec not installed")
and continue.

### Step A5: Run YARA

```bash
yara -j ~/.dream-studio/security/binary/{client}/{target}/yara-rules.yar {binary_path} > yara-matches.json
```

Store output as `yara-matches.json`. If `yara` is not installed, record `yara` as `skipped`
with the reason and continue.

### Step A6: Run Strings Analysis

```bash
strings {binary_path} | grep -E '(https?://|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|password|secret|api.key|token)' > strings-findings.txt
```

Apply PII patterns from `data.pii_patterns` against strings output. If `strings` is not
available (for example on Windows without binutils), record `strings` as `skipped` with
the reason and continue. When the pattern matches nothing the file is empty; keep it
(an empty `strings-findings.txt` is a result, a missing one is not).

### Step A7: PE/ELF Header Analysis (needs `pefile` for PE, `pyelftools` for ELF)

Try the import first. If the library for the binary's format is not installed, record
`header_analysis` as `skipped` with the reason (for example "pefile is not installed") --
do not just move on, because nothing downstream can tell a skipped header analysis from
one that found nothing.

```python
# For PE (Windows):
import pefile
pe = pefile.PE(binary_path)
# Check: unsigned, debug symbols, known vulnerable compiler

# For ELF (Linux):
from elftools.elf.elffile import ELFFile
# Check: interpreter, sections, symbols
```

Write the checks to `header-analysis.json`, one boolean per check, `true` when the
property holds and `false` when it does not (each `false` becomes a finding):

```json
{"format": "pe", "checks": {"signed": false, "debug_symbols_stripped": true,
                            "no_known_vulnerable_compiler": true}}
```

PE checks: `signed`, `debug_symbols_stripped`, `no_known_vulnerable_compiler`. ELF
checks: `interpreter_trusted`, `symbols_stripped`, `no_writable_executable_sections`.
A check named anything else is still read and reported as a medium finding.

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
     "steps": [
       {"step": "checksec", "status": "ran", "tool": "checksec"},
       {"step": "yara", "status": "ran", "tool": "yara"},
       {"step": "strings", "status": "ran", "tool": "strings"},
       {"step": "header_analysis", "status": "skipped", "tool": "pefile",
        "reason": "pefile is not installed"}
     ],
     "ingested_at": "{ISO-8601}"
   }
   ```
   `steps` is the run record: one entry for each of `checksec`, `yara`, `strings` and
   `header_analysis`, with `status` `ran`, `skipped` or `failed`, the `tool` used, and a
   `reason` when the status is not `ran`. `scanners` lists only the scanners that
   actually ran (it is no longer the planned list). A scan directory written before
   `steps` existed stays readable: ingest reports its coverage as `unknown`.

### Step A9: Present Summary

Show: binary analyzed, hash, checksec pass/fail summary, YARA matches count, strings findings count, and every step recorded `skipped` or `failed` with its reason.

---

## Mode: `ingest`

### Step I0: Parse Arguments

- `--client <name>` — required.
- `--target <name>` — required.
- `--file <path>` — optional.

### Step I1: Locate Results

Find `checksec.json`, `yara-matches.json`, `strings-findings.txt` and `header-analysis.json` in the scan directory.

### Step I2: Parse Results

Run parse_binary.py:
```bash
py -3.12 templates/security/etl/parse_binary.py --client {client} --scans-dir {scan_dir} --coverage-output {scan_dir}/coverage.json
```

Each finding carries `coverage` (`complete` | `partial` | `unknown`) and `limitations`,
read from the `steps` run record in `scan-meta.json` and from what the parser actually
read: `complete` only when all four steps are recorded `ran` AND a result was read for
each, `partial` naming each skipped, failed, or ran-but-unread step (missing, empty or
unparseable result file), `unknown` when `scan-meta.json` has no usable run record (an
older scan directory, a malformed entry, a step recorded twice). `coverage.json` holds
the same per scan directory, with the limitations. It is the only place coverage shows
when a scan produced no findings, and it is written even when ingest then exits 1
because there was nothing to parse.

### Step I3: Present Summary

Show: findings by category (hardening failures, YARA matches, strings findings), severity breakdown, and the coverage. When coverage is not `complete`, say so first and name the skipped steps: "no findings" from a partial scan is not a clean result.

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