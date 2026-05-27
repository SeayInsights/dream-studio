# Security Build Mode

## Metadata
- **Pack:** quality
- **Mode:** security:build
- **Type:** enforcement
- **Model:** sonnet
- **Inputs:** target_language, target_file_type, generated_code_snippet
- **Outputs:** security_verdict (PASS | BLOCK | WARN), findings

## Before you start
1. Read `../rules.yml`.
2. Read `../config.yml`.

## Trigger
`build:security`, `enforce security:`, or called by ds-core:build when security enforcement is active.

## Purpose
Check code about to be generated against rules.yml using static pattern matching only. Fast, synchronous — no LLM calls, no subprocess tools. Block generation on critical/high findings. Warn on medium.

---

## Step 1 — Identify Applicable Rules

Load `../rules.yml`. Filter to rules where:
- `action.build_mode` is NOT null (excludes sec-016, sec-022 and any compliance/ops-only rules)
- `applies_to.languages` includes the target language (or is empty/universal)
- `applies_to.file_types` includes the target file extension

Result: a subset of rules to enforce for this specific generation context.

---

## Step 2 — Static Pattern Checks

Apply pattern matching to the generated code snippet. No tool execution — inline pattern recognition only.

**sec-001 (secrets):** Flag if any of these patterns appear with an obvious value (not a variable reference):
- `API_KEY = "..."`, `api_key = "..."`, `SECRET = "..."`, `PASSWORD = "..."`, `TOKEN = "..."`, `sk-`, `ghp_`, `AKIA`
- Any variable ending in `_key`, `_secret`, `_password`, `_token` assigned a string literal

**sec-002 (SQL injection):** Flag if SQL keywords appear inside f-string or %-format expressions:
- `f"...SELECT...{`, `f"...WHERE...{`, `f"...INSERT...{`, `"SELECT..." % `, `"WHERE..." % `

**sec-005 (password hashing):** Flag if password-related variable is passed to `hashlib.md5`, `hashlib.sha1`, or stored/returned without hashing:
- `md5(password`, `sha1(password`, `sha256(password` (sha256 is also insufficient for passwords)
- Password stored directly without bcrypt/argon2/scrypt

**sec-021 (crypto libraries):** Flag use of known weak algorithms:
- `hashlib.md5(`, `hashlib.sha1(`, `DES`, `ECB` mode, `RC4`, `Blowfish` in crypto context
- `random.` used for security-sensitive values (use `secrets.` instead)

**sec-007 (cookies):** Flag `set_cookie` or `response.set_cookie` without `secure=True`, `httponly=True`:
- `set_cookie(` without both `secure` and `httponly` flags present in the same call

**sec-013 (PII in logs):** Flag if `logging.` or `print(` receives variables named `email`, `password`, `ssn`, `dob`, `phone`, `credit_card`, `token`:
- `log.info(.*email`, `print(.*password`, etc.

**context_scope note:** Build mode applies these checks to the entire generated snippet (no AST extraction needed for the subset of static rules active in build mode).

---

## Step 3 — Verdict

**If ANY critical or high finding:**

```
⛔ Security enforcement: cannot generate this code.

Finding: {rule.name} (severity: {rule.severity})
Location: {approximate location in generated snippet}
{explanation of what was detected and why it violates the rule}

Required change: {rule.remediation.summary}

Example of correct approach:
{provide a one-line correct pattern if obvious, e.g., "Use os.environ.get('API_KEY') instead of a hardcoded string"}

Resubmit with the corrected pattern to proceed.
```

Do NOT output the flagged code. Block applies to the specific generated block only — not the whole session.

**If ANY medium finding (and no critical/high):**

Generate the code AND append a warning block after the code:

```
⚠ Security warning: {rule.name} (severity: medium)
{explanation}
Recommended fix: {rule.remediation.summary}
This does not block generation but should be addressed before ship.
```

**If no findings:**

Generate code normally. No annotation.

---

## Note on Scope

Build mode covers only rules where `action.build_mode` is not null. Rules excluded from build mode (per D8 approval):

| Rule | Reason excluded from build mode |
|------|--------------------------------|
| sec-016 (rate limiting) | Architectural — requires seeing the full route registration context |
| sec-022 (constant-time comparison) | Multi-file — requires seeing what the generated function is called with |

These rules apply to audit mode only.
