# Reports API Contracts

All endpoints under `/api/v1/reports/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## Generate Report

**Method**: POST
**Path**: /api/v1/reports/generate
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| reportType | string | yes | Enum: `contribution_summary`, `customer_analysis`, `team_performance`, `binding_overview`, `period_comparison` | Report type |
| title | string | no | Max 200 chars | Custom report title |
| startDate | string | yes | ISO 8601 date (YYYY-MM-DD) | Report period start |
| endDate | string | yes | ISO 8601 date (YYYY-MM-DD) | Report period end |
| filters | object | no | Type-specific filters | Additional filtering options |
| format | string | no | Enum: `xlsx`, `csv`, default `xlsx` | Export format |

### filters (by reportType)

**contribution_summary**:
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| customerId | string | no | Length 1-64 | Filter by customer |
| groupBy | string | no | Enum: `month`, `quarter` | Aggregation granularity |

**customer_analysis**:
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| minContribution | integer | no | >= 0 | Minimum contribution amount in fen |
| includeInactive | boolean | no | Default false | Include inactive customers |

**team_performance**:
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| promoterIds | array[string] | no | Max 50 items | Specific promoters |
| includeSubTeams | boolean | no | Default true | Include child org node teams |

**binding_overview**:
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| promoterId | string | no | Length 1-64 | Filter by promoter |

**period_comparison**:
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| compareStartDate | string | yes | ISO 8601 date (YYYY-MM-DD) | Comparison period start |
| compareEndDate | string | yes | ISO 8601 date (YYYY-MM-DD) | Comparison period end |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "reportId": "rpt_001",
    "reportType": "contribution_summary",
    "reportTypeLabel": "contribution summary",
    "title": "2026 July Contribution Summary",
    "status": "processing",
    "statusLabel": "generating",
    "format": "xlsx",
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000058",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40040 | Invalid date range | No |
| 40090 | A similar report is already being generated | Yes |
| 40091 | Unsupported report type | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Report generation is asynchronous; the endpoint returns immediately with `status: "processing"`.
- The client should poll until status becomes `completed` or `failed`.
- Reports are generated as Excel (.xlsx) files and stored in OSS.
- Maximum report period: 366 days.

---

## List Reports

**Method**: GET
**Path**: /api/v1/reports
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| reportType | string | no | Enum | Filter by report type |
| status | string | no | Enum: `processing`, `completed`, `failed` | Filter by status |
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
        "reportId": "rpt_001",
        "reportType": "contribution_summary",
        "reportTypeLabel": "contribution summary",
        "title": "2026 July Contribution Summary",
        "status": "completed",
        "statusLabel": "completed",
        "format": "xlsx",
        "fileSize": 245760,
        "fileSizeFormatted": "240 KB",
        "periodStart": "2026-07-01",
        "periodEnd": "2026-07-31",
        "createdAt": "2026-07-30T12:00:00+08:00",
        "completedAt": "2026-07-30T12:01:00+08:00",
        "expiresAt": "2026-08-06T12:01:00+08:00"
      }
    ],
    "nextCursor": "cursor_rpt",
    "hasMore": false
  },
  "requestId": "req_20260730120000059",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Reports are visible only to the creator (and admins with appropriate scope).
- Files expire 7 days after completion.
- Results sorted by `createdAt` descending.

---

## Report Detail

**Method**: GET
**Path**: /api/v1/reports/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Report ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "reportId": "rpt_001",
    "reportType": "contribution_summary",
    "reportTypeLabel": "contribution summary",
    "title": "2026 July Contribution Summary",
    "status": "completed",
    "statusLabel": "completed",
    "format": "xlsx",
    "fileSize": 245760,
    "fileSizeFormatted": "240 KB",
    "parameters": {
      "startDate": "2026-07-01",
      "endDate": "2026-07-31",
      "filters": { "groupBy": "month" }
    },
    "summary": {
      "totalRows": 45,
      "totalContribution": "8560000",
      "totalContributionFormatted": "85600.00"
    },
    "downloadUrl": "https://oss.example.com/reports/rpt_001.xlsx?token=xxx",
    "createdAt": "2026-07-30T12:00:00+08:00",
    "completedAt": "2026-07-30T12:01:00+08:00",
    "expiresAt": "2026-08-06T12:01:00+08:00",
    "errorMessage": null
  },
  "requestId": "req_20260730120000060",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Report not found | No |
| 40300 | Not authorized to view this report | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `downloadUrl` is present only when `status` is `completed`; it includes a signed OSS token valid for 1 hour.
- `errorMessage` is populated only when `status` is `failed`.

---

## Export / Download Report

**Method**: GET
**Path**: /api/v1/reports/{id}/export
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Report ID |

### Response (Success)
Returns a binary file stream with Content-Type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and Content-Disposition attachment header.

The response is a direct file download (not wrapped in the unified JSON envelope).

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Report not found | No |
| 40300 | Not authorized to download this report | No |
| 40092 | Report is not yet completed | Yes |
| 40093 | Report file has expired | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Proxies the OSS file and streams it to the client.
- Can only download completed reports.
- Each download generates a fresh signed OSS URL.
