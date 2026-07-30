# Content API Contracts

All endpoints under `/api/v1/articles/` and `/api/v1/admin/articles/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

---

## List Published Articles (Public / Promoter-Facing)

**Method**: GET
**Path**: /api/v1/articles
**Auth**: Required
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| category | string | no | Max 50 chars | Article category filter |
| keyword | string | no | Max 100 chars | Search title or summary |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "articleId": "art_001",
        "title": "2026年Q3推广政策解读",
        "summary": "详细介绍第三季度的推广政策和激励措施",
        "coverImageUrl": "https://oss.example.com/articles/cover_001.jpg",
        "category": "政策解读",
        "author": "运营部",
        "viewCount": 1250,
        "publishedAt": "2026-07-15T09:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_art",
    "hasMore": false
  },
  "requestId": "req_20260730120000061",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 50001 | Internal server error | Yes |

### Business Rules
- Returns only published articles (`status: "published"`).
- Results sorted by `publishedAt` descending.
- `coverImageUrl` may be null if no cover image is set.
- `viewCount` is incremented on detail view, not on list view.

---

## Article Detail

**Method**: GET
**Path**: /api/v1/articles/{id}
**Auth**: Required
**Idempotency**: Not applicable

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Article ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "art_001",
    "title": "2026年Q3推广政策解读",
    "summary": "详细介绍第三季度的推广政策和激励措施",
    "content": "<p>富文本HTML内容...</p>",
    "coverImageUrl": "https://oss.example.com/articles/cover_001.jpg",
    "category": "政策解读",
    "tags": ["政策", "激励", "Q3"],
    "author": "运营部",
    "viewCount": 1251,
    "status": "published",
    "publishedAt": "2026-07-15T09:00:00+08:00",
    "createdAt": "2026-07-14T16:00:00+08:00",
    "updatedAt": "2026-07-15T08:50:00+08:00"
  },
  "requestId": "req_20260730120000062",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40400 | Article not found | No |
| 40094 | Article is not published | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Accessing the detail endpoint increments `viewCount` by 1.
- Only published articles are visible via this endpoint.
- `content` may contain HTML (sanitized server-side, no scripts allowed).
- `tags` is a free-form array of labels.

---

## CMS: List All Articles

**Method**: GET
**Path**: /api/v1/admin/articles
**Auth**: Required (admin)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| status | string | no | Enum: `draft`, `published`, `unpublished` | Filter by status |
| category | string | no | Max 50 chars | Filter by category |
| keyword | string | no | Max 100 chars | Search title |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "articleId": "art_001",
        "title": "2026年Q3推广政策解读",
        "summary": "详细介绍第三季度的推广政策和激励措施",
        "category": "政策解读",
        "status": "published",
        "statusLabel": "已发布",
        "author": "运营部",
        "viewCount": 1250,
        "createdBy": "u_admin001",
        "creatorName": "管理员张三",
        "publishedAt": "2026-07-15T09:00:00+08:00",
        "createdAt": "2026-07-14T16:00:00+08:00",
        "updatedAt": "2026-07-15T08:50:00+08:00"
      }
    ],
    "nextCursor": "cursor_cms_art",
    "hasMore": false
  },
  "requestId": "req_20260730120000063",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns articles regardless of status (draft, published, unpublished).
- Results sorted by `updatedAt` descending.
- `createdBy` and `creatorName` identify the admin who created the article.

---

## CMS: Create Article

**Method**: POST
**Path**: /api/v1/admin/articles
**Auth**: Required (admin)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| title | string | yes | Length 2-200 | Article title |
| summary | string | no | Max 500 chars | Article summary / excerpt |
| content | string | no | Max 100,000 chars | Article body (sanitized HTML) |
| coverImageUrl | string | no | Max 2048 chars | Cover image URL |
| category | string | no | Max 50 chars | Category |
| tags | array[string] | no | Max 20 items, each max 30 chars | Tags |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "art_002",
    "title": "新产品上线通知",
    "status": "draft",
    "statusLabel": "草稿",
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000064",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40095 | Title is required | No |
| 40096 | Content contains disallowed HTML tags | No |
| 50001 | Internal server error | Yes |

### Business Rules
- New articles are created in `draft` status by default.
- `content` is sanitized: only safe HTML tags are allowed (p, b, i, u, h1-h6, ul, ol, li, a, img, br, div, span, table, tr, td, th, blockquote). Script/style tags and event handlers are stripped.
- `title` must be unique among non-deleted articles.

---

## CMS: Update Article

**Method**: PUT
**Path**: /api/v1/admin/articles/{id}
**Auth**: Required (admin)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Article ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| title | string | no | Length 2-200 | Article title |
| summary | string | no | Max 500 chars | Article summary |
| content | string | no | Max 100,000 chars | Article body |
| coverImageUrl | string | no | Max 2048 chars | Cover image URL |
| category | string | no | Max 50 chars | Category |
| tags | array[string] | no | Max 20 items, each max 30 chars | Tags |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "art_002",
    "title": "新产品上线通知(修订版)",
    "status": "draft",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000065",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Article not found | No |
| 40095 | Title is required when updating | No |
| 40096 | Content contains disallowed HTML tags | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Articles in any status can be updated. Updates do not change the status.
- Supplied fields are merged; omitted fields retain their current value.
- If `title` is updated, uniqueness is checked.

---

## CMS: Publish Article

**Method**: POST
**Path**: /api/v1/admin/articles/{id}/publish
**Auth**: Required (admin)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Article ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "art_002",
    "status": "published",
    "statusLabel": "已发布",
    "publishedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000066",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Article not found | No |
| 40097 | Article is already published | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Sets `publishedAt` to the current time when status changes to `published`.
- If the article was previously published, `publishedAt` is updated to reflect the re-publish time.
- The article becomes visible to all promoters via `/api/v1/articles`.

---

## CMS: Unpublish Article

**Method**: POST
**Path**: /api/v1/admin/articles/{id}/unpublish
**Auth**: Required (admin)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Article ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "articleId": "art_001",
    "status": "unpublished",
    "statusLabel": "已下架",
    "unpublishedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000067",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Article not found | No |
| 40098 | Article is not published | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Unpublishing removes the article from the public list immediately.
- The article is retained in CMS and can be re-published.
- Existing view counts and metadata are preserved.
