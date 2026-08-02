# Organization Qualification API Contracts（后台组织资质）

`/api/v1/admin/orgs/{orgId}/qualifications` 与 `/api/v1/admin/org-qualifications/`。统一响应封装：`{ code, message, data, requestId, serverTime }`。查看需 `org:manage`；审核需 `qualification:review`（复用现有资质审核权限）。

---

## 组织资质列表

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/qualifications
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "qualificationId": "q_2001",
        "orgId": "org_1002",
        "legalEntityName": "北京儒泰华北区公司",
        "qualificationTypes": ["business_license", "medical_institution_permit"],
        "fileUrls": [{ "url": "https://cos.xxx/q2001.pdf", "type": "pdf", "size": 12345 }],
        "validFrom": "2026-07-01",
        "validUntil": "2027-06-30",
        "status": "approved",
        "reviewComment": null,
        "reviewedBy": "admin001",
        "reviewedAt": "2026-07-02T10:00:00+08:00",
        "createdAt": "2026-07-01T09:00:00+08:00"
      }
    ]
  },
  "requestId": "req_x",
  "serverTime": "2026-08-02T15:00:00+08:00"
}
```

### Business Rules
- 展示当前资质清单与各条状态（审核中/已通过/已驳回/即将到期/已过期）与有效期（US2-AC1）。
- 最新一条（`createdAt`）为当前有效记录。

---

## 上传组织资质

**Method**: POST
**Path**: /api/v1/admin/orgs/{orgId}/qualifications
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| legalEntityName | string | yes | Length 1-256 | 法人主体名称 |
| qualificationTypes | array[string] | yes | 1-10 items | 资质类型（`business_license` 等） |
| creditCode | string | yes | Length 18 | 统一社会信用代码 |
| fileUrls | array[object] | yes | 1-20 items | COS 文件 `{url,type,size}` |
| validFrom | date | no | - | 生效日期 |
| validUntil | date | yes | - | 到期日期 |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": { "qualificationId": "q_2002", "orgId": "org_1002", "status": "reviewing" },
  "requestId": "req_x", "serverTime": "2026-08-02T15:05:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40006 | 到期日期早于生效日期 | No |

### Business Rules
- 上传后置为"审核中"，通知有审核权限的后台账号（US2-AC2）。
- 文件沿用现有 COS 上传凭证机制（先取短时上传凭证，再提交 URL）。

---

## 审核组织资质

**Method**: POST
**Path**: /api/v1/admin/org-qualifications/{qualificationId}/review
**Auth**: Required (admin, `qualification:review`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| action | string | yes | Enum: `approve`, `reject` | 审核动作 |
| comment | string | no | Max 1000 chars | 驳回原因（`reject` 必填） |

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": { "qualificationId": "q_2002", "status": "approved" },
  "requestId": "req_x", "serverTime": "2026-08-02T15:10:00+08:00"
}
```

### Business Rules
- 审核通过：该组织及其下分销员可开展业务（组织资质即业务准入门槛，FR-008）。
- 审核驳回：暂停该组织下分销员业务，历史业绩不受影响；记录驳回原因（US2-AC3/5）。
- 审核动作记录审核人/时间/原因。

---

## 资质历史

**Method**: GET
**Path**: /api/v1/admin/orgs/{orgId}/qualifications/history
**Auth**: Required (admin, `org:manage`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0, "message": "success",
  "data": {
    "items": [
      { "qualificationId": "q_2001", "action": "reviewed", "operator": "admin001", "result": "approved", "at": "2026-07-02T10:00:00+08:00" }
    ]
  },
  "requestId": "req_x", "serverTime": "2026-08-02T15:15:00+08:00"
}
```

### Business Rules
- 可追溯每次上传/审核/驳回/续期记录与操作人（US2-AC6）。
