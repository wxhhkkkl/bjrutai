# API Contract: 小程序文章资讯与阅读

**Feature**: 014-article-reading  
**Base path**: `/api/v1`  
**Status**: Existing backend contract consumed by the mini-program

所有成功和业务错误响应使用统一封装：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "requestId": "request-id",
  "serverTime": "2026-08-10T08:00:00Z"
}
```

两个端点均为公开只读接口，不要求 Bearer token。小程序请求应显式使用公共访问模式，但仍通过统一 request client 校验响应封装。

## 1. GET `/articles`

返回已发布文章，按 `publishedAt DESC, articleId DESC` 排序。

### Query

| Field | Required | Rules | Mini-program usage |
|-------|----------|-------|--------------------|
| `cursor` | no | 最多 256 字符；上一响应的 nextCursor | 列表加载更多原样回传 |
| `limit` | no | integer 1–100，默认 20 | 首页 3；完整列表 20 |
| `category` | no | 最多 50 字符 | 本迭代不发送 |
| `keyword` | no | 最多 100 字符 | 本迭代不发送 |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "articleId": "123",
        "title": "夏季健康管理提示",
        "summary": "关注高温天气下的日常健康管理。",
        "coverImageUrl": "https://example-cos-domain/articles/cover.jpg",
        "category": "健康科普",
        "author": "儒泰内容团队",
        "viewCount": 36,
        "publishedAt": "2026-08-10T07:30:00Z"
      }
    ],
    "nextCursor": "MTIz",
    "hasMore": true
  },
  "requestId": "req-list",
  "serverTime": "2026-08-10T08:00:00Z"
}
```

### Empty `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "nextCursor": null,
    "hasMore": false
  },
  "requestId": "req-empty",
  "serverTime": "2026-08-10T08:00:00Z"
}
```

### Contract rules

- `items` MUST contain only currently published articles.
- `items` MUST NOT include full `content`.
- `articleId` and `title` are required for every item; optional metadata may be null.
- `hasMore=true` requires non-empty `nextCursor`.
- Cursor is opaque. The client MUST NOT decode, increment or derive it.
- 首页文章失败不得转换为首页工作台失败；完整列表首屏失败进入页面可重试状态。

## 2. GET `/articles/{articleId}`

返回一篇当前已发布文章详情。成功读取由后端将浏览量增加一次，响应中的 `viewCount` 为增加后的服务端值。

### Path

| Field | Rules |
|-------|-------|
| `articleId` | positive integer |

### Success `200`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "123",
    "title": "夏季健康管理提示",
    "summary": "关注高温天气下的日常健康管理。",
    "content": "<h2>合理补水</h2><p>请根据身体情况及时补水。</p><img src=\"https://example-cos-domain/articles/body.jpg\">",
    "coverImageUrl": "https://example-cos-domain/articles/cover.jpg",
    "category": "健康科普",
    "tags": ["夏季", "健康"],
    "author": "儒泰内容团队",
    "viewCount": 37,
    "status": "published",
    "publishedAt": "2026-08-10T07:30:00Z",
    "createdAt": "2026-08-09T03:00:00Z",
    "updatedAt": "2026-08-10T07:30:00Z"
  },
  "requestId": "req-detail",
  "serverTime": "2026-08-10T08:01:00Z"
}
```

### Not found / no longer published `404`

```json
{
  "code": 40400,
  "message": "Article not found",
  "data": null,
  "requestId": "req-not-found",
  "serverTime": "2026-08-10T08:01:00Z"
}
```

客户端对不存在、草稿和已下架统一显示“文章已下架或不存在”，不得用列表中的旧摘要拼出详情。

### Contract rules

- 成功响应 `status` MUST be `published`。
- `content` 可为空字符串；客户端显示明确空正文状态。
- 客户端不得执行 `content` 中的 script、事件属性、iframe、表单或嵌入程序。
- 页面每次新进入只发一次详情请求；`onShow` 不重复调用。用户明确重试可再次请求。
- 客户端不得自行增加 `viewCount`。

## 3. Error mapping

| Boundary | Client state | Retry |
|----------|--------------|-------|
| timeout / network | `recoverable-error` | yes |
| malformed envelope/data | `recoverable-error` | yes; no Mock fallback |
| detail 404 | `not-found` | return to list; retry optional |
| HTTP/business 500 | `recoverable-error` | yes |
| invalid local articleId | local validation error | no request; return/list action |

## 4. Compatibility and backend-change gate

现有后端实现和测试已覆盖本合同，计划不修改生产接口。联调若发现以下任一情况，必须先新增失败的后端合同测试，再做最小修复：

- 公开列表出现 draft/unpublished；
- 列表排序或 cursor 不稳定；
- detail 对下架文章返回正文；
- 成功响应不符合统一 envelope；
- detail 浏览量更新失败或响应值不是服务端最新值。
