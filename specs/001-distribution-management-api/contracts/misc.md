# Miscellaneous API Contracts

All endpoints under `/api/v1/me/`, `/api/v1/promotion-code/`, `/api/v1/workbench/`, `/api/v1/app/`, `/api/v1/agreements/`, `/api/v1/consents/`, `/api/v1/feedbacks/`, `/api/v1/feedback-files/`, `/api/v1/notifications/`, and `/api/v1/customer-analysis`.

Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## My Profile

**Method**: GET
**Path**: /api/v1/me/profile
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "userId": "u_abc123",
    "openId": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "unionId": "uXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "nickname": "用户昵称",
    "avatarUrl": "https://example.com/avatars/xxx.png",
    "phone": "138****1234",
    "phoneRaw": "13812341234",
    "realName": "张三",
    "gender": "male",
    "genderLabel": "男",
    "role": "promoter",
    "promoterCode": "ABC123",
    "orgNodeId": "org_002",
    "orgNodeName": "华东大区",
    "qualificationStatus": "approved",
    "qualificationStatusLabel": "已认证",
    "bindingCount": 12,
    "createdAt": "2026-01-15T08:00:00+08:00"
  },
  "requestId": "req_20260730120000068",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- `phone` is masked. `phoneRaw` is the full number (visible only to the owning user).
- `promoterCode` is present only for users with role `promoter` and approved qualification.
- `qualificationStatus` enum: `none`, `draft`, `pending_review`, `approved`, `rejected`.

---

## Update My Profile

**Method**: PUT
**Path**: /api/v1/me/profile
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| nickname | string | no | Length 1-50 | Display nickname |
| avatarUrl | string | no | Max 2048 chars | Avatar image URL |
| gender | string | no | Enum: `male`, `female`, `other` | Gender |
| realName | string | no | Length 2-50 | Real name (only changeable if qualification not submitted) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "userId": "u_abc123",
    "nickname": "新昵称",
    "avatarUrl": "https://example.com/avatars/new_xxx.png",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000069",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40100 | Not authenticated | No |
| 40101 | Token invalid | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `realName` is locked once qualification has been submitted (any status beyond `none`).
- Supplied fields are merged; omitted fields are unchanged.

---

## Avatar Upload Token

**Method**: POST
**Path**: /api/v1/me/avatar/upload-token
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| fileName | string | yes | Max 255 chars, ends with `.jpg`, `.jpeg`, `.png`, `.webp` | Original file name |
| fileSize | integer | yes | 1 - 5,242,880 (5 MB) | File size in bytes |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "uploadToken": "UPLOAD_TOKEN_avatar123",
    "uploadUrl": "https://oss.example.com/upload/avatar_xxx.jpg",
    "expiresAt": "2026-07-30T12:15:00+08:00",
    "fileKey": "avatars/u_abc123/avatar_xxx.jpg",
    "contentType": "image/jpeg"
  },
  "requestId": "req_20260730120000070",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40010 | Unsupported file type | No |
| 40011 | File size exceeds maximum allowed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- After successful upload, the client calls `PUT /api/v1/me/profile` with the resulting `fileKey` as `avatarUrl`.
- Upload token expires in 15 minutes.
- Maximum file size: 5 MB.

---

## Account Summary

**Method**: GET
**Path**: /api/v1/me/account-summary
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "userId": "u_abc123",
    "role": "promoter",
    "roleLabel": "推广员",
    "qualificationStatus": "approved",
    "qualificationStatusLabel": "已认证",
    "activeBindingCount": 10,
    "totalContribution": "8560000",
    "totalContributionFormatted": "85,600.00",
    "thisMonthContribution": "1250000",
    "thisMonthContributionFormatted": "12,500.00",
    "thisMonthOrderCount": 5,
    "customerCount": 10,
    "unreadNotificationCount": 3,
    "lastLoginAt": "2026-07-30T08:00:00+08:00"
  },
  "requestId": "req_20260730120000071",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Lightweight summary suitable for displaying on the app home screen.
- `thisMonth*` fields are relative to the current calendar month.

---

