# Auth API Contracts（变更）

`/api/v1/auth/` 下新增分销员账密登录与微信绑定。统一响应封装：`{ code, message, data, requestId, serverTime }`。现有微信授权登录 `/auth/wechat-login` 保留（已绑定用户快速登录）。

---

## 分销员手机号+密码登录

**Method**: POST
**Path**: /api/v1/auth/distributor-login
**Auth**: Not required
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| phone | string | yes | 11 digits | 分销员手机号（登录标识） |
| password | string | yes | Length 8-128 | 密码（明文传输，服务端哈希校验） |

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
    "requiresWechatBinding": true,
    "distributor": {
      "distributorId": "d_1001",
      "orgId": "org_1001",
      "orgName": "北京儒泰华北区",
      "orgRole": "member",
      "name": "张三",
      "phone": "138****1234",
      "status": "active"
    }
  },
  "requestId": "req_20260802120000001",
  "serverTime": "2026-08-02T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40101 | 手机号或密码错误 | No |
| 40102 | 账号已停用 | No |
| 40103 | 连续失败次数超限，账号已锁定 | No |
| 50001 | 服务器内部错误 | Yes |

### Business Rules
- 连续 5 次密码错误锁定 15 分钟（沿用后台账号锁定策略）。
- `requiresWechatBinding: true` 表示该分销员尚未绑定微信，客户端必须引导完成微信绑定后方可进入主流程（FR-027）。
- 已停用（`disabled`）分销员登录被拒绝（FR-011）。

---

## 首次登录绑定微信

**Method**: POST
**Path**: /api/v1/auth/bind-wechat
**Auth**: Required (distributor access token, pending binding state)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| code | string | yes | Length 1-256 | WeChat `wx.login()` code |
| encryptedData | string | no | Max 4096 chars | WeChat 加密用户信息 |
| iv | string | no | Max 256 chars | AES 解密向量 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "bound": true,
    "openId": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "accessToken": "eyJhbGciOi...",
    "refreshToken": "eyJhbGciOi..."
  },
  "requestId": "req_20260802121000001",
  "serverTime": "2026-08-02T12:10:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40001 | 无效的微信 code | No |
| 40005 | 该微信已绑定其他分销员账户 | No |
| 50001 | 服务器内部错误 | Yes |

### Business Rules
- 绑定后 `users.openid` 写入，此后可经 `/auth/wechat-login` 快速登录（FR-027）。
- 一个微信 openid 至多绑定一个分销员账户（`users.openid` UNIQUE）。
