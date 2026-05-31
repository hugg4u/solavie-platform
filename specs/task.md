# Master System Task Checklist — Solavie Marketing Platform

## Overview
This master checklist tracks the development and deployment of the entire Solavie Marketing Platform microservices and infrastructure. Detailed tasks for individual services are linked below.

## Development & Deployment Phases

### [ ] Phase 1: Core Infrastructure & Gateway (Foundation)
*Goal: Set up database clustering, identity management, API Gateway routing, LLM gateway, and vector knowledge base.*
  - [x] [**AUTH Service**](specs/solavie-system/services/auth/task.md) (5 requirements) - Tech: Keycloak 24+
  - [x] [**GATEWAY Service**](specs/solavie-system/services/gateway/task.md) (5 requirements) - Tech: Kong Gateway OSS 3.x
  - [x] [**AI-CORE Service**](specs/solavie-system/services/ai-core/task.md) (10 requirements) - Tech: Python 3.12 (FastAPI + gRPC + LangGraph)
  - [ ] [**KNOWLEDGE-BASE Service**](specs/solavie-system/services/knowledge-base/task.md) (6 requirements) - Tech: Python 3.12 (FastAPI)

### [ ] Phase 2: Core Messaging & Engagement (Interactions)
*Goal: Connect social channels, unify messaging inbox, and deploy chatbot dialog engine.*
  - [ ] [**CHANNEL-CONNECTOR Service**](specs/solavie-system/services/channel-connector/task.md) (5 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**MESSAGING Service**](specs/solavie-system/services/messaging/task.md) (4 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**CHATBOT Service**](specs/solavie-system/services/chatbot/task.md) (13 requirements) - Tech: Python 3.12, FastAPI + LangGraph + gRPC

### [ ] Phase 3: Content & Scheduling (Automation)
*Goal: Create AI content generation assistant and scheduler for queue postings.*
  - [ ] [**CONTENT Service**](specs/solavie-system/services/content/task.md) (5 requirements) - Tech: Python 3.12 (FastAPI)
  - [ ] [**SCHEDULER Service**](specs/solavie-system/services/scheduler/task.md) (4 requirements) - Tech: Java 21 (Spring Boot 3 + Quartz Scheduler)

### [ ] Phase 4: Business Logic & Analytics (Operations)
*Goal: Setup analytics aggregations, CRM solar deal pipeline, and marketing campaign A/B testing.*
  - [ ] [**ANALYTICS Service**](specs/solavie-system/services/analytics/task.md) (4 requirements) - Tech: Java 21 (Spring Boot 3)
  - [ ] [**CRM Service**](specs/solavie-system/services/crm/task.md) (8 requirements) - Tech: Node.js 20, NestJS, PostgreSQL crm_db
  - [ ] [**CAMPAIGN Service**](specs/solavie-system/services/campaign/task.md) (3 requirements) - Tech: Java 21 (Spring Boot 3)

### [ ] Phase 5: Auxiliary Services (Supporting)
*Goal: Complete supporting features: comments integration, multi-channel notifications, tenant config reload, DMS files, link shortener, and media workers.*
  - [ ] [**COMMENT-MANAGER Service**](specs/solavie-system/services/comment-manager/task.md) (3 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**NOTIFICATION Service**](specs/solavie-system/services/notification/task.md) (3 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**TENANT-CONFIG Service**](specs/solavie-system/services/tenant-config/task.md) (9 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**DMS Service**](specs/solavie-system/services/dms/task.md) (9 requirements) - Tech: Node.js 20 (NestJS)
  - [ ] [**LINK-SHORTENER Service**](specs/solavie-system/services/link-shortener/task.md) (5 requirements) - Tech: Node.js 20 (Fastify)
  - [ ] [**MEDIA-PROCESSOR Service**](specs/solavie-system/services/media-processor/task.md) (5 requirements) - Tech: Python 3.12 (FastAPI)
  - [ ] [**OBSERVABILITY Service**](specs/solavie-system/services/observability/task.md) (5 requirements) - Tech: Prometheus/Grafana Stack

## System-Level Infrastructure Tasks

- [ ] **Step 1: Dev Environment Setup**
  - [ ] Create root `docker-compose.yml` for 6 infrastructure services (Postgres, Redis, Kafka, Qdrant, MinIO, Kong).
  - [ ] Create root `.env` configuration from `.env.example`.
  - [ ] Verify local database migrations and OIDC realm config import flows.
- [ ] **Step 2: Shared Library & Protobuf compilation**
  - [ ] Set up compile tasks for shared gRPC Protobuf files (`proto/chatbot.proto`, `proto/ai_core.proto`).
  - [ ] Create shared validation schemas and error handler packages.
- [ ] **Step 3: Gateway Routing & Plugin verification**
  - [ ] Route all path prefixes: `/api/v1/auth` to Keycloak, `/api/v1/chatbot` to Chatbot, etc.
  - [ ] Verify global plugins (OIDC claims extraction, Rate limiting, CORS).
- [ ] **Step 4: Real-time Messaging Inbox & real-time client sync**
  - [ ] Verify WebSockets connection upgrade via Kong API Gateway.
  - [ ] Check Redis pub/sub replication of inbox notifications across Gateway replicas.
- [ ] **Step 5: End-to-End System Integration Testing**
  - [ ] Trigger mock message inflow -> Chatbot processing -> RAG retrieval -> Guardrails -> CRM Lead auto-update.
  - [ ] Audit tenant isolation at every network request and database transaction.

## Done When

- [ ] All 18 microservices and 6 infrastructure components are successfully running locally under Docker.
- [ ] Master routing rules on Kong Gateway function correctly with zero authentication bypasses on protected resources.
- [ ] Cross-tenant row-level security (RLS) validations prevent any data leakage.
- [ ] High p95 latency margins (Chatbot response < 2s, vector search < 10ms) are validated through load testing.