## Get Promotion Code

**Method**: GET
**Path**: /api/v1/promotion-code
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "code": "ABC123",
    "qrCodeUrl": "https://oss.example.com/qrcodes/ABC123.png",
    "createdAt": "2026-01-15T08:00:00+08:00",
    "totalScans": 458,
    "totalRegistrations": 23,
    "conversionRate": "5.02"
  },
  "requestId": "req_20260730120000072",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40099 | Promotion code not available (qualification required) | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Promotion code is only available after qualification is approved.
- `qrCodeUrl` is a pre-generated QR code image for sharing.
- `conversionRate` = `totalRegistrations / totalScans * 100`, returned as a string with 2 decimal places.

---

## Refresh Promotion Code

**Method**: POST
**Path**: /api/v1/promotion-code/refresh
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "code": "XYZ789",
    "qrCodeUrl": "https://oss.example.com/qrcodes/XYZ789.png",
    "previousCode": "ABC123",
    "refreshedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000073",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40099 | Promotion code not available | No |
| 40100 | Can only refresh once every 30 days | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Generates a new unique promotion code. The old code continues to work but new scans will be attributed to the new code.
- Rate limited: once per 30 days.
- Previous code statistics remain accessible.

---

## Promotion Code Statistics

**Method**: GET
**Path**: /api/v1/promotion-code/statistics
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Start of range |
| endDate | string | no | ISO 8601 date (YYYY-MM-DD) | End of range |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "code": "ABC123",
    "totalScans": 458,
    "totalRegistrations": 23,
    "conversionRate": "5.02",
    "dailyStats": [
      {
        "date": "2026-07-29",
        "scans": 15,
        "registrations": 2
      }
    ],
    "summary": {
      "periodStart": "2026-07-01",
      "periodEnd": "2026-07-30",
      "totalScans": 120,
      "totalRegistrations": 7,
      "conversionRate": "5.83"
    }
  },
  "requestId": "req_20260730120000074",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40099 | Promotion code not available | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `dailyStats` includes every day in the range, zero-filled when no activity.
- Maximum date range: 90 days.

---

## Promotion Code Poster

**Method**: GET
**Path**: /api/v1/promotion-code/poster
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "posterUrl": "https://oss.example.com/posters/ABC123_poster.jpg",
    "code": "ABC123",
    "qrCodeUrl": "https://oss.example.com/qrcodes/ABC123.png",
    "templateId": "tpl_default",
    "generatedAt": "2026-07-30T08:00:00+08:00"
  },
  "requestId": "req_20260730120000075",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40099 | Promotion code not available | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns a pre-generated promotional poster image (composite of template + QR code).
- Posters are re-generated once per day; the endpoint returns the latest cached version.
- Returns `data: null` if no poster template is configured.

---

## Workbench

**Method**: GET
**Path**: /api/v1/workbench
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "greeting": "下午好",
    "userName": "张三",
    "todayStats": {
      "contribution": "120000",
      "contributionFormatted": "1,200.00",
      "newCustomers": 2,
      "newBindings": 1
    },
    "thisMonthStats": {
      "contribution": "1250000",
      "contributionFormatted": "12,500.00",
      "newCustomers": 5,
      "newBindings": 3
    },
    "quickActions": [
      {
        "actionId": "invite_customer",
        "label": "邀请客户",
        "iconUrl": "https://example.com/icons/invite.png",
        "route": "/pages/invite/index"
      }
    ],
    "unreadNotificationCount": 3
  },
  "requestId": "req_20260730120000076",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- `greeting` is localized Chinese: 早上好 (before 12:00), 下午好 (12:00-18:00), 晚上好 (after 18:00).
- `quickActions` is admin-configurable; admins see admin-specific actions.
- All monetary values are in 分 (integer cents), returned as strings.

---

## Workbench Notices

