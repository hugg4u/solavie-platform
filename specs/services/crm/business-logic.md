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

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| AI Core scoring timeout | Keep old score, retry in next batch |
| Duplicate merge conflict | Require manual resolution (UI prompt) |
| Kafka event missing data | Log warn, skip (don't create incomplete contact) |
| Score calculation error | Keep old score, log error, alert |
