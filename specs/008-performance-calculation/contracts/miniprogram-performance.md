# Mini-Program Performance API Contracts

小程序端绩效展示接口。统一响应包。鉴权：`Bearer` access token（`get_current_user`）。仅返回**提成金额明细**（不含业绩贡献值，FR-009）。

## GET /api/v1/my/performance/commission

推广员本人绩效：当月预估（实时）+ 历史已确认月份（冻结）。

**Query**: `month` (YYYY-MM, 可选；默认当前月为预估月)

**Response data**:
```json
{
  "currentMonth": {
    "month": "2026-08",
    "status": "estimate",
    "intraOrg": {"baseCent": 800000, "ratio": 0.05, "commissionCent": 40000},
    "orgManagement": null
  },
  "confirmed": [
    {"month": "2026-07", "status": "confirmed",
     "intraOrg": {"baseCent": 750000, "ratio": 0.05, "commissionCent": 37500},
     "orgManagement": null}
  ]
}
```
- 推广员是组织管理员时 `orgManagement` 有值（子树总额对应提成）。
- `confirmed` 仅含 `performance_settlements.status=reviewed` 的月份（FR-004）。

## GET /api/v1/org/performance/commission

组织管理员所管理组织的绩效：当月预估 + 历史已确认（组织维度）。

**Query**: `month` (YYYY-MM, 可选)

**Response data**:
```json
{
  "orgId": "12",
  "orgName": "北京儒泰总部",
  "currentMonth": {
    "month": "2026-08", "status": "estimate",
    "summary": {"baseCent": 5000000, "commissionCent": 400000},
    "members": [
      {"distributorId": "101", "name": "张三", "baseCent": 800000, "ratio": 0.05, "commissionCent": 40000}
    ]
  },
  "confirmed": [
    {"month": "2026-07", "status": "confirmed",
     "summary": {"baseCent": 4600000, "commissionCent": 368000},
     "members": [
       {"distributorId": "101", "name": "张三", "baseCent": 750000, "ratio": 0.05, "commissionCent": 37500}
     ]}
  ]
}
```
- 未确认月份不作为 `confirmed` 返回。
- 权限：调用者为该组织的组织管理员（否则 403）。
