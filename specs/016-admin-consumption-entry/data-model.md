# Phase 1 Data Model: 后台消费录入

**Feature**: `016-admin-consumption-entry`  
**Migration**: `016_manual_consumption_entry.py`

## Entity overview

| Entity | Change | Purpose |
|---|---|---|
| `bills` | Extend existing table | Store manual consumption in the existing consumption source of truth |
| `customers` | No schema change | Validate selected customer and obtain current ownership |
| `distributors` / `organizations` | No schema change | Validate active attribution and capture snapshots |
| `admin_accounts` | No schema change | Identify the administrator who entered the consumption |
| `audit_logs` | No schema change | Write security audit evidence for every manual entry |

## bills

Existing amount and status fields remain authoritative. Migration 016 adds nullable metadata where needed so existing synchronized bills remain valid.

| Field | Type | Null | Rule |
|---|---|---:|---|
| `source` | varchar(20) | no | Default `rutai_sync`; manual records use `manual` |
| `attributed_distributor_id` | integer | yes | Manual record's distributor ID at submission; historical reference, no cascading FK |
| `attributed_person_name` | varchar(100) | yes | Person-name snapshot at submission |
| `attributed_org_id` | integer | yes | Organization ID at submission; historical reference, no cascading FK |
| `attributed_org_name` | varchar(128) | yes | Organization-name snapshot at submission |
| `entry_note` | text | yes | Optional administrator note, maximum 500 characters at API boundary |
| `created_by_admin_id` | integer | yes | FK to `admin_accounts.id`, `ON DELETE SET NULL`; null for synchronized bills |
| `idempotency_key` | varchar(128) | yes | Required for manual records; null for synchronized bills |
| `submission_fingerprint` | char(64) | yes | SHA-256 of normalized customer/version/time/amount/note for key-reuse validation |

### Existing fields used by manual records

| Field | Manual value |
|---|---|
| `customer_id` | Selected, revalidated bound customer |
| `rutai_user_id` | Customer's current Rutai user ID when present; not used for external write-back |
| `transaction_id` | System-generated `MANUAL-{date}-{random}` unique record number |
| `transaction_time` | Validated consumption time normalized to the database time convention |
| `consultation_fee_cent` | `0` |
| `medicine_fee_cent` | `0` |
| `total_amount_cent` | Same as `paid_amount_cent` |
| `discount_amount_cent` | `0` |
| `paid_amount_cent` | Request `amountCent`, integer greater than zero |
| `refund_amount_cent` | `0` |
| `transaction_status` | `paid` |
| `created_at` / `updated_at` | Creation time |

### Constraints and indexes

- Keep existing unique constraint/index on `transaction_id`.
- Add unique constraint `uq_bills_admin_idempotency(created_by_admin_id, idempotency_key)`.
- Add index `ix_bills_source_created(source, created_at, id)` for source-aware operations and diagnostics.
- Existing synchronized rows are backfilled to `source='rutai_sync'`; all new rows receive a non-null source.
- Manual rows require application-level presence checks for attribution snapshots, administrator, idempotency key and fingerprint. Synchronized rows may keep those fields null.

## Attribution rule

For any bill used by consumer-facing totals, trends, reports or rankings:

```text
effective distributor = bill.attributed_distributor_id ?? customer.distributor_id
effective person name = bill.attributed_person_name ?? current distributor user name
effective organization = bill.attributed_org_id/name ?? current distributor organization
```

- Manual bills always carry snapshot fields and therefore retain submission-time attribution.
- Existing and future Rutai-synchronized bills retain the existing current-customer attribution behavior.
- `refunded` and `cancelled` remain excluded; manual creation only produces `paid`.

## Customer eligibility

A customer is selectable and submittable only when all conditions hold at query time:

- `customers.binding_status = bound`
- `customers.distributor_id` exists
- related `distributors.status = active`
- related `organizations.status = active`
- submitted `customerVersion` equals the current `customers.version`

Customer search returns only:

- customer ID and version
- name
- masked phone and masked ID card
- distributor ID and display name
- organization ID and display name

Raw phone, ID card, medical account and family phone are never returned by this feature.

## Idempotency state

The database row is the idempotency record:

1. New `(admin, key)` + valid request → create bill and audit row.
2. Existing `(admin, key)` + identical fingerprint → return the original bill, with `replayed=true`.
3. Existing `(admin, key)` + different fingerprint → reject with conflict; create nothing.
4. Concurrent inserts race on the unique constraint; the loser reloads and applies steps 2 or 3.

## AuditLog entry

| Field | Value |
|---|---|
| `user_id` | `null` because the actor is an AdminAccount, not a mini-program User |
| `action` | `manual_consumption_create` |
| `entity_type` | `bill` |
| `entity_id` | Created Bill ID as string |
| `detail` | Admin ID, username snapshot, customer ID, distributor/org snapshot IDs, amount cent, source; no raw sensitive values or note text |
| `ip_address` | Request client IP when available |

Bill creation and AuditLog insertion commit or roll back together.

## State transitions

```text
manual entry form
  -> validated and confirmed
  -> bill(paid, source=manual)
```

No edit, delete, cancellation, refund or outbound synchronization transition is introduced in this feature.

