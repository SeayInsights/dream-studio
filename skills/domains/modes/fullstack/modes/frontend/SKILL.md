---
ds:
  pack: domains
  mode: fullstack/frontend
  mode_type: build
  inputs: [feature_spec, api_contract, design_intent]
  outputs: [frontend_artifact, fetch_calls]
  capabilities_required: [Read, Write, Edit, Grep, Bash]
  model_preference: sonnet
  estimated_duration: 30-120min
---

# Fullstack: Frontend — Website Delegate

## Trigger Keywords

| Keyword | Action |
|---|---|
| `fullstack frontend` | Build UI with API contract awareness |
| `fullstack front` | Same as above |
| `fullstack ui` | Same as above |

---

## Decision Table

| Condition | Action |
|---|---|
| `.planning/api-contract.json` exists | Read it, extract endpoint list, pass to page step |
| `.planning/api-contract.json` missing | Proceed without it — frontend works standalone |
| User gives a specific website sub-mode | Invoke `domains:website` with that sub-mode |
| No sub-mode specified | Invoke `domains:website` with auto-detect |
| Stack is React SPA | Route to `domains:saas-build` instead of `domains:website` |
| Stack is Astro or vanilla HTML | Route to `domains:website` page mode |

---

## Execution Steps

1. **Check for API contract**
   - Look for `.planning/api-contract.json`
   - If present: read it and extract every `{ method, path, auth, request, response }` entry
   - If missing: note it and continue — do not block

2. **Invoke `domains:website`**
   - Delegate all design and build work to the `domains:website` pipeline
   - The user's stated intent determines which website sub-mode runs (page, prototype, deck, animate, etc.)
   - Do not replicate website pipeline logic here

3. **Inject endpoint awareness into the page step**
   - Before the page sub-mode generates HTML, provide the extracted endpoint list
   - Every `fetch()` call in generated HTML must use the exact `method` and `path` from the contract
   - Base URL must come from an environment variable — not hardcoded
   - Every fetch needs loading, success, and error UI states

4. **Post-build**
   - Run `scripts/lint-artifact.py` on every HTML artifact (inherited from `domains:website` requirement)
   - If integration is the next step, confirm fetch call paths match backend routes exactly

---

## DO / DON'T Rules

DO delegate all design and build work to `domains:website`.
DON'T duplicate website pipeline logic (discover, direction, brand, page, prototype, deck, animate, cip, critique) in this file.

DO read `.planning/api-contract.json` before building pages if it exists.
DON'T fail or block when the API contract is missing — frontend can work standalone.

DO pass the full endpoint list to the page-building step so every fetch call is contract-accurate.
DON'T hardcode API base URLs — use `import.meta.env.PUBLIC_API_URL`, `process.env.API_URL`, or equivalent env-var patterns.

DO use the exact `method` and `path` from the contract in every fetch call.
DON'T invent endpoint shapes during build — if the contract is missing a needed endpoint, stop and update the contract via `fullstack spec` first.

DO include loading, success, and error UI states for every fetch call.
DON'T skip error state UI — silent failures are a UX bug and a security risk.

DO match request body field names to the contract exactly (case-sensitive).
DON'T silently rename fields between the contract and the fetch call.

---

## Endpoint Injection Format

When passing endpoint context to the page step, structure it as:

```
API endpoints available:
- POST /api/resource   auth: bearer   body: { field: type }   response: { field: type }
- GET  /api/resource   auth: none     response: { items: array }
```

Pass this block in the prompt context for the page sub-mode invocation.

---

## Anti-Patterns

DON'T start page builds without checking for the API contract first.
DON'T hardcode `http://localhost:3000` or any absolute URL in fetch calls.
DON'T call `fullstack backend` or `fullstack integrate` from this sub-mode — those are sibling modes under the fullstack orchestrator.
