# Business Logic — CRM Service

## Tổng quan vai trò

CRM Service quản lý **khách hàng**: auto-create contacts, track interactions, AI lead scoring, tagging/segmentation, duplicate detection & merge.

## Luồng xử lý chi tiết

### Luồng 1: Auto-Create Contact (Kafka Consumer)

```
Kafka: messaging.conversation.created
│
▼
┌─────────────────────────────────┐
│ 1. CHECK EXISTING CONTACT       │
│    - Lookup by platform +       │
│      sender_id + tenant_id      │
│    - If exists → update         │
│      last_interaction_at        │
│    - If not → create new        │
└────────────┬────────────────────┘
             │ (new contact)
             ▼
┌─────────────────────────────────┐
│ 2. CREATE CONTACT               │
│    - display_name (from platform)│
│    - channel_ids: {fb: "id"}    │
│    - lead_score: 0 (initial)    │
│    - first_seen_at: now         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. CHECK DUPLICATES             │
│    - Same phone across channels?│
│    - Same email?                │
│    - If potential dup → flag    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. PUBLISH EVENT                │
│    - crm.contact.created        │
└─────────────────────────────────┘
```

### Luồng 2: AI Lead Scoring

```
Trigger: Mỗi khi có interaction mới
hoặc: Batch job hàng ngày recalculate all
│
▼
┌─────────────────────────────────┐
│ 1. COLLECT BEHAVIOR DATA        │
│    - Message frequency (7 days) │
│    - Product mentions           │
│    - Sentiment history          │
│    - Response engagement        │
│    - Time since first contact   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. CALL AI CORE (scoring)       │
│    - use_case: "lead_scoring"   │
│    - Input: behavior summary    │
│    - Output: score 0-100 +      │
│      reasoning                  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. UPDATE SCORE                 │
│    - Save new score             │
│    - Calculate delta            │
│    - If |delta| > 10 →         │
│      publish score.changed      │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. CATEGORIZE                   │
│    - Hot (>80): Notify sales    │
│    - Warm (50-80): Nurture      │
│    - Cold (<50): Keep in funnel │
└─────────────────────────────────┘
```

**Scoring Logic:**

```typescript
interface ScoringFactors {
  message_frequency: number;    // messages in last 7 days (0-10)
  product_interest: number;     // mentions of products/pricing (0-10)
  sentiment_trend: number;      // avg sentiment score (-1 to 1)
  engagement_speed: number;     // avg response time (faster = higher)
  recency: number;              // days since last interaction
  channel_diversity: number;    // contacted via multiple channels?
}

// AI prompt for scoring
const SCORING_PROMPT = `Score this lead 0-100 based on purchase likelihood.

Factors:
- Message frequency (last 7 days): {message_frequency}
- Product/price mentions: {product_interest}
- Sentiment trend: {sentiment_trend}
- Response speed: {engagement_speed}
- Days since last contact: {recency}
- Multi-channel contact: {channel_diversity}

Scoring guide:
- 80-100: Ready to buy (asking about price, availability, how to order)
- 50-79: Interested (asking about features, comparing)
- 20-49: Exploring (general questions, browsing)
- 0-19: Cold (one-time contact, no engagement)

Return JSON: {"score": 0-100, "reason": "brief explanation"}`;
```

### Luồng 3: Duplicate Detection & Merge

```typescript
class DuplicateDetector {
  async detectDuplicates(tenantId: string): Promise<DuplicateGroup[]> {
    // Strategy 1: Same phone number across different channels
    const phoneMatches = await this.db.query(`
      SELECT array_agg(id) as contact_ids, phone
      FROM contacts
      WHERE tenant_id = $1 AND phone IS NOT NULL
      GROUP BY phone
      HAVING COUNT(*) > 1
    `, [tenantId]);

    // Strategy 2: Same email
    const emailMatches = await this.db.query(`
      SELECT array_agg(id) as contact_ids, email
      FROM contacts
      WHERE tenant_id = $1 AND email IS NOT NULL
      GROUP BY email
      HAVING COUNT(*) > 1
    `, [tenantId]);

    // Strategy 3: Same display_name + same channel (fuzzy)
    // Less reliable, flag for manual review

    return [...phoneMatches, ...emailMatches];
  }

  async mergeContacts(primaryId: string, secondaryIds: string[]): Promise<Contact> {
    // 1. Merge channel_ids (combine all platform IDs)
    // 2. Keep primary's name/email/phone (or pick most complete)
    // 3. Merge tags (union)
    // 4. Keep highest lead_score
    // 5. Move all interactions to primary
    // 6. Delete secondary contacts
    // 7. Update conversations to point to primary contact

    const primary = await this.contactRepo.findById(primaryId);
    
    for (const secId of secondaryIds) {
      const secondary = await this.contactRepo.findById(secId);
      
      // Merge channel_ids
      primary.channel_ids = { ...primary.channel_ids, ...secondary.channel_ids };
      
      // Merge tags
      primary.tags = [...new Set([...primary.tags, ...secondary.tags])];
      
      // Keep higher score
      primary.lead_score = Math.max(primary.lead_score, secondary.lead_score);
      
      // Move interactions
      await this.interactionRepo.updateMany(
        { contact_id: secId },
        { contact_id: primaryId }
      );
      
      // Delete secondary
      await this.contactRepo.delete(secId);
    }
    
    await this.contactRepo.save(primary);
    return primary;
  }
}
```

