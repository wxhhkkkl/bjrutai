# Data Model: 意见与反馈提交及后台管理

**Feature**: 013-feedback-management  
**Date**: 2026-08-10  
**Migration**: `backend/migrations/versions/015_feedback_management.py` (`down_revision = '014'`)

## 1. Feedback（`feedbacks`）

反馈当前状态的唯一事实来源。用户原始类型、正文和附件创建后不可修改或删除。

| Column | Type | Constraints / Default | Purpose |
|--------|------|-----------------------|---------|
| `id` | INTEGER | PK, autoincrement | 内部主键；兼容 SQLite 测试自增 |
| `feedback_no` | VARCHAR(40) | NOT NULL, UNIQUE | 用户/管理员可见的稳定反馈编号 |
| `user_id` | INTEGER | NULL, FK `users.id`, ON DELETE SET NULL | 提交用户；注销后历史仍保留 |
| `submitter_name_snapshot` | VARCHAR(100) | NULL | 提交时姓名快照，供全局列表和历史检索 |
| `submitter_phone_masked_snapshot` | VARCHAR(20) | NULL | 仅保存脱敏手机号快照，不复制明文 |
| `type` | VARCHAR(20) | NOT NULL | `bug` / `suggestion` / `other` |
| `content` | TEXT | NOT NULL | 新提交 trim 后 10–500 字；历史数据原样保留 |
| `image_files` | JSON | NOT NULL, default `[]` | 按展示顺序保存 0–3 个附件描述对象（对象键、MIME、历史标记） |
| `status` | VARCHAR(20) | NOT NULL, default `submitted` | `submitted` / `processing` / `resolved` |
| `first_handler_id` | INTEGER | NULL, FK `admin_accounts.id`, ON DELETE SET NULL | 首位将反馈置为处理中者，仅追溯、不独占 |
| `first_handled_at` | DATETIME | NULL | 首次进入处理中时间（UTC） |
| `resolved_by_id` | INTEGER | NULL, FK `admin_accounts.id`, ON DELETE SET NULL | 实际解决管理员 |
| `resolved_at` | DATETIME | NULL | 解决时间（UTC） |
| `resolution` | TEXT | NULL | 用户可见处理结果；resolved 时 trim 后 1–500 字 |
| `version` | INTEGER | NOT NULL, default `1` | 管理员写入的乐观锁版本 |
| `idempotency_key` | VARCHAR(128) | NULL | 新提交请求键；历史记录可为空 |
| `submission_fingerprint` | CHAR(64) | NULL | 规范化请求体 SHA-256，用于检测同键不同内容 |
| `source_audit_log_id` | INTEGER | NULL, UNIQUE, FK `audit_logs.id`, ON DELETE SET NULL | 历史 AuditLog 来源与迁移幂等标记 |
| `notification_status` | VARCHAR(20) | NOT NULL, default `not_required` | `not_required` / `pending` / `sent` / `failed` |
| `notification_attempts` | INTEGER | NOT NULL, default `0` | 站内通知尝试次数 |
| `notification_next_retry_at` | DATETIME | NULL | 下次补偿时间 |
| `notification_last_error` | VARCHAR(500) | NULL | 截断后的非敏感错误，不含正文/结果 |
| `notification_sent_at` | DATETIME | NULL | 站内通知成功创建时间 |
| `created_at` | DATETIME | NOT NULL | 提交时间（UTC） |
| `updated_at` | DATETIME | NOT NULL | 最近业务更新时间（UTC） |

### Indexes and constraints

- `uq_feedbacks_feedback_no (feedback_no)`
- `uq_feedbacks_user_idempotency (user_id, idempotency_key)`；`idempotency_key IS NULL` 只用于历史数据
- `uq_feedbacks_source_audit_log (source_audit_log_id)`
- `ix_feedbacks_status_created (status, created_at, id)`
- `ix_feedbacks_type_created (type, created_at, id)`
- `ix_feedbacks_created (created_at, id)`
- `ix_feedbacks_user_created (user_id, created_at, id)`
- `ix_feedbacks_submitter_name (submitter_name_snapshot)`

