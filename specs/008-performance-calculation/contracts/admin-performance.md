# Admin Performance API Contracts

管理后台「绩效计算」相关接口。统一响应包 `{code, message, data, requestId, serverTime}`（`code=0` 成功）。权限：估算/明细查看 `sharing_rules.read`；审核/打回/重算/导出 `performance.settle`（FR-014）。

## GET /api/v1/admin/performance/estimates

管理端当月/指定月绩效估算（实时，不落库），按选中组织返回。

**Query**: `period` (YYYY-MM, 必填), `orgId` (int, 可选，默认根组织)

**Response data**:
```json
{
  "orgId": "12",
  "period": "2026-08",
  "intraOrg": [
    {"distributorId": "101", "name": "张三", "baseCent": 800000, "ratio": 0.05, "commissionCent": 40000}
  ],
  "orgManagement": [
    {"distributorId": "202", "name": "李四", "baseCent": 5000000, "ratio": 0.08, "commissionCent": 400000}
  ],
  "unconfigured": []
}
```
金额单位：分（cents）。`unconfigured` 列出未配置的规则类型（`intra_org` / `org_management`）。

## GET /api/v1/admin/performance/settlements

查询某周期的结算批次状态（含历史周期）。

**Query**: `period` (YYYY-MM, 可选；不传返回各周期状态列表)

**Response data**:
```json
{
  "items": [
    {"period": "2026-08", "status": "pending", "reviewedBy": null, "reviewedAt": null, "rejectReason": null}
  ]
}
```

## GET /api/v1/admin/commission-results（复用既有端点，不新增）

月度核算明细查询复用既有 `GET /api/v1/admin/commission-results`（006，支持 `period` + `orgId` 组织子树过滤 + 分页）。不新增重复端点。

## POST /api/v1/admin/performance/settlements/{period}/review

审核确认某月（整体确认，FR-012）。仅 `pending` 可确认。

**Response data**: `{"period": "2026-08", "status": "reviewed", "reviewedBy": 1, "reviewedAt": "..."}`

**错误**：已确认/不存在/非法状态 → 业务错误（含 `code` 非 0，message 明确）。

## POST /api/v1/admin/performance/settlements/{period}/reject

打回某月（FR-013）。仅 `pending` 可打回，`reason` 必填。

**Request**:
```json
{"reason": "核对发现金额有误，需重新核算"}
```
**Response data**: `{"period": "2026-08", "status": "rejected", "reviewedBy": 1, "reviewedAt": "...", "rejectReason": "..."}`

## POST /api/v1/admin/performance/settlements/{period}/recompute

手动重算某月（FR-008）。仅 `pending` / `rejected` 可重算；`reviewed` 拒绝（冻结）。重算后 `rejected → pending`。

**Response data**: `{"period": "2026-08", "status": "pending", "computed": 120}`

## GET /api/v1/admin/performance/settlements/{period}/export

导出某月核算明细（CSV 表格文件，FR-010）。

**Query**: `orgId` (可选，组织子树过滤)

**Response**: `text/csv; charset=utf-8`，附件下载。列：`period, orgId, orgName, distributorId, name, ruleType, baseCent, ratio, commissionCent, computedAt`。无数据时返回 204 或空表（前端提示）。
