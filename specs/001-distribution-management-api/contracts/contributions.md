# Contributions API Contracts

All endpoints under `/api/v1/contributions/` and `/api/v1/team/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

Contribution amounts are returned as strings (integer cents).

---

## Contribution Overview

**Method**: GET
**Path**: /api/v1/contributions/overview
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| period | string | no | Enum: `today`, `this_week`, `this_month`, `this_quarter`, `this_year`, `custom` | Time period preset. Default: `this_month` |
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Required when `period=custom` |
| endDate | string | no | ISO 8601 date (YYYY-MM-DD) | Required when `period=custom` |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "totalContribution": "8560000",
    "totalContributionFormatted": "85,600.00",
    "totalOrders": 42,
    "totalCustomers": 12,
    "averagePerCustomer": "713333",
    "averagePerCustomerFormatted": "7,133.33",
    "periodLabel": "本月",
    "periodStart": "2026-07-01T00:00:00+08:00",
    "periodEnd": "2026-07-31T23:59:59+08:00",
    "comparedToPrevious": {
      "percentage": 15.3,
      "trend": "up",
      "previousAmount": "7420000",
      "previousAmountFormatted": "74,200.00"
    }
  },
  "requestId": "req_20260730120000029",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40040 | Invalid date range | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `comparedToPrevious.percentage` is a signed float; positive = increase, negative = decrease.
- `trend`: `up`, `down`, `flat` (when percentage change is within +/- 0.5%).
- Previous period is the same-length period immediately before the current one.
- Only settled contributions are counted.

---

## Contribution Trend

**Method**: GET
**Path**: /api/v1/contributions/trend
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| granularity | string | no | Enum: `daily`, `weekly`, `monthly`, `quarterly`, `yearly`. Default: `daily` | Bucket size |
| startDate | string | yes | ISO 8601 date (YYYY-MM-DD) | Start date (inclusive) |
| endDate | string | yes | ISO 8601 date (YYYY-MM-DD) | End date (inclusive) |
| maxDays | integer | no | Default 90 | Maximum range in days (prevents over-fetch). Server may cap |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "granularity": "daily",
    "points": [
      {
        "date": "2026-07-01",
        "amount": "280000",
        "orderCount": 3,
        "customerCount": 2
      },
      {
        "date": "2026-07-02",
        "amount": "150000",
        "orderCount": 1,
        "customerCount": 1
      }
    ],
    "summary": {
      "totalAmount": "8560000",
      "totalAmountFormatted": "85,600.00",
      "maxSingleDayAmount": "1200000",
      "maxSingleDayDate": "2026-07-20"
    }
  },
  "requestId": "req_20260730120000030",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40040 | Invalid date range | No |
| 40041 | Date range exceeds maximum allowed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `points` includes every bucket in the range, even if the value is zero (zero-filled).
- `maxDays` caps the range to prevent excessive data fetching. Default 90 days; absolute max 365 days.
- `summary` aggregates across the entire time range, not just the points array.

---

## Contribution Composition

**Method**: GET
**Path**: /api/v1/contributions/composition
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Start of range |
| endDate | string | no | ISO 8601 date (YYYY-MM-DD) | End of range |
| groupBy | string | no | Enum: `customer`, `product`, `region`. Default: `customer` | Dimension to group by |
| topN | integer | no | 1-50, default 10 | Number of top items |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "groupBy": "customer",
    "totalAmount": "8560000",
    "totalAmountFormatted": "85,600.00",
    "items": [
      {
        "id": "cust_001",
        "name": "王五",
        "amount": "2500000",
        "amountFormatted": "25,000.00",
        "percentage": 29.21,
        "orderCount": 8
      },
      {
        "id": null,
        "name": "其他",
        "amount": "1800000",
        "amountFormatted": "18,000.00",
        "percentage": 21.03,
        "orderCount": 12
      }
    ]
  },
  "requestId": "req_20260730120000031",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40040 | Invalid date range | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the top N items by contribution amount, plus an aggregated "其他" (others) row for remaining items.
- `percentage` is relative to `totalAmount`.
- Items with zero contribution are excluded.
- `groupBy=region` uses the customer's province as the region key.

---

## List Contributions

**Method**: GET
**Path**: /api/v1/contributions
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Start of range |
| endDate | string | no | ISO 8601 date (YYYY-MM-DD) | End of range |
| status | string | no | Enum: `pending`, `settled`, `cancelled` | Filter by status |
| customerId | string | no | Length 1-64 | Filter by customer |
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
        "orderAmount": "1500000",
        "orderAmountFormatted": "15,000.00",
        "coefficient": "0.3333",
        "status": "settled",
        "statusLabel": "已结算",
        "customer": {
          "customerId": "cust_001",
          "name": "王五",
          "phone": "150****9999"
        },
        "settledAt": "2026-07-25T00:00:00+08:00"
      }
    ],
    "summary": {
      "totalAmount": "8560000",
      "totalAmountFormatted": "85,600.00",
      "count": 12
    },
    "nextCursor": "cursor_ctrb_list",
    "hasMore": true
  },
  "requestId": "req_20260730120000032",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns contributions for the current user (promoter's own contributions).
- `coefficient` is the share ratio applied to the order amount to compute the contribution.
- `summary` aggregates across the entire matching result set.
- Results are sorted by `settledAt` descending, then by `createdAt` descending.

---

## Contribution Detail

**Method**: GET
**Path**: /api/v1/contributions/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Contribution ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "contributionId": "ctrb_001",
    "amount": "500000",
    "amountFormatted": "5,000.00",
    "type": "purchase",
    "typeLabel": "采购贡献",
    "orderId": "ord_001",
    "orderAmount": "1500000",
    "orderAmountFormatted": "15,000.00",
    "coefficient": "0.3333",
    "coefficientLabel": "33.33%",
    "status": "settled",
    "statusLabel": "已结算",
    "customer": {
      "customerId": "cust_001",
      "name": "王五",
      "phone": "150****9999"
    },
    "sharingRules": [
      {
        "targetId": "u_prom001",
        "targetName": "李四",
        "targetType": "promoter",
        "percentage": 70,
        "amount": "350000"
      },
      {
        "targetId": "org_001",
        "targetName": "北京总部",
        "targetType": "org_node",
        "percentage": 30,
        "amount": "150000"
      }
    ],
    "adjustments": [
      {
        "adjustmentId": "adj_001",
        "amount": "50000",
        "reason": "季度奖励",
        "operatorId": "u_admin001",
        "operatorName": "管理员",
        "adjustedAt": "2026-07-26T10:00:00+08:00"
      }
    ],
    "createdAt": "2026-07-25T00:00:00+08:00",
    "settledAt": "2026-07-25T00:00:00+08:00"
  },
  "requestId": "req_20260730120000033",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Contribution not found | No |
| 40300 | Not authorized to view this contribution | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `sharingRules` shows the distribution of the contribution across promoters and org nodes.
- `adjustments` lists any manual adjustments made by admin.
- The sum of `sharingRules[*].percentage` should equal 100%.

---

## Team Contributions

**Method**: GET
**Path**: /api/v1/team/contributions
**Auth**: Required
**Idempotency**: Not applicable

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
        "promoterId": "u_prom001",
        "promoterName": "李四",
        "promoterCode": "ABC123",
        "avatarUrl": "https://example.com/avatars/xxx.png",
        "totalContribution": "3500000",
        "totalContributionFormatted": "35,000.00",
        "customerCount": 5,
        "orderCount": 18,
        "trend": "up",
        "trendPercentage": 8.5
      }
    ],
    "summary": {
      "teamTotalAmount": "8560000",
      "teamTotalAmountFormatted": "85,600.00",
      "memberCount": 3
    },
    "nextCursor": "cursor_team",
    "hasMore": false
  },
  "requestId": "req_20260730120000034",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- For a team leader: returns all team members with their contribution summaries.
- For a regular promoter: returns only the promoter's own summary (team of one).
- `trend` compares the current period to the same-length previous period.
- Results sorted by `totalContribution` descending.

---

## Specific Team Member Contributions

**Method**: GET
**Path**: /api/v1/team/contributions/{promoterId}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| promoterId | string | yes | Team member's promoter ID |

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
    "promoter": {
      "promoterId": "u_prom001",
      "promoterName": "李四",
      "promoterCode": "ABC123",
      "avatarUrl": "https://example.com/avatars/xxx.png"
    },
    "summary": {
      "totalAmount": "3500000",
      "totalAmountFormatted": "35,000.00",
      "customerCount": 5,
      "orderCount": 18
    },
    "items": [
      {
        "contributionId": "ctrb_010",
        "amount": "500000",
        "amountFormatted": "5,000.00",
        "type": "purchase",
        "typeLabel": "采购贡献",
        "customerName": "王五",
        "status": "settled",
        "statusLabel": "已结算",
        "settledAt": "2026-07-25T00:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_member",
    "hasMore": true
  },
  "requestId": "req_20260730120000035",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Promoter not found in your team | No |
| 40300 | Not authorized to view this team member | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only accessible if the requesting user is a team leader and `promoterId` belongs to their team.
- Admins can view any team member's contributions within their org scope.
