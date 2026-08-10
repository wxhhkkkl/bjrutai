# Tasks: 意见与反馈提交及后台管理

**Input**: Design documents from `/specs/013-feedback-management/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 本项目 Constitution 强制 TDD。每个用户故事的测试任务必须先执行并确认因缺少目标能力而失败，再开始对应实现任务。

**Organization**: 任务按用户故事分组；后端是反馈状态、权限和附件访问的唯一事实来源，管理后台与小程序不得自行推断或改写后端业务规则。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 在前置依赖完成后，可与同阶段其他标记任务并行，且不会修改同一文件
- **[Story]**: 对应 `spec.md` 中的用户故事（US1–US4）
- 每项任务均包含明确的仓库相对路径

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 固定实施基线，避免把现有失败误判为本功能回归。

- [ ] T001 在修改业务代码前运行现有反馈、通知、管理端构建和小程序测试基线，并将仅与本机环境有关的偏差记录到 `specs/013-feedback-management/quickstart.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立四个用户故事共同依赖的数据结构、历史迁移和权限定义。

**⚠️ CRITICAL**: 本阶段完成前不得开始任一用户故事的实现。

### Foundational tests (write and fail first)

- [ ] T002 [P] 为 `feedbacks`、`feedback_actions`、`notifications.feedback_id`、历史 AuditLog 复制、类型归一化、长正文保留和迁移幂等编写失败集成测试 `backend/tests/integration/test_feedback_migration.py`
- [ ] T003 [P] 为系统管理员自动同步 `feedbacks.read` 与 `feedbacks.write` 编写失败测试 `backend/tests/integration/test_seed.py`

### Foundational implementation

- [X] T004 实现 Alembic `015` 表结构、索引、外键、历史反馈/附件描述迁移和可逆结构降级 `backend/migrations/versions/015_feedback_management.py`
- [X] T005 [P] 创建 Feedback、FeedbackAction、状态枚举、附件描述和数据库约束模型 `backend/src/models/feedback.py`
- [X] T006 注册 Feedback 模型并为 Notification 增加唯一可空 `feedback_id` 关联 `backend/src/models/__init__.py`、`backend/src/models/notification.py`
- [X] T007 将 `feedbacks.read`、`feedbacks.write` 加入系统管理员幂等权限同步并通过 seed 测试 `backend/src/services/seed_service.py`

**Checkpoint**: 迁移可升级，历史反馈 100% 复制且原 AuditLog 不变，模型和系统权限可供所有故事复用。

---

## Phase 3: User Story 1 - 小程序用户提交意见与反馈 (Priority: P1) 🎯 MVP

**Goal**: 用户可提交 10–500 字、0–3 张反馈截图，获得稳定反馈编号；重复点击或未知结果重试只创建一条反馈。

**Independent Test**: 使用已登录用户分别提交无图和三图反馈，验证专用附件路径、归属/格式/存在性校验、反馈编号和待处理状态；模拟响应丢失后用同一 Idempotency-Key 重试，数据库仍只有一条记录且草稿未清空。

### Tests for User Story 1 (write and fail first)

- [ ] T008 [P] [US1] 为反馈上传令牌、提交、用户列表、统一响应、边界校验、附件越权和 Idempotency-Key 隔离编写失败合同测试 `backend/tests/contract/test_feedbacks.py`
- [ ] T009 [P] [US1] 为 payload 规范化、fingerprint、同键同响应、同键异内容 40911、反馈编号和附件描述编写失败单元测试 `backend/tests/unit/test_feedback_service.py`
- [ ] T010 [P] [US1] 为反馈 token、COS PUT 和带 Idempotency-Key 的提交请求编写失败客户端合同测试 `miniProgram/tests/contract/feedback-api-contract.test.js`
- [ ] T011 [P] [US1] 为上传中禁用、失败保留草稿、重复点击防护、类型映射和成功编号弹窗编写失败页面测试 `miniProgram/tests/unit/help-feedback.test.js`
- [ ] T012 [P] [US1] 为图片上传、响应丢失、冻结 payload 和复用请求键重试编写失败流程测试 `miniProgram/tests/integration/feedback-flow.test.js`

### Implementation for User Story 1

