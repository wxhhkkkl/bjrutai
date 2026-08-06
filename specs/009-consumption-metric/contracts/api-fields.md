# 业绩相关 API 字段变更契约（009）

统一响应包 `{code, message, data, requestId, serverTime}`（`code=0` 成功）。金额字段统一为**整数分**（`*AmountCent`），前端展示为元。URL 路径全部保留，仅响应字段/语义变化（FR-007）。

> 说明：本契约记录「业绩贡献 → 消费金额」的字段变更。所有端点均有对应 contract 测试同步（`test_contributions.py`、`test_admin_contribution_dashboard.py`、`test_org_performance.py` 等）。

## 1. 推广员消费业绩（/api/v1/contributions）

### GET /api/v1/contributions/overview

**Query**: `month` (YYYY-MM, 必填)

**Response data**:
```json
{
  "monthlyAmountCent": 125000,
  "totalAmountCent": 860000,
  "growthRate": 12.5
}
```
`growthRate` 为环比月增长（%），上月无消费时为 `null`。
**变更**：旧 `{total, count, breakdown}`（贡献值+分类构成）→ 新 `{monthlyAmountCent, totalAmountCent, growthRate}`。

### GET /api/v1/contributions/trend

**Query**: `period`（默认 `6m`，支持 `3m/6m/12m/24m`）

**Response data**:
```json
{ "categories": ["2026-03", "2026-04"], "values": [0, 125000] }
```
**变更**：旧返回贡献值月度趋势 → 新返回消费金额（分）趋势。

### GET /api/v1/contributions（列表）

**Query**: `month`?, `status`?, `cursor`?, `pageSize`（默认 20，max 100）

**Response data**:
```json
{
  "items": [
    {"id": 1, "title": "txn_abc", "amountCent": 120000, "status": "PAID", "occurredAt": "...", "customerName": "王女士"}
  ],
  "nextCursor": "42", "hasMore": false
}
```
`status` 过滤值 = 账单 `transaction_status`（`PAID`/`PARTIALLY_REFUNDED`/...）。`category` 过滤已移除。
**变更**：旧贡献记录字段（`points`/`category`/`status` 贡献状态机）→ 新账单字段（`amountCent`/账单状态）。

### GET /api/v1/contributions/{bill_id}（明细）

**Response data**:
```json
{
  "id": 1, "title": "txn_abc", "amountCent": 120000,
  "status": "PAID", "occurredAt": "...", "customerName": "王女士",
  "refundAmountCent": 0
}
```
**变更**：路径参数由 `contribution_id` 改为 `bill_id`；返回账单明细。

### 已移除端点

- `GET /api/v1/contributions/composition`（分类构成，随贡献值概念删除）。

## 2. 管理后台消费业绩（/api/v1/admin/contributions，URL 不变）

### GET /api/v1/admin/contributions/dashboard

**Query**: `month` (YYYY-MM), `period`（默认 `12m`）, `orgId`?

**Response data**:
```json
{
  "stats": {"monthlyAmountCent": 5000000, "totalAmountCent": 86000000, "orgCount": 12, "personCount": 120, "boundUserCount": 300},
  "trend": [{"month": "2026-03", "amountCent": 3000000}],
  "latest": [
    {"id": 1, "distributorId": "101", "personName": "张三", "orgName": "总部",
     "title": "txn_abc", "amountCent": 120000, "status": "PAID", "occurredAt": "..."}
  ]
}
```
**变更**：`stats.monthlyPoints/totalPoints` → `monthlyAmountCent/totalAmountCent`；`trend[].points` → `amountCent`；`latest[].points` → `amountCent`；`latest[].category` 移除；`latest[].title` 由贡献标题改为账单 `transaction_id`。

### GET /api/v1/admin/contributions/rankings/orgs|persons|bindings

**Query**: `month` (YYYY-MM), `orgId`?, `page`?, `pageSize`?

**Response data**: 排名项数值字段 `points` → `amountCent`（orgs/persons）；bindings 排名仍按绑定数（不变）。
**变更**：组织/个人排名的业绩数值从贡献值改为消费金额（分）。

## 3. 工作台（/api/v1/workbench）

### GET /api/v1/workbench（指标）

**变更**：`metrics.myMonthlyContribution` → `metrics.myMonthlyConsumption`（本人当月消费金额，分）。

### GET /api/v1/workbench/contribution-summary（URL 保留）

**Query**: `month`?

**Response data**（管理员=全系统，分销员=本人）:
```json
{ "month": "2026-08", "totalAmountCent": 5000000, "count": 320 }
```
**变更**：旧 `{total, count, breakdown}`（贡献值+分类构成）→ 新 `{month, totalAmountCent, count}`；`breakdown` 移除。

## 4. 客户（/api/v1/customers）

### GET /api/v1/customers/{customer_id}/detail

**变更**：
- `monthlyContribution` / `monthlyContributionCount` / `totalContribution` → `monthlyConsumptionCent` / `totalConsumptionCent`（本月/累计消费金额，分）。

### GET /api/v1/customers/{customer_id}/contributions（URL 保留）

**Response data**:
```json
{
  "items": [
    {"id": 1, "title": "txn_abc", "amountCent": 120000, "status": "PAID", "occurredAt": "..."}
  ],
  "nextCursor": "42", "hasMore": false
}
```
**变更**：旧贡献记录字段（`points`/`category`/`settledAt`）→ 新账单字段（`amountCent`/账单状态）。

## 5. 组织绩效（/api/v1/org/performance，小程序）

**变更**：`summary.thisMonth` / `summary.cumulative` 及成员/下级组织的 `thisMonth`/`cumulative` 由字符串贡献值改为**整数分**消费金额（`OrgMemberPerformance.this_month: int`）。前端 `fmtYuan()` 展示为元。
