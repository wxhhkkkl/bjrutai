# API Contract: 后台消费录入

Base path: `/api/v1/admin/contributions`  
All responses use `{code, message, data, requestId, serverTime}`.  
All messages shown for business failures are Chinese.

## Search eligible customers

**Method**: `GET`  
**Path**: `/api/v1/admin/contributions/customers`  
**Auth**: Admin bearer token + `contributions.write`

### Query

| Name | Type | Required | Constraints |
|---|---|---:|---|
| `keyword` | string | yes | Trimmed length 1-100; matches customer name, phone or ID card |
| `pageSize` | integer | no | 1-20, default 20 |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "customerId": "42",
        "customerVersion": 3,
        "name": "张三",
        "phoneMasked": "138****1234",
        "idCardMasked": "110***********1234",
        "distributorId": "8",
        "personName": "李明",
        "orgId": "2",
        "orgName": "北京儒泰服务有限公司"
      }
    ]
  },
  "requestId": "request-id",
  "serverTime": "2026-09-02T09:00:00Z"
}
```

### Rules

- Only bound customers with active distributor and active organization are returned.
- No raw phone, ID card, medical account or family phone is returned.
- No match returns `items: []`, not an error.
- Results are ordered by the strongest exact match first, then latest customer ID, capped by `pageSize`.

## Create manual consumption

**Method**: `POST`  
**Path**: `/api/v1/admin/contributions/manual`  
**Auth**: Admin bearer token + `contributions.write`  
**Header**: `Idempotency-Key` required, 1-128 characters

### Request

```json
{
  "customerId": "42",
  "customerVersion": 3,
  "consumedAt": "2026-09-02T16:30:00+08:00",
  "amountCent": 12880,
  "note": "线下收款补录"
}
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `customerId` | numeric string | yes | Existing customer |
| `customerVersion` | integer | yes | At least 1; must equal current version |
| `consumedAt` | ISO 8601 datetime | yes | Must include timezone and must not be in the future |
| `amountCent` | integer | yes | Greater than 0 |
| `note` | string/null | no | Trimmed, maximum 500 characters |

### Success `200`

```json
{
  "code": 0,
  "message": "消费录入成功",
  "data": {
    "id": "901",
    "recordNo": "MANUAL-20260902-A1B2C3D4",
    "customerId": "42",
    "customerName": "张三",
    "phoneMasked": "138****1234",
    "distributorId": "8",
    "personName": "李明",
    "orgId": "2",
    "orgName": "北京儒泰服务有限公司",
    "amountCent": 12880,
    "status": "paid",
    "source": "manual",
    "consumedAt": "2026-09-02T08:30:00Z",
    "replayed": false
  },
  "requestId": "request-id",
  "serverTime": "2026-09-02T08:30:01Z"
}
```

An identical replay returns the same record with `replayed: true` and does not create another bill or audit record.

### Error contract

| HTTP | Code | Message | Condition |
|---:|---:|---|---|
| 400 | 40000 | `缺少或无效的 Idempotency-Key` | Header absent or invalid |
| 401 | 40100 | Existing auth message | Missing or expired token |
| 403 | 40300 | `缺少权限: contributions.write` | Read-only or unauthorized account |
| 404 | 40400 | `客户不存在` | Customer ID does not exist |
| 409 | 40920 | `客户资料或归属已变化，请重新选择客户` | Customer version changed |
| 409 | 40921 | `该客户当前不可录入消费` | Customer is unbound or its distributor/organization is disabled |
| 409 | 40922 | `幂等键已用于不同的消费内容` | Same admin/key but different fingerprint |
| 422 | 42200 | `提交数据校验失败` | Invalid amount, missing timezone, future time, invalid ID or oversized note |

No failed request creates a bill or audit record.

## Dashboard response extension

Existing endpoint: `GET /api/v1/admin/contributions/dashboard`.

Each `data.latest[]` item adds:

```json
{
  "customerId": "42",
  "customerName": "张三",
  "phoneMasked": "138****1234",
  "source": "manual"
}
```

- Existing synchronized bills return `source: "rutai_sync"`.
- Manual items use submission-time person and organization snapshots.
- Existing fields and response envelope remain backward compatible.

