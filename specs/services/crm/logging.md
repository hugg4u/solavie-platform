# Logging & Observability — CRM Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "crm",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Lead score updated",
  "context": {
    "contact_id": "contact-uuid",
    "old_score": 45,
    "new_score": 72,
    "change": 27,
    "scoring_factors": ["high_message_frequency", "product_interest"]
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | DB write fail, AI Core scoring fail, merge conflict | `"Lead scoring failed: AI Core timeout"` |
| WARN | Duplicate detected, score spike (possible anomaly) | `"Potential duplicate: same phone across 2 contacts"` |
| INFO | Contact created, score updated, segment recalculated, merge completed | `"Contact merged: 2 records → 1"` |
| DEBUG | Scoring factors detail, segment filter queries, merge resolution | `"Segment 'hot-leads' recalculated: 45 contacts"` |

## Prometheus Metrics
```typescript
crm_contacts_total: Gauge [tenant_id]
crm_contacts_created_total: Counter [channel]
crm_lead_score_updates_total: Counter [tenant_id]
crm_lead_score_distribution: Histogram [buckets: 0,10,20,...,100]
crm_duplicates_detected_total: Counter []
crm_merges_completed_total: Counter []
crm_segments_recalculated_total: Counter []
crm_ai_scoring_duration: Histogram []
crm_kafka_events_consumed_total: Counter [topic]
```

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "postgres": "connected", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| ScoringFailing | ai_scoring errors > 5 in 10m | warning |
| HighDuplicateRate | duplicates_detected > 20 in 1h | info |
| KafkaConsumerLag | lag > 500 for 5m | warning |
