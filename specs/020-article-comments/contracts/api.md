# API Contract: 文章评论与评论管理

**Feature**: 020-article-comments  
**Base path**: `/api/v1`  
**Status**: Ready for implementation planning

所有响应使用统一封装：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "requestId": "request-id",
  "serverTime": "2026-09-21T08:00:00Z"
}
```

除文章正文原有公开接口外，本契约所有评论接口都要求：

```http
Authorization: Bearer <mini-program-access-token>
```

未登录不得读取评论正文、评论数量、点赞状态或发表评论控件所需数据。

## 1. GET `/articles/{articleId}/comments`

读取一篇已发布文章的可见评论。文章不存在、未发布或当前用户未登录时，按现有错误映射返回，不泄露隐藏文章或隐藏评论的存在。

### Query

| Field | Required | Rules |
|---|---|---|
| `cursor` | no | 不透明字符串；上一页 `nextCursor` 原样回传 |
| `limit` | no | integer 1–50，默认 20 |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "commentId": "901",
        "displayName": "Lee",
        "avatarUrl": "https://example.com/avatar.jpg",
        "content": "这篇文章很实用。😊",
        "isPinned": true,
        "likeCount": 3,
        "liked": false,
        "createdAt": "2026-09-21T07:30:00Z"
      }
    ],
    "nextCursor": null,
    "hasMore": false,
    "total": 1
  },
  "requestId": "req-comments",
  "serverTime": "2026-09-21T08:00:00Z"
}
```

仅返回 `status=visible` 的评论，排序为置顶优先、发表时间倒序、评论 ID 倒序。`liked` 只描述当前登录用户，不返回其他点赞用户。

## 2. POST `/articles/{articleId}/comments`

提交评论并执行本地审查。

### Headers

```http
Idempotency-Key: comment-submit-<client-generated-id>
```

同一用户的同一 key 重试必须返回第一次结果；同一 key 携带不同正文返回冲突错误。

### Request body

```json
{
  "content": "这篇文章很实用。😊"
}
```

规则：去除首尾空白后 1–500 字；允许文字表情；拒绝链接、图片、语音、贴纸标记、HTML、脚本、仅空白内容和控制字符。

### Success `200` — approved

```json
{
  "code": 0,
  "message": "评论已发布",
  "data": {
    "commentId": "901",
    "status": "visible",
    "moderationStatus": "passed"
  }
}
```

### Success `200` — pending review

```json
{
  "code": 0,
  "message": "评论已提交，审核通过后展示",
  "data": {
    "commentId": "902",
    "status": "pending",
    "moderationStatus": "flagged"
  }
}
```

客户端不得将 `pending` 评论插入公开列表，只向当前用户显示受控状态提示。

## 3. POST `/articles/{articleId}/comments/{commentId}/like`

为当前登录用户创建点赞关系。评论必须属于指定文章且当前为可见状态。

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": { "commentId": "901", "liked": true, "likeCount": 4 }
}
```

重复点赞按幂等成功处理，不重复增加 `likeCount`。

## 4. DELETE `/articles/{articleId}/comments/{commentId}/like`

取消当前登录用户对评论的点赞。

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": { "commentId": "901", "liked": false, "likeCount": 3 }
}
```

未点赞时按幂等成功处理，计数不得小于零。

## 5. GET `/admin/comments`

评论管理列表，需要 `comments.read`。

### Query

| Field | Rules |
|---|---|
| `articleId` | positive integer，可选 |
| `status` | `pending|visible|hidden|rejected|deleted`，可选 |
| `keyword` | 最多 100 字，搜索评论正文摘要或显示名；后台有权限才可使用正文搜索 |
| `createdFrom` / `createdTo` | RFC 3339，可选；结束时间不得早于开始时间 |
| `cursor` | 不透明 cursor，可选 |
| `limit` | integer 1–100，默认 20 |

### Response `data`

```json
{
  "items": [
    {
      "commentId": "901",
      "articleId": "123",
      "articleTitle": "夏季健康管理提示",
      "displayName": "Lee",
      "contentPreview": "这篇文章很实用。😊",
      "status": "visible",
      "moderationStatus": "passed",
      "moderationCategory": null,
      "isPinned": true,
      "likeCount": 4,
      "createdAt": "2026-09-21T07:30:00Z",
      "updatedAt": "2026-09-21T07:35:00Z"
    }
  ],
  "nextCursor": null,
  "hasMore": false,
  "total": 1
}
```

后台列表不返回手机号、身份证号、token 或完整审查词条。`contentPreview` 最多 100 字。

## 6. GET `/admin/comments/{commentId}`

需要 `comments.read`。返回评论详情、审查信息和业务动作时间线。删除清理窗口结束后正文返回“内容已清理”，不返回原文。

## 7. PATCH `/admin/comments/{commentId}`

需要 `comments.write`，使用乐观锁执行人工处置。

### Request body

```json
{
  "action": "approve",
  "reason": "审核通过",
  "expectedVersion": 3
}
```

`action` 枚举：`approve`、`reject`、`hide`、`restore`、`pin`、`unpin`、`delete`。

规则：

- `approve`：`pending/rejected/hidden` → `visible`。
- `reject`：`pending` → `rejected`。
- `hide`：`visible` → `hidden`，必须记录原因。
- `restore`：`hidden` → `visible`；不得恢复 `deleted`。
- `pin`：只能作用于 `visible`，同文章已有置顶时在同一事务内取消旧置顶。
- `unpin`：取消当前置顶，不改变可见状态。
- `delete`：任意未清理状态 → `deleted`，自动取消置顶和删除公开点赞关系。
- `expectedVersion` 不匹配返回 HTTP 409 / `40910`，客户端需刷新后重试。

### Success `200`

返回更新后的后台详情对象，并包含新的 `version`、状态、动作时间和审计摘要。

## 8. Error mapping

| Condition | HTTP / code | Client behavior |
|---|---:|---|
| Missing/expired token | 401 / `40100` | 触发现有登录过期流程 |
| No comment permission | 403 / `40300` | 不显示后台功能并提示无权限 |
| Article/comment not found or not public | 404 / `40400` | 不泄露隐藏对象存在性 |
| Invalid content/link/length/rate | 400 / `40000` | 展示受控中文提示，不清空草稿 |
| Local moderation flagged | 200 pending or 400 controlled rejection | 不公开正文，显示审核提示 |
| Idempotency key reused with different body | 409 / `40911` | 保留原草稿，要求重新生成 key |
| Admin version conflict | 409 / `40910` | 刷新详情后重试 |
| Malformed/temporary server error | 500 / `50000` | 文章正文保持可读，评论区显示局部重试 |

## 9. Security and privacy contract

- 评论接口必须在服务端校验 token、用户激活状态和文章发布状态。
- 公开响应只返回显示名快照、头像、正文、时间、置顶和点赞聚合；不返回 user ID、手机号或点赞明细。
- 审计 `detail` 不保存完整正文、敏感词命中片段或内部规则词表。
- 删除正文和业务动作记录按 7 天清理；安全审计摘要按系统既有保留策略留存。