---

## Audit Logging

Các action sau PHẢI ghi audit log (theo `shared/standards.md`), publish lên Kafka topic `audit.events`:

| Action | Khi nào | Ghi gì |
|--------|---------|--------|
| `contact.merge` | Merge duplicate contacts | primary_id, merged_ids, actor, before/after |
| `contact.delete` | Xóa contact | contact_id, actor, reason |
| `contact.lead_score.change` | Score thay đổi đáng kể | contact_id, old_score → new_score, factors |
| `contact.tag.change` | Thêm/xóa tags | contact_id, tags, actor |

Merge contacts là **destructive + irreversible** (gộp interaction history) → audit log bắt buộc để trace và rollback nếu merge sai.


## Zero-Trust Security & Dynamic RBAC Logic

Dịch vụ thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- Dịch vụ trích xuất các headers từ request:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User.
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `crm:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `crm:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `crm:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `crm:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `crm:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| AI Core scoring timeout | Keep old score, retry in next batch |
| Duplicate merge conflict | Require manual resolution (UI prompt) |
| Kafka event missing data | Log warn, skip (don't create incomplete contact) |
| Score calculation error | Keep old score, log error, alert |

---

## Luồng xử lý MCP Server Tool Execution

Mọi cuộc gọi tool từ AI Core chuyển tiếp qua Kong Gateway đến CRM Service được xử lý theo luồng dưới đây:

### Luồng xử lý yêu cầu gọi Tool qua SSE

```
Incoming Request (POST /api/v1/mcp/:server/messages)
│
▼
┌──────────────────────────────────────────┐
│ 1. XÁC THỰC JWT & TRÍCH XUẤT TENANT      │
│    - Kiểm tra Bearer Token trong header  │
│    - Lấy tenant_id từ JWT hoặc           │
│      header X-Tenant-ID                  │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│ 2. KIỂM TRA CHÉO ĐA THUÊ BAO (SECURITY)   │
│    - So sánh tenant_id trích xuất được    │
│      với tham số 'tenant_id' trong        │
│      payload của cuộc gọi tool.           │
└──────────────────┬───────────────────────┘
                   │
                   ├─► [KHÔNG KHỚP] ──► Ghi crm_mcp_security_violations_total
                   │                    Trả về lỗi JSON-RPC -32602 (Invalid Params)
                   │
                   └─► [HỢP LỆ]
                               │
                               ▼
┌──────────────────────────────────────────┐
│ 3. ĐỊNH TUYẾN THỰC THI TOOL              │
│    - solar_calc -> Chạy công thức ROI    │
│    - crm        -> Lấy contact / deal    │
│    - om_ticket  -> Tạo ticket sự cố      │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│ 4. TRUY VẤN CƠ SỞ DỮ LIỆU (PRISMA)       │
│    - Ép buộc lọc theo tenant_id          │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│ 5. TRẢ VỀ PHẢN HỒI (MCP FORMAT)          │
│    - Trả về JSON-RPC response dạng text  │
│    - Ghi nhận crm_mcp_tool_executions     │
└──────────────────────────────────────────┘
```

**Chi tiết xử lý:**
*   **Với `solar_calc__calculate_solar_roi`:** Gọi module tính toán ROI cục bộ dựa trên dữ liệu bức xạ và điện mặt trời đã lọc theo `tenant_id` của khách hàng.
*   **Với `crm__get_contact_360`:** Truy vấn bảng `contacts`, `crm_deals`, `crm_tickets` để tổng hợp hồ sơ khách hàng. Prisma tự động thêm điều kiện `tenant_id` trong câu lệnh `findUnique` hoặc `findFirst`.
*   **Với `om_ticket__create_om_ticket`:** Kiểm tra xem `contact_id` có thuộc `tenant_id` không, sau đó thực hiện chèn bản ghi mới vào bảng `crm_tickets` và phát event `crm.ticket.created` lên Kafka.
