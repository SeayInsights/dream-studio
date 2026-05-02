# API Contract Template

This file defines the interface between frontend and backend. Place it at `.planning/api-contract.json` before writing any code. Frontend reads it to build fetch calls; backend reads it to implement routes; integrate mode reads it to verify both sides match.

---

## Contract Format

```json
{
  "version": "1.0",
  "base_url": "/api",
  "auth": {
    "type": "jwt | session | api-key | none",
    "token_header": "Authorization",
    "token_prefix": "Bearer"
  },
  "endpoints": [
    {
      "path": "/users",
      "method": "GET",
      "description": "List all users",
      "auth_required": true,
      "request": {
        "query": { "page": "number", "limit": "number" },
        "body": null
      },
      "response": {
        "200": { "users": "User[]", "total": "number" },
        "401": { "error": "string" }
      }
    }
  ]
}
```

---

## Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| version | string | yes | Contract version |
| base_url | string | yes | API base path |
| auth.type | enum | yes | Auth mechanism |
| endpoints[].path | string | yes | Route path |
| endpoints[].method | enum | yes | HTTP method |
| endpoints[].auth_required | boolean | yes | Whether route needs auth |
| endpoints[].request | object | no | Request shape |
| endpoints[].response | object | yes | Response shapes by status code |

---

## Example Contract

```json
{
  "version": "1.0",
  "base_url": "/api",
  "auth": {
    "type": "jwt",
    "token_header": "Authorization",
    "token_prefix": "Bearer"
  },
  "endpoints": [
    {
      "path": "/auth/login",
      "method": "POST",
      "description": "Authenticate user and return token",
      "auth_required": false,
      "request": {
        "query": null,
        "body": { "email": "string", "password": "string" }
      },
      "response": {
        "200": { "token": "string", "user": "User" },
        "401": { "error": "string" }
      }
    },
    {
      "path": "/users/me",
      "method": "GET",
      "description": "Get current user profile",
      "auth_required": true,
      "request": {
        "query": null,
        "body": null
      },
      "response": {
        "200": { "user": "User" },
        "401": { "error": "string" }
      }
    },
    {
      "path": "/items",
      "method": "GET",
      "description": "List items for current user",
      "auth_required": true,
      "request": {
        "query": { "page": "number", "limit": "number" },
        "body": null
      },
      "response": {
        "200": { "items": "Item[]", "total": "number" },
        "401": { "error": "string" }
      }
    },
    {
      "path": "/items",
      "method": "POST",
      "description": "Create a new item",
      "auth_required": true,
      "request": {
        "query": null,
        "body": { "name": "string", "description": "string" }
      },
      "response": {
        "201": { "item": "Item" },
        "400": { "error": "string" },
        "401": { "error": "string" }
      }
    }
  ]
}
```

---

## Usage Notes

- Keep types simple: `string`, `number`, `boolean`, `ObjectName`, `ObjectName[]` — not full JSON Schema
- Frontend uses this to generate typed fetch calls before backend is built
- Backend uses this as the route implementation checklist
- Integrate mode diffs actual routes/fetch calls against this contract to flag mismatches
- Add new endpoints to this file before coding them — contract is the source of truth
