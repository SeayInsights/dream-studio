---
pack: domains
mode: fullstack/integrate
mode_type: build
model_preference: sonnet
---

# Integrate Mode

Wires frontend to backend after both are built. The API contract (`.planning/api-contract.json`) is the single source of truth. All mismatches are reported before any fix is applied.

## Verification Checklist

| Check | Source | Target | Pass Criteria |
|---|---|---|---|
| Endpoint coverage | API contract | Frontend fetch calls | Every contract endpoint has a matching fetch |
| Method match | API contract | Frontend fetch calls | GET/POST/PUT/DELETE matches exactly |
| Payload shape | API contract request schema | Frontend request body | Fields match type and required status |
| Response handling | API contract response schema | Frontend response parsing | Frontend destructures all expected fields |
| Auth headers | API contract auth requirements | Frontend auth implementation | Auth tokens sent on protected routes |
| CORS config | Frontend origin | Backend CORS settings | Frontend origin is in allowed origins |

## Integration Steps

1. Read `.planning/api-contract.json` — establish ground truth for all endpoints, methods, schemas, and auth requirements
2. Scan frontend HTML/JS for all `fetch`, `axios`, and API call patterns — collect URL, method, request body, and response destructuring per call
3. Scan backend for all route definitions — collect path, method, handler signature, and middleware
4. Run verification checklist — compare each check against both sides
5. Report all mismatches with `file:line` references before suggesting any fix
6. Generate targeted fix suggestions for each mismatch
7. Wire environment config — create or update `.env` template with `API_BASE_URL` and auth endpoint vars

## Drift Detection

Flag these three gap types explicitly in output:

- **Backend gap** — contract has endpoint, backend does not implement it
- **Undocumented endpoint** — frontend calls endpoint not in contract
- **Contract gap** — backend implements endpoint not in contract

Each flag includes the specific endpoint, file, and line number.

## DO / DON'T

DO read the API contract as the single source of truth before touching any code.
DON'T assume frontend and backend are in sync — verify every endpoint.

DO report all mismatches first, in a structured list, before suggesting fixes.
DON'T auto-apply fixes without showing the user exactly what changes.

DO check CORS configuration explicitly against the frontend origin.
DON'T skip auth header verification on any route marked protected in the contract.

DO generate a `.env.template` file with `API_BASE_URL` and all auth endpoint variables.
DON'T hardcode `localhost` URLs — flag any hardcoded host as a mismatch requiring an env var.

DO include `file:line` references for every mismatch and every fix suggestion.
DON'T merge frontend and backend changes in a single step — verify after each wire.
