# Implementation Plan: 意见与反馈提交及后台管理

**Branch**: `013-feedback-management` | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/013-feedback-management/spec.md`

## Summary

将现有仅写入 `audit_logs` 的反馈提交能力升级为完整反馈业务模块：小程序继续使用现有“帮助与反馈”页面，复用头像上传的通用 COS 传输代码但改用反馈专用上传令牌，并通过持久化幂等键提交反馈；后端新增反馈主记录与不可变处理记录、历史审计反馈迁移、全局管理查询、乐观锁状态更新、短时图片预览和站内通知重试；管理端新增“意见与反馈”列表及详情处理抽屉，并使用独立的查看/处理权限控制。

技术方案保持三端分离：后端是反馈状态与权限的唯一事实来源；管理端只负责筛选、展示和提交处理动作；小程序仅补齐幂等提交、成功编号展示及既有站内通知适配。具体接口见 [contracts/api.md](./contracts/api.md)，后台交互见 [contracts/admin-page.md](./contracts/admin-page.md)。

## Technical Context

**Language/Version**: Python 3.11+（backend）；JavaScript ES Modules（manageSystem）；微信小程序 JavaScript / WXML / WXSS（miniProgram）  
**Primary Dependencies**: FastAPI、Pydantic v2、SQLAlchemy 2.0 async、Alembic、APScheduler、httpx；Vue 3、Vite、Element Plus、Axios、Pinia；微信小程序原生 SDK  
**Storage**: MySQL 8.0（反馈、处理记录、通知及审计）；腾讯云 COS（反馈图片，数据库仅存对象键）  
**Testing**: pytest + pytest-asyncio + httpx（后端）；Vitest + Vue Test Utils（管理端）；Node.js `node:test`（小程序）  
**Target Platform**: Linux API 服务；现代桌面浏览器管理后台；微信小程序 iOS/Android  
**Project Type**: Web service + admin SPA + mobile mini-program  
**Performance Goals**: 反馈提交 p95 ≤ 3 秒；10,000 条验收数据下管理列表/筛选/分页 p95 ≤ 2 秒；管理员完整处理流程 ≤ 2 分钟；站内通知 95% 在解决后 1 分钟内可见  
**Constraints**: 统一响应封装 `{code,message,data,requestId,serverTime}`；手机号统一脱敏；图片最多 3 张、仅 JPG/PNG、单图 ≤ 5 MiB；反馈原文不可编辑/删除；不新增微信订阅消息、反馈历史入口、FAQ 管理、指派、导出或批量处理  
**Scale/Scope**: 预计至少 10,000 条反馈；单条 10–500 字、0–3 张图片；三个状态；一套全局后台队列；2 个新权限；小程序 1 个既有页面最小适配

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Pre-design | Post-design | Evidence |
|-----------|------------|-------------|----------|
| I. TDD (NON-NEGOTIABLE) | PASS | PASS | 每个新/改 API 先增加合同测试，服务层先增加状态、幂等、并发、迁移和通知失败单元/集成测试；管理端与小程序先补组件/合同测试再实现。 |
| II. API-First Design | PASS | PASS | [contracts/api.md](./contracts/api.md) 先定义小程序提交、当前用户兼容查询和后台列表/详情/处理接口，全部使用 `/api/v1` 与统一响应封装。 |
| III. Separation of Concerns | PASS | PASS | 校验、权限、状态、图片访问和通知重试均在后端；管理端和小程序只做展示及表单校验，不直接访问数据库/COS 私有对象。 |
| IV. Database Integrity | PASS | PASS | Alembic `015` 管理表/索引/历史迁移；手机号只返回脱敏值；图片只返回短时预览地址；读取和处理行为写入不含正文/图片的审计记录。 |
| V. Simplicity (YAGNI) | PASS | PASS | 使用直接 service + SQLAlchemy 模型，不引入 Repository/消息队列；最多 3 个附件以内嵌 JSON 保存；站内通知复用现有 Notification 与 APScheduler。 |

**Gate result**: ALL PASS — Phase 0 and Phase 1 design may proceed. No constitutional exception requires justification.

## Project Structure

### Documentation (this feature)

```text
specs/013-feedback-management/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md
│   └── admin-page.md
├── checklists/
│   └── requirements.md
└── tasks.md                     # /speckit-tasks 生成，本阶段不创建
```

### Source Code (planned changes)

```text
backend/
├── migrations/versions/
│   └── 015_feedback_management.py       # NEW: 表、索引、权限兼容数据及历史反馈迁移
├── src/
│   ├── api/v1/
│   │   ├── feedbacks.py                 # MODIFY: 新表提交、幂等、当前用户兼容查询
│   │   └── admin_feedbacks.py           # NEW: 后台列表、详情、处理
│   ├── models/
│   │   ├── feedback.py                  # NEW: Feedback / FeedbackAction
│   │   ├── notification.py              # MODIFY: 可选 feedback_id 唯一关联
│   │   └── __init__.py                  # MODIFY: 注册新模型
│   ├── schemas/
│   │   └── feedback.py                  # NEW: 请求、筛选和响应模型
│   ├── services/
│   │   ├── feedback_service.py          # NEW: 查询、状态、幂等、迁移后序列化
│   │   └── seed_service.py              # MODIFY: feedbacks.read/write 系统权限
│   ├── integrations/
│   │   └── cos_client.py                # MODIFY: 所有权检查、对象存在检查、短时 GET URL
│   ├── tasks/
│   │   └── feedback_tasks.py            # NEW: 失败/待发送站内通知重试
│   └── main.py                           # MODIFY: 注册后台路由与 60 秒重试任务
└── tests/
    ├── contract/
    │   ├── test_feedbacks.py             # NEW/MODIFY: 小程序提交和兼容查询合同
    │   └── test_admin_feedbacks.py       # NEW: 列表、详情、权限、状态、冲突合同
    ├── unit/
    │   └── test_feedback_service.py      # NEW: 状态机、附件、幂等、通知逻辑
    └── integration/
        └── test_feedback_migration.py    # NEW: AuditLog 历史迁移完整性/幂等性