**Method**: GET
**Path**: /api/v1/workbench/notices
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-50, default 10 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "noticeId": "notice_001",
        "title": "系统维护通知",
        "content": "系统将于7月31日凌晨2:00-4:00进行维护升级",
        "type": "system",
        "typeLabel": "系统公告",
        "isRead": false,
        "publishedAt": "2026-07-29T10:00:00+08:00"
      }
    ],
    "nextCursor": null,
    "hasMore": false
  },
  "requestId": "req_20260730120000077",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns system notices targeting the current user's org scope.
- `type` enum: `system`, `policy`, `event`.
- Results sorted by `publishedAt` descending.

---

## Workbench Recent Bindings

**Method**: GET
**Path**: /api/v1/workbench/recent-bindings
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "bindingId": "bind_003",
        "customerId": "cust_012",
        "customerName": "新客户A",
        "status": "accepted",
        "statusLabel": "已绑定",
        "boundAt": "2026-07-29T14:00:00+08:00"
      }
    ]
  },
  "requestId": "req_20260730120000078",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the 5 most recent bindings (accepted status only).
- Results sorted by `boundAt` descending.

---

## Workbench Contribution Summary

**Method**: GET
**Path**: /api/v1/workbench/contribution-summary
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "today": {
      "amount": "120000",
      "amountFormatted": "1,200.00",
      "orderCount": 2
    },
    "thisWeek": {
      "amount": "850000",
      "amountFormatted": "8,500.00",
      "orderCount": 8
    },
    "thisMonth": {
      "amount": "1250000",
      "amountFormatted": "12,500.00",
      "orderCount": 15
    },
    "trend": {
      "direction": "up",
      "percentage": 12.5,
      "label": "较上月增长12.5%"
    }
  },
  "requestId": "req_20260730120000079",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Compact contribution summary for the workbench dashboard card.
- `trend` compares current month-to-date vs same period last month.
- All amounts in 分 (integer cents), returned as strings.

---

## App Bootstrap

**Method**: GET
**Path**: /api/v1/app/bootstrap
**Auth**: Required (token optional; returns guest config if no token)
**Idempotency**: Not applicable

### Response (Success - Authenticated)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": {
      "userId": "u_abc123",
      "nickname": "用户昵称",
      "avatarUrl": "https://example.com/avatars/xxx.png",
      "role": "promoter"
    },
    "config": {
      "appVersion": "1.2.0",
      "minAppVersion": "1.0.0",
      "forceUpdate": false,
      "updateUrl": "https://example.com/update",
      "features": {
        "bindingEnabled": true,
        "qualificationEnabled": true,
        "reportsEnabled": true
      },
      "ossConfig": {
        "bucket": "bjrutai-prod",
        "region": "oss-cn-beijing",
        "endpoint": "https://oss-cn-beijing.aliyuncs.com"
      },
      "themeConfig": {
        "primaryColor": "#1890FF",
        "logoUrl": "https://example.com/logo.png"
      }
    },
    "permissions": ["binding.submit", "customer.read", "contribution.read"],
    "unreadNotificationCount": 3
  },
  "requestId": "req_20260730120000080",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Response (Success - Guest)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": null,
    "config": {
      "appVersion": "1.2.0",
      "minAppVersion": "1.0.0",
      "forceUpdate": false,
      "updateUrl": "https://example.com/update",
      "features": {
        "bindingEnabled": false,
        "qualificationEnabled": false,
        "reportsEnabled": false
      },
      "themeConfig": {
        "primaryColor": "#1890FF",
        "logoUrl": "https://example.com/logo.png"
      }
    },
    "permissions": [],
    "unreadNotificationCount": 0
  },
  "requestId": "req_20260730120000081",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- The app calls this endpoint on launch to fetch user state and global configuration in a single request.
- If the Authorization header is absent or the token is expired, a guest response is returned (no error).
- `forceUpdate: true` means the app must show an update modal and block usage until updated.
- `features` map controls which modules are visible in the app UI.

---

## Latest Agreement

