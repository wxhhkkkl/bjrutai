# API Contracts: 小程序注册自动挂载默认组织顶级部门

**Feature**: 012-register-default-dept
**Date**: 2026-08-08

---

## 1. POST /api/v1/auth/wechat-login (MODIFIED)

### 变更说明

在现有 `wechat-login` 响应中新增 `distributor` 字段。当新用户注册并成功自动挂载时返回 distributor 信息。

### Response (success, HTTP 200)

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJ...",
    "refreshToken": "eyJ...",
    "expiresIn": 7200,
    "tokenType": "Bearer",
    "user": {
      "userId": "42",
      "openId": "oABC123...",
      "unionId": null,
      "nickname": null,
      "avatarUrl": null,
      "phone": null,
      "role": "promoter",
      "isNewUser": true
    },
    "distributor": {
      "distributorId": "15",
      "orgId": "1",
      "orgName": "北京儒泰服务有限公司",
      "orgRole": "member",
      "sourceChannel": "wechat_register"
    }
  },
  "requestId": "abc123",
  "serverTime": "2026-08-08T10:30:00Z"
}
```

### 字段说明

| Field | Type | When Present | Description |
|-------|------|-------------|-------------|
| `distributor` | object | 新用户自动挂载成功时；已有用户返回 `null` | Distributor 信息 |
| `distributor.distributorId` | string | always in object | Distributor 记录 ID |
| `distributor.orgId` | string | always in object | 所属组织 ID |
| `distributor.orgName` | string | always in object | 所属组织名称 |
| `distributor.orgRole` | string | always in object | 组织角色：`member` |
| `distributor.sourceChannel` | string | always in object | 来源渠道：`wechat_register` |

### 向后兼容

- 已有用户（`isNewUser: false`）的响应中 **不添加** `distributor` 字段 → 前端通过判断 `result.distributor` 是否存在决定路由。
- `user.isNewUser` 保持现有语义不变。

---

## 2. POST /api/v1/auth/distributor-register (NEW)

### 说明

新增手机号+密码自主注册端点。与 `distributor-login` 分离，语义清晰。

### Request

```json
{
  "phone": "13800001111",
  "password": "password1234",
  "name": "张三"
}
```

### Validation

- `phone`: 11 位数字，必填
- `password`: 8-128 字符，必填
- `name`: 1-100 字符，可选

### Response (success, HTTP 201)

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJ...",
    "refreshToken": "eyJ...",
    "expiresIn": 7200,
    "tokenType": "Bearer",
    "user": {
      "userId": "43",
      "openId": null,
      "nickname": "张三",
      "phone": "138****1111",
      "role": "distributor",
      "isNewUser": true
    },
    "distributor": {
      "distributorId": "16",
      "orgId": "1",
      "orgName": "北京儒泰服务有限公司",
      "orgRole": "member",
      "sourceChannel": "phone_register"
    }
  },
  "requestId": "def456",
  "serverTime": "2026-08-08T10:31:00Z"
}
```

### Error Responses

| code | message | 触发条件 |
|------|---------|---------|
| 40901 | 该手机号已注册 | phone 已存在于 users 表且有关联 Distributor |
| 40001 | 密码至少 8 位 | password 长度 < 8 |
| 40002 | 请输入正确的手机号 | phone 格式不匹配 |

---

## 3. GET /api/v1/auth/session (MODIFIED)

### 变更说明

session 响应中的 `user` 对象新增 distributor 关联信息，使小程序端能获取当前用户的组织归属。

### Response (现有字段 + 新增)

```json
{
  "code": 0,
  "data": {
    "user": {
      "userId": "42",
      "openId": "oABC123...",
      "nickname": "张三",
      "phone": "138****1111",
      "role": "promoter",
      "orgNodeId": "1",
      "orgNodeName": "北京儒泰服务有限公司",
      "distributorId": "15",
      "orgRole": "member",
      "sourceChannel": "wechat_register"
    },
    "tokenExpiresAt": "2026-08-08T12:30:00+0000",
    "permissions": []
  }
}
```

### 新增字段

| Field | Type | Description |
|-------|------|-------------|
| `user.orgNodeId` | string | 所属组织节点 ID |
| `user.orgNodeName` | string | 所属组织节点名称 |
| `user.distributorId` | string | Distributor 记录 ID（无 distributor 时为 null） |
| `user.orgRole` | string | 组织角色 |
| `user.sourceChannel` | string | 来源渠道 |
