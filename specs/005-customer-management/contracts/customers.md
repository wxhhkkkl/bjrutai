# 后台客户管理 API Contracts

`/api/v1/admin/customers/`。统一响应封装：`{ code, message, data, requestId, serverTime }`。所有接口需管理员会话；读操作需 `customers.read`，写操作需 `customers.write`（`require_permission`）。

取代旧的"绑定管理"页面所用接口。`/admin/bindings` 的 `unbind`/`transfer` 端点随解绑移除与转移迁移而删除。

**脱敏约定**: 身份证/医保账户/手机号在所有响应中一律脱敏展示（如 `110***********1234`、`138****1234`），后端不提供明文响应。存储为明文（spec 澄清 Q1）。

---

## 组织维度客户列表

**Method**: GET
**Path**: /api/v1/admin/customers
**Auth**: Required (admin, `customers.read`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| orgId | string | yes | 组织 ID | 选中组织；返回该组织及全部下级组织范围（子树）客户 |
| status | string | no | Enum: `bound`, `pending`, `unbound` | 按绑定状态筛选 |
| keyword | string | no | Max 100 chars | 按姓名/手机号搜索 |
| page | integer | no | Default 1, ≥1 | 页码 |
| pageSize | integer | no | Default 20, 1-100 | 每页条数 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "12",
        "name": "张伟",
        "phoneMasked": "138****1234",
        "idCardMasked": "110***********1234",
        "bindingStatus": "bound",
        "distributorId": "3",
        "promoterName": "李丽",
        "orgId": "4",
        "orgName": "石家庄",
        "note": null,
        "updatedAt": "2026-08-03T10:00:00+08:00"
      }
    ],
    "total": 5,
    "page": 1,
    "pageSize": 20,
    "hasMore": false
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:01:00+08:00"
}
```

### Business Rules
- `orgId` 必填；客户所属组织由推广员（分销员）所属组织推导，`orgId` 范围取该组织子树（FR-003）。
- 多根森林：`orgId` 为任一根/节点，不支持跨根聚合（切换根由前端控制）。

---

## 手工录入客户

**Method**: POST
**Path**: /api/v1/admin/customers
**Auth**: Required (admin, `customers.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | yes | Length 1-100 | 客户姓名 |
| phone | string | yes | 7-20 chars | 手机号 |
| idCard | string | yes | 18 chars | 身份证号（唯一） |
| medicalAccount | string | no | Max 64 chars | 医保账户 |
| familyPhone | string | no | Max 20 chars | 家属电话 |
| note | string | no | Max 500 chars | 备注 |
| distributorId | string | yes | 分销员 ID | 初始推广员（当前组织及子树下分销员） |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "13",
    "name": "王芳",
    "phoneMasked": "139****5678",
    "idCardMasked": "210***********4321",
    "bindingStatus": "bound",
    "distributorId": "3",
    "promoterName": "李丽",
    "orgId": "4",
    "orgName": "石家庄",
    "rutaiUserId": "hrb_mock_101",
    "boundAt": "2026-08-03T10:05:00+08:00",
    "matchResult": { "matched": true, "failureReason": null }
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:05:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40000 | 姓名/手机号/身份证号为必填项 | No |
| 40900 | 该身份证号已建档 | No |
| 40020 | 推广员不存在或不可开展业务 | No |
| 40000 | 身份证号格式不正确 | No |

### Business Rules
- 创建客户后**立即调用哈尔滨互联网医院接口**尝试绑定匹配（FR-008）：`matched` → `bindingStatus=bound` + `rutaiUserId` + `boundAt`；否则 `bindingStatus=pending`，失败原因写入关联 `BindingRequest.failure_reason`，**建档不阻断**（医院接口异常仍建档）。
- 生成 `customer_change_logs`（operation=created，记录初始推广员）。
- 身份证号唯一查重（FR-007）。

---

## 客户详情

