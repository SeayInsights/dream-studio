# Security Mode — Smoke Test

## Setup

Create a minimal test fixture with a deliberately bad security pattern:

```powershell
# Windows
$fixture = "<repo-root>\.planning\workstreams\18-4-1\smoke-fixture.py"
@'
# Smoke test fixture — hardcoded secret (should trigger sec-001)
import sqlite3

API_KEY = "sk-test-1234567890abcdef"
DB_PASSWORD = "hunter2"

def get_user(username):
    conn = sqlite3.connect("app.db")
    # SQL injection (should trigger sec-002)
    query = f"SELECT * FROM users WHERE name = '{username}'"
    return conn.execute(query).fetchall()
'@ | Set-Content $fixture
```

## Run (audit mode)

```
ds-quality:security:audit --scope <fixture-path>
```

## Expected

Report should contain:
- **sec-001** (No secrets in source) — severity: critical — gitleaks or LLM finds `API_KEY` and `DB_PASSWORD`
- **sec-002** (Parameterized queries) — severity: critical — f-string SQL construction flagged
- At minimum 2 critical findings in the summary

If gitleaks not installed: report should show `⚠ Degraded: gitleaks not installed — LLM fallback active for sec-001`

## Run (build mode)

Invoke build mode with the secret-containing snippet as the generated code:
```
ds-quality:security:build
[then provide the API_KEY = "sk-test..." line as the code being generated]
```

Expected: `⛔ Security enforcement` block citing sec-001, generation blocked.

## If It Fails

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No findings | rules.yml not loading | Check rules.yml YAML syntax: `py -c "import yaml; yaml.safe_load(open('rules.yml'))"` |
| rules.yml not found | Wrong working dir | Ensure skill is invoked from repo root |
| LLM finds nothing | Confidence threshold too high | Check `config.yml` `min_confidence_for_llm_finding` |
| No degradation warning | `log_tool_degradation: false` | Check `config.yml` behavior section |