### Feedback number

- 新记录：`FB-YYYYMMDD-XXXXXXXX`，其中随机部分使用服务端安全随机值；数据库唯一约束处理极小概率碰撞并重试生成。
- 历史记录：优先保留旧 `AuditLog.entity_id`；缺失或发生冲突时使用 `LEGACY-{audit_log_id}`。
- 客户端必须将反馈编号视为不透明字符串，不解析日期或长度。

## 2. FeedbackAction（`feedback_actions`）

只增不改的后台处理时间线。原反馈提交不是管理员动作，不写入此表。

| Column | Type | Constraints / Default | Purpose |
|--------|------|-----------------------|---------|
| `id` | INTEGER | PK, autoincrement | 动作主键 |
| `feedback_id` | INTEGER | NOT NULL, FK `feedbacks.id`, ON DELETE CASCADE | 所属反馈 |
| `operator_id` | INTEGER | NULL, FK `admin_accounts.id`, ON DELETE SET NULL | 实际管理员账号 |
| `operator_name_snapshot` | VARCHAR(100) | NOT NULL | 管理员账号删除/更名后仍可追溯 |
| `action_type` | VARCHAR(20) | NOT NULL | `status_change` / `note` / `resolve` |
| `from_status` | VARCHAR(20) | NOT NULL | 操作前状态 |
| `to_status` | VARCHAR(20) | NOT NULL | 操作后状态；追加备注时可相同 |
| `internal_note` | TEXT | NULL | 后台内部备注，trim 后最多 1000 字 |
| `user_resolution` | TEXT | NULL | 本次写入的用户可见结果，最多 500 字 |
| `version_before` | INTEGER | NOT NULL | 操作前版本 |
| `version_after` | INTEGER | NOT NULL | 操作后版本 |
| `created_at` | DATETIME | NOT NULL | 操作时间（UTC） |

### Indexes and immutability

- `ix_feedback_actions_feedback_created (feedback_id, created_at, id)`
- 应用不提供 UPDATE / DELETE FeedbackAction 能力。
- 数据库迁移不为动作提供“软删除”字段，避免出现可隐藏历史的路径。

## 3. Notification（现有 `notifications` 表变更）

站内通知继续使用现有 `NotificationCategory.SYSTEM`，小程序现有消息中心无需新增分类。

| New Column | Type | Constraints | Purpose |
|------------|------|-------------|---------|
| `feedback_id` | INTEGER | NULL, UNIQUE, FK `feedbacks.id`, ON DELETE SET NULL | 一条反馈最多一条解决通知，防止立即发送与重试重复 |

反馈通知内容：

- `user_id`: 原反馈 `user_id`；用户已被物理删除时保持 `failed`，不创建无主通知。
- `category`: `system`。
- `title`: `反馈 {feedback_no} 已处理`。
- `summary`: 纯文本组合“反馈类型、用户可见处理结果、解决时间”，不含内部备注、管理员或其他用户信息。
- `target`: `NULL`，不跳转至已移除的反馈历史，也不重新打开提交表单。

## 4. FeedbackAttachment（嵌套值对象，不建独立表）

`image_files` 是有序 JSON 数组，不向客户端暴露其存储结构。新附件描述对象形如：

```json
{
  "objectKey": "feedbacks/123/2026/08/random_screenshot.png",
  "contentType": "image/png",
  "legacy": false
}
```

历史附件描述对象保留旧对象键，`contentType` 无法可靠推断时为 `null`，并设置 `legacy=true`。

提交前必须满足：

1. 数量 0–3，且不得重复。
2. 前缀严格属于当前用户的 `feedbacks/{user_id}/` 命名空间。
3. 扩展名和上传令牌登记的 MIME 仅允许 JPEG/PNG，申请上传令牌时单图 1 byte–5 MiB。
4. COS HEAD 验证对象存在，证明预签名 PUT 已完成。
5. 管理员详情不返回永久公开 URL，只返回 10 分钟短时签名预览 URL 与过期时间。

