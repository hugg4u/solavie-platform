# Requirements — Notification Service

## Overview
Dịch vụ thông báo đa kênh — Slack, email, in-app push. Delivery guarantee, user preferences, priority routing, quiet hours.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (notification_db)
- **Queue:** Kafka (consumer)

## Requirements

### Requirement 1: Multi-channel Delivery

#### Acceptance Criteria
1. THE Notification_Service SHALL hỗ trợ: Slack, email, in-app push
2. THE Notification_Service SHALL route notification theo user preferences
3. THE Notification_Service SHALL retry nếu delivery thất bại
4. Handoff notifications SHALL delivered trong < 3 giây

### Requirement 2: User Preferences

#### Acceptance Criteria
1. THE Notification_Service SHALL cho phép user cấu hình: channels, quiet hours, priority levels
2. THE Notification_Service SHALL respect quiet hours (không gửi ngoài giờ làm việc)
3. THE Notification_Service SHALL hỗ trợ priority levels: critical (always), high, normal, low

### Requirement 3: Delivery Guarantee

#### Acceptance Criteria
1. IF primary channel thất bại, THEN fallback sang channel khác
2. IF tất cả channels thất bại, THEN queue cho retry sau
3. THE Notification_Service SHALL log delivery status per notification
