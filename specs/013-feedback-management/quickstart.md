# Quickstart: 意见与反馈提交及后台管理

**Feature**: 013-feedback-management  
**Date**: 2026-08-10

## 1. Prerequisites

- 当前分支：`013-feedback-management`。
- Backend 使用测试/开发数据库，不直接在未备份的生产数据库尝试迁移。
- `.env` 已配置数据库和腾讯 COS；COS 桶应为私有读，并允许预签名 PUT/GET/HEAD。
- 微信开发者工具已配置小程序 API base URL 和“不校验合法域名”或对应开发域名。
- 管理员重新登录以获得新增的 `feedbacks.read` / `feedbacks.write` JWT 权限。

## 2. Database migration

```bash
cd backend
alembic current
alembic upgrade head
```

预期 head 为 `015`。迁移后验证：

```sql
SELECT COUNT(*) AS feedback_count FROM feedbacks;
SELECT COUNT(*) AS legacy_feedback_count
FROM feedbacks
WHERE source_audit_log_id IS NOT NULL;

SELECT COUNT(*) AS old_audit_count
FROM audit_logs
WHERE action = 'feedback_submit';
```

第二个数量应等于旧审计反馈数量；原 AuditLog 数量不应减少。历史正文不因新 500 字规则被截断。

> `downgrade` 无法无损恢复上线后新增的处理状态和动作。对已有业务数据执行降级前必须备份 `feedbacks`、`feedback_actions` 及反馈关联通知。

## 3. Focused TDD checks

### Backend

```bash
cd backend
pytest tests/unit/test_feedback_service.py -v
pytest tests/contract/test_feedbacks.py tests/contract/test_admin_feedbacks.py -v
pytest tests/integration/test_feedback_migration.py -v
```

重点验证：

- 10/500 字边界、三种类型、最多三图、5 MiB 图片令牌。
- 图片用途/当前用户归属/COS HEAD 校验。
- 相同提交 key 同响应、不同 payload 返回 40911、不同用户 key 隔离。
- `feedbacks.read/write` 分离、全局列表、手机号脱敏。
- 三状态、跨管理员继续处理、version 409、不重复动作。
- resolved 成功后通知异常不回滚，任务补发不重复通知。
- AuditLog 不包含正文、附件、手机号、内部备注或结果全文。

### Admin frontend

```bash
cd manageSystem
npm test -- --run \
  tests/api/feedbacks.test.js \
  tests/pages/feedbacks.test.js \
  tests/router/feedbacks-permission.test.js
npm run build
```

### Mini-program

```bash
cd miniProgram
node --test \
  tests/unit/help-feedback.test.js \
  tests/contract/feedback-api-contract.test.js \
  tests/integration/feedback-flow.test.js \
  tests/unit/notification.test.js
```

## 4. Start local services

### Backend

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### Admin

```bash
cd manageSystem
npm run dev
```

打开管理端，使用含反馈权限的管理员重新登录。

### Mini-program

在微信开发者工具中打开 `miniProgram/`，重新编译。无需再次“构建 npm”，除非依赖文件本身发生变化。

## 5. Manual end-to-end acceptance

### A. Submit without images

1. 小程序进入“我的—帮助与反馈”。
2. 选择“产品建议”，输入 10–500 字，点击提交。
3. 确认提交按钮不会重复触发，并在成功弹窗看到反馈编号。
4. 管理端打开“意见与反馈”，确认该反馈位于全局列表顶部，手机号为脱敏值。

### B. Submit with images

1. 选择 1–3 张 JPG/PNG，每张不超过 5 MiB。
2. 上传期间点击提交应被阻止；上传全部完成后再提交。
3. 管理端详情抽屉可预览短时签名图片；刷新详情后可获得新的有效预览地址。
4. 超过三张、错误格式、其他用户 fileId 或只取 token 未 PUT 的对象均应被服务端拒绝。

### C. Idempotent retry

1. 在提交请求发出后模拟响应丢失或超时。
2. 页面保留并冻结原草稿，点击重试复用同一 Idempotency-Key。
3. 管理端和数据库只存在一条反馈，成功结果返回同一反馈编号。

### D. Read/write permissions

1. 使用只有 `feedbacks.read` 的管理员：可查看所有组织反馈和详情，但没有处理表单。
2. 使用 `feedbacks.read + feedbacks.write`：可置为处理中、追加备注、解决。
3. 使用无 read 的管理员：无侧栏入口，直接访问 `/feedbacks` 被路由守卫拦截，API 返回 40300。

### E. Concurrent handling

1. 两名有写权限的管理员同时打开同一反馈。
2. 管理员 A 先保存“处理中”。
3. 管理员 B 用旧 version 保存，应收到 409 并自动刷新，不覆盖 A。
4. B 基于最新详情可继续处理并解决；时间线分别记录 A、B。

### F. Resolution notification

1. 管理员填写用户可见结果并标记已解决。
2. 小程序用户进入消息中心，看到系统通知，内容包含反馈编号、类型、结果和解决时间。
3. 点击通知只标记已读，不跳回反馈提交页；通知不显示内部备注。
4. 模拟首次通知创建失败，反馈仍保持已解决；补偿任务成功后只出现一条通知。

### G. Historical feedback

1. 找到迁移前 `audit_logs.feedback_submit` 的反馈编号或提交用户。
2. 后台可以搜索并打开该记录。
3. 历史类型被正确归一化，长正文未截断；旧附件缺失时只显示“附件不可用”，不影响其他内容。

## 6. Full regression

```bash
cd backend
pytest -q

cd ../manageSystem
npm test -- --run
npm run build

cd ../miniProgram
node --test tests/unit/*.test.js tests/contract/*.test.js tests/integration/*.test.js
```

若任何必需检查失败，不进入合并；记录具体失败命令、错误和未验证环境。

## 7. Operational checks

- 观察反馈提交错误率、管理列表 p95、409 冲突数、`notification_status=failed` 数量和最老 pending 时长。
- 日志抽查不得出现反馈正文、COS 对象键、手机号明文、内部备注或用户结果全文。
- 多 worker 部署时确认 `notifications.feedback_id` 唯一约束和冲突收敛逻辑生效，不产生重复消息。
