# Design — Observability Service

## Overview

Stack giám sát toàn hệ thống — Prometheus (metrics scrape + alert rules), Loki (log aggregation), Jaeger (distributed tracing via OpenTelemetry), Grafana (dashboards), OpenTelemetry Collector, Alertmanager (Slack/email routing). Thu thập telemetry từ tất cả 18 services, alert rules cho service health, AI cost spike, Kafka consumer lag.

## Components and Interfaces

Xem **Architecture**, **Prometheus Config**, **Alert Rules**, và **Grafana Dashboards** bên dưới.
| Component | Technology | Port | Vai trò |
|-----------|-----------|------|---------|
| Metrics | Prometheus | 9090 | Scrape & store time-series metrics |
| Logs | Loki | 3100 | Log aggregation & search |
| Log Shipper | Promtail | - | Ship logs từ containers → Loki |
| Tracing | Jaeger | 16686 (UI), 4318 (OTLP) | Distributed tracing |
| Dashboard | Grafana | 3000 | Visualize metrics, logs, traces |
| Collector | OpenTelemetry Collector | 4317 (gRPC), 4318 (HTTP) | Receive & route telemetry |
| Alerting | Alertmanager | 9093 | Route alerts to Slack/email |

## Architecture

```mermaid
graph TB
    subgraph "All Services (instrumented)"
        S1["Channel Connector"]
        S2["Messaging"]
        S3["Chatbot"]
        S4["Content"]
        S5["...all 14 services"]
    end

    subgraph "OpenTelemetry Collector"
        OTEL["OTEL Collector :4317"]
    end

    subgraph "Observability Stack"
        PROM["Prometheus :9090"]
        LOKI["Loki :3100"]
        JAEGER["Jaeger :16686"]
        GRAFANA["Grafana :3000"]
        ALERT["Alertmanager :9093"]
    end

    subgraph "Notification Channels"
        SLACK["Slack"]
        EMAIL["Email"]
    end

    S1 & S2 & S3 & S4 & S5 -->|OTLP (traces + metrics)| OTEL
    S1 & S2 & S3 & S4 & S5 -->|stdout logs| Promtail
    Promtail --> LOKI

    OTEL -->|metrics| PROM
    OTEL -->|traces| JAEGER

    PROM -->|scrape /metrics| S1 & S2 & S3 & S4 & S5
    PROM -->|alert rules| ALERT
    ALERT --> SLACK & EMAIL

    GRAFANA -->|query| PROM & LOKI & JAEGER
```

## Prometheus Config

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerts/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  # Node.js services
  - job_name: "channel-connector"
    static_configs:
      - targets: ["channel-connector:3001"]
    metrics_path: /metrics

  - job_name: "messaging"
    static_configs:
      - targets: ["messaging:3002"]
    metrics_path: /metrics

  - job_name: "crm"
    static_configs:
      - targets: ["crm:3003"]
    metrics_path: /metrics

  - job_name: "notification"
    static_configs:
      - targets: ["notification:3004"]
    metrics_path: /metrics

  - job_name: "comment-manager"
    static_configs:
      - targets: ["comment-manager:3005"]
    metrics_path: /metrics

  # Python services
  - job_name: "chatbot"
    static_configs:
      - targets: ["chatbot:8001"]
    metrics_path: /metrics

  - job_name: "content"
    static_configs:
      - targets: ["content:8002"]
    metrics_path: /metrics

  - job_name: "knowledge-base"
    static_configs:
      - targets: ["knowledge-base:8004"]
    metrics_path: /metrics

  - job_name: "ai-core"
    static_configs:
      - targets: ["ai-core:8005"]
    metrics_path: /metrics

  # Java services
  - job_name: "scheduler"
    static_configs:
      - targets: ["scheduler:8003"]
    metrics_path: /actuator/prometheus

  - job_name: "analytics"
    static_configs:
      - targets: ["analytics:8006"]
    metrics_path: /actuator/prometheus

  - job_name: "campaign"
    static_configs:
      - targets: ["campaign:8007"]
    metrics_path: /actuator/prometheus

  # Infrastructure
  - job_name: "kong"
    static_configs:
      - targets: ["kong:8001"]
    metrics_path: /metrics

  - job_name: "kafka"
    static_configs:
      - targets: ["kafka-exporter:9308"]

  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]

  - job_name: "postgres"
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

## Alert Rules

```yaml
# alerts/service-health.yml
groups:
  - name: service_health
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.job }} is down"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "{{ $labels.job }} error rate > 5%"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "{{ $labels.job }} p95 latency > 2s"

  - name: ai_metrics
    rules:
      - alert: AICoreCostSpike
        expr: sum(rate(ai_core_cost_usd_total[1h])) > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "AI Core cost > $10/hour"

      - alert: HighHandoffRate
        expr: rate(chatbot_handoff_total[30m]) / rate(chatbot_requests_total[30m]) > 0.5
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Chatbot handoff rate > 50%"

  - name: kafka_health
    rules:
      - alert: KafkaConsumerLag
        expr: kafka_consumer_group_lag > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer lag > 1000 for {{ $labels.group }}"
```