- [X] T013 [US1] 定义反馈上传、创建、当前用户列表及统一响应 schema，兼容旧 `feature` 输入但不再输出 `contactAllowed` `backend/src/schemas/feedback.py`
- [X] T014 [P] [US1] 为反馈生成 `feedbacks/{user_id}/` 私有对象键，校验 JPG/PNG 与 5 MiB，并增加 COS HEAD 和短时签名基础能力 `backend/src/integrations/cos_client.py`
- [X] T015 [US1] 实现反馈创建、持久化幂等、附件归属/重复/存在性校验、反馈编号和当前用户游标列表 `backend/src/services/feedback_service.py`
- [X] T016 [US1] 将现有 AuditLog 提交端点替换为 service 驱动的反馈上传、提交和当前用户查询接口 `backend/src/api/v1/feedbacks.py`
- [X] T017 [P] [US1] 将内存幂等缓存作用域收紧为方法、路径、认证主体摘要和请求键，避免跨用户/接口串用响应 `backend/src/main.py`
- [X] T018 [P] [US1] 抽取通用微信图片元数据与 COS PUT 传输器并让头像上传继续复用 `miniProgram/services/cos-upload.js`、`miniProgram/services/profile-service.js`
- [X] T019 [US1] 使用反馈专用上传令牌、通用 COS 传输器和 request-service 幂等头实现反馈客户端 `miniProgram/services/feedback-service.js`
- [X] T020 [US1] 将反馈页切换到专用图片上传，管理冻结 payload/request key、失败草稿保留并在成功弹窗展示反馈编号 `miniProgram/pages/help-feedback/index.js`
- [ ] T021 [US1] 运行 US1 后端、小程序合同/单元/流程测试并按独立验收场景核对结果 `backend/tests/contract/test_feedbacks.py`、`backend/tests/unit/test_feedback_service.py`、`miniProgram/tests/contract/feedback-api-contract.test.js`、`miniProgram/tests/integration/feedback-flow.test.js`

**Checkpoint**: US1 可独立作为 MVP 交付；后台尚未实现时也能通过数据库和用户兼容查询确认反馈只创建一次。

---

## Phase 4: User Story 2 - 管理员查看与筛选反馈 (Priority: P1)

**Goal**: 具备查看权限的管理员可在全局列表中筛选、搜索、分页并打开含原文、脱敏用户、短时图片和时间线的详情。

**Independent Test**: 准备跨组织、不同类型/日期/状态及历史迁移反馈，验证全局倒序列表、组合条件、编号/姓名搜索、稳定分页、短时图片、附件不可用占位、详情访问审计和无权限 403。

### Tests for User Story 2 (write and fail first)

- [ ] T022 [P] [US2] 为后台全局列表、组合筛选、稳定分页、详情、脱敏、短时附件、历史记录和 read 权限编写失败合同测试 `backend/tests/contract/test_admin_feedbacks.py`
- [ ] T023 [P] [US2] 为列表参数、详情路径、统一响应解包和错误转换编写失败 API 客户端测试 `manageSystem/tests/api/feedbacks.test.js`
- [ ] T024 [P] [US2] 为加载/空/错误状态、筛选重置、分页保持、只读详情和不可用附件编写失败页面测试 `manageSystem/tests/pages/feedbacks.test.js`
- [ ] T025 [P] [US2] 为侧栏和 `/feedbacks` 路由的 `feedbacks.read` 守卫编写失败权限测试 `manageSystem/tests/router/feedbacks-permission.test.js`

### Implementation for User Story 2

- [X] T026 [US2] 扩展列表筛选、分页、提交人脱敏、详情附件和处理时间线响应 schema `backend/src/schemas/feedback.py`
- [X] T027 [US2] 实现无组织过滤的后台查询、稳定排序、姓名/编号搜索、手机号脱敏、短时预览和不含敏感内容的详情访问审计 `backend/src/services/feedback_service.py`
- [X] T028 [US2] 实现受 `feedbacks.read` 保护的后台列表/详情端点并注册路由 `backend/src/api/v1/admin_feedbacks.py`、`backend/src/main.py`
- [X] T029 [P] [US2] 实现后台反馈 list/detail/update API 封装与统一错误解包 `manageSystem/src/api/feedbacks.js`
- [X] T030 [P] [US2] 在权限模块中加入反馈查看和处理权限供角色管理复用 `manageSystem/src/constants/permissions.js`
- [X] T031 [US2] 注册带 `feedbacks.read` meta 的 `/feedbacks` 路由 `manageSystem/src/router/index.js`
- [X] T032 [US2] 添加仅在拥有 `feedbacks.read` 时显示的“意见与反馈”侧栏入口 `manageSystem/src/App.vue`
- [X] T033 [US2] 实现筛选区、全局列表、状态标签、摘要、加载/空/错误状态和稳定分页 `manageSystem/src/pages/feedbacks/index.vue`
- [X] T034 [US2] 实现只读详情抽屉、原文换行、脱敏提交人、短时图片预览、附件不可用占位和时间线 `manageSystem/src/components/feedbacks/FeedbackDetailDrawer.vue`
- [ ] T035 [US2] 运行 US2 后端合同、管理端 API/页面/路由测试和管理端构建并按独立验收场景核对 `backend/tests/contract/test_admin_feedbacks.py`、`manageSystem/tests/api/feedbacks.test.js`、`manageSystem/tests/pages/feedbacks.test.js`、`manageSystem/tests/router/feedbacks-permission.test.js`

