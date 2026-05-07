---
name: database
tier: 1
description: "Universal database domain rules"
---

# Database

Migrations: always reversible. Rollback script written alongside forward migration. Test on copy before prod. Never drop without deprecation period (announce removal, wait 2+ releases).

Indexes: cover the query shape, not just the column. Run EXPLAIN before shipping. Test with realistic data volume.

Never N+1: eager load relationships or batch queries. Verify with query logs/profiler.

Connection pool: sized to workload, not defaults. Timeout configured. Connection limits enforced per application.

Transactions: scoped tight. Rollback path explicit and tested. Long transactions cause lock contention.

Backup: verified via restore test, not just existence check. Tested on non-prod environment regularly.

Schema evolution: additive first. Deprecate before removal. Remove in separate release after deprecation period.

## Don'ts

- Raw string queries (parameterized always)
- 1:1 table-to-endpoint mapping
- Migrate without rollback script
- Trust ORM to pick right index—profile and tune