## Grafana Dashboards

| Dashboard | Panels |
|-----------|--------|
| System Overview | All services status, total request rate, error rate, avg latency |
| Per-Service Detail | Request rate, latency histogram, error breakdown, resource usage |
| AI Performance | Token usage/cost per tenant, model distribution, confidence histogram, handoff rate |
| Business Metrics | Messages/day, posts published, active conversations, lead score distribution |
| Kafka | Topic throughput, consumer lag, partition distribution |
| Infrastructure | PostgreSQL connections, Redis memory, Qdrant search latency |

## Docker Compose

```yaml
prometheus:
  image: prom/prometheus:v2.51.0
  volumes:
    - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - ./infra/prometheus/alerts:/etc/prometheus/alerts
    - prometheus_data:/prometheus
  ports:
    - "9090:9090"

loki:
  image: grafana/loki:2.9.0
  volumes:
    - ./infra/loki/loki-config.yml:/etc/loki/local-config.yaml
    - loki_data:/loki
  ports:
    - "3100:3100"

promtail:
  image: grafana/promtail:2.9.0
  volumes:
    - ./infra/promtail/promtail-config.yml:/etc/promtail/config.yml
    - /var/log:/var/log
    - /var/lib/docker/containers:/var/lib/docker/containers:ro
  depends_on:
    - loki

jaeger:
  image: jaegertracing/all-in-one:1.54
  environment:
    COLLECTOR_OTLP_ENABLED: true
  ports:
    - "16686:16686"  # UI
    - "4317:4317"    # OTLP gRPC
    - "4318:4318"    # OTLP HTTP

grafana:
  image: grafana/grafana:10.4.0
  environment:
    GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
  volumes:
    - ./infra/grafana/provisioning:/etc/grafana/provisioning
    - grafana_data:/var/lib/grafana
  ports:
    - "3000:3000"
  depends_on:
    - prometheus
    - loki
    - jaeger

alertmanager:
  image: prom/alertmanager:v0.27.0
  volumes:
    - ./infra/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
  ports:
    - "9093:9093"

otel-collector:
  image: otel/opentelemetry-collector-contrib:0.96.0
  volumes:
    - ./infra/otel/otel-collector-config.yml:/etc/otelcol-contrib/config.yaml
  ports:
    - "4317:4317"   # OTLP gRPC
    - "4318:4318"   # OTLP HTTP
```


## Data Models

Service n�y kh�ng c� database ri�ng. Xem data models t?i c�c services li�n quan.

## Correctness Properties

### Property 1: Tenant Isolation
**Validates: Requirements 4.1**
Moi query va operation phai filter theo tenant_id tu JWT claims. Khong co cross-tenant data leakage o bat ky tang nao (DB, Kafka, Redis, Qdrant, MinIO).

### Property 2: Idempotency
**Validates: Requirements 3.1**
Moi write operation phai co idempotency key de tranh duplicate processing khi retry. Kafka consumer phai idempotent.

### Property 3: At-least-once Delivery
**Validates: Requirements 3.1**
Kafka events phai duoc xu ly it nhat mot lan. Sau 3 retries voi exponential backoff (1s, 2s, 4s), event chuyen vao dead-letter queue.

### Property 4: Circuit Breaker Correctness
**Validates: Requirements 5.1**
Sync calls toi external services phai qua circuit breaker. Open sau 5 failures trong 30s, Half-Open probe sau 60s.

### Property 5: Data Consistency
**Validates: Requirements 3.1**
Distributed transactions dung Saga pattern voi compensating actions khi rollback. Moi destructive action ghi audit.events Kafka topic.
## Error Handling

| Scenario | Strategy |
|----------|----------|
| External API timeout | Retry t?i da 3 l?n v?i exponential backoff (1s, 2s, 4s); sau d� tr? v? l?i c� c?u tr�c |
| Database connection error | Circuit breaker + fallback response; alert qua Alertmanager |
| Kafka publish failure | Retry 3 l?n; n?u v?n th?t b?i ghi v�o dead-letter queue |
| Invalid tenant_id | Reject ngay v?i HTTP 403 + ghi security warning v�o audit log |
| Validation error | Tr? v? HTTP 422 v?i danh s�ch field errors chi ti?t |
| Unhandled exception | Log structured JSON v?i trace_id; tr? v? HTTP 500 v?i error_id d? debug |

## Testing Strategy

| Layer | Tool | Coverage Target |
|-------|------|----------------|
| Unit Tests | Jest (Node.js) / pytest (Python) / JUnit 5 (Java) | > 80% business logic |
| Integration Tests | Testcontainers (PostgreSQL, Redis, Kafka) | Happy path + error paths |
| Contract Tests | Pact (consumer-driven) cho gRPC interfaces | Chatbot?AI Core, Messaging?Chatbot |
| Property-Based Tests | fast-check (JS) / Hypothesis (Python) | Tenant isolation, idempotency |
| Load Tests | k6 | Chatbot E2E < 2s t?i 100 concurrent users |
