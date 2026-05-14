# API Patterns Reference

## REST Conventions

| Pattern | Convention | Example |
|---------|-----------|---------|
| List resources | GET /resources | GET /api/users |
| Get one | GET /resources/:id | GET /api/users/123 |
| Create | POST /resources | POST /api/users |
| Update (full) | PUT /resources/:id | PUT /api/users/123 |
| Update (partial) | PATCH /resources/:id | PATCH /api/users/123 |
| Delete | DELETE /resources/:id | DELETE /api/users/123 |
| Nested | GET /resources/:id/sub | GET /api/users/123/posts |
| Search | GET /resources?q=term | GET /api/users?q=john |

## HTTP Status Codes

| Code | When | Response Body |
|------|------|--------------|
| 200 | Success (with body) | Resource or list |
| 201 | Created | New resource + Location header |
| 204 | Success (no body) | Empty (DELETE, some PUT) |
| 400 | Bad request | `{ error: string, fields?: object }` |
| 401 | Not authenticated | `{ error: "Unauthorized" }` |
| 403 | Not authorized | `{ error: "Forbidden" }` |
| 404 | Not found | `{ error: "Not found" }` |
| 409 | Conflict | `{ error: string }` |
| 422 | Validation error | `{ error: string, fields: object }` |
| 429 | Rate limited | Retry-After header |
| 500 | Server error | `{ error: "Internal server error" }` — never leak stack |

## Pagination

```json
// Offset: GET /api/users?page=2&limit=20
{ "data": [...], "total": 150, "page": 2, "limit": 20 }

// Cursor: GET /api/users?cursor=abc123&limit=20
{ "data": [...], "next_cursor": "def456", "has_more": true }
```

Use **offset** for admin UIs with page navigation. Use **cursor** for infinite scroll or large datasets where rows may be inserted mid-page.

## Error Response Shape

```json
{
  "error": "Validation failed",
  "code": "VALIDATION_ERROR",
  "fields": {
    "email": "Must be a valid email",
    "password": "Must be at least 8 characters"
  }
}
```

Always include `error` (human string) and `code` (machine constant). Include `fields` only for validation errors (400/422).

## Versioning

| Strategy | Format | Notes |
|----------|--------|-------|
| URL prefix | `/api/v1/users` | Simple, explicit, cacheable — **recommended** |
| Header | `Accept: application/vnd.api+json;version=1` | Clean URLs but harder to test in browser |
| Query param | `/api/users?v=1` | Avoid — pollutes query space |

Default to URL prefix (`/api/v1/`). Bump to `/api/v2/` only on breaking changes; maintain both during deprecation window.

## GraphQL vs REST

Use **REST** for standard CRUD, public APIs, and simple resource models. Use **GraphQL** when clients have varied data needs, queries span multiple nested resources, or you want to avoid over-fetching across mobile and web clients.

Avoid GraphQL if the team lacks resolver/N+1 experience — REST with a few extra endpoints is faster to ship and debug.
