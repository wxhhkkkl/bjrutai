# API Contracts: 意见与反馈提交及后台管理

**Feature**: 013-feedback-management  
**Base path**: `/api/v1`  
**Envelope**: 所有成功和业务错误响应均使用 `{code,message,data,requestId,serverTime}`。

## Common enums

| Concept | Wire values | Display |
|---------|-------------|---------|
| Feedback type | `bug`, `suggestion`, `other` | 功能异常、产品建议、其他 |
| Feedback status | `submitted`, `processing`, `resolved` | 待处理、处理中、已解决 |
| Notification status | `not_required`, `pending`, `sent`, `failed` | 无需发送、待发送、已发送、发送失败 |

服务端为旧客户端兼容可将输入 `feature` 归一化为 `suggestion`，但新客户端不得发送 `feature`。响应时间均为 UTC RFC 3339 字符串。

---

## 1. POST `/feedback-files/upload-token`

为已登录小程序用户签发反馈截图 COS PUT 地址。该接口复用通用图片上传传输代码，但对象用途固定为 feedback。

**Auth**: Bearer user token  
**Idempotency**: 不要求；每次调用生成新的对象键

### Request

```json
{
  "fileName": "error-page.png",
  "contentType": "image/png",
  "fileSize": 382144
}
```

| Field | Rules |
|-------|-------|
| `fileName` | 1–255 字符；扩展名仅 `.jpg` / `.jpeg` / `.png` |
| `contentType` | `image/jpeg` 或 `image/png` |
| `fileSize` | 1–5,242,880 bytes（5 MiB） |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "fileId": "feedbacks/42/2026/08/9ab0c1d2_error-page.png",
    "uploadUrl": "https://bucket.cos...?...signature...",
    "expiresAt": "2026-08-10T12:10:00Z",
    "contentType": "image/png"
  },
  "requestId": "f1d2...",
  "serverTime": "2026-08-10T12:00:00Z"
}
```

- 客户端将 `fileId` 视为不透明值。
- 客户端必须在 `expiresAt` 前以 PUT 将文件上传到 `uploadUrl`，成功后才能把 `fileId` 放入反馈提交。
- 响应不返回永久公开读 URL。

---

## 2. POST `/feedbacks`

提交一条反馈。

**Auth**: Bearer user token  
**Required header**: `Idempotency-Key: <1..128 chars>`

### Request

```json
{
  "type": "bug",
  "content": "客户绑定页面点击提交后没有显示任何结果",
  "imageFiles": [
    "feedbacks/42/2026/08/9ab0c1d2_error-page.png"
  ]
}
```

| Field | Required | Rules |
|-------|----------|-------|
| `type` | yes | `bug` / `suggestion` / `other` |
| `content` | yes | trim 后 10–500 字符 |
| `imageFiles` | no | 0–3 个互不重复的反馈 fileId；必须属于当前用户且 COS 对象存在 |

兼容说明：旧客户端发送的 `contactAllowed` 可暂时被忽略，但不得保存、返回或出现在新接口文档生成模型中；小程序本次改造会停止发送该字段。

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "feedbackId": "153",
    "feedbackNo": "FB-20260810-A1B2C3D4",
    "type": "bug",
    "status": "submitted",
    "submittedAt": "2026-08-10T12:00:00Z",
    "version": 1
  },
  "requestId": "a1b2...",
  "serverTime": "2026-08-10T12:00:00Z"
}
```

### Idempotency behavior

- 同一用户、同一 key、同一规范化 payload：始终返回同一 `feedbackId` / `feedbackNo`。
- 同一用户、同一 key、不同 payload：HTTP `409`, code `40911`，message `幂等键已用于不同的反馈内容`。
- 不同用户可以使用相同 key，数据互不影响。

---

## 3. GET `/feedbacks`（兼容保留）

保留现有“当前用户反馈列表”接口以维持 v1 向后兼容，但本迭代不恢复小程序反馈历史入口。

**Auth**: Bearer user token

### Query

| Field | Required | Rules |
|-------|----------|-------|
| `status` | no | `submitted` / `processing` / `resolved` |
| `cursor` | no | 上一页 `nextCursor` |
| `pageSize` | no | 1–100，默认 20 |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "feedbackId": "153",
        "feedbackNo": "FB-20260810-A1B2C3D4",
        "type": "bug",
        "content": "客户绑定页面点击提交后没有显示任何结果",
        "imageCount": 1,
        "status": "submitted",
        "resolution": null,
        "createdAt": "2026-08-10T12:00:00Z",
        "updatedAt": "2026-08-10T12:00:00Z"
      }
    ],
    "nextCursor": null,
    "hasMore": false
  },
  "requestId": "b1c2...",
  "serverTime": "2026-08-10T12:00:00Z"
}
```

仅返回当前 token 对应用户的数据。

---

## 4. GET `/admin/feedbacks`

后台全局反馈列表。

**Auth**: Bearer admin token  
**Permission**: `feedbacks.read`  
**Scope**: 全部组织，不接收 `orgId`

### Query

| Field | Required | Rules |
|-------|----------|-------|
| `status` | no | `submitted` / `processing` / `resolved` |
| `type` | no | `bug` / `suggestion` / `other` |
| `keyword` | no | trim 后最多 100 字；匹配反馈编号/历史编号或提交用户姓名 |
| `submittedFrom` | no | RFC 3339，闭区间开始 |
| `submittedTo` | no | RFC 3339，闭区间结束；不得早于 submittedFrom |
| `page` | no | ≥1，默认 1 |
| `pageSize` | no | 1–100，默认 20 |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "feedbackId": "153",
        "feedbackNo": "FB-20260810-A1B2C3D4",
        "type": "bug",
        "contentSummary": "客户绑定页面点击提交后没有显示任何结果",
        "imageCount": 1,
        "submitter": {
          "name": "张三",
          "phoneMasked": "138****1234",
          "available": true
        },
        "status": "submitted",
        "firstHandlerName": null,
        "createdAt": "2026-08-10T12:00:00Z",
        "updatedAt": "2026-08-10T12:00:00Z",
        "version": 1
      }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 20,
    "hasMore": false
  },
  "requestId": "c1d2...",
  "serverTime": "2026-08-10T12:00:00Z"
}
```

