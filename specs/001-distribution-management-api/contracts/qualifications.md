# Qualifications API Contracts

All endpoints under `/api/v1/qualifications/` and `/api/v1/qualification-files/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## Get Current Qualification

**Method**: GET
**Path**: /api/v1/qualifications/current
**Auth**: Required
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "qualificationId": "qual_001",
    "status": "approved",
    "statusLabel": "已通过",
    "submittedAt": "2026-06-15T10:30:00+08:00",
    "reviewedAt": "2026-06-16T09:00:00+08:00",
    "reviewComment": "资料齐全，审核通过",
    "fields": {
      "realName": "张三",
      "idCardNumber": "110***********1234",
      "idCardFrontUrl": "https://oss.example.com/qual/xxx_front.jpg",
      "idCardBackUrl": "https://oss.example.com/qual/xxx_back.jpg",
      "bankCardNumber": "6***********7890",
      "bankName": "中国工商银行",
      "bankBranch": "北京XX支行",
      "education": "本科",
      "profession": "销售"
    }
  },
  "requestId": "req_20260730120000007",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Response (No Qualification)
```json
{
  "code": 0,
  "message": "success",
  "data": null,
  "requestId": "req_20260730120000008",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns `data: null` if the user has not yet submitted a qualification.
- `status` enum: `draft`, `pending_review`, `approved`, `rejected`.
- Sensitive fields (idCardNumber, bankCardNumber) are masked in response.

---

## Upload Token for Qualification Files

**Method**: POST
**Path**: /api/v1/qualification-files/upload-token
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| fileType | string | yes | Enum: `id_card_front`, `id_card_back`, `bank_card`, `handheld_id` | Type of qualification file |
| fileName | string | yes | Max 255 chars, ends with `.jpg`, `.jpeg`, `.png`, `.pdf` | Original file name |
| fileSize | integer | yes | 1 - 10,485,760 (10 MB) | File size in bytes |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "uploadToken": "UPLOAD_TOKEN_abc123",
    "uploadUrl": "https://oss.example.com/upload/qual_xxx.jpg",
    "expiresAt": "2026-07-30T12:15:00+08:00",
    "fileKey": "qualifications/u_abc123/2026/07/id_card_front_xxx.jpg",
    "contentType": "image/jpeg"
  },
  "requestId": "req_20260730120000009",
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
- The upload token expires after 15 minutes.
- Client must first obtain this token, then PUT the file directly to `uploadUrl` with the token in the Authorization header.
- After successful OSS upload, the client includes `fileKey` in the qualification submit request.
- File name is sanitized server-side; path stored as `qualifications/{userId}/YYYY/MM/{fileType}_{random}.{ext}`.

---

## Submit Qualification

**Method**: POST
**Path**: /api/v1/qualifications
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| realName | string | yes | Length 2-50 | Real name |
| idCardNumber | string | yes | Length 18 | Resident ID card number |
| idCardFrontFileKey | string | yes | Max 512 chars | OSS file key for ID card front image |
| idCardBackFileKey | string | yes | Max 512 chars | OSS file key for ID card back image |
| bankCardNumber | string | yes | Length 16-19 | Bank card number |
| bankName | string | yes | Max 100 chars | Bank name |
| bankBranch | string | no | Max 200 chars | Branch name |
| education | string | no | Enum: `high_school`, `associate`, `bachelor`, `master`, `phd`, `other` | Education level |
| profession | string | no | Max 100 chars | Profession |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "qualificationId": "qual_001",
    "status": "pending_review",
    "statusLabel": "待审核",
    "submittedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000010",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40012 | A qualification record is already under review or approved | No |
| 40013 | Invalid ID card number format | No |
| 40014 | ID card number already registered | No |
| 40015 | Invalid bank card number | No |
| 40016 | Some file keys are invalid or expired | No |
| 50001 | Internal server error | Yes |

### Business Rules
- A user can have at most one active qualification record (status: `pending_review` or `approved`).
- ID card number is validated against Chinese resident ID card checksum algorithm.
- After submission, status enters `pending_review` and triggers an admin review notification.

---

## Update / Resubmit Qualification

**Method**: PUT
**Path**: /api/v1/qualifications/{id}
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Qualification record ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| realName | string | no | Length 2-50 | Real name |
| idCardNumber | string | no | Length 18 | ID card number |
| idCardFrontFileKey | string | no | Max 512 chars | Updated ID card front file key |
| idCardBackFileKey | string | no | Max 512 chars | Updated ID card back file key |
| bankCardNumber | string | no | Length 16-19 | Bank card number |
| bankName | string | no | Max 100 chars | Bank name |
| bankBranch | string | no | Max 200 chars | Branch name |
| education | string | no | Enum | Education level |
| profession | string | no | Max 100 chars | Profession |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "qualificationId": "qual_001",
    "status": "pending_review",
    "statusLabel": "待审核",
    "submittedAt": "2026-07-30T14:00:00+08:00"
  },
  "requestId": "req_20260730120000011",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Qualification record not found | No |
| 40017 | Can only update rejected or draft records | No |
| 40016 | Some file keys are invalid or expired | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only rejected (`rejected`) or draft (`draft`) qualifications can be edited and resubmitted.
- Resubmission sets status back to `pending_review`.
- Submitted time is reset to the resubmission time.

---

## Qualification Review History

**Method**: GET
**Path**: /api/v1/qualifications/{id}/reviews
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Qualification record ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "reviewId": "rev_001",
        "reviewerName": "管理员张三",
        "action": "approved",
        "actionLabel": "通过",
        "comment": "资料齐全，审核通过",
        "reviewedAt": "2026-06-16T09:00:00+08:00"
      }
    ]
  },
  "requestId": "req_20260730120000012",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Qualification record not found | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns all review actions in chronological order (oldest first).
- Action enum: `approved`, `rejected`, `returned_for_amend`.
- The user can only see reviews for their own qualification records.

---

## Save Qualification Draft

**Method**: POST
**Path**: /api/v1/qualifications/draft
**Auth**: Required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| realName | string | no | Length 2-50 | Real name |
| idCardNumber | string | no | Length 18 | ID card number |
| idCardFrontFileKey | string | no | Max 512 chars | ID card front file key |
| idCardBackFileKey | string | no | Max 512 chars | ID card back file key |
| bankCardNumber | string | no | Length 16-19 | Bank card number |
| bankName | string | no | Max 100 chars | Bank name |
| bankBranch | string | no | Max 200 chars | Branch name |
| education | string | no | Enum | Education level |
| profession | string | no | Max 100 chars | Profession |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "qualificationId": "qual_draft_001",
    "status": "draft",
    "statusLabel": "草稿",
    "savedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000013",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40012 | A qualification record is already under review or approved | No |
| 40016 | Some file keys are invalid or expired | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Creates or updates a draft qualification. Drafts do not trigger review.
- If a draft already exists, this endpoint overwrites it (upsert semantics).
- Drafts cannot exist concurrently with an `approved` or `pending_review` qualification.
- All fields are optional; empty fields are simply omitted from the draft.
- The client can call this endpoint repeatedly to auto-save progress.
