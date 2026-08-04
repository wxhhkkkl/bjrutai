# 绩效规则 API Contracts

`/api/v1/admin/`。统一响应封装：`{ code, message, data, requestId, serverTime }`。所有接口需管理员会话；读操作需 `sharing_rules.read`，写操作需 `sharing_rules.write`（沿用现有权限点，未改名为 `performance.*`）。

取代旧 `/admin/sharing-rules`（按层级）接口。金额字段一律以**分**（整数）传输。

---

## 获取组织绩效提成方式

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/performance-rules
**Auth**: Required (admin, `sharing_rules.read`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "orgId": "4",
    "intraOrg": {
      "ruleId": "1",
      "ruleType": "intra_org",
      "tiers": [
        { "minCent": 0, "maxCent": 1000000, "ratio": 0.05 },
        { "minCent": 1000000, "maxCent": null, "ratio": 0.08 }
      ],
      "status": "active",
      "version": 2,
      "updatedAt": "2026-08-03T10:00:00+08:00"
    },
    "orgManagement": null,
    "summary": {
      "intraOrgConfigured": true,
      "orgManagementConfigured": false
    }
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:01:00+08:00"
}
```

### Business Rules
- `intraOrg` / `orgManagement` 为 null 表示该组织未配置对应方式（US1-AC4）。
- 只返回当前生效（`active`）的一条。

---

## 保存绩效提成方式

**Method**: PUT
**Path**: /api/v1/admin/orgs/{orgId}/performance-rules/{ruleType}
**Auth**: Required (admin, `sharing_rules.write`)
**Idempotency**: Required (Idempotency-Key header)

`ruleType` ∈ `intra_org` | `org_management`。

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| tiers | array | yes | 1-20 项 | 阶梯列表 |
| tiers[].minCent | integer | yes | ≥0 | 区间下限（分），含 |
| tiers[].maxCent | integer/null | yes | >minCent 或 null | 区间上限（分），不含；null=上不封顶 |
| tiers[].ratio | number | yes | 0 < ratio ≤ 1 | 提成比率（小数） |

### Response (Success)
```json
{ "code": 0, "message": "success", "data": { "ruleId": "1", "ruleType": "intra_org", "tiers": [ { "minCent": 0, "maxCent": 1000000, "ratio": 0.05 }, { "minCent": 1000000, "maxCent": null, "ratio": 0.08 } ], "status": "active", "version": 3, "updatedAt": "2026-08-03T10:05:00+08:00" }, "requestId": "req_x", "serverTime": "2026-08-03T10:05:00+08:00" }
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40000 | 阶梯区间需连续覆盖任意金额，不得有空隙或重叠 | No |
| 40000 | 比率必须大于 0 且不超过 100% | No |
| 40000 | 首项阶梯下限必须为 0 / 末项阶梯上限必须为空 | No |
| 40400 | 组织不存在 | No |

### Business Rules
- 首次保存创建规则；再次保存覆盖（version +1），写入 `performance_rule_change_logs`（FR-007）。
- 阶梯校验（FR-006）：**区间连续、无空隙、无重叠——任意金额必被某个阶梯覆盖**；首项 `minCent=0`、末项 `maxCent=null`。金额在接口以**分**传输（前端配置界面以**元**展示/录入，保存时换算为分）。

---

## 应用到全部下级组织

**Method**: POST
**Path**: /api/v1/admin/orgs/{orgId}/performance-rules/{ruleType}/apply-to-descendants
**Auth**: Required (admin, `sharing_rules.write`)
**Idempotency**: Required (Idempotency-Key header)

`ruleType` ∈ `intra_org` | `org_management`。将**当前组织的该绩效提成方式**（阶梯）一键复制到其**全部下级组织**（子树，不含自身），覆盖下级已有相同配置。

### Response (Success)
```json
{ "code": 0, "message": "success", "data": { "applied": 2, "orgIds": ["3", "4"] }, "requestId": "req_x", "serverTime": "2026-08-04T10:00:00+08:00" }
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40000 | 当前组织未配置该绩效提成方式，无法应用到下级组织 | No |

### Business Rules
- 对每个下级组织执行 `_upsert_rule`（创建或覆盖，version +1，写变更日志）。
- 无下级组织时 `applied=0`。

---

## 变更历史

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/performance-rules/history
**Auth**: Required (admin, `sharing_rules.read`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      { "ruleId": "1", "ruleType": "intra_org", "changedBy": "admin001", "oldValue": { "tiers": "..." }, "newValue": { "tiers": "..." }, "createdAt": "2026-08-03T10:05:00+08:00" }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:06:00+08:00"
}
```

### Business Rules
- 返回该组织两种提成方式的全部变更记录，按时间倒序（FR-007）。

---

## 实时提成预览

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/performance-rules/preview
**Auth**: Required (admin, `sharing_rules.read`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| period | string | yes | `YYYY-MM` | 预览周期 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "orgId": "4",
    "period": "2026-07",
    "intraOrg": [
      { "distributorId": "3", "name": "李丽", "baseCent": 800000, "ratio": 0.05, "commissionCent": 40000 }
    ],
    "orgManagement": [
      { "distributorId": "1", "name": "张强", "baseCent": 2500000, "ratio": 0.08, "commissionCent": 200000 }
    ],
    "unconfigured": ["org_management"]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:07:00+08:00"
}
```

### Business Rules
- 按**当前规则**实时计算，不落库（FR-013）；与月度落库结果同口径（SC-008）。
- 未配置的提成方式在 `unconfigured` 中列出。
- **计算语义（已确认更新）**：组织管理员**同时**计算两类提成——组织内提成（自身消费金额 × 组织内阶梯）与组织管理提成（管理子树消费总额 × 组织管理阶梯）；普通成员仅组织内提成。
- 预览/月度结果接口保留于后端（供结算与对账），管理后台 UI 当前**不展示**这两个入口（已隐藏）。

---

## 月度提成结果

**Method**: GET
**Path**: /api/v1/admin/commission-results
**Auth**: Required (admin, `sharing_rules.read`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| period | string | yes | `YYYY-MM` | 结算周期 |
| orgId | string | no | 组织 ID | 按组织过滤（含子树） |
| page / pageSize | integer | no | page≥1, pageSize 1-100 | 分页 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      { "period": "2026-07", "distributorId": "3", "name": "李丽", "orgId": "4", "ruleType": "intra_org", "baseCent": 800000, "ratio": 0.05, "commissionCent": 40000, "computedAt": "2026-08-01T00:05:00+08:00" }
    ],
    "total": 12, "page": 1, "pageSize": 20, "hasMore": false
  },
  "requestId": "req_x",
  "serverTime": "2026-08-03T10:08:00+08:00"
}
```

### Business Rules
- 返回月度结算已落库的提成结果（FR-013/SC-009），按 `(period, distributor_id, rule_type)` 唯一。

---

## 关联变更（非新增端点）

### 组织管理员单一约束（修改既有行为）
- `PUT /api/v1/admin/distributors/{id}/role`（`distributor_service.set_role`）：将某成员设为组织管理员时，若该组织**已有管理员**则拒绝（40000，"该组织已有管理员，请先撤销"）；撤销不受限（FR-008）。

### 已移除接口
- `GET/POST/PUT/DELETE /admin/sharing-rules` 及 `/admin/.../coefficient`（旧按层级分成规则与分成系数，FR-010/FR-012）。