manageSystem/
└── src/
    ├── api/
    │   └── feedbacks.js                  # NEW: 后台反馈 API 客户端
    ├── pages/feedbacks/
    │   └── index.vue                     # NEW: 筛选、表格和分页
    ├── components/feedbacks/
    │   └── FeedbackDetailDrawer.vue      # NEW: 详情、图片、时间线和处理表单
    ├── router/index.js                   # MODIFY: /feedbacks + feedbacks.read
    ├── constants/permissions.js          # MODIFY: feedbacks.read/write
    └── App.vue                           # MODIFY: 权限控制的“意见与反馈”菜单
manageSystem/tests/
├── api/feedbacks.test.js                 # NEW: 查询参数、更新和响应解包
├── pages/feedbacks.test.js               # NEW: 页面状态、权限和冲突
└── router/feedbacks-permission.test.js   # NEW: 菜单/路由权限

miniProgram/
├── pages/help-feedback/index.js          # MODIFY: 请求键、成功编号、失败保留
├── services/
│   ├── cos-upload.js                     # NEW: 从头像上传抽出的通用 COS PUT 传输
│   ├── profile-service.js                # MODIFY: 头像复用通用传输
│   └── feedback-service.js               # MODIFY: 专用 token、上传和幂等提交
└── tests/
    ├── contract/feedback-api-contract.test.js  # NEW
    ├── integration/feedback-flow.test.js       # NEW
    └── unit/help-feedback.test.js              # MODIFY
```

**Structure Decision**: 沿用仓库既有三层目录，不创建第四个应用或共享包。反馈业务规则全部位于 `backend/src/services/feedback_service.py`；两端各自使用现有 HTTP 客户端。

## Implementation Sequence

1. **后端数据与合同（Red）**：先写提交、查询、权限、状态机、版本冲突、通知和历史迁移失败测试，再新增迁移、模型、schema 与 service。
2. **小程序提交闭环（Red → Green）**：先扩展服务合同测试，复用 `request-key` 为反馈生成并复用幂等键，再展示后端反馈编号；不改页面布局。
3. **后台只读队列（Red → Green）**：先写 API 客户端和列表组件测试，再实现路由、菜单、筛选、表格、分页、加载/空/错误状态。
4. **后台处理闭环（Red → Green）**：先写详情、权限、状态和 409 冲突测试，再实现详情抽屉、图片预览、内部备注和解决结果。
5. **通知与迁移验收**：验证历史 `feedback_submit` 审计记录 100% 可见、站内通知按用户隔离、失败任务可重试且不回滚已解决状态。
6. **全量回归**：依次运行后端反馈测试、后端全量测试、管理端测试/构建、小程序测试，并按 quickstart 完成人工联调。

## Complexity Tracking

*(No violations — table intentionally empty.)*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
