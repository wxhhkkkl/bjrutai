# 业绩贡献看板 API Contracts

`/api/v1/admin/contributions/`。统一响应封装：`{ code, message, data, requestId, serverTime }`。所有接口需管理员会话 + `contributions.read` 权限。

取代管理后台对个人视角 `/contributions` 的调用（该端点为分销员个人贡献，admin 调用无效）。贡献值 `points` 在响应中以数值（数字）返回。

---

## 看板聚合（统计 + 趋势 + 最新明细）

**Method**: GET
**Path**: /api/v1/admin/contributions/dashboard
**Auth**: Required (admin, `contributions.read`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| month | string | yes | `YYYY-MM` | 统计口径月份（当月业绩/最新明细） |
| period | string | no | `6m`/`12m`/`3m` | 趋势月数，默认 `12m` |
| orgId | string | no | 组织 ID | 按组织及其子树过滤（默认全局） |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "stats": {
      "monthlyPoints": 125000.5,
      "totalPoints": 3200000,
      "orgCount": 8,
      "personCount": 23,
      "boundUserCount": 156
    },
    "trend": [
      { "month": "2025-09", "points": 98000 },
      { "month": "2025-10", "points": 105000 }
    ],
    "latest": [
      { "id": "102", "distributorId": "3", "personName": "李丽", "orgName": "石家庄", "title": "消费贡献", "category": "bill", "points": 500, "status": "confirmed", "occurredAt": "2026-07-28T10:00:00+08:00" }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-04T10:00:00+08:00"
}
```

### Business Rules
- `stats`/`trend`/`latest` 同源（SC-002/SC-006）：月度业绩 = 当月明细之和；最新明细为最近 30 条（按 `occurred_at` 倒序）。
- `orgId` 提供时统计/趋势/明细限定在该组织及子树范围内。
- **时间口径**：看板为**单月**口径（`month` 必填，默认前端取当前月份），不支持任意日期区间（已确认）。

---

## 组织当月业绩排名

**Method**: GET
**Path**: /api/v1/admin/contributions/rankings/orgs
**Auth**: Required (admin, `contributions.read`)

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| month | string | yes | `YYYY-MM` | 排名月份 |
| orgId | string | no | 组织 ID | 筛选某组织及子树；缺省=全部组织 |
| page / pageSize | integer | no | page≥1, pageSize 1-100 | 分页（默认 page 1, pageSize 20） |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": {
    "items": [
      { "rank": 1, "orgId": "4", "orgName": "石家庄", "points": 125000.5 },
      { "rank": 2, "orgId": "2", "orgName": "总部", "points": 98000 }
    ],
    "total": 8, "page": 1, "pageSize": 20, "hasMore": false
  },
  "requestId": "req_x", "serverTime": "2026-08-04T10:00:00+08:00"
}
```

### Business Rules
- 按当月贡献值从高到低；并列同 `rank`（SC-003）。
- `orgId` 缺省=全局所有组织排名；提供时=该组织及子树内的组织排名（FR-004）。

---

## 个人当月业绩排名

**Method**: GET
**Path**: /api/v1/admin/contributions/rankings/persons
**Auth**: Required (admin, `contributions.read`)

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| month | string | yes | `YYYY-MM` | 排名月份 |
| orgId | string | no | 组织 ID | 限定组织及子树内人员 |
| page / pageSize | integer | no | - | 分页 |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": {
    "items": [
      { "rank": 1, "distributorId": "3", "name": "李丽", "orgId": "4", "orgName": "石家庄", "points": 65000 },
      { "rank": 2, "distributorId": "1", "name": "张强", "orgId": "2", "orgName": "总部", "points": 50000 }
    ],
    "total": 23, "page": 1, "pageSize": 20, "hasMore": true
  },
  "requestId": "req_x", "serverTime": "2026-08-04T10:00:00+08:00"
}
```

### Business Rules
- 按当月贡献值从高到低；并列同 `rank`（SC-004）；人员按当前归属组织展示。

---

## 绑定用户数量排名

**Method**: GET
**Path**: /api/v1/admin/contributions/rankings/bindings
**Auth**: Required (admin, `contributions.read`)

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| scope | string | yes | `person` 或 `org` | 排名维度（FR-006） |
| orgId | string | no | 组织 ID | 限定范围 |
| page / pageSize | integer | no | - | 分页 |

### Response (Success) — scope=person
```json
{
  "code": 0, "message": "success",
  "data": {
    "items": [
      { "rank": 1, "distributorId": "3", "name": "李丽", "orgId": "4", "orgName": "石家庄", "boundCount": 12 },
      { "rank": 2, "distributorId": "1", "name": "张强", "orgId": "2", "orgName": "总部", "boundCount": 9 }
    ],
    "total": 23, "page": 1, "pageSize": 20, "hasMore": false
  },
  "requestId": "req_x", "serverTime": "2026-08-04T10:00:00+08:00"
}
```

### Response (Success) — scope=org
```json
{ "code": 0, "message": "success",
  "data": { "items": [ { "rank": 1, "orgId": "4", "orgName": "石家庄", "boundCount": 30 } ], "total": 8, "page": 1, "pageSize": 20, "hasMore": false },
  "requestId": "req_x", "serverTime": "2026-08-04T10:00:00+08:00" }
```

### Business Rules
- `person`：各分销员当前累计已绑定（`bound`）客户数；`org`：组织及全部下级人员的绑定客户总数（SC-005）。

---

## 关联说明

- 管理后台业绩贡献页不再调用个人视角 `/contributions/*`；小程序端分销员个人贡献继续使用 `/contributions/*`（不受影响）。
- 月度结算操作（前端触发 `/contributions/settle` 或既有结算流程）保留。
