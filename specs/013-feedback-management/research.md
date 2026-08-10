# Research: 意见与反馈提交及后台管理

**Feature**: 013-feedback-management  
**Date**: 2026-08-10

## R1: 反馈业务数据不能继续只存 AuditLog

**Decision**: 新增 `feedbacks` 主表和 `feedback_actions` 不可变处理记录表；`AuditLog` 仅继续承担安全审计，不再作为反馈业务事实来源。

**Rationale**:
- 现有 `feedbacks.py` 将正文和图片放在 `audit_logs.detail`，状态永远返回 `submitted`，无法稳定筛选、分页、并发更新或生成处理时间线。
- 独立主表提供当前状态，动作表保留每次变化，查询成本与职责清晰。
- 用户原始反馈不允许修改/删除，正适合“主记录 + 追加动作”的模型。

**Alternatives considered**:
1. 继续更新 `audit_logs.detail`：JSON 状态筛选与并发控制困难，且混淆审计和业务数据。
2. 只建 `feedbacks`、不建动作表：无法满足不可覆盖的完整处理轨迹。
3. 为附件和通知各建独立业务表：当前附件最多 3 张、通知一对一，超出本迭代需要。

## R2: 历史反馈采用迁移复制，保留原审计记录

**Decision**: Alembic `015` 创建新表后，将 `audit_logs.action='feedback_submit'` 的记录复制到 `feedbacks`；保留原审计行，通过 `source_audit_log_id` 唯一关联保证可追溯和幂等。

**Rationale**:
- 满足历史数据保留率 100%，且不会破坏既有审计证据。
- 历史 `entity_id` 继续作为反馈编号；类型 `feature` 归一化为 `suggestion`，其他未知类型归为 `other`；状态统一为 `submitted`。
- 历史正文即使超过新提交的 500 字限制也原样保留，新限制只约束新请求。

**Alternatives considered**:
1. 后台同时查询新表和 AuditLog：永久双读使筛选、分页、总数和状态更新复杂。
2. 删除/改写 AuditLog：破坏审计完整性。
3. 忽略历史数据：违反 FR-007 与 SC-008。

## R3: 附件以内嵌 JSON 保存，并复用头像上传的通用传输能力

**Decision**: `feedbacks.image_files` 保存最多 3 个附件描述对象（COS 对象键、MIME、历史标记）；小程序从头像上传中抽取通用 COS PUT 传输器，头像仍使用 `/me/avatar/upload-token`，反馈使用现有 `/feedback-files/upload-token`。反馈接口生成 `feedbacks/{user_id}/...` 对象键并限制 JPG/PNG、单图 5 MiB；提交时后端校验用途/所有权前缀、唯一性、格式及对象存在性，再把客户端的 fileId 解析为内部描述对象；后台详情只返回短时签名预览 URL。

**Rationale**:
- 用户已明确要求复用头像上传能力；复用通用图片元数据读取与 COS PUT 代码即可避免两套传输实现，同时保留头像/反馈各自的业务用途边界。
- 附件没有独立生命周期、数量固定且很小，JSON 比附件表更简单。
- 数据库存内部附件描述而非永久公开 URL，便于权限校验、历史附件兼容和短时访问。
- 后端对象存在检查避免“取得上传凭据但未完成上传”产生损坏附件。

**Alternatives considered**:
1. 继续直接使用 `/me/avatar/upload-token`：截图落在头像目录，无法可靠验证业务用途。
2. 保存本地临时路径：跨设备无效。
3. 返回永久 COS 公网 URL：不能满足仅授权管理员访问截图的隐私要求。
4. 独立 `feedback_attachments` 表：当前无独立编辑、删除、标签或生命周期需求。

## R4: 使用业务表持久化幂等，而非只依赖现有内存中间件

**Decision**: `POST /feedbacks` 强制要求 `Idempotency-Key`；`feedbacks` 对 `(user_id, idempotency_key)` 建唯一约束。重复请求返回首次创建的同一反馈，不再次写记录；同时将现有内存中间件缓存键从裸请求键收紧为“HTTP 方法 + 路径 + 认证主体摘要 + 请求键”，防止跨用户或跨接口串用响应。

**Rationale**:
- 小程序 `request-service` 和 `request-key` 已支持幂等键，可直接复用。
- 现有 `IdempotencyMiddleware` 使用进程内字典，重启、多 worker 和多实例时无法保证幂等，且原始键没有用户/路径范围。
- 业务唯一约束可跨进程可靠工作，并自然限定在当前用户。
- 中间件收紧只修复当前安全边界，不把本功能扩展为全局持久化幂等改造。

**Alternatives considered**:
1. 只复用内存中间件：生产可靠性不足。
2. 改造全局幂等中间件：影响所有写接口，超出本功能范围。
3. 仅在小程序禁用按钮：无法覆盖响应丢失后的重试。

## R5: 三状态 + version 乐观锁

**Decision**: 数据库存储 `submitted`、`processing`、`resolved`；响应分别展示“待处理”“处理中”“已解决”。每次有效管理更新携带 `expectedVersion`，使用条件更新并令 `version + 1`；版本过期返回 HTTP 409 / code 40910。

