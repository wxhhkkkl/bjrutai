# Auth API Contracts

All endpoints under `/api/v1/auth/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## WeChat Mini-Program Login

**Method**: POST
**Path**: /api/v1/auth/wechat-login
**Auth**: Not required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| code | string | yes | Length 1-256 | WeChat `wx.login()` returned code |
| encryptedData | string | no | Max 4096 chars | WeChat encrypted user info |
| iv | string | no | Max 256 chars | AES decryption initialization vector |
| promoterCode | string | no | Length 6-32 | Optional promoter invitation code on first login |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJhbGciOi...",
    "refreshToken": "eyJhbGciOi...",
    "expiresIn": 7200,
    "tokenType": "Bearer",
    "user": {
      "userId": "u_abc123",
      "openId": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
      "unionId": "uXXXXXXXXXXXXXXXXXXXXXXXXXXX",
      "nickname": "用户昵称",
      "avatarUrl": "https://example.com/avatars/xxx.png",
      "phone": "138****1234",
      "role": "promoter",
      "isNewUser": false
    }
  },
  "requestId": "req_20260730120000001",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40001 | Invalid WeChat code (code expired or already used) | No |
| 40002 | WeChat service error, please retry | Yes |
| 40003 | Encrypted data decryption failed | No |
| 40004 | Invalid promoter code | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `code` is single-use; each WeChat `wx.login()` call produces a fresh code valid for 5 minutes.
- If `promoterCode` is supplied and valid, the binding relationship is pre-established on first login.
- `isNewUser: true` means no profile record exists yet — the client should guide through onboarding.
- Access token expires in `expiresIn` seconds; use the refresh endpoint before expiry.

---

## Admin Account+Password Login

**Method**: POST
**Path**: /api/v1/auth/admin-login
**Auth**: Not required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| account | string | yes | Length 4-64 | Admin account name |
| password | string | yes | Length 8-128 | Password (cleartext; hashed server-side) |
| captchaToken | string | no | Max 1024 chars | CAPTCHA verify token (required after 3rd failed attempt) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJhbGciOi...",
    "refreshToken": "eyJhbGciOi...",
    "expiresIn": 7200,
    "tokenType": "Bearer",
    "user": {
      "userId": "u_def456",
      "account": "admin001",
      "displayName": "管理员张三",
      "role": "admin",
      "permissions": ["qualification.review", "binding.transfer", "admin.accounts.read"],
      "orgNodeId": "org_001",
      "orgNodeName": "北京总部"
    }
  },
  "requestId": "req_20260730120000002",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40101 | Invalid account or password | No |
| 40102 | Account is disabled, contact administrator | No |
| 40103 | Account locked due to too many failed attempts (retry after 15 minutes) | No |
| 40104 | CAPTCHA verification required | No |
| 40105 | CAPTCHA verification failed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- After 3 consecutive failed login attempts, `captchaToken` becomes required. The account locks for 15 minutes after 5 failed attempts, returning `40103`.
- Successful login resets the failure counter.
- Password must be hashed with bcrypt (cost factor >= 12) before storage; never log or return the plaintext password.

---

## Bind WeChat Phone

**Method**: POST
**Path**: /api/v1/auth/phone-bind
**Auth**: Required (Bearer token)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| code | string | yes | Length 1-256 | WeChat phone number auth code (from `<button open-type="getPhoneNumber">`) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "phone": "138****1234"
  },
  "requestId": "req_20260730120000003",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40005 | Invalid phone auth code | No |
| 40006 | Phone already bound to another account | No |
| 50001 | Internal server error | Yes |

### Business Rules
- A phone number can be bound to at most one account. Attempting to bind an already-claimed phone returns `40006`.
- After successful binding, the user's `phone` field is updated in profile.

---

## Current Session

**Method**: GET
**Path**: /api/v1/auth/session
**Auth**: Required (Bearer token)
**Idempotency**: Not applicable

### Query Parameters
None.

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": {
      "userId": "u_abc123",
      "openId": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
      "unionId": "uXXXXXXXXXXXXXXXXXXXXXXXXXXX",
      "nickname": "用户昵称",
      "avatarUrl": "https://example.com/avatars/xxx.png",
      "phone": "138****1234",
      "role": "promoter",
      "orgNodeId": "org_002",
      "orgNodeName": "华东大区"
    },
    "tokenExpiresAt": "2026-07-30T14:00:00+08:00",
    "permissions": ["binding.submit", "customer.read", "contribution.read"]
  },
  "requestId": "req_20260730120000004",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40100 | Token expired | No |
| 40101 | Token invalid or malformed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the validity status of the current access token. If the token is expired, the client should use the refresh endpoint.
- `tokenExpiresAt` uses ISO 8601 with timezone.

---

## Refresh Tokens

**Method**: POST
**Path**: /api/v1/auth/refresh
**Auth**: Not required (uses refresh token in body)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| refreshToken | string | yes | Length 1-2048 | Refresh token received during login |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJhbGciOi...",
    "refreshToken": "eyJhbGciOi...",
    "expiresIn": 7200,
    "tokenType": "Bearer"
  },
  "requestId": "req_20260730120000005",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40106 | Refresh token expired, please re-login | No |
| 40107 | Refresh token revoked | No |
| 40101 | Token invalid or malformed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Access token lifetime: 2 hours. Refresh token lifetime: 30 days.
- Each refresh rotates both tokens: the old refresh token is invalidated and a new pair is issued.
- A refresh token that has been revoked (e.g., after password change or admin action) returns `40107`.

---

## Logout

**Method**: POST
**Path**: /api/v1/auth/logout
**Auth**: Required (Bearer token)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
None.

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": null,
  "requestId": "req_20260730120000006",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40100 | Token expired | No |
| 40101 | Token invalid or malformed | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Invalidates the current access token and its associated refresh token server-side.
- Subsequent requests with the same token will receive `40107` (token revoked).
- Idempotent: calling logout multiple times returns success (no error for already-invalidated tokens).
