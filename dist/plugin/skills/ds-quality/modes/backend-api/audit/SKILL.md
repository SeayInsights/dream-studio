# Backend API — Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** backend-api:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** backend_api_audit_report

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` fully — all 12 rules.
3. Detect API framework from `detect_stack().web_framework` signal.

## Trigger
`ds-quality:backend-api:audit`, `api audit:`, `check api:`, `backend audit:`

## Purpose
Audit HTTP/REST API route handlers for production-readiness. Static checks first where framework patterns are known; LLM confirmation for rules requiring judgment. Never fixes — classifies and reports only.

## Step 1 — Detect Framework and Scope

Parse invocation flags:
- `--changed` (default): changed API route files vs main
- `--full-repo`: all route files matching framework patterns
- `--scope <path>`: specific file or directory

**Framework detection via `detect_stack().web_framework`:**
- FastAPI: `*.py` with `from fastapi import` or `@app.*` decorator
- Flask: `*.py` with `from flask import`, `@app.route`
- Django REST: `*.py` with `from rest_framework import`
- Next.js API: `src/app/api/**/*.ts` or `pages/api/**/*.ts` files
- Express: `*.js`/`*.ts` with `app.get|post|put|delete|patch`
- Gin (Go): `*.go` with `gin.Context` or `r.GET|POST|PUT|DELETE`
- Axum (Rust): `*.rs` with `axum::Router` or `#[handler]`

**File type inclusion:**
- Python API routes: `*.py` (excluding `tests/`, `migrations/`)
- Next.js API routes: `src/app/api/**/*.ts`, `pages/api/**/*.ts`
- Express routes: `routes/**/*.js`, `routes/**/*.ts`
- Go handlers: `*.go` (excluding `*_test.go`)
- Rust handlers: `*.rs` (excluding `tests/`)

## Step 2 — Static Pass

Apply rules with static detection:
- api-001: Find route handlers with no input validation (static regex for framework patterns)
- api-010: Find routes returning 200 on error paths (static pattern)
- api-011: Find CORS config files with `*` origin (static pattern)
- api-012: Check response shape consistency (static + LLM)

## Step 3 — Candidate/Confirm Pass

For rules requiring judgment:
- api-004 (auth enforcement): static finds undecorated routes → LLM confirms auth layer coverage
- api-002 (error shape): static finds except/catch blocks → LLM confirms whether error detail leaks

## Step 4 — LLM Semantic Pass

For pure-judgment rules:
- api-003, api-005, api-006, api-007, api-008, api-009

## Step 5 — Generate Report

Report format matches other quality skills. Group by severity. Include framework detected and scope.