- `contentSummary` 最多 100 字，禁止写入前端日志。
- `phoneMasked` 永远不返回明文；无手机号时为 null。
- 默认排序：`created_at DESC, id DESC`。

---

## 5. GET `/admin/feedbacks/{feedbackNo}`

读取反馈完整详情并记录不含敏感内容的访问审计。

**Auth**: Bearer admin token  
**Permission**: `feedbacks.read`

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "feedbackId": "153",
    "feedbackNo": "FB-20260810-A1B2C3D4",
    "type": "bug",
    "content": "客户绑定页面点击提交后没有显示任何结果",
    "attachments": [
      {
        "order": 0,
        "contentType": "image/png",
        "available": true,
        "previewUrl": "https://bucket.cos...?...signature...",
        "expiresAt": "2026-08-10T12:10:00Z"
      }
    ],
    "submitter": {
      "name": "张三",
      "phoneMasked": "138****1234",
      "available": true
    },
    "status": "processing",
    "firstHandler": {
      "id": "7",
      "name": "ops01",
      "handledAt": "2026-08-10T12:03:00Z"
    },
    "resolver": null,
    "resolution": null,
    "notificationStatus": "not_required",
    "createdAt": "2026-08-10T12:00:00Z",
    "updatedAt": "2026-08-10T12:03:00Z",
    "version": 2,
    "actions": [
      {
        "actionId": "81",
        "actionType": "status_change",
        "operatorName": "ops01",
        "fromStatus": "submitted",
        "toStatus": "processing",
        "internalNote": "已复现，转交研发排查",
        "userResolution": null,
        "createdAt": "2026-08-10T12:03:00Z"
      }
    ]
  },
  "requestId": "d1e2...",
  "serverTime": "2026-08-10T12:03:00Z"
}
```

- 历史附件无法访问时仍返回对应位置，`available=false`，`previewUrl/expiresAt=null`。
- `internalNote` 只在后台详情返回，绝不进入用户通知或当前用户反馈列表。

---

## 6. PATCH `/admin/feedbacks/{feedbackNo}`

改变状态或在 processing 状态追加内部备注。

**Auth**: Bearer admin token  
**Permission**: `feedbacks.write`

### Request: mark processing

```json
{
  "expectedVersion": 1,
  "status": "processing",
  "internalNote": "已复现，正在排查"
}
```

### Request: resolve

```json
{
  "expectedVersion": 2,
  "status": "resolved",
  "internalNote": "研发已修复并完成回归",
  "resolution": "问题已修复，请重新进入客户绑定页面操作。"
}
```

| Field | Required | Rules |
|-------|----------|-------|
| `expectedVersion` | yes | integer ≥1，必须等于当前详情 version |
| `status` | yes | `processing` 或 `resolved`；必须符合状态机 |
| `internalNote` | no | trim 后 1–1000 字；processing→processing 时必填 |
| `resolution` | resolved 时 yes | trim 后 1–500 字；仅 resolved 接收 |

### Success `200`

返回与详情接口相同的最新结构；其中 `version` 已加 1。解决成功时 `notificationStatus` 至少为 `pending`，若立即创建站内通知成功可为 `sent`。

### Conflict `409`

```json
{
  "code": 40910,
  "message": "反馈已被其他管理员更新，请刷新后重试",
  "data": {
    "currentVersion": 3
  },
  "requestId": "e1f2...",
  "serverTime": "2026-08-10T12:05:00Z"
}
```

客户端收到 409 后必须重新获取详情，不得自动覆盖。

---

## Error contract

| HTTP | code | Typical trigger |
|------|------|-----------------|
| 400 | `40000` | 缺少 Idempotency-Key、非法状态转换、附件不属于用户/不存在 |
| 401 | `40100` | token 缺失、失效或非法 |
| 403 | `40300` | 缺少 `feedbacks.read` / `feedbacks.write` |
| 404 | `40400` | 反馈编号不存在 |
| 409 | `40910` | 管理员 expectedVersion 过期或反馈已解决 |
| 409 | `40911` | 同一提交幂等键携带不同 payload |
| 422 | `42200` | 类型、正文、图片数量、日期范围或处理表单校验失败 |
| 500 | `50000` | 未处理服务异常；响应及日志不得包含反馈正文/图片/备注 |

## Permission and audit contract

- `feedbacks.read`: 全局读取列表和详情；详情读取写 `feedback_view` 审计。
- `feedbacks.write`: 处理反馈；API 同时要求管理员身份，处理写 `feedback_process` 审计和 FeedbackAction。
- 系统管理员 seed 默认同时拥有两项权限；权限更新后管理员需要刷新 token 或重新登录。
- AuditLog.detail 仅记录反馈编号、管理员账号 ID、状态、版本、文本长度；禁止记录正文、附件键、手机号、内部备注和用户结果全文。
