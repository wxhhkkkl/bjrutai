# Binding API Contracts

All endpoints under `/api/v1/promoters/`, `/api/v1/binding-requests/`, and `/api/v1/binding-summary`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## Selectable Promoters

**Method**: GET
**Path**: /api/v1/promoters/selectable
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| keyword | string | no | Max 100 chars | Search by promoter name or code |
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
        "promoterId": "u_prom001",
        "promoterCode": "ABC123",
        "displayName": "李四",
        "avatarUrl": "https://example.com/avatars/xxx.png",
        "orgNodeName": "华东大区",
        "bindingCount": 15
      }
    ],
    "nextCursor": "cursor_abc",
    "hasMore": true
  },
  "requestId": "req_20260730120000014",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns active promoters whose qualifications have been approved.
- Results are sorted by `bindingCount` descending (most popular first), then by `displayName`.
- Promoters assigned to the same org node as the requesting user appear first.
- Cursor pagination: `nextCursor` is null when there are no more results.

---

## Submit Binding Request

**Method**: POST
**Path**: /api/v1/binding-requests
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| promoterId | string | yes | Length 1-64 | Target promoter user ID |
| promoterCode | string | no | Length 6-32 | Target promoter code (one of promoterId or promoterCode required) |
| customerInfo | object | no | See below | Optional customer information linked to this user |
| customerInfo.name | string | no | Max 100 chars | Customer name |
| customerInfo.phone | string | no | Length 11 | Customer phone (China mobile) |
| customerInfo.remark | string | no | Max 500 chars | Remark |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "requestId": "bindreq_001",
    "status": "pending",
    "statusLabel": "等待确认",
    "promoterId": "u_prom001",
    "promoterName": "李四",
    "submittedAt": "2026-07-30T12:00:00+08:00",
    "expiresAt": "2026-08-06T12:00:00+08:00"
  },
  "requestId": "req_20260730120000015",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40020 | Promoter not found or not selectable | No |
| 40021 | You already have a pending binding request for this promoter | No |
| 40022 | You are already bound to this promoter | No |
| 40023 | Maximum active bindings reached for this promoter | No |
| 40025 | User qualification must be approved before binding | No |
| 50001 | Internal server error | Yes |

### Business Rules
- A binding request expires after 7 days if not accepted or rejected.
- A user can have at most one pending binding request at a time (across all promoters).
- After submission, the promoter receives a notification to accept or reject.
- `expiresAt` is computed as `submittedAt + 7 days`.

---

## List Binding Requests

**Method**: GET
**Path**: /api/v1/binding-requests
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| status | string | no | Enum: `pending`, `accepted`, `rejected`, `expired`, `cancelled` | Filter by status |
| role | string | no | Enum: `initiator`, `target` | "initiator" = I sent, "target" = I received. Default: `initiator` |
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
        "requestId": "bindreq_001",
        "status": "pending",
        "statusLabel": "等待确认",
        "initiator": {
          "userId": "u_abc123",
          "displayName": "张三",
          "avatarUrl": "https://example.com/avatars/xxx.png",
          "phone": "138****1234"
        },
        "target": {
          "userId": "u_prom001",
          "displayName": "李四",
          "avatarUrl": "https://example.com/avatars/yyy.png",
          "phone": "139****5678"
        },
        "customerInfo": {
          "name": "王五",
          "phone": "150****9999",
          "remark": "重点客户"
        },
        "submittedAt": "2026-07-30T12:00:00+08:00",
        "expiresAt": "2026-08-06T12:00:00+08:00",
        "resolvedAt": null
      }
    ],
    "nextCursor": "cursor_bcd",
    "hasMore": false
  },
  "requestId": "req_20260730120000016",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- When `role=initiator`: returns requests the current user initiated.
- When `role=target`: returns requests where the current user is the promoter being requested.
- For promoters viewing incoming requests: `initiator` is the requesting user, `target` is the promoter.
- `resolvedAt` is non-null only when status is `accepted`, `rejected`, `expired`, or `cancelled`.

