# Org Performance API Contracts（小程序组织管理员业绩视图）

`/api/v1/org/` 下组织业绩接口，供**组织管理员**在小程序查看。统一响应封装：`{ code, message, data, requestId, serverTime }`。

---

## 组织业绩总览（组织管理员）

**Method**: GET
**Path**: /api/v1/org/performance
**Auth**: Required (distributor, `org_role = admin`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| month | string | no | `YYYY-MM` | 指定月份；缺省为当前月 |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "orgId": "org_1001",
    "orgName": "北京儒泰总部",
    "period": "2026-08",
    "summary": {
      "thisMonth": 125000.00,
      "cumulative": 860000.00
    },
    "subOrgs": [
      {
        "orgId": "org_1002",
        "orgName": "华北区",
        "thisMonth": 52000.00,
        "cumulative": 310000.00
      }
    ],
    "members": [
      {
        "distributorId": "d_1001",
        "orgId": "org_1002",
        "name": "张三",
        "thisMonth": 23000.00,
        "cumulative": 150000.00
      }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-02T16:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40301 | 当前账号非组织管理员，无权限查看 | No |
| 50002 | 组织业绩数据聚合失败 | Yes |

### Business Rules
- 仅组织管理员（`org_role=admin`）可访问；普通分销员返回 40301（FR-016）。
- 可见范围 = 授权组织及其全部下级组织（整个子树），任何子树外数据一律不可见（FR-016 / SC-007）。
- 返回组织汇总 + 各下级组织汇总 + 树内各分销员贡献值（本月/累计），**不含客户级明细**（FR-015）。
- 只显示贡献值数值，不显示金额（US5-AC2）。
- 聚合数据与个人贡献值同源，同一时段数值一致（FR-017 / SC-006）。
- 授权被撤销后该接口对分销员返回 40301（FR-014）。
