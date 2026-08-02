# Organization API Contracts（后台组织树管理）

`/api/v1/admin/orgs/`。统一响应封装：`{ code, message, data, requestId, serverTime }`。所有接口需管理员会话并具备 `org:manage` 权限（除公开查询）。取代现有 `/admin/hierarchy` 接口。

---

## 获取组织树

**Method**: GET
**Path**: /api/v1/admin/orgs
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| orgType | string | no | Max 50 chars | 按组织类型筛选 |
| keyword | string | no | Max 100 chars | 按名称搜索 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "tree": [
      {
        "orgId": "org_1001",
        "name": "北京儒泰总部",
        "orgType": "headquarters",
        "level": 1,
        "parentId": null,
        "sortOrder": 0,
        "status": "active",
        "children": [
          {
            "orgId": "org_1002",
            "name": "华北区",
            "orgType": "region",
            "level": 2,
            "parentId": "org_1001",
            "sortOrder": 1,
            "status": "active",
            "children": []
          }
        ]
      }
    ]
  },
  "requestId": "req_20260802130000001",
  "serverTime": "2026-08-02T13:00:00+08:00"
}
```

---

## 创建组织节点

**Method**: POST
**Path**: /api/v1/admin/orgs
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | yes | Length 1-128 | 组织名称 |
| parentId | string | no | 组织 ID | 上级组织；缺省为根组织 |
| orgType | string | yes | Max 50 chars | 组织类型（后台配置） |
| sortOrder | integer | no | Default 0 | 同级排序 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "orgId": "org_1003",
    "name": "华东区",
    "orgType": "region",
    "level": 2,
    "parentId": "org_1001",
    "sortOrder": 2,
    "status": "active"
  },
  "requestId": "req_20260802130500001",
  "serverTime": "2026-08-02T13:05:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40401 | 上级组织不存在 | No |
| 40901 | 组织层级超过最大深度限制 | No |

### Business Rules
- 新建节点自动计算 `level`；若后台配置了最大深度且超限，返回 40901。
- 记录操作日志（FR-004）。

---

## 编辑组织节点

**Method**: PUT
**Path**: /api/v1/admin/orgs/{orgId}
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | no | Length 1-128 | 新名称 |
| orgType | string | no | Max 50 chars | 新类型 |
| sortOrder | integer | no | - | 新排序 |
| status | string | no | Enum: `active`, `disabled` | 停用/启用 |

### Response (Success)
```json
{ "code": 0, "message": "success", "data": { "orgId": "org_1002", "name": "华北一区", "orgType": "region", "status": "active" }, "requestId": "req_x", "serverTime": "2026-08-02T13:10:00+08:00" }
```

---

## 删除组织节点

**Method**: DELETE
**Path**: /api/v1/admin/orgs/{orgId}
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Response (Success)
```json
{ "code": 0, "message": "success", "data": null, "requestId": "req_x", "serverTime": "2026-08-02T13:15:00+08:00" }
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40902 | 该组织下仍有分销员或下级组织，无法删除 | No |

### Business Rules
- 组织下有分销员或子组织时拒绝删除并引导处理（US1-AC5）。
- 记录操作日志（FR-004）。

---

## 迁移组织子树

**Method**: POST
**Path**: /api/v1/admin/orgs/{orgId}/migrate
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| newParentId | string | no | 组织 ID | 新上级；缺省为根 |
| newSortOrder | integer | no | - | 新排序 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": { "orgId": "org_1002", "level": 2, "parentId": "org_1005" },
  "requestId": "req_x",
  "serverTime": "2026-08-02T13:20:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40903 | 组织关系不允许形成闭环 | No |
| 40901 | 组织层级超过最大深度限制 | No |

### Business Rules
- 迁移含整个子树；递归更新子树的 `level`（FR-002）。
- 环路检测（目标为自身或自身后代时拒绝，FR-003）；组织管理员授权随组织迁移（US4-AC5）。
- 记录迁移操作日志（FR-004）。

---

## 组织操作历史

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/history
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      { "action": "moved", "operator": "admin001", "from": "org_1001", "to": "org_1005", "at": "2026-08-02T13:20:00+08:00" }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-02T13:21:00+08:00"
}
```

### Business Rules
- 返回该组织的创建/编辑/迁移/删除操作记录（FR-004）。