**Method**: GET
**Path**: /api/v1/agreements/latest
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| type | string | no | Enum: `terms_of_service`, `privacy_policy`, `promoter_agreement`. Default: `terms_of_service` | Agreement type |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "agreementId": "agr_001",
    "type": "terms_of_service",
    "typeLabel": "服务协议",
    "title": "北京儒泰用户服务协议 v2.3",
    "version": "2.3",
    "content": "<p>富文本HTML内容...</p>",
    "effectiveAt": "2026-07-01T00:00:00+08:00",
    "publishedAt": "2026-06-28T10:00:00+08:00"
  },
  "requestId": "req_20260730120000082",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40100 | No agreement found for this type | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the latest published agreement of the requested type with the highest `version`.
- `content` may contain sanitized HTML.
- Agreements are immutable once published; updates create a new version.

---

## Agreement Detail

**Method**: GET
**Path**: /api/v1/agreements/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Agreement ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "agreementId": "agr_001",
    "type": "terms_of_service",
    "typeLabel": "服务协议",
    "title": "北京儒泰用户服务协议 v2.3",
    "version": "2.3",
    "content": "<p>富文本HTML内容...</p>",
    "effectiveAt": "2026-07-01T00:00:00+08:00",
    "publishedAt": "2026-06-28T10:00:00+08:00",
    "previousVersionId": "agr_000"
  },
  "requestId": "req_20260730120000083",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Agreement not found | No |
| 50001 | Internal server error | Yes |

---

## Record Consent

**Method**: POST
**Path**: /api/v1/consents
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| agreementId | string | yes | Length 1-64 | Agreement ID being consented to |
| consented | boolean | yes | - | User consent |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "consentId": "consent_001",
    "agreementId": "agr_001",
    "agreementType": "terms_of_service",
    "consented": true,
    "recordedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000084",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Agreement not found | No |
| 40101 | Consent already recorded for this agreement version | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only one consent record per user per agreement version.
- `consented: false` means the user declined. Access may be restricted accordingly.
- Consent records are immutable once created.

---

## My Consents

**Method**: GET
**Path**: /api/v1/me/consents
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "consentId": "consent_001",
        "agreementId": "agr_001",
        "agreementTitle": "北京儒泰用户服务协议 v2.3",
        "agreementType": "terms_of_service",
        "agreementTypeLabel": "服务协议",
        "consented": true,
        "recordedAt": "2026-07-30T12:00:00+08:00"
      }
    ]
  },
  "requestId": "req_20260730120000085",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the user's consent records across all agreement types.
- Results grouped by `agreementType`, showing only the latest consent per type.

---

## Update Privacy Settings

**Method**: PUT
**Path**: /api/v1/me/privacy-settings
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| showPhoneToPromoter | boolean | no | - | Whether bound promoter can see phone number |
| showContributionToTeam | boolean | no | - | Whether team members can see contribution details |
| allowMarketingMessages | boolean | no | - | Whether to receive marketing notifications |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "settings": {
      "showPhoneToPromoter": true,
      "showContributionToTeam": false,
      "allowMarketingMessages": true
    },
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000086",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Supplied fields are merged with existing settings.
- `showPhoneToPromoter`: when `false`, phone is fully masked (`****`) for all other users.
- `showContributionToTeam`: when `false`, team contribution views show `--` for this user.
- `allowMarketingMessages`: when `false`, marketing notifications are suppressed.

---

## Feedback File Upload Token

**Method**: POST
**Path**: /api/v1/feedback-files/upload-token
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| fileName | string | yes | Max 255 chars, ends with `.jpg`, `.jpeg`, `.png`, `.pdf` | Original file name |
| fileSize | integer | yes | 1 - 10,485,760 (10 MB) | File size in bytes |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "uploadToken": "UPLOAD_TOKEN_fb123",
    "uploadUrl": "https://oss.example.com/upload/fb_xxx.jpg",
    "expiresAt": "2026-07-30T12:15:00+08:00",
    "fileKey": "feedbacks/u_abc123/2026/07/xxx.jpg",
    "contentType": "image/jpeg"
  },
  "requestId": "req_20260730120000087",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40010 | Unsupported file type | No |
| 40011 | File size exceeds maximum allowed | No |
| 50001 | Internal server error | Yes |

---

## Submit Feedback