**Checkpoint**: 只读管理员可以独立完成全局定位和查看反馈；无查看权限无法从菜单、路由或 API 获取数据。

---

## Phase 5: User Story 3 - 管理员查看详情并处理反馈 (Priority: P1)

**Goal**: 具备处理权限的任意管理员可将待处理反馈置为处理中或已解决，追加备注并留下不可覆盖的完整操作记录。

**Independent Test**: 两名管理员同时打开反馈，A 先更新后 B 的旧版本请求返回 40910 且不覆盖；B 刷新后可继续处理并解决，首位处理人不变，实际操作人、状态、备注和用户结果均按顺序留痕；只读管理员无法写入。

### Tests for User Story 3 (write and fail first)

- [ ] T036 [P] [US3] 为状态机、首位处理人、跨管理员接续、追加动作、终态、expectedVersion 和通知 pending 边界编写失败单元测试 `backend/tests/unit/test_feedback_service.py`
- [ ] T037 [P] [US3] 为 PATCH 权限、字段校验、允许/禁止转换、40910 和不可变原反馈编写失败合同测试 `backend/tests/contract/test_admin_feedbacks.py`
- [ ] T038 [P] [US3] 为 read/write 分离、处理表单、成功刷新、保存禁用和 409 拉新不重放编写失败组件测试 `manageSystem/tests/pages/feedbacks.test.js`

### Implementation for User Story 3

- [X] T039 [US3] 实现条件版本更新、三状态转换、首位/实际处理人、不可变 FeedbackAction、处理审计和 resolved 通知 pending 状态 `backend/src/services/feedback_service.py`
- [X] T040 [US3] 实现受 `feedbacks.write` 保护的 PATCH 端点、422 字段映射和 40910 当前版本响应 `backend/src/api/v1/admin_feedbacks.py`
- [X] T041 [US3] 在详情抽屉实现按权限/状态派生的内部备注与用户结果表单、expectedVersion 提交、终态只读和冲突恢复 `manageSystem/src/components/feedbacks/FeedbackDetailDrawer.vue`
- [X] T042 [US3] 在保存成功或冲突后保持筛选/页码刷新当前列表，并协调抽屉最新详情 `manageSystem/src/pages/feedbacks/index.vue`
- [ ] T043 [US3] 运行 US3 服务、合同和管理端组件测试，并用双管理员场景核对动作时间线和无覆盖行为 `backend/tests/unit/test_feedback_service.py`、`backend/tests/contract/test_admin_feedbacks.py`、`manageSystem/tests/pages/feedbacks.test.js`

**Checkpoint**: 后台处理闭环完成；任意有写权限的管理员可接续处理，但过期版本不能覆盖其他管理员结果。

---

## Phase 6: User Story 4 - 用户收到反馈处理结果通知 (Priority: P2)

**Goal**: 反馈解决后向原用户创建一条仅站内可见的系统通知；发送失败不回滚解决状态，并可自动补偿且不重复。

**Independent Test**: 解决反馈后原用户消息中心显示反馈编号、类型、用户结果和解决时间，target 为空且不展示内部备注；模拟首次创建失败后反馈仍为已解决，补偿成功只生成一条通知，其他用户不可见。

### Tests for User Story 4 (write and fail first)

- [ ] T044 [P] [US4] 为立即通知、失败状态、退避时间、重复补偿、用户删除和唯一冲突收敛编写失败单元测试 `backend/tests/unit/test_feedback_service.py`
- [ ] T045 [P] [US4] 为反馈系统通知内容、用户隔离、空 target、已读和内部备注不泄露编写失败合同测试 `backend/tests/contract/test_notifications.py`
- [ ] T046 [P] [US4] 为 system 类反馈通知纯文本展示、空 target 不跳转和标记已读编写失败小程序测试 `miniProgram/tests/unit/notification.test.js`

### Implementation for User Story 4

- [X] T047 [US4] 实现反馈通知创建、pending/failed/sent 状态、1m/5m/30m/1h/每小时退避和 `notifications.feedback_id` 冲突收敛任务 `backend/src/tasks/feedback_tasks.py`
- [X] T048 [US4] 注册每 60 秒反馈通知补偿任务并设置 coalesce、max_instances=1 `backend/src/main.py`
- [ ] T049 [US4] 运行通知服务、通知合同和小程序现有消息中心测试，并模拟首次失败后补偿成功 `backend/tests/unit/test_feedback_service.py`、`backend/tests/contract/test_notifications.py`、`miniProgram/tests/unit/notification.test.js`

**Checkpoint**: 解决通知只在现有小程序消息中心显示，不请求或发送微信订阅消息，通知异常不影响反馈处理结果。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 验证性能、安全、迁移和三端完整联调，不扩展本迭代范围。

