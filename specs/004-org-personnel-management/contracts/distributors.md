# Distributor API Contracts（后台分销员管理）

`/api/v1/admin/` 下分销员账户管理。统一响应封装：`{ code, message, data, requestId, serverTime }`。组织与分销员列表接口需 `org:manage` 或 `distributor:manage`；组织管理员设置接口需 `org_admin:assign`。

---

## 组织内分销员列表

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/distributors
**Auth**: Required (admin, `org:manage` 或 `distributor:manage`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| includeSubtree | boolean | no | Default false | 是否包含全部下级组织分销员 |
| role | string | no | Enum: `member`, `admin` | 按身份筛选 |
| status | string | no | Enum: `active`, `disabled` | 按状态筛选 |
| keyword | string | no | Max 100 chars | 按姓名/手机号搜索 |
| cursor | string | no | Max 256 chars | 分页游标 |
| limit | integer | no | 1-100, default 20 | 页大小 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "distributorId": "d_1001",
        "orgId": "org_1002",
        "orgName": "华北区",
        "name": "张三",
        "phone": "138****1234",
        "orgRole": "member",
        "status": "active",
        "wechatBound": true,
        "createdAt": "2026-07-01T08:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_dst_1001",
    "hasMore": false
  },
  "requestId": "req_x",
  "serverTime": "2026-08-02T14:00:00+08:00"
}
```

---

## 新建分销员账户

**Method**: POST
**Path**: /api/v1/admin/orgs/{orgId}/distributors
**Auth**: Required (admin, `distributor:manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | yes | Length 1-64 | 分销员姓名 |
| phone | string | yes | 11 digits | 手机号（登录标识，全局唯一） |
| initialPassword | string | yes | Length 8-128 | 初始密码（首登后建议修改） |
| orgRole | string | no | Enum: `member`, `admin`, default member | 初始身份（管理员设置走专用接口） |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "distributorId": "d_1002",
    "orgId": "org_1002",
    "orgName": "华北区",
    "name": "李四",
    "phone": "139****5678",
    "orgRole": "member",
    "status": "active",
    "wechatBound": false
  },
  "requestId": "req_x",
  "serverTime": "2026-08-02T14:05:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40904 | 该手机号已存在分销员账户 | No |
| 40402 | 组织不存在 | No |

### Business Rules
- 分销员账户与 `users` 关联，写入 `password_hash`；`users.phone` 唯一（FR-012）。
- 创建即归属到该组织（FR-009 / 单组织归属 FR-019）。
- 记录创建操作日志。

---

## 调整分销员归属/状态

**Method**: PUT
**Path**: /api/v1/admin/distributors/{distributorId}
**Auth**: Required (admin, `distributor:manage`)
**Idempotency**: Not applicable

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| orgId | string | no | 组织 ID | 调整所属组织（FR-010） |
| status | string | no | Enum: `active`, `disabled` | 停用/启用（FR-011） |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": { "distributorId": "d_1002", "orgId": "org_1003", "status": "active" },
  "requestId": "req_x", "serverTime": "2026-08-02T14:10:00+08:00"
}
```

### Business Rules
- 调整组织后，新业绩计入新组织（FR-010）；历史业绩归属不变。
- 停用后无法登录（FR-011）。

---

## 重置分销员登录凭证

**Method**: POST
**Path**: /api/v1/admin/distributors/{distributorId}/reset-password
**Auth**: Required (admin, `distributor:manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| newPassword | string | yes | Length 8-128 | 新密码 |

### Response (Success)
```json
{ "code": 0, "message": "success", "data": null, "requestId": "req_x", "serverTime": "2026-08-02T14:15:00+08:00" }
```

### Business Rules
- 重置后旧凭证立即失效（US3-AC5）。

---

## 设置/撤销组织管理员

**Method**: PUT
**Path**: /api/v1/admin/distributors/{distributorId}/role
**Auth**: Required (admin, `org_admin:assign`)
**Idempotency**: Not applicable

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| orgRole | string | yes | Enum: `member`, `admin` | 设置或撤销管理员身份 |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": { "distributorId": "d_1001", "orgRole": "admin" },
  "requestId": "req_x", "serverTime": "2026-08-02T14:20:00+08:00"
}
```

### Business Rules
- 仅后台管理员可执行（FR-026）。
- 设置后该分销员小程序端出现组织业绩入口；撤销后入口即时消失（FR-014）。
- 分销员仅能成为其**所属组织**的管理员（单组织归属约束）。
