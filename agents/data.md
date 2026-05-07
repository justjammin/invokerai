---
name: data
tier: 1
description: "Universal data domain rules"
---

# Data

Pipelines idempotent: safe to rerun without duplicating records. Key by source record ID.

Data quality checks at ingestion boundary: schema validation, null checks, range validation. Reject bad records to dead letter queue.

Lineage tracked: every output traceable to source dataset and transform version. Document in metadata.

Schema evolution: additive only in flight. Deprecate before removal. No destructive changes mid-pipeline.

Dead letter queue for failed records: never silent drop. Alert on DLQ entries.

Backfill strategy defined before schema change ships. How do we populate historical data for new fields?

## Don'ts

- Accumulate state in memory across large datasets
- Pipeline with no observability/alerting (record counts, error rates, latency)
- Skip data quality checks for "trusted" sources
- Use mutable global state in transforms
- Hardcode column positions—reference by name
