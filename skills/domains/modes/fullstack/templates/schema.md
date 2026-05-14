# Database Schema Template

Define normalized database schema in a stack-agnostic way for any relational or document database.

## Tables

### table_name
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | uuid | PK, auto | Primary key |
| created_at | timestamp | not null, default now | Creation time |
| updated_at | timestamp | not null, default now | Last update |

## Relationships

| From | To | Type | FK Column |
|------|-----|------|-----------|
| table_a | table_b | many-to-one | table_b_id |

## Indexes

| Table | Columns | Type | Purpose |
|-------|---------|------|---------|
| table_name | column_name | unique or regular | Description |

---

## Example: E-Commerce Schema

### users
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | uuid | PK, auto | Primary key |
| email | varchar(255) | unique, not null | User email |
| password_hash | varchar(255) | not null | Bcrypt hash |
| first_name | varchar(100) | not null | First name |
| last_name | varchar(100) | not null | Last name |
| created_at | timestamp | not null, default now | Account creation |
| updated_at | timestamp | not null, default now | Last update |

### sessions
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | uuid | PK, auto | Primary key |
| user_id | uuid | FK not null | User reference |
| token | varchar(500) | unique, not null | Session token |
| expires_at | timestamp | not null | Token expiration |
| created_at | timestamp | not null, default now | Session start |

### items
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | uuid | PK, auto | Primary key |
| user_id | uuid | FK not null | Owner reference |
| name | varchar(255) | not null | Item name |
| description | text | nullable | Item details |
| price | decimal(10,2) | not null | Price in cents |
| quantity | integer | not null, default 0 | Stock count |
| created_at | timestamp | not null, default now | Item creation |
| updated_at | timestamp | not null, default now | Last update |

## Relationships

| From | To | Type | FK Column |
|------|-----|------|-----------|
| sessions | users | many-to-one | user_id |
| items | users | many-to-one | user_id |

## Indexes

| Table | Columns | Type | Purpose |
|-------|---------|------|---------|
| users | email | unique | Login lookup |
| sessions | user_id | regular | User session queries |
| sessions | token | unique | Token validation |
| items | user_id | regular | User item list |
| items | created_at | regular | Recent items |

---

## Stack-Specific Notes

**PostgreSQL:** Use `uuid_generate_v4()` for auto-uuid, `timestamptz` for timezone-aware timestamps.

**D1/SQLite:** Use `TEXT` for UUIDs, `INTEGER` for Unix timestamps (seconds since epoch).

**DynamoDB:** Design for single-table pattern with partition key (PK) and sort key (SK); denormalize relationships into items.
