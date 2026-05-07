---
name: postgres
tier: 2
domain: database
description: "PostgreSQL-specific patterns"
---

# PostgreSQL

VACUUM and ANALYZE: schedule configured (not relying on autovacuum defaults for high-churn tables). Monitor `last_vacuum` / `last_analyze` times.

`pg_stat_statements` enabled for query analysis. Identify N+1, missing indexes, slow queries.

Indexes: partial indexes for filtered queries (`WHERE status = 'active'`), covering indexes for hot paths (all columns needed in index).

Connection: PgBouncer for pooling at scale, not application-level pooling alone. Configure `pool_mode` per workload.

JSONB over JSON (indexed, binary stored). Use GIN index for JSONB queries.

Constraints: NOT NULL, UNIQUE, CHECK, FOREIGN KEY defined schema-side. Enforce at database.

Window functions for analytics instead of application-side computation.

## Don'ts

- `SELECT *` in application queries (enumerate columns)
- `LIKE '%term'` on large tables without `pg_trgm` extension
- `SERIAL` instead of `IDENTITY` columns in new schemas
- Trust autovacuum without monitoring
- Connection leaks (always close/return to pool)