---

## Binding Request Detail

**Method**: GET
**Path**: /api/v1/binding-requests/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Binding request ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "requestId": "bindreq_001",
    "status": "accepted",
    "statusLabel": "已接受",
    "initiator": {
      "userId": "u_abc123",
      "displayName": "张三",
      "avatarUrl": "https://example.com/avatars/xxx.png",
      "phone": "138****1234"
    },
    "target": {
      "userId": "u_prom001",
      "displayName": "李四",
      "avatarUrl": "https://example.com/avatars/yyy.png",
      "phone": "139****5678"
    },
    "customerInfo": {
      "name": "王五",
      "phone": "150****9999",
      "remark": "重点客户"
    },
    "events": [
      {
        "action": "submitted",
        "actionLabel": "提交申请",
        "operatorId": "u_abc123",
        "operatorName": "张三",
        "timestamp": "2026-07-30T12:00:00+08:00"
      },
      {
        "action": "accepted",
        "actionLabel": "接受绑定",
        "operatorId": "u_prom001",
        "operatorName": "李四",
        "timestamp": "2026-07-30T14:00:00+08:00"
      }
    ],
    "submittedAt": "2026-07-30T12:00:00+08:00",
    "expiresAt": "2026-08-06T12:00:00+08:00",
    "resolvedAt": "2026-07-30T14:00:00+08:00"
  },
  "requestId": "req_20260730120000017",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Binding request not found | No |
| 40300 | Not authorized to view this binding request | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only the initiator, target, and admin users can view the detail.
- `events` is an audit trail of all actions on this request, ordered chronologically.

---

## Binding Summary

**Method**: GET
**Path**: /api/v1/binding-summary
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "totalBindings": 12,
    "activeBindings": 10,
    "pendingRequests": 1,
    "rejectedRequests": 3,
    "expiredRequests": 2,
    "lastBindingAt": "2026-07-28T15:00:00+08:00"
  },
  "requestId": "req_20260730120000018",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- For promoters: `totalBindings` and `activeBindings` count downstream users bound to this promoter.
- For regular users: counts the user's own binding records.
- `pendingRequests` counts requests in `pending` status.

---

## Retry Binding Request

**Method**: POST
**Path**: /api/v1/binding-requests/{id}/retry
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Binding request ID to retry |

### Request Body
None.

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "requestId": "bindreq_002",
    "status": "pending",
    "statusLabel": "等待确认",
    "promoterId": "u_prom001",
    "promoterName": "李四",
    "submittedAt": "2026-07-30T16:00:00+08:00",
    "expiresAt": "2026-08-06T16:00:00+08:00"
  },
  "requestId": "req_20260730120000019",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Binding request not found | No |
| 40026 | Can only retry rejected, expired, or cancelled requests | No |
| 40021 | Another pending request already exists for this promoter | No |
| 40022 | Already bound to this promoter | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only `rejected`, `expired`, or `cancelled` requests can be retried.
- Retry creates a brand-new binding request (new ID, new `expiresAt`).
- The old request remains in its resolved state; the new request is a separate record.
- If the promoter already has maximum active bindings, retry will fail with `40023`.

---

## Update Customer Info on Binding Request

**Method**: PUT
**Path**: /api/v1/binding-requests/{id}/customer-info
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Binding request ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | no | Max 100 chars | Customer name |
| phone | string | no | Length 11 | Customer phone |
| remark | string | no | Max 500 chars | Remark |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "requestId": "bindreq_001",
    "customerInfo": {
      "name": "王五",
      "phone": "150****9999",
      "remark": "重点客户-已更新"
    },
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000020",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Binding request not found | No |
| 40027 | Can only update customer info for pending requests | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Customer info can only be updated while the request is in `pending` status.
- Only the initiator (the user who sent the request) can update customer info.
- Supplied fields are merged; omitted fields retain their previous value.
