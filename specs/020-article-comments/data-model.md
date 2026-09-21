# Data Model: 文章评论与评论管理

**Feature**: 020-article-comments  
**Date**: 2026-09-21  
**Database migration**: Alembic `020` (revises `019`)

## 1. ArticleComment

`article_comments` 是评论业务事实来源。评论只允许挂在文章上；文章删除时级联清理未保留的业务关联，公开查询始终额外校验文章状态为 `published`。

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | 自增；作为稳定排序的最终 tie-breaker |
| `article_id` | integer FK → `articles.id` | required；索引 `(article_id, status, is_pinned, created_at, id)` |
| `user_id` | integer FK → `users.id` nullable | 用户删除后可置空，依靠显示快照保留评论展示身份 |
| `display_name_snapshot` | varchar(100) | 创建时取用户昵称映射；缺失使用“儒泰用户” |
| `avatar_url_snapshot` | varchar(500) nullable | 创建时取用户头像；只用于公开展示 |
| `content` | text | 新评论 1–500 字；允许文字表情，不允许链接/图片/语音/回复；删除清理窗口后清空或移除 |
| `status` | enum/string | `pending`、`visible`、`hidden`、`rejected`、`deleted` |
| `moderation_status` | enum/string | `pending`、`passed`、`flagged`、`rejected`、`error` |
| `moderation_category` | varchar(32) nullable | `sexual`、`violence`、`political`、`other`；不存完整命中片段 |
| `moderation_rule_version` | varchar(32) nullable | 本地规则版本，便于复核 |
| `moderation_checked_at` | datetime nullable | 最近一次本地审查时间 |
| `moderation_reason` | varchar(255) nullable | 受控后台原因，不返回小程序 |
| `is_pinned` | boolean | 默认 false；每篇文章最多一条 true |
| `like_count` | integer | 默认 0；不得小于 0 |
| `version` | integer | 默认 1；后台操作乐观锁，每次有效更新 +1 |
| `hidden_at` | datetime nullable | 下架时间 |
| `deleted_at` | datetime nullable | 软删除时间；清理任务据此计算 7 天窗口 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 最近更新时间 |

### Status semantics

| Status | Public list | Admin list | Allowed transitions |
|---|---|---|---|
| `pending` | no | yes | `visible` (人工放行), `rejected`, `deleted` |
| `visible` | yes | yes | `hidden`, `deleted`, `visible` (置顶变化不改状态) |
| `hidden` | no | yes | `visible`, `deleted` |
| `rejected` | no | yes | `visible` (仅人工放行), `deleted` |
| `deleted` | no | yes（7 天内） | 无前台恢复；清理后不再返回正文 |

`is_pinned=true` 只能出现在 `visible` 评论上；下架、拒绝或删除时自动取消置顶。

## 2. CommentLike

`comment_likes` 表示一个用户对一条评论的有效点赞关系。

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | 自增 |
| `comment_id` | integer FK → `article_comments.id` | required；删除评论时级联删除 |
| `user_id` | integer FK → `users.id` | required |
| `created_at` | datetime | 首次点赞时间 |

Constraints/indexes:

- `UNIQUE(comment_id, user_id)`：同一用户对同一评论最多一条有效关系。
- `INDEX(user_id, comment_id)`：支持当前用户状态查询和账号清理。
- 点赞/取消点赞事务同时锁定评论计数；计数以关系变化为准，不接受客户端传入数量。

## 3. CommentAction

`comment_actions` 是评论业务处置时间线，不替代安全审计日志。

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | 自增 |
| `comment_id` | integer FK → `article_comments.id` | required；业务记录清理时级联 |
| `operator_admin_id` | integer FK → `admin_accounts.id` nullable | 自动审查可为空，人工动作记录管理员 |
| `operator_name_snapshot` | varchar(100) | 人工操作时保存显示名/账号快照 |
| `action_type` | varchar(24) | `auto_review`, `approve`, `reject`, `hide`, `restore`, `pin`, `unpin`, `delete` |
| `from_status` | varchar(20) | 变更前状态 |
| `to_status` | varchar(20) | 变更后状态 |
| `reason` | varchar(500) nullable | 管理原因；不得写入完整评论正文 |
| `moderation_rule_version` | varchar(32) nullable | 自动审查动作的规则版本 |
| `version_before` | integer | 乐观锁证据 |
| `version_after` | integer | 乐观锁结果 |
| `created_at` | datetime | 动作时间 |

Indexes:

- `INDEX(comment_id, created_at, id)`：后台时间线查询。
- `INDEX(action_type, created_at)`：审查和运营统计。

业务动作记录在评论删除后保留 7 天；安全动作摘要另写 `AuditLog`，按现有合规策略保留，且不包含完整正文。

## 4. Moderation rule model (non-persistent configuration)

本地审查规则作为后端代码/配置中的版本化规则集，不新增客户端可下载的词表接口。

| Value | Meaning |
|---|---|
| `sexual` | 色情/淫秽相关规则 |
| `violence` | 暴力、威胁、极端伤害相关规则 |
| `political` | 当前产品定义的政治违规规则 |
| `other` | 规则配置错误或未分类风险 |

执行顺序：`trim` → NFKC 归一化 → 大小写/空白/常见标点规整 → 规则匹配 → 写入 moderation 状态和版本 → 决定 `visible` / `pending` / `rejected`。

## 5. Public response models

### CommentListItem

| Field | Type | Rules |
|---|---|---|
| `commentId` | string | 非空正整数文本 |
| `displayName` | string | 显示快照；缺失统一为“儒泰用户” |
| `avatarUrl` | string/null | 仅公开头像地址 |
| `content` | string | 仅 `visible` 评论返回正文 |
| `isPinned` | boolean | 公开列表只会为 `visible` 评论返回 true |
| `likeCount` | non-negative integer | 服务端计数 |
| `liked` | boolean | 当前登录用户是否存在 `CommentLike` |
| `createdAt` | RFC 3339 string | 服务端时间 |

### CommentPage

| Field | Type | Rules |
|---|---|---|
| `items` | `CommentListItem[]` | 只含当前文章的 `visible` 评论 |
| `nextCursor` | string/null | 不透明；无下一页为 null |
| `hasMore` | boolean | true 时 nextCursor 必须非空 |
| `total` | integer | 当前查询条件下可见评论数量，或由实现选择不返回；若返回必须服务端计算 |

## 6. Admin response models

后台列表/详情可返回 `pending/visible/hidden/rejected/deleted` 的状态、审查分类、规则版本、操作时间线、点赞数和 `displayName`，但不得返回手机号、身份证号、用户内部 token 或完整审查词条。删除清理窗口结束后，正文以“内容已清理”替代。

## 7. Retention and cleanup

1. `visible`、`pending`、`hidden` 评论按文章业务生命周期保留。
2. `deleted_at <= now - 7 days` 的评论清理正文、审查原始结果、点赞关系和 `CommentAction` 业务记录。
3. 清理前后保留不含正文的 `AuditLog` 摘要，符合系统既有审计策略。
4. 清理任务按主键分批执行，失败回滚当前批次并记录不含正文的错误。

## 8. State transition summary

```text
submit ──local pass──────────────► visible
   │
   ├─rule hit / uncertain─────────► pending ──admin approve──► visible
   │                                  │  └─admin reject──────► rejected
   └─invalid input / rate limit────► request rejected (no public row)

visible ──admin hide──────────────► hidden ──admin restore────► visible
visible/pending/hidden/rejected ──► deleted ──7 days──────────► purged
visible ──admin pin───────────────► visible + is_pinned=true (one/article)
```