**Rationale**:
- 状态值兼容现有提交接口的 `submitted`，同时满足规格三状态。
- 反馈处理冲突概率低，乐观锁比数据库长事务或独占锁简单。
- 所有有处理权限的管理员仍可协作，只阻止覆盖过期数据。
- 已解决状态为终态；不支持重开、删除或继续追加备注。

**Alternatives considered**:
1. 悲观行锁贯穿管理员编辑：无法跨浏览器交互持有事务，且形成事实独占。
2. 最后写入覆盖：会丢失另一管理员的处理结果。
3. 指派/领取队列：规格明确不做指派和独占。

## R6: 站内通知使用轻量 outbox 状态和定时补偿

**Decision**: 反馈解决事务只将 `notification_status` 置为 `pending` 并提交；提交后立即尝试创建 `Notification(category=system, feedback_id=...)`。成功置 `sent`，失败置 `failed`；APScheduler 每 60 秒扫描到达 `notification_next_retry_at` 的记录，并按 1 分钟、5 分钟、30 分钟、1 小时后每小时的节奏持续补偿。`notifications.feedback_id` 唯一约束防止重复消息；通知 target 为空，用户直接在消息卡片阅读结果，不跳回反馈表单。

**Rationale**:
- 已确认只使用站内通知，不需要微信订阅授权、模板或外部消息服务。
- 先提交解决结果，再创建通知，满足通知失败不回滚反馈状态。
- 现有 Notification、消息中心和 APScheduler 均可复用，不引入消息队列。
- 唯一反馈外键使立即发送与重试并发时仍只生成一条消息。

**Alternatives considered**:
1. 同一事务直接创建通知：简单，但通知写入异常会回滚已解决状态，违反 FR-020。
2. 引入 Redis/Celery/Kafka：当前规模和单一站内通知不需要。
3. 微信订阅消息：澄清已明确排除。
4. 新增 `feedback` 通知枚举和小程序筛选项：规格只要求站内消息可读，复用 `system` 可避免额外枚举迁移和前端筛选改造。

## R7: 管理端采用单页列表 + 详情处理抽屉

**Decision**: 新建 `pages/feedbacks/index.vue`，页面本地维护筛选/分页状态，详情与处理放在右侧抽屉；API 封装在 `api/feedbacks.js`，不新增 Pinia store。

**Rationale**:
- 反馈管理是单页面、无跨路由共享状态，页面本地状态更简单。
- 抽屉允许管理员保留列表筛选上下文，同时展示全文、图片和时间线。
- 复用 Element Plus 现有表格、标签、日期选择、图片预览、抽屉和表单。

**Alternatives considered**:
1. 独立详情路由：需要额外路由和状态恢复，当前信息量不需要。
2. 新增 Pinia store：没有跨页面消费者。
3. 行内展开全文/处理：截图、时间线和处理表单会使表格过于拥挤。

## R8: 权限使用 feedbacks.read / feedbacks.write 全局队列

**Decision**: 新增 `feedbacks.read` 与 `feedbacks.write`；路由、API 与按钮分别校验。系统管理员 seed 自动包含两项；其他角色由角色管理配置。拥有 read 权限即看到全部组织用户反馈。

**Rationale**:
- 与现有 `customers.read/write`、`articles.read/write` 命名一致。
- 澄清已确认不按组织范围隔离，后端查询无需组织过滤。
- 前端隐藏只是体验，后端 `require_permission` 才是安全边界。

**Alternatives considered**:
1. 复用 `notifications.*`：反馈管理与消息发送职责不同。
2. 只使用管理员角色：无法支持只读运营账号。
3. 按组织子树过滤：与澄清结论冲突，且现有 AdminAccount 无组织范围关联。

## R9: 敏感内容最小化日志与访问审计

**Decision**: 列表只返回 100 字以内摘要和脱敏手机号；详情正文/短时图片只返回有 `feedbacks.read` 权限的管理员。每次详情读取与处理动作写 AuditLog，但 detail 仅含管理员 ID、反馈 ID、状态与结果长度，不复制正文、图片键、手机号或备注。

**Rationale**:
- 反馈正文和截图可能包含用户主动填写的身份信息。
- Constitution 要求敏感访问可审计，同时禁止在普通日志扩散敏感值。
- FeedbackAction 负责业务时间线，AuditLog 负责安全访问证据，二者职责不同。

**Alternatives considered**:
1. 在审计 detail 保存完整请求：增加敏感信息副本和泄露面。
2. 不记录详情读取：不满足敏感访问审计原则。

## R10: 本迭代不新增反馈专用限流

**Decision**: 依赖登录鉴权、页面防重复、持久化幂等和现有全局基础设施；暂不扩展当前只覆盖认证接口的 RateLimitMiddleware。

**Rationale**:
- 规格未定义每日提交配额，擅自限流可能阻断合法反馈。
- 已登录用户可追踪，幂等约束能消除重复点击造成的数据膨胀。
- 若上线监控发现滥用，再单独明确产品配额和多实例限流方案。

**Alternatives considered**:
1. 固定每用户每天 5/10 条：缺少产品依据。
2. 复用按 IP 的认证限流：共享网络下会误伤多个用户，且多进程不一致。