历史 `AuditLog.detail.imageFiles` 可能位于 `avatars/`、`qualifications/` 或旧 `feedbacks/` 前缀：迁移时原样保留并标记为历史附件；读取时无法验证/签名的单图返回 `available=false`，不阻断整条反馈详情。

## 5. State transitions

```text
submitted（待处理） ───────► processing（处理中） ───────► resolved（已解决）
        │                                                     ▲
        └─────────────────────────────────────────────────────┘

processing ──► processing  （只追加内部备注，仍会 version + 1）
resolved   ──X             （终态；不重开、不追加、不删除）
```

### Transition rules

| From | To | Required | Effects |
|------|----|----------|---------|
| submitted | processing | `expectedVersion`; internalNote optional | 首次写 `first_handler_id/at`，增加 action，version + 1 |
| submitted | resolved | `expectedVersion`, `resolution` | 写解决人/时间，增加 resolve action，通知置 pending，version + 1 |
| processing | processing | `expectedVersion`, 非空 internalNote | 增加 note action，version + 1；首位处理人不变 |
| processing | resolved | `expectedVersion`, `resolution` | 写解决人/时间，增加 resolve action，通知置 pending，version + 1 |
| resolved | any | — | 拒绝，HTTP 409 |

- `UPDATE feedbacks ... WHERE id=:id AND version=:expectedVersion` 未命中时返回版本冲突，不覆盖新数据。
- 任意具有 `feedbacks.write` 的管理员都可执行允许的转换，不检查其是否为首位处理人。

## 6. Idempotency rules

### User submission

- 规范化 payload：类型归一化、content trim、imageFiles 保持顺序后计算 fingerprint。
- 首次 `(user_id, key)` 创建反馈。
- 同一 key + 同一 fingerprint：返回原反馈与原反馈编号，不新增 AuditLog 或业务记录。
- 同一 key + 不同 fingerprint：返回 HTTP 409 / code `40911`，防止未知结果重试时静默替换内容。
- 小程序对 NETWORK/TIMEOUT/SERVER/MALFORMED 结果保留同一 key 和冻结的 payload；明确校验失败后才允许重新编辑并创建新 key。

### Admin update

- `expectedVersion` 阻止重复/过期动作写入。
- 已达到相同状态且没有新备注/结果的请求视为无有效变化，返回 422，不新增 action。
- 响应丢失后的重试会得到 409 并重新拉取最新详情；页面以最新已生效结果为准。

## 7. Historical migration

Alembic `015` 的 upgrade 顺序：

1. 创建 `feedbacks` 和 `feedback_actions`、索引及约束。
2. 向 `notifications` 增加 nullable unique `feedback_id`。
3. 扫描 `audit_logs.action='feedback_submit'`，按 `source_audit_log_id` 防重复制：
   - `feedback_bug` / detail.type=bug → `bug`
   - `feedback_feature`、feature、suggestion → `suggestion`
   - 其他 → `other`
   - status → `submitted`
   - content 原样保留，不截断旧 5000 字正文；imageFiles 的对象键原样写入 `legacy=true` 的附件描述对象
   - contactAllowed 不进入新模型，但保留原 AuditLog
   - 用户存在时写快照；不存在时 user_id=NULL、姓名显示“历史用户”
4. 不删除、不更新原 AuditLog。

`downgrade()` 只能移除新增结构，无法将上线后处理状态无损还原到旧 JSON。执行 downgrade 前必须备份新表；发布手册将其标注为数据不可逆降级。

## 8. Security and audit

- 列表/详情手机号只读取 `phone_masked` 或重新按统一规则脱敏，任何响应不出现明文 phone。
- 详情读取写 `AuditLog(action='feedback_view')`，处理写 `feedback_process`；detail 只包含 `adminAccountId`、`feedbackNo`、状态、版本和文本长度，不包含正文、图片对象键、手机号、内部备注或结果全文。
- FeedbackAction.operator_id 指向 `admin_accounts.id`，不得误用只关联 `users.id` 的 `AuditLog.user_id`。
- COS 对象桶应为私有读；预览地址有效期 10 分钟。
