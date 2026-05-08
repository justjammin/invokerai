---
name: data
tier: 1
description: "Universal data domain rules"
---

# Roleplay Notes

- Idempotency: safe to rerun without duplicating — key by source record ID
- Data quality: at ingestion boundary (schema, null, range validation)
- Bad records: reject to dead letter queue (never silent drop)
- DLQ alerting: alert on dead letter queue entries
- Lineage: every output traceable to source dataset + transform version
- Lineage metadata: documented
- Schema evolution: additive only in flight
- Deprecation: required before removal
- Destructive changes: no mid-pipeline (wait for new deployment)
- Backfill: strategy defined before schema change ships
- Backfill question: how to populate historical data for new fields?

## Don'ts

- Accumulate state in memory across large datasets
- Pipeline without observability/alerting (record counts, error rates, latency)
- Skip data quality checks for "trusted" sources
- Use mutable global state in transforms
- Hardcode column positions — reference by name
