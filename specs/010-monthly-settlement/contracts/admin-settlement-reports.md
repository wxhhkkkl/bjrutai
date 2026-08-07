# Admin Settlement & Settlement-Report API Contracts

管理后台「月度核算 + 数据报表展示」相关接口。统一响应包 `{code, message, data, requestId, serverTime}`（`code=0` 成功）。

权限：
- 可核算月份查询、估算查看、核算报表记录查看/导出：`sharing_rules.read`（FR-011，澄清 Q1=B）
- 发起核算、审核确认、打回、重算：`performance.settle`（FR-011）

既有 008 端点（`GET /admin/performance/estimates`、`GET/POST /admin/performance/settlements...`、`review`/`reject`/`recompute`/`export`）不变，仅 `settle` 为新增、`settlements` 列表补充可核算月份语义。

## GET /api/v1/admin/performance/settleable-periods

可核算月份列表（FR-002）：有账单业务数据、非未来月、且非 `pending/reviewed` 的月份（`rejected` 含在内）。用于绩效计算页月份选择器。

**权限**: `sharing_rules.read`

**Response data**:
```json
{
  "periods": ["2026-06", "2026-07"]
}
```
- 升序返回。
- 若系统无任何账单数据，返回空数组。

## POST /api/v1/admin/performance/settlements/{period}/settle

对某可核算月份**发起核算**（FR-001/FR-002）。仅允许 `period` 属于 `settleable-periods`（无核算记录或已打回）；`pending`/`reviewed`/未来月返回业务错误。核算成功后该月进入 `pending`，并自动生成/更新该月核算报表记录（FR-005）。

**权限**: `performance.settle`

**Response data**:
```json
{
  "period": "2026-07",
  "status": "pending",
  "computed": 120
}
```

**错误**：
- 非可核算月份（已待审核/已冻结/未来月） → 业务错误 `code != 0`，message 明确（如"该月已核算，待审核中"/"该月已冻结，不可重复核算"）。

## 既有审核/打回/重算端点（008，复用）

- `POST /admin/performance/settlements/{period}/review` — 审核确认 → `reviewed`（冻结），同步报表记录状态。
- `POST /admin/performance/settlements/{period}/reject` — 打回（`reason` 必填）→ `rejected`，同步报表记录状态。
- `POST /admin/performance/settlements/{period}/recompute` — 重算（`pending`/`rejected` 允许）→ 回到 `pending`，同步报表记录状态。

## 核算报表记录（数据报表，reports）

核算成功后自动生成一条 `source='performance_settlement'` 的报表记录，出现在既有 `GET /reports` 历史列表，状态标记随之流转（待审核 → 已确认/已打回）。

### GET /api/v1/reports（列表，扩展字段）

既有 `GET /reports` 返回列表项，新增 `source/period/status`：

```json
{
  "items": [
    {
      "reportId": "abc123...",
      "dateRange": {"startDate": "2026-07-01", "endDate": "2026-07-31"},
      "dimensions": ["performance"],
      "generatedAt": "2026-08-07T10:00:00Z",
      "generatedBy": "User 1",
      "source": "performance_settlement",
      "period": "2026-07",
      "status": "pending"
    }
  ]
}
```
- 对 `source='reconciliation'`（手工对账）记录，`source/period/status` 为 `source='reconciliation'`、`period=null`、`status=null`。
- **权限**: 调用者无 `sharing_rules.read` 时，列表**过滤** `source='performance_settlement'` 记录（仅返回 `reconciliation` 记录）。

### GET /api/v1/reports/{report_id}（详情）

核算来源记录的 `sections` 含 `performance` 维度（汇总+明细，与核算结果同源，FR-006）：

```json
{
  "reportId": "abc123...",
  "dateRange": {"startDate": "2026-07-01", "endDate": "2026-07-31"},
  "dimensions": ["performance"],
  "sections": {
    "performance": {
      "title": "绩效核算",
      "summary": {"周期": "2026-07", "状态": "待审核", "核算人数": 8, "提成总额(元)": 1250.00, "组织数": 2},
      "details": [
        {"组织": "北京儒泰总部", "姓名": "张三", "提成类型": "组织内提成", "计算基数(元)": 8000.00, "比例": "0.05", "提成金额(元)": 400.00}
      ]
    }
  },
  "source": "performance_settlement",
  "period": "2026-07",
  "status": "pending",
  "generatedAt": "2026-08-07T10:00:00Z"
}
```
- **权限**: `source='performance_settlement'` 且调用者无 `sharing_rules.read` → 403。

### GET /api/v1/reports/{report_id}/export（导出）

核算来源记录导出为 Excel，含「绩效核算」sheet（汇总+明细，FR-012）。权限同上（无 `sharing_rules.read` → 403）。

## 导出路径说明

- 绩效计算页（008）：`GET /admin/performance/settlements/{period}/export` 导出该月核算明细 **CSV**，保持不变。
- 数据报表（本需求，FR-012）：核算报表记录经 `GET /reports/{id}/export` 导出 **Excel**（含「绩效核算」sheet）。
- 两者数据同源（`commission_results`），格式不同、入口不同，互不替代。

## 权限标签

| 权限点 | 作用 |
|--------|------|
| `sharing_rules.read` | 查看估算、查询可核算月份、查看/导出核算报表记录 |
| `performance.settle` | 发起核算、审核确认、打回、重算 |
