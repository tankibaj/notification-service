# Entity Schema: notification-service

> Auto-generated from SQLAlchemy models on 2026-04-25 23:13 UTC. Do not edit manually.

---

## Table: `notifications`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `UUID` | NO | PK |  |
| `tenant_id` | `UUID` | NO |  |  |
| `channel` | `VARCHAR(10)` | NO |  |  |
| `template_id` | `VARCHAR(100)` | NO |  |  |
| `recipient_address` | `VARCHAR(254)` | NO |  |  |
| `recipient_name` | `VARCHAR(200)` | YES |  |  |
| `payload` | `JSONB` | NO |  |  |
| `status` | `VARCHAR(20)` | NO |  |  |
| `retry_count` | `INTEGER` | NO |  |  |
| `created_at` | `DATETIME` | NO |  |  |
| `delivered_at` | `DATETIME` | YES |  |  |
| `idempotency_key` | `VARCHAR(64)` | YES |  |  |

**Indexes:**
- `idx_notifications_status`: (`status`)
- `idx_notifications_idempotency`: UNIQUE (`tenant_id`, `idempotency_key`)
- `idx_notifications_tenant`: (`tenant_id`)

---
