# Data Model: 小程序文章资讯与阅读

**Feature**: 014-article-reading  
**Date**: 2026-08-10  
**Database migration**: None

本功能不新增数据库实体。后端 `Article` 继续是文章、发布状态、排序与浏览量的唯一事实来源；以下模型是公开接口和小程序页面中的只读视图。

## 1. ArticleListItem（公开列表项）

| Field | Wire type | Client normalized type | Rules / Display |
|-------|-----------|------------------------|-----------------|
| `articleId` | string | string | 必须为非空正整数文本；作为列表 key 和详情参数 |
| `title` | string | string | 必填；trim 后为空视为格式错误 |
| `summary` | string/null | string | 可空；列表最多展示既定行数 |
| `coverImageUrl` | string/null | string | 可空；无效/缺失使用统一占位 |
| `category` | string/null | string | 可空；无值隐藏分类标签 |
| `author` | string/null | string | 可空；无值隐藏作者 |
| `viewCount` | integer | non-negative integer | 非法或负数归一化为 0，仅展示服务端值 |
| `publishedAt` | RFC 3339/null | raw + display string | 可空；有值按中国本地时间格式化 |

列表项没有正文，也不要求客户端读取 `status`。服务端公开列表本身负责只返回 published。

## 2. ArticleDetail（公开详情）

在 ArticleListItem 基础上增加：

| Field | Wire type | Client normalized type | Rules / Display |
|-------|-----------|------------------------|-----------------|
| `content` | string/null | string | 后台 HTML；空值显示“暂无正文内容” |
| `tags` | string[]/null | string[] | 过滤空值和非字符串；可空 |
| `status` | string | string | 公开成功响应应为 `published`；未知值进入格式错误状态 |
| `createdAt` | RFC 3339/null | string | 元数据保留，默认不作为主要发布时间 |
| `updatedAt` | RFC 3339/null | string | 元数据保留 |

详情模型不保存用户 ID、token、阅读历史或管理字段 `version`。

## 3. ArticlePage（游标分页）

| Field | Type | Rules |
|-------|------|-------|
| `items` | ArticleListItem[] | 缺失或非数组为 malformed response；适配后按响应顺序保留 |
| `nextCursor` | string | 客户端视为不透明；无下一页时归一化为空字符串 |
| `hasMore` | boolean | 只有严格 `true` 表示可继续；为 true 时 nextCursor 必须非空 |

### Merge rules

1. 首次加载/刷新：用新 `items` 替换旧列表。
2. 加载更多：按 `articleId` 追加未出现的项目，保持服务端顺序。
3. `hasMore=false`：清空 nextCursor，禁止继续请求。
4. `hasMore=true` 但 cursor 空、下一 cursor 与当前相同，或整页均重复：停止自动加载并进入受控分页异常，避免无限请求。
5. 刷新增加 requestVersion；旧首屏/分页响应到达时丢弃。

## 4. HomeArticleState（首页文章局部状态）

| Field | Values | Purpose |
|-------|--------|---------|
| `articleState` | `loading`, `success`, `empty`, `recoverable-error` | 与首页 `state` 完全隔离 |
| `articleItems` | ArticleListItem[] | 最多 3 条 |
| `articleStateMessage` | string | 局部失败提示，不写入首页主错误 |
| `articleRequestVersion` | integer (instance field) | 丢弃隐藏/卸载后的迟到响应 |

### State transitions

```text
idle/onShow ──► loading ──success──► success(items 1..3)
                         ├─empty───► empty(items 0)
                         └─error───► recoverable-error

任何文章状态变化不得修改首页主 state/summary/notices/records。
```

## 5. ArticleListPageState（文章列表页面状态）

| Field | Type / Values | Purpose |
|-------|---------------|---------|
| `state` | loading/success/empty/recoverable-error | 首屏状态 |
| `items` | ArticleListItem[] | 当前已加载文章 |
| `nextCursor` | string | 下一页游标 |
| `hasMore` | boolean | 是否允许继续加载 |
| `loadingMore` | boolean | 防止并发分页 |
| `loadMoreError` | string | 分页失败提示；不清空 items |
| `openingArticleId` | string | 防快速重复导航；导航完成后清理 |
| `requestVersion` | integer (instance field) | 刷新/卸载响应隔离 |

## 6. ArticleDetailPageState（文章详情页面状态）

| Field | Type / Values | Purpose |
|-------|---------------|---------|
| `articleId` | string | onLoad 校验后的稳定参数 |
| `state` | loading/success/not-found/recoverable-error | 详情状态 |
| `article` | ArticleDetail/null | 每次请求前清空，禁止显示上一文章 |
| `stateMessage` | string | 404 与网络错误使用不同文案 |
| `requestVersion` | integer (instance field) | 返回/卸载后丢弃迟到响应 |
| `hasLoaded` | boolean (instance field) | 避免 onShow 重复请求 |

## 7. Navigation actions

| Action | Target | Inputs |
|--------|--------|--------|
| `article-list` | `/pages/articles/index` | none |
| direct article | `/pages/article-detail/index?articleId={id}` | 仅合法 articleId，必须编码 |

首页“查看全部”和“我的”文章服务项使用 `article-list`；首页卡片和列表项使用 direct article。

## 8. Persistence and privacy

- 不向 storage 写入文章列表、正文、浏览量或阅读历史。
- 页面栈内存可暂时保留列表以支持返回位置；页面卸载即释放。
- 不在日志、错误提示或埋点中复制完整正文。
- 图片 URL 只用于 `<image>`/富文本展示，不作为云存储管理凭证。