**Method**: GET
**Path**: /api/v1/admin/customers/{id}
**Auth**: Required (admin, `customers.read`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "13",
    "name": "王芳",
    "phoneMasked": "139****5678",
    "idCardMasked": "210***********4321",
    "medicalAccountMasked": "2301******5678",
    "familyPhone": "010-88886666",
    "bindingStatus": "bound",
    "rutaiUserId": "hrb_mock_101",
    "boundAt": "2026-08-03T10:05:00+08:00",
    "distributorId": "3",
    "promoterName": "李丽",
    "orgId": "4",
    "orgName": "石家庄",
    "note": "高血压随访",
    "serviceCount": 0,
    "followupCount": 0,
    "createdAt": "2026-08-03T10:05:00+08:00",
    "updatedAt": "2026-08-03T10:05:00+08:00"
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:06:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | 客户不存在 | No |

---

## 编辑客户（含敏感字段）

**Method**: PATCH
**Path**: /api/v1/admin/customers/{id}
**Auth**: Required (admin, `customers.write`)
**Idempotency**: Not applicable

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| name | string | no | Length 1-100 | 姓名 |
| phone | string | no | 7-20 chars | 手机号（敏感） |
| idCard | string | no | 18 chars | 身份证号（敏感） |
| medicalAccount | string | no | Max 64 chars | 医保账户（敏感） |
| familyPhone | string | no | Max 20 chars | 家属电话 |
| note | string | no | Max 500 chars | 备注 |
| changeReason | string | **条件必填** | Max 500 chars | 修改任一敏感字段（phone/idCard/medicalAccount）时必须填写 |

### Response (Success)
```json
{ "code": 0, "message": "success", "data": { "id": "13", "name": "王芳", "phoneMasked": "139****5678", "idCardMasked": "210***********4321", "updatedAt": "2026-08-03T11:00:00+08:00" }, "requestId": "req_x", "serverTime": "2026-08-03T11:00:00+08:00" }
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40000 | 修改敏感字段必须填写修改原因 | No |
| 40900 | 该身份证号已建档 | No |

### Business Rules
- 敏感字段（phone/idCard/medicalAccount）修改必须携带 `changeReason`，否则拒绝（FR-010）。
- 修改敏感字段写入 `AuditLog`（action=`update_customer_sensitive`，detail 含字段与原因）。
- 修改 `idCard` 后需同步刷新 `idCardMasked`；若身份证变化需重新做唯一查重。

---

## 更改客户推广员

**Method**: POST
**Path**: /api/v1/admin/customers/{id}/transfer
**Auth**: Required (admin, `customers.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| newDistributorId | string | yes | 分销员 ID | 新推广员 |
| reason | string | yes | Max 500 chars | 变更原因 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "customerId": "13",
    "previousDistributorId": "3",
    "previousPromoterName": "李丽",
    "newDistributorId": "6",
    "newPromoterName": "赵强",
    "transferredAt": "2026-08-03T11:30:00+08:00"
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T11:30:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40020 | 新推广员不存在或不可开展业务 | No |
| 40000 | 不能更改为当前推广员 | No |
| 40400 | 客户不存在 | No |

### Business Rules
- 目标推广员必须存在且 `is_distributor_selectable`（组织资质已通过且未停用），否则拒绝（FR-011）。
- 生成 `customer_change_logs`（operation=transfer）+ `AuditLog`；完整记录操作人/时间/变更前后推广员/原因（FR-012）。
- **不改变**客户 `bindingStatus`（推广员变更不影响医院绑定状态）。

---

## 推广员变更记录

**Method**: GET
**Path**: /api/v1/admin/customers/{id}/change-logs
**Auth**: Required (admin, `customers.read`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "7",
        "operationType": "transfer",
        "previousDistributorId": "3",
        "previousPromoterName": "李丽",
        "newDistributorId": "6",
        "newPromoterName": "赵强",
        "operatorName": "admin001",
        "reason": "客户区域调整",
        "createdAt": "2026-08-03T11:30:00+08:00"
      },
      {
        "id": "5",
        "operationType": "created",
        "previousDistributorId": null,
        "newDistributorId": "3",
        "newPromoterName": "李丽",
        "operatorName": "admin001",
        "reason": "手工录入建档",
        "createdAt": "2026-08-03T10:05:00+08:00"
      }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T11:31:00+08:00"
}
```

### Business Rules
- 返回该客户全部推广员变更记录（created/transfer），按时间倒序（FR-012）。

---

## 关联变更（非新增端点）

### 分销员端绑定流程去重（修改既有行为）
- `POST /api/v1/bindings`（`binding_service.submit_binding_request`）：医院匹配成功后，先按 `Customer.id_card_encrypted == id_card` 查重。
  - 已存在 → 复用/更新该档案（`binding_status=bound`、`rutai_user_id`、`bound_at`；若 `distributor_id` 变化则更新并写 `customer_change_logs`(transfer)），**不新建**（FR-007）。
  - 不存在 → 新建（现状不变）。

### 已移除接口
- `POST /api/v1/admin/bindings/{id}/unbind`（解绑移除，spec 澄清 Q2）
- `POST /api/v1/admin/bindings/{id}/transfer`（转移迁移至 `/admin/customers/{id}/transfer`）