- [ ] T050 [P] 使用至少 10,000 条反馈验证列表/组合筛选/分页 p95 ≤ 2 秒并补充索引回归测试 `backend/tests/performance/test_feedbacks.py`
- [ ] T051 [P] 增加敏感信息回归检查，确保普通日志和 AuditLog 不包含正文、对象键、手机号明文、内部备注或处理结果全文 `backend/tests/integration/test_feedback_audit_security.py`
- [ ] T052 执行迁移升级与历史数量核对、后端全量 pytest、管理端 Vitest/build、小程序全量 node:test，并把实际命令或环境差异更新到 `specs/013-feedback-management/quickstart.md`
- [ ] T053 按无图/有图、幂等重试、读写权限、双管理员并发、通知补偿和历史反馈场景完成人工联调验收 `specs/013-feedback-management/quickstart.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup**: 无依赖，可立即开始。
- **Phase 2 Foundational**: 依赖 Phase 1，阻塞全部用户故事。
- **US1 (Phase 3)** 与 **US2 (Phase 4)**: 均依赖 Foundational；使用测试数据时可并行推进。
- **US3 (Phase 5)**: 依赖 US2 的后台详情/API 基础；可使用迁移测试记录，不要求 US1 页面已完成。
- **US4 (Phase 6)**: 依赖 US3 的 resolved 状态事务，并依赖 US1 的用户归属语义。
- **Polish (Phase 7)**: 依赖计划交付的全部用户故事。

### User story dependency graph

```text
Setup → Foundational ─┬→ US1 用户提交 ─────────┐
                     └→ US2 后台查看 → US3 处理 ┴→ US4 站内通知 → Polish
```

### Within each user story

1. 先创建测试并确认按预期失败。
2. schema/模型和外部存储适配先于 service。
3. service 先于 API/页面集成。
4. 后端契约通过后再以其为准连接管理后台或小程序；前端不得为规避错误自行改变状态机或字段语义。
5. 完成该故事的 focused tests 和 Independent Test 后才进入下一个依赖故事。

### Parallel opportunities

- Foundational 中 T002、T003、T005 修改不同文件，可并行。
- US1 的五项 Red 测试 T008–T012 可并行；T014、T017、T018 在测试固定后可并行。
- US2 的四项 Red 测试 T022–T025 可并行；T029 与 T030 可并行。
- US3 的 Red 测试 T036–T038 可并行。
- US4 的 Red 测试 T044–T046 可并行。
- Polish 的性能测试 T050 与安全测试 T051 可并行。

---

## Parallel Examples

### User Story 1

```text
并行：T008 backend contract、T009 backend unit、T010 mini contract、T011 mini unit、T012 mini integration
随后并行：T014 COS adapter、T017 idempotency scope、T018 mini generic COS transport
```

### User Story 2

```text
并行：T022 backend admin contract、T023 admin API test、T024 admin page test、T025 router permission test
随后并行：T029 admin API client、T030 permission constants
```

### User Story 3

```text
并行：T036 backend state-machine unit、T037 backend PATCH contract、T038 admin drawer test
串行收敛：T039 service → T040 endpoint → T041 drawer → T042 list coordination
```

### User Story 4

```text
并行：T044 retry unit、T045 notification contract、T046 mini notification test
串行收敛：T047 retry task → T048 scheduler registration → T049 focused validation
```

---

## Implementation Strategy

### MVP first: User Story 1

1. 完成 Setup 与 Foundational。
2. 完成 US1 的 Red → Green 任务。
3. 停止并独立验证无图、有图和幂等重试。
4. 后台尚未交付时，可通过用户兼容查询和数据库验证唯一反馈记录。

### Incremental delivery

1. **US1**: 可靠提交和反馈编号。
2. **US2**: 全局只读管理队列和详情。
3. **US3**: 多管理员处理闭环与并发保护。
4. **US4**: 站内结果通知和补偿。
5. **Polish**: 10,000 条性能、安全、历史迁移和完整联调。

### Scope guardrails

- 不修改微信订阅消息、不恢复反馈历史入口或联系客服。
- 不增加 FAQ 后台、组织范围过滤、指派/领取、独占锁、重开、删除、导出或批量处理。
- 原反馈类型、正文和截图不可由管理员修改；只允许追加处理动作。
- 发现前后端契约不匹配时以 `specs/013-feedback-management/contracts/api.md` 为评审依据，未经确认不改变后端既有领域逻辑。

---

## Notes

- `[P]` 只表示在对应前置依赖完成后可并行，不表示可以跳过依赖。
- 每个故事的测试任务必须先失败，再实现并转绿。
- 每完成一个 Checkpoint 都可独立演示和提交。
- 禁止在 console、普通日志、错误消息或 AuditLog.detail 中复制反馈敏感内容。
