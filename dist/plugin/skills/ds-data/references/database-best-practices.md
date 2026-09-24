# Database best practices & security

Canonical reference list of database practices, security measures, and operational standards that apply to Dream Studio user projects. The ds-quality skill cites this document when reviewing database design, schema migrations, and database-related code.

## Tier legend

- 🔴 **Mandatory if in scope** — regulation or contractual/breach-level risk
- 🟠 **De facto mandatory** — skipping = audit findings, breach exposure, or dev pain
- 🟢 **Should have** — best practice

## Contents

- [A. Access & authentication](#a-access--authentication)
- [B. Encryption](#b-encryption)
- [C. Data classification & minimization](#c-data-classification--minimization)
- [D. Schema, integrity & correctness](#d-schema-integrity--correctness)
- [E. Query & performance](#e-query--performance)
- [F. Backups & disaster recovery](#f-backups--disaster-recovery)
- [G. High availability & reliability](#g-high-availability--reliability)
- [H. Logging, monitoring & audit](#h-logging-monitoring--audit)
- [I. Vulnerability & patch management](#i-vulnerability--patch-management)
- [J. Multi-tenancy](#j-multi-tenancy-if-saas)
- [K. Compliance-specific data handling](#k-compliance-specific-data-handling)
- [L. Development practices](#l-development-practices)
- [M. Specific engines — quick gotchas](#m-specific-engines--quick-gotchas)

---

## A. Access & authentication

- 🔴 No public internet exposure (DB in private subnet/VPC behind bastion or VPN)
- 🔴 Default-deny network rules; explicit allowlist by app/service IP or security group
- 🔴 No default credentials — change postgres/root/sa/admin passwords immediately
- 🔴 Strong password policy on DB users (or better: IAM/cert-based auth, no passwords)
- 🔴 No shared accounts — every human and every service gets its own identity
- 🔴 MFA on any DB admin console (RDS console, Atlas, Supabase dashboard, etc.)
- 🟠 IAM-based authentication where supported (AWS IAM auth for RDS, Azure AD for SQL, GCP IAM)
- 🟠 Short-lived credentials (rotated tokens, not static passwords)
- 🔴 Least-privilege roles — app accounts get only the tables/operations they need
- 🔴 Separate read-only vs. read-write vs. admin roles
- 🔴 Separate analytics/BI accounts from app accounts
- 🟠 Just-in-time elevated access for admins (no standing prod write access for engineers)
- 🟠 Time-bounded break-glass accounts, logged and alerted on use
- 🔴 Revoke access immediately on offboarding (automated through SSO/SCIM where possible)
- 🟠 Row-level security (RLS) for multi-tenant data — Postgres RLS, Supabase policies, SQL Server RLS

## B. Encryption

- 🔴 Encryption at rest on the storage volume (TDE / cloud-managed encryption)
- 🔴 Encryption in transit — TLS required, reject unencrypted connections
- 🟠 Cert verification on the client side (not sslmode=require only — use verify-full)
- 🟠 Field-level encryption for highly sensitive columns (SSN, tokens, secrets, health data)
- 🟠 Application-layer encryption for data you don't want the cloud provider to see
- 🔴 Customer-managed keys (CMK/BYOK) if your customers require it (enterprise/regulated)
- 🔴 Key rotation policy
- 🔴 Backups encrypted with separate keys from the live DB
- 🟢 Searchable encryption / tokenization for fields that need to be queried but not readable

## C. Data classification & minimization

- 🔴 Classify every column by sensitivity (public / internal / confidential / restricted / regulated)
- 🔴 Don't store what you don't need (especially: full card numbers, SSN, government IDs, biometrics)
- 🔴 Tokenize cards (Stripe/Braintree hold them — your DB shouldn't)
- 🔴 Hash, don't store, passwords (argon2id / bcrypt)
- 🟠 Hash + salt other sensitive identifiers where you only need equality checks
- 🟠 Separate PII into its own schema/table for easier deletion + access control
- 🔴 No PII in URLs, logs, or analytics events
- 🔴 No production data in dev/staging/test (use synthetic or masked data)
- 🟠 Automated PII scanning of databases (Macie, Nightfall, cloud-native scanners)

## D. Schema, integrity & correctness

- 🔴 Primary keys on every table
- 🔴 Foreign keys with ON DELETE behavior chosen deliberately (cascade vs. restrict vs. null)
- 🔴 NOT NULL constraints where appropriate
- 🔴 CHECK constraints for invariants (status enums, ranges)
- 🔴 UNIQUE constraints for natural keys (email, slug, etc.)
- 🟠 Use the right data type — timestamptz not varchar, uuid not text, numeric not float for money
- 🔴 Always store money as integer cents or numeric/decimal, never float
- 🔴 Always store timestamps as UTC with timezone; convert at the edge
- 🟠 Use ENUMs or lookup tables instead of magic strings
- 🟠 Soft-delete pattern where needed (deleted_at) — but document retention implications
- 🟠 Audit columns: created_at, updated_at, created_by, updated_by
- 🟢 Versioning / temporal tables for records that need history
- 🔴 Schema in version control (migration files, not GUI changes)
- 🔴 Migrations are forward-only, reversible, and tested
- 🟠 Zero-downtime migration patterns (expand-contract, not rename-in-place)
- 🟢 Schema documented (dbdocs, schemaspy, or comments)

## E. Query & performance

- 🔴 Parameterized queries / prepared statements (never string concatenation — SQLi vector)
- 🔴 ORM or query builder, not raw concatenation
- 🔴 Indexes on every foreign key
- 🔴 Indexes on every column used in WHERE, ORDER BY, JOIN
- 🟠 Composite indexes for multi-column filters (in the right column order)
- 🟠 Partial indexes for filtered queries
- 🟢 Covering indexes for hot paths
- 🟠 EXPLAIN/EXPLAIN ANALYZE every slow query before shipping
- 🟠 Slow query log enabled with threshold (~100ms)
- 🟠 Query timeout / statement timeout configured (don't let one query hang the DB)
- 🟠 Connection pooling (PgBouncer, RDS Proxy, app-side pool)
- 🟠 Connection limits set to avoid exhaustion
- 🟢 Pagination via cursors/keysets, not OFFSET on large tables
- 🟢 Avoid N+1 queries — measure with APM
- 🟢 Avoid SELECT * in app code
- 🟠 Batch operations for bulk work
- 🟠 Async/queue for slow writes, not inline

## F. Backups & disaster recovery

- 🔴 Automated backups enabled (point-in-time recovery where the DB supports it)
- 🔴 Backup retention meets your RPO and your retention policy
- 🔴 Backups stored in a separate account/region from production
- 🔴 Backups encrypted
- 🔴 Test restores at least quarterly — backups you haven't restored are aspirational
- 🔴 Documented RTO (recovery time) and RPO (data loss tolerance)
- 🟠 Cross-region replication for critical systems
- 🟠 Immutable backups / WORM storage to defeat ransomware
- 🟢 Logical backups (pg_dump/mysqldump) in addition to snapshots for portability
- 🔴 DR runbook documented, with named owners
- 🟠 DR drill at least annually

## G. High availability & reliability

- 🟠 Multi-AZ deployment for production
- 🟢 Read replicas for scaling reads
- 🟠 Failover tested, not just configured
- 🟠 Health checks + automated failover
- 🟢 Connection retry with exponential backoff in app code
- 🟢 Circuit breakers for downstream DB calls
- 🔴 Monitor replication lag if using replicas
- 🟠 Maintenance windows scheduled and communicated

## H. Logging, monitoring & audit

- 🔴 Audit logging enabled (who connected, what they ran — at least for admin/DDL)
- 🔴 Logs shipped off the DB host immediately (don't store on the same volume)
- 🔴 Centralized log aggregation (Datadog, CloudWatch, Splunk, ELK)
- 🔴 Logs immutable + retained per your retention policy
- 🔴 PII scrubbed from logs (or logs treated as restricted data)
- 🟠 Anomaly alerting (sudden mass read, off-hours admin access, privilege changes, failed auth spikes)
- 🟠 Database Activity Monitoring (DAM) tools for regulated environments
- 🔴 Key metrics monitored: CPU, memory, IOPS, connection count, replication lag, lock waits, deadlocks, cache hit ratio
- 🟠 Storage growth tracked and alerted before hitting limits
- 🟠 Long-running query alerts
- 🟢 Query performance baseline so anomalies are detectable

## I. Vulnerability & patch management

- 🔴 DB engine on a supported version (don't run EOL Postgres/MySQL/Mongo)
- 🔴 Security patches applied within defined SLAs
- 🟠 Managed DB service (RDS, Aurora, Cloud SQL, Atlas) — let the provider handle most patching
- 🟢 CVE feed for your DB engine watched
- 🟠 Extensions/plugins audited — only enable what you need

## J. Multi-tenancy (if SaaS)

- 🔴 Tenant isolation strategy chosen deliberately (shared schema + tenant_id / schema-per-tenant / database-per-tenant)
- 🔴 Tenant ID enforced at every query (RLS or ORM scope, not just app discipline)
- 🟠 Test for tenant data leakage in integration tests
- 🟠 Per-tenant encryption keys for high-security customers
- 🟠 Per-tenant rate limiting and quotas
- 🔴 Tenant deletion process complete — including backups, replicas, analytics

## K. Compliance-specific data handling

- 🔴 PII discoverable and deletable on DSAR request (GDPR Art. 17, CCPA delete) — across primary + replicas + backups + analytics
- 🔴 Data portability export per user (GDPR Art. 20)
- 🔴 Retention policy enforced — automated deletion, not policy doc
- 🔴 Pseudonymization where appropriate (GDPR Art. 25/32)
- 🔴 Data residency honored — EU data stays in EU region if required
- 🔴 Cross-border transfer mechanism if data leaves region
- 🔴 PHI handled per HIPAA Security Rule (if healthcare)
- 🔴 PCI scope minimized — no PAN storage if possible
- 🔴 Children's data (COPPA) flagged and gated
- 🔴 Biometric data (BIPA) stored only with consent + retention limits + destruction schedule
- 🟠 Right to rectification implemented (user can edit their data)
- 🟢 Consent records linked to user record, queryable

## L. Development practices

- 🔴 Migrations reviewed before merge
- 🔴 Migrations tested against a copy of production (or realistic data volume)
- 🔴 No direct prod database access for developers (port-forward through bastion + JIT only)
- 🟠 Read-only prod replica for debugging if needed
- 🔴 No DROP, TRUNCATE, or unfiltered UPDATE/DELETE in app code paths
- 🟠 Destructive migrations require explicit approval + backup verification
- 🟢 Database tests in CI — schema linting, migration up/down, performance regression
- 🟢 Use database fixtures or factories for test data, not snapshots of prod

## M. Specific engines — quick gotchas

A few engine-specific things that bite people:

- **Postgres:** enable RLS where multi-tenant; watch out for search_path security; use pgaudit; vacuum/analyze settings
- **MySQL:** be aware of sql_mode defaults; utf8 is not real UTF-8 — use utf8mb4
- **MongoDB:** never expose without auth (the classic breach); enable auth and TLS; use field-level encryption for sensitive data; bind to internal interface only
- **Redis:** never expose to internet; require auth; disable dangerous commands (FLUSHALL, CONFIG, EVAL) in production; don't store PII in cache unless treated like primary
- **Elasticsearch / OpenSearch:** auth + TLS + private network — open ES clusters are a perennial breach source
- **SQLite (D1, edge DBs):** backup strategy is different (file-based); WAL mode matters; concurrent write limits
- **DynamoDB / NoSQL:** design for access patterns up front, not normalized later
- **D1 (Cloudflare, which you're on):** read replicas are auto-managed but consistency is eventual on replicas; backups are time-travel restore (30 days on paid); migrations are first-class — use Wrangler migrations; size limits are real (currently 10 GB/db); no row-level security primitive, so enforce tenant isolation in the app/Worker layer
