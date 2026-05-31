# Requirements — Comment Manager Service

## Overview
Dịch vụ quản lý bình luận trên bài đăng — auto-classify (spam/negative/question/praise), auto-hide spam, auto-reply questions, escalate negatives, learn from overrides.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (comment_db)
- **Queue:** Kafka (consumer + producer)
- **AI:** AI Core (REST) cho classification + auto-reply

## Requirements

### Requirement 1: Comment Classification

#### Acceptance Criteria
1. WHEN comment mới nhận được, THE Comment_Manager SHALL classify: spam, negative, question, praise, neutral
2. Classification SHALL dùng AI_Core (semantic, không chỉ keyword)
3. THE Comment_Manager SHALL cho phép human override classification
4. THE Comment_Manager SHALL learn từ overrides để improve accuracy

### Requirement 2: Auto-Actions

#### Acceptance Criteria
1. WHEN spam detected, THE Comment_Manager SHALL auto-hide comment
2. WHEN question detected, THE Comment_Manager SHALL generate auto-reply (via AI Core + Knowledge Base)
3. WHEN negative detected, THE Comment_Manager SHALL escalate cho agent (via Notification)
4. WHEN praise detected, THE Comment_Manager SHALL auto-like (if platform supports)

### Requirement 3: Comment Management UI

#### Acceptance Criteria
1. THE Comment_Manager SHALL list comments per post (filterable by classification)
2. THE Comment_Manager SHALL hỗ trợ manual reply, hide, unhide
3. THE Comment_Manager SHALL show classification stats (accuracy, volume)
