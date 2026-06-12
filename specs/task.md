# Master System Task Checklist — Solavie Marketing Platform

## Overview
This master checklist tracks the development and deployment of the entire Solavie Marketing Platform microservices and infrastructure. Detailed tasks for individual services are linked below.

## Development & Deployment Phases

### [x] Phase 1: Core Infrastructure & Gateway (Foundation) ✅
*Goal: Set up database clustering, identity management, API Gateway routing, LLM gateway, and vector knowledge base.*
  - [x] [**AUTH Service**](file:///d:/workspace/project/solavie-system/specs/services/auth/task.md) (5 requirements) ✅ — Keycloak 24+, RBAC, Dynamic Password Policy & Brute Force Sync
  - [x] [**GATEWAY Service**](file:///d:/workspace/project/solavie-system/specs/services/gateway/task.md) (6 requirements - Tích hợp MCP) ✅ — Kong OSS 3.x, dynamic-policy plugin, Dynamic CORS & Rate Limit
  - [x] [**AI-CORE Service**](file:///d:/workspace/project/solavie-system/specs/services/ai-core/task.md) (11 requirements - Tích hợp MCP) ✅ - Tech: Python 3.12 (FastAPI + gRPC + LangGraph)
  - [ ] [**KNOWLEDGE-BASE Service**](file:///d:/workspace/project/solavie-system/specs/services/knowledge-base/task.md) (7 requirements - Tích hợp MCP) - Tech: Python 3.12 (FastAPI)

### [ ] Phase 2: Core Messaging & Engagement (Interactions)
*Goal: Connect social channels, unify messaging inbox, and deploy chatbot dialog engine.*
  - [ ] [**CHANNEL-CONNECTOR Service**](file:///d:/workspace/project/solavie-system/specs/services/channel-connector/task.md) (5 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**MESSAGING Service**](file:///d:/workspace/project/solavie-system/specs/services/messaging/task.md) (5 requirements - Tích hợp MCP) - Tech: Node.js 20 (NestJS)
  - [ ] [**CHATBOT Service**](file:///d:/workspace/project/solavie-system/specs/services/chatbot/task.md) (13 requirements) - Tech: Python 3.12, FastAPI + LangGraph + gRPC

### [ ] Phase 3: Content & Scheduling (Automation)
*Goal: Create AI content generation assistant and scheduler for queue postings.*
  - [ ] [**CONTENT Service**](file:///d:/workspace/project/solavie-system/specs/services/content/task.md) (6 requirements - Tích hợp MCP) - Tech: Python 3.12 (FastAPI)
  - [ ] [**SCHEDULER Service**](file:///d:/workspace/project/solavie-system/specs/services/scheduler/task.md) (5 requirements - Tích hợp MCP) - Tech: Java 21 (Spring Boot 3 + Quartz Scheduler)

### [ ] Phase 4: Business Logic & Analytics (Operations)
*Goal: Setup analytics aggregations, CRM solar deal pipeline, and marketing campaign A/B testing.*
  - [ ] [**ANALYTICS Service**](file:///d:/workspace/project/solavie-system/specs/services/analytics/task.md) (5 requirements - Tích hợp MCP) - Tech: Java 21 (Spring Boot 3)
  - [ ] [**CRM Service**](file:///d:/workspace/project/solavie-system/specs/services/crm/task.md) (9 requirements - Tích hợp MCP) - Tech: Node.js 20, NestJS, PostgreSQL crm_db
  - [ ] [**CAMPAIGN Service**](file:///d:/workspace/project/solavie-system/specs/services/campaign/task.md) (3 requirements) - Tech: Java 21 (Spring Boot 3)

### [ ] Phase 5: Auxiliary Services (Supporting)
*Goal: Complete supporting features: comments integration, multi-channel notifications, tenant config reload, DMS files, link shortener, and media workers.*
  - [ ] [**COMMENT-MANAGER Service**](file:///d:/workspace/project/solavie-system/specs/services/comment-manager/task.md) (4 requirements - Tích hợp MCP) - Tech: Node.js 20 (NestJS)
  - [ ] [**NOTIFICATION Service**](file:///d:/workspace/project/solavie-system/specs/services/notification/task.md) (4 requirements - Tích hợp MCP) - Tech: Node.js 20 (NestJS)
  - [ ] [**TENANT-CONFIG Service**](file:///d:/workspace/project/solavie-system/specs/services/tenant-config/task.md) (10 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**DMS Service**](file:///d:/workspace/project/solavie-system/specs/services/dms/task.md) (9 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**LINK-SHORTENER Service**](file:///d:/workspace/project/solavie-system/specs/services/link-shortener/task.md) (5 requirements) - Tech: Node.js 20 (Fastify)
  - [ ] [**MEDIA-PROCESSOR Service**](file:///d:/workspace/project/solavie-system/specs/services/media-processor/task.md) (5 requirements) - Tech: Python 3.12 (FastAPI)
  - [ ] [**OBSERVABILITY Service**](file:///d:/workspace/project/solavie-system/specs/services/observability/task.md) (5 requirements) - Tech: Prometheus/Grafana Stack

## System-Level Infrastructure Tasks

- [x] **Step 1: Dev Environment Setup** ✅
  - [x] Create root `docker-compose.yml` for 6 infrastructure services (Postgres, Redis, Kafka, Qdrant, MinIO, Kong).
  - [x] Create root `.env` configuration from `.env.example`.
  - [x] Verify local database migrations and OIDC realm config import flows.
- [ ] **Step 2: Shared Library & Protobuf compilation**
  - [ ] Set up compile tasks for shared gRPC Protobuf files (`proto/chatbot.proto`, `proto/ai_core.proto`).
  - [ ] Create shared validation schemas and error handler packages.
- [x] **Step 3: Gateway Routing & Plugin verification** ✅
  - [x] Route all path prefixes: `/api/v1/auth` to Keycloak, `/api/v1/chatbot` to Chatbot, etc.
    - Implemented in `generate_kong_config.py` — 6 services, 7 routes
  - [x] Verify global plugins (OIDC claims extraction, Rate limiting, CORS).
    - JWT plugin: RS256 key validation từ Keycloak
    - dynamic-policy plugin: Dynamic CORS (403 invalid origin) + Dynamic Rate Limit (429 per-tenant) + X-Tenant-ID injection
- [ ] **Step 4: Real-time Messaging Inbox & real-time client sync**
  - [ ] Verify WebSockets connection upgrade via Kong API Gateway.
  - [ ] Check Redis pub/sub replication of inbox notifications across Gateway replicas.
- [ ] **Step 5: End-to-End System Integration Testing**
  - [ ] Trigger mock message inflow -> Chatbot processing -> RAG retrieval -> Guardrails -> CRM Lead auto-update.
  - [ ] Audit tenant isolation at every network request and database transaction.
- [x] **Step 6: Service Discovery & Gateway Routing Optimization** ✅
  - [x] Cấu hình Active/Passive Healthcheck và Circuit Breaker trên Kong.
  - [x] Chuyển Kong sang DB-mode và nâng cấp Sync Daemon sang Async (gọi REST Admin API thay vì reload YAML).
  - [x] Cải tiến giải thuật IP Discovery Fallback và cung cấp endpoint `/health` cho 20 microservices.

## Done When

- [ ] All 19 microservices and 6 infrastructure components are successfully running locally under Docker.
- [ ] Master routing rules on Kong Gateway function correctly with zero authentication bypasses on protected resources.
- [ ] Cross-tenant row-level security (RLS) validations prevent any data leakage.
- [ ] High p95 latency margins (Chatbot response < 2s, vector search < 10ms) are validated through load testing.
- [ ] Service Discovery and Kong DB-mode targets sync functions smoothly under node failures in under 1 second.
