# Customers API Contracts

All endpoints under `/api/v1/customers/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## List Customers

**Method**: GET
**Path**: /api/v1/customers
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| keyword | string | no | Max 100 chars | Search name or phone |
| status | string | no | Enum: `active`, `inactive` | Customer activity status |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |
| sortBy | string | no | Enum: `createdAt`, `name`, `totalContribution` | Sort field |
| sortOrder | string | no | Enum: `asc`, `desc`, default `desc` | Sort order |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "customerId": "cust_001",
        "name": "王五",
        "phone": "150****9999",
        "status": "active",
        "statusLabel": "活跃",
        "totalContribution": "1250000",
        "totalContributionFormatted": "12,500.00",
        "lastServiceAt": "2026-07-25T10:00:00+08:00",
        "boundPromoter": {
          "promoterId": "u_prom001",
          "displayName": "李四"
        },
        "createdAt": "2026-01-15T08:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_xyz",
    "hasMore": true
  },
  "requestId": "req_20260730120000021",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Visibility: promoters see only customers bound to them (directly). Admins see all customers governed by their org node.
- `totalContribution` is returned as a string (currency in 分). `totalContributionFormatted` is the display string (元 with thousand separators).
- Phone numbers are masked in list view.
- Cursor pagination uses a composite cursor of `sortValue + customerId`.
- `lastServiceAt` is the timestamp of the most recent service record.

---

## Customer Detail

**Method**: GET
**Path**: /api/v1/customers/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "customerId": "cust_001",
    "name": "王五",
    "phone": "150****9999",
    "phoneRaw": "15012349999",
    "wechatNickname": "微信昵称",
    "status": "active",
    "statusLabel": "活跃",
    "address": {
      "province": "北京市",
      "city": "北京市",
      "district": "朝阳区",
      "detail": "某某街道100号"
    },
    "totalContribution": "1250000",
    "totalContributionFormatted": "12,500.00",
    "bindingInfo": {
      "bindingId": "bind_001",
      "promoterId": "u_prom001",
      "promoterName": "李四",
      "promoterCode": "ABC123",
      "boundAt": "2026-01-15T08:00:00+08:00",
      "isActive": true
    },
    "tags": ["VIP", "高净值"],
    "remark": "重点客户，保持每月跟进",
    "createdAt": "2026-01-15T08:00:00+08:00",
    "updatedAt": "2026-07-28T09:30:00+08:00"
  },
  "requestId": "req_20260730120000022",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to view this customer | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `phone` is masked (e.g., `150****9999`). The full raw phone is returned in `phoneRaw` when the viewer is the bound promoter or an admin.
- `bindingInfo` shows the currently active binding. If no active binding exists, this is `null`.
- `address` fields are optional and may be partial.
- `tags` is a free-form list of labels assigned by the bound promoter.

---

## Update Customer

**Method**: PATCH
**Path**: /api/v1/customers/{id}
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | no | Max 100 chars | Customer name |
| phone | string | no | Length 11 | Phone (China mobile) |
| wechatNickname | string | no | Max 100 chars | WeChat nickname |
| province | string | no | Max 50 chars | Province |
| city | string | no | Max 50 chars | City |
| district | string | no | Max 50 chars | District |
| detail | string | no | Max 200 chars | Detailed address |
| tags | array[string] | no | Max 20 items, each max 20 chars | Tags |
| remark | string | no | Max 500 chars | Remark |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "customerId": "cust_001",
    "name": "王五",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000023",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to update this customer | No |
| 40030 | Phone number format invalid | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only the bound promoter or an admin can update customer information.
- Supplied fields are merged (partial update). Omitted fields are not modified.
- When `phone` is changed, the system validates the new number is unique across all customers.
- `tags` replaces the entire tag list (not append). To clear tags, send an empty array.

---

## Service Records

**Method**: GET
**Path**: /api/v1/customers/{id}/service-records
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "recordId": "svc_001",
        "type": "visit",
        "typeLabel": "上门拜访",
        "content": "拜访客户并介绍新产品",
        "operatorId": "u_prom001",
        "operatorName": "李四",
        "createdAt": "2026-07-25T10:00:00+08:00",
        "attachments": [
          {
            "fileKey": "svc_files/xxx.jpg",
            "fileName": "拜访照片.jpg",
            "url": "https://oss.example.com/svc_files/xxx.jpg"
          }
        ]
      }
    ],
    "nextCursor": "cursor_svc",
    "hasMore": false
  },
  "requestId": "req_20260730120000024",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to view this customer | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Service records are returned in reverse chronological order (newest first).
- `type` enum: `visit`, `call`, `message`, `order_assist`, `after_sales`, `other`.

---

## Binding History

**Method**: GET
**Path**: /api/v1/customers/{id}/binding-history
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "bindingId": "bind_001",
        "promoterId": "u_prom001",
        "promoterName": "李四",
        "promoterCode": "ABC123",
        "boundAt": "2026-01-15T08:00:00+08:00",
        "unboundAt": null,
        "isActive": true,
        "unbindReason": null
      },
      {
        "bindingId": "bind_000",
        "promoterId": "u_prom003",
        "promoterName": "赵六",
        "promoterCode": "DEF456",
        "boundAt": "2025-06-01T08:00:00+08:00",
        "unboundAt": "2025-12-31T18:00:00+08:00",
        "isActive": false,
        "unbindReason": "推广员离职"
      }
    ]
  },
  "requestId": "req_20260730120000025",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to view this customer | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns all historical binding records for this customer, ordered by `boundAt` descending.
- `isActive: true` means this binding is the current active one.
- When a customer is transferred, the old binding gets an `unboundAt` and the new binding takes effect.

---

## Contributions

**Method**: GET
**Path**: /api/v1/customers/{id}/contributions
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Start of range |
| endDate | string | no | ISO 8601 date (YYYY-MM-DD) | End of range |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "contributionId": "ctrb_001",
        "amount": "500000",
        "amountFormatted": "5,000.00",
        "type": "purchase",
        "typeLabel": "采购贡献",
        "orderId": "ord_001",
        "status": "settled",
        "statusLabel": "已结算",
        "settledAt": "2026-07-25T00:00:00+08:00"
      }
    ],
    "summary": {
      "totalAmount": "1250000",
      "totalAmountFormatted": "12,500.00",
      "count": 5
    },
    "nextCursor": "cursor_ctrb",
    "hasMore": false
  },
  "requestId": "req_20260730120000026",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to view this customer | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns contributions for this customer filtered by the bound promoter (who receives the contribution credit).
- `summary` aggregates the entire matching set, not just the current page.
- `status` enum: `pending`, `settled`, `cancelled`. Only `settled` amounts count toward total contribution.
- `amount` is in 分 (integer cents), returned as a string.

---

## Followups

**Method**: GET
**Path**: /api/v1/customers/{id}/followups
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "followupId": "fup_001",
        "type": "call",
        "typeLabel": "电话",
        "content": "电话沟通客户近期需求",
        "nextFollowupAt": "2026-08-15T10:00:00+08:00",
        "operatorId": "u_prom001",
        "operatorName": "李四",
        "createdAt": "2026-07-28T14:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_fup",
    "hasMore": false
  },
  "requestId": "req_20260730120000027",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to view this customer | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Followups are returned in reverse chronological order (newest first).
- `nextFollowupAt` is the planned time for the next followup action.

---

## Create Followup

**Method**: POST
**Path**: /api/v1/customers/{id}/followups
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Customer ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| type | string | yes | Enum: `call`, `visit`, `message`, `other` | Followup type |
| content | string | yes | Max 2000 chars | Followup content |
| nextFollowupAt | string | no | ISO 8601 datetime | Planned next followup time |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "followupId": "fup_002",
    "type": "visit",
    "typeLabel": "拜访",
    "content": "预约下周拜访",
    "nextFollowupAt": "2026-08-05T10:00:00+08:00",
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000028",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Customer not found | No |
| 40300 | Not authorized to create followup for this customer | No |
| 40031 | Next followup time must be in the future | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only the bound promoter can create followup records.
- `nextFollowupAt` must be a future datetime.
- Content is plain text (no HTML / Markdown).
