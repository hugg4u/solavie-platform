# Requirements — Campaign Service

## Overview
Dịch vụ quản lý chiến dịch marketing — multi-post campaigns, A/B testing, statistical significance detection, lifecycle management, performance tracking.

## Tech Stack
- **Language:** Java 21
- **Framework:** Spring Boot 3
- **Database:** PostgreSQL (campaign_db)
- **Queue:** Kafka (producer)

## Requirements

### Requirement 1: Campaign Management

#### Acceptance Criteria
1. THE Campaign_Service SHALL cho phép tạo campaign gồm nhiều posts trên nhiều channels
2. THE Campaign_Service SHALL hỗ trợ lifecycle: Draft → Active → Paused → Completed
3. THE Campaign_Service SHALL track performance metrics per-campaign
4. THE Campaign_Service SHALL hỗ trợ campaign goals (reach, engagement, conversion targets)

### Requirement 2: A/B Testing

#### Acceptance Criteria
1. THE Campaign_Service SHALL hỗ trợ A/B testing với >= 2 variants
2. THE Campaign_Service SHALL distribute traffic evenly across variants
3. WHEN statistical significance đạt (p < 0.05), THE Campaign_Service SHALL auto-select winner
4. THE Campaign_Service SHALL report variant performance comparison

### Requirement 3: Performance Tracking

#### Acceptance Criteria
1. THE Campaign_Service SHALL track: reach, engagement rate, click-through, conversion
2. THE Campaign_Service SHALL generate performance summary khi campaign kết thúc
3. THE Campaign_Service SHALL compare performance vs campaign goals