**Method**: POST
**Path**: /api/v1/feedbacks
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| type | string | yes | Enum: `bug`, `suggestion`, `complaint`, `other` | Feedback type |
| content | string | yes | Max 2000 chars | Feedback content |
| fileKeys | array[string] | no | Max 10 items | Uploaded file keys |
| contactInfo | string | no | Max 200 chars | Optional contact info for follow-up |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "feedbackId": "fb_001",
    "type": "suggestion",
    "typeLabel": "建议",
    "status": "submitted",
    "submittedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000088",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40102 | Content is required | No |
| 40103 | Too many files | No |
| 50001 | Internal server error | Yes |

---

## List My Feedbacks

**Method**: GET
**Path**: /api/v1/feedbacks
**Auth**: Required
**Idempotency**: Not applicable

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
        "feedbackId": "fb_001",
        "type": "suggestion",
        "typeLabel": "建议",
        "content": "希望增加批量导入功能...",
        "status": "submitted",
        "statusLabel": "已提交",
        "hasFiles": true,
        "adminReply": null,
        "submittedAt": "2026-07-30T12:00:00+08:00"
      }
    ],
    "nextCursor": null,
    "hasMore": false
  },
  "requestId": "req_20260730120000089",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns only the current user's feedback submissions.
- `adminReply` is populated when an admin responds to the feedback.
- Results sorted by `submittedAt` descending.

---

## Notifications

**Method**: GET
**Path**: /api/v1/notifications
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| isRead | boolean | no | - | Filter by read status |
| type | string | no | Enum: `binding`, `qualification`, `contribution`, `system`, `marketing` | Filter by type |
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
        "notificationId": "notif_001",
        "type": "binding",
        "typeLabel": "绑定通知",
        "title": "新的绑定申请",
        "content": "用户张三申请与您绑定",
        "isRead": false,
        "actionUrl": "/pages/binding/detail?id=bindreq_001",
        "createdAt": "2026-07-30T11:00:00+08:00"
      }
    ],
    "unreadCount": 3,
    "nextCursor": "cursor_notif",
    "hasMore": true
  },
  "requestId": "req_20260730120000090",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- `unreadCount` is the total unread count across all notifications (not just the current page).
- `actionUrl` is a deeplink path the client should navigate to when the notification is tapped.
- Results sorted by `createdAt` descending.

---

## Mark Notification as Read

**Method**: POST
**Path**: /api/v1/notifications/{id}/read
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Notification ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "notificationId": "notif_001",
    "isRead": true,
    "readAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000091",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Notification not found | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Idempotent: marking an already-read notification returns success.
- Only the owning user can mark their notifications as read.

---

## Customer Analysis

**Method**: GET
**Path**: /api/v1/customer-analysis
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| dimension | string | no | Enum: `region`, `contribution_level`, `activity_level`, `binding_duration`. Default: `contribution_level` | Analysis dimension |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "dimension": "contribution_level",
    "dimensionLabel": "贡献等级",
    "totalCustomers": 12,
    "segments": [
      {
        "label": "高贡献 (>= 10,000元)",
        "customerCount": 3,
        "percentage": 25.0,
        "totalContribution": "7500000",
        "totalContributionFormatted": "75,000.00",
        "averageContribution": "2500000",
        "averageContributionFormatted": "25,000.00"
      },
      {
        "label": "中贡献 (1,000-10,000元)",
        "customerCount": 5,
        "percentage": 41.7,
        "totalContribution": "1000000",
        "totalContributionFormatted": "10,000.00",
        "averageContribution": "200000",
        "averageContributionFormatted": "2,000.00"
      },
      {
        "label": "低贡献 (< 1,000元)",
        "customerCount": 4,
        "percentage": 33.3,
        "totalContribution": "60000",
        "totalContributionFormatted": "600.00",
        "averageContribution": "15000",
        "averageContributionFormatted": "150.00"
      }
    ],
    "generatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000092",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Segments customers of the current user (promoter) or org node (admin) by the chosen dimension.
- Segment thresholds are server-configured.
- All amounts in 分 (integer cents), returned as strings.
- `generatedAt` indicates when the analysis was computed (cached for up to 1 hour).
