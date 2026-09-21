# Tasks: 文章评论、点赞与评论管理

**Input**: Design documents from `/specs/020-article-comments/`  
**Prerequisites**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`

**执行规则**：严格遵循 TDD。每个测试任务都必须先写测试并运行确认失败，再实现对应代码；完成一个用户故事后运行该故事的独立验收测试。所有任务默认在当前 `020-article-comments` 分支执行，不在本阶段提交或合并主干。

> 实施进度（2026-09-21）：Phase 1–2、US1–US4 的后端接口、审查、点赞、清理、小程序评论区和管理后台页面已实现并通过对应回归测试；Phase 7 的性能专项与提交发布仍需在发布前单独确认。

## Phase 1: Setup（测试骨架与基线）

**目的**：准备评论功能的测试入口和统一 fixture，不增加新的运行时依赖。

- [x] T001 [P] 建立后端评论测试 fixture：在 `backend/tests/conftest.py` 增加已发布文章、登录小程序用户、后台只读/可写管理员和时钟注入 fixture；不得写入真实手机号或完整评论正文日志。
- [x] T002 [P] 建立小程序评论测试桩：在 `miniProgram/tests/unit/comment.test.js`、`miniProgram/tests/contract/comment-api-contract.test.js`、`miniProgram/tests/integration/article-comments-flow.test.js` 创建失败占位测试和请求 mock，覆盖 token、cursor、幂等键及统一响应封装。
- [x] T003 [P] 建立管理后台评论测试入口：在 `manageSystem/src/pages/comments/__tests__/index.spec.js` 和 `manageSystem/src/api/__tests__/comments.spec.js` 创建权限、筛选、动作和错误状态的失败占位测试。
- [x] T004 运行现有后端、管理后台和小程序基线测试并记录结果，确保新测试失败原因来自未实现评论功能，而不是现有环境故障。

## Phase 2: Foundational（共享数据、权限和维护能力）

**目的**：完成所有用户故事依赖的数据库、RBAC、统一 schema 和清理基础；本阶段结束前不进入前端故事实现。

### 先写测试（必须先失败）

- [x] T005 [P] 在 `backend/tests/unit/test_comment_models.py` 增加模型约束测试：点赞唯一键、计数非负、评论状态/置顶语义、版本递增和删除级联。
- [x] T006 [P] 在 `backend/tests/integration/test_comment_migration.py` 增加 Alembic `020` 升级/回滚检查，验证三张表、索引、外键和唯一约束。
- [x] T007 [P] 在 `backend/tests/contract/test_admin_comments.py` 增加 `comments.read` / `comments.write` 的权限拒绝测试，覆盖 JWT 无权限、过期 token 和系统管理员完整权限。
- [x] T008 [P] 在 `backend/tests/integration/test_comment_cleanup.py` 增加删除后第 7 天保留、第 8 天清理、非删除评论不清理和 AuditLog 不删除的失败测试。

### 实现基础能力

- [x] T009 [P] 创建 `backend/migrations/versions/020_article_comments.py`，新增 `article_comments`、`comment_likes`、`comment_actions`，建立文章/用户/管理员外键、cursor 查询索引、点赞唯一键及 `deleted_at` 清理所需索引。
- [x] T010 [P] 创建 `backend/src/models/article_comment.py`、`backend/src/models/comment_like.py`、`backend/src/models/comment_action.py`，实现状态常量、关系、时间字段、非负计数和版本字段，并在 `backend/src/models/__init__.py` 注册模型供 Alembic 发现。
- [x] T011 [P] 在 `backend/src/schemas/comment.py` 定义评论创建、列表、公开条目、后台列表/详情、动作请求和统一错误所需的 Pydantic schema；禁止把手机号、用户 ID、token 或完整规则词条放进公开响应。
- [x] T012 [P] 在 `backend/src/services/seed_service.py` 增加 `comments.read` / `comments.write` 到系统管理员权限集合；在 `manageSystem/src/constants/permissions.js` 增加同名模块和中文权限标签。
- [x] T013 在 `backend/src/tasks/maintenance_tasks.py` 增加按主键分批清理已删除评论的任务入口，并在 `backend/src/main.py` 注册每日调度；任务失败只记录不含正文的错误摘要。
- [x] T014 在 `backend/src/api/v1/__init__.py`、`backend/src/main.py` 和现有路由注册处预留评论公开/后台路由挂载位置，复用现有认证、统一响应和异常处理依赖。

**Checkpoint**：迁移可升级，模型可被导入，系统管理员拿到新权限，清理任务可运行；所有基础测试由红转绿后再开始用户故事。

## Phase 3: User Story 1 - 登录后浏览并发表评论（Priority: P1）🎯 MVP

**目标**：已登录用户可以读取已发布文章的可见评论并发表评论；未登录、未发布文章和不合规内容不得进入公开列表。

**独立验收**：登录用户打开已发布文章，看到稳定分页评论、空态和输入区；通过审查的评论公开，待审评论不公开；未登录用户看不到评论正文和互动控件。

### 先写测试（必须先失败）

- [ ] T015 [P] [US1] 在 `backend/tests/contract/test_comments.py` 编写并运行失败的 `GET /api/v1/articles/{article_id}/comments` 契约测试：登录要求、已发布文章校验、置顶/时间/ID 稳定排序、cursor、limit 1–50、统一响应和隐私字段。
- [ ] T016 [P] [US1] 在 `backend/tests/contract/test_comments.py` 编写并运行失败的 `POST /api/v1/articles/{article_id}/comments` 契约测试：`Idempotency-Key`、1–500 字、纯文本/文字表情、重复 key、草稿文章、未登录和受控审查结果。
- [ ] T017 [P] [US1] 在 `backend/tests/unit/test_comment_service.py` 编写并运行失败的评论服务测试：作者显示名/头像快照、pending/visible 状态、3 次/分钟限制、文章状态、重复提交和事务回滚。
- [ ] T018 [P] [US1] 在 `miniProgram/tests/contract/comment-api-contract.test.js` 编写并运行失败的评论请求适配测试：Bearer token、cursor、幂等键、统一 envelope、登录过期和局部错误。
- [ ] T019 [P] [US1] 在 `miniProgram/tests/integration/article-comments-flow.test.js` 编写并运行失败的文章详情流程测试：登录前隐藏评论区、登录后加载、空态、加载更多、发表评论草稿保留和 pending 提示。

### 实现

- [ ] T020 [US1] 在 `backend/src/services/comment_service.py` 实现评论列表和创建服务：校验发布文章、读取可见评论、生成稳定 cursor、快照昵称头像、持久化幂等指纹并应用服务端限流。
- [ ] T021 [US1] 在 `backend/src/api/v1/article_comments.py` 实现公开评论列表和创建接口，接入 `get_current_user`、统一响应、错误码和响应脱敏；注册到 `backend/src/main.py`。
- [ ] T022 [US1] 在 `miniProgram/services/comment-service.js`、`miniProgram/models/comment.js` 实现列表/创建请求、cursor 适配、幂等键生成、状态映射和局部错误处理。
- [ ] T023 [US1] 修改 `miniProgram/pages/article-detail/index.js`，在登录态下加载评论、分页、提交和重试；未登录不请求评论接口，文章正文和现有分享功能不受评论失败影响。
- [ ] T024 [US1] 修改 `miniProgram/pages/article-detail/index.wxml`、`index.wxss`，增加评论数量、纯文本输入、字符计数、空态、待审核提示、错误重试和安全的纯文本渲染；不得使用富文本 HTML。
- [ ] T025 [US1] 运行 US1 后端契约/单元测试和小程序流程测试，修复回归后确认“登录后可评论、未登录不可读评论”独立验收通过。

**Checkpoint**：US1 可独立演示并部署，不依赖点赞或后台管理页面。

## Phase 4: User Story 2 - 评论点赞与取消点赞（Priority: P1）

**目标**：登录用户可对可见评论点赞/取消点赞，同一用户同一评论最多一条关系，重复操作幂等且计数不为负。

**独立验收**：同一用户连续点击 10 次最终最多一条点赞关系；第二个用户计数独立；评论下架/删除后不能点赞。

### 先写测试（必须先失败）

- [ ] T026 [P] [US2] 在 `backend/tests/contract/test_comments.py` 编写并运行失败的点赞/取消点赞契约测试：登录、文章/评论归属、可见状态、重复 POST/DELETE、`liked` 和非负 `likeCount`。
- [ ] T027 [P] [US2] 在 `backend/tests/unit/test_comment_service.py` 增加并发点赞、取消点赞、唯一约束冲突和隐藏/删除评论拒绝测试，验证计数和关系同事务更新。
- [ ] T028 [P] [US2] 在 `miniProgram/tests/unit/comment.test.js` 增加失败的乐观状态回滚测试：请求失败时恢复原状态、重复点击锁定、成功后使用服务端计数。

### 实现

- [ ] T029 [US2] 在 `backend/src/services/comment_service.py` 实现点赞/取消点赞事务：锁定评论计数、维护 `CommentLike` 唯一关系、幂等处理和可见性校验。
- [ ] T030 [US2] 在 `backend/src/api/v1/article_comments.py` 增加 POST/DELETE like 路由，返回 `commentId`、`liked`、`likeCount`，统一处理 401/404/409/500。
- [ ] T031 [US2] 在 `miniProgram/services/comment-service.js` 和文章详情状态中接入点赞/取消点赞，处理并发点击、失败回滚和列表刷新后的 `liked` 同步。
- [ ] T032 [US2] 更新 `miniProgram/pages/article-detail/index.wxml`、`index.wxss` 增加点赞按钮、数量和无障碍文本，确保只能对可见评论操作。
- [ ] T033 [US2] 运行 US2 契约、服务和小程序单元测试，确认重复点击、第二用户计数和下架后拒绝均通过。

**Checkpoint**：US1 + US2 可独立提供前台评论互动。

## Phase 5: User Story 3 - 后台评论管理（Priority: P1）

**目标**：具有权限的管理员可以筛选、查看、审查、下架/恢复、置顶/取消置顶和软删除评论；无权限用户只能得到服务端拒绝。

**独立验收**：`comments.read` 账号可只读查看；`comments.write` 账号可操作；每篇文章最多一条置顶；版本冲突不会覆盖他人操作；删除后前台不可见。

### 先写测试（必须先失败）

- [ ] T034 [P] [US3] 在 `backend/tests/contract/test_admin_comments.py` 编写并运行失败的后台列表/详情契约测试：权限、文章/状态/关键词/日期筛选、cursor、100 字摘要、7 天正文窗口和隐私输出。
- [ ] T035 [P] [US3] 在 `backend/tests/contract/test_admin_comments.py` 编写并运行失败的动作契约测试：approve/reject/hide/restore/pin/unpin/delete、原因校验、`expectedVersion`、40910、权限 40300 和统一响应。
- [ ] T036 [P] [US3] 在 `backend/tests/unit/test_comment_service.py` 增加状态转换、置顶互斥、隐藏/删除自动取消置顶、动作快照和审计摘要测试。
- [ ] T037 [P] [US3] 在 `manageSystem/src/api/__tests__/comments.spec.js`、`manageSystem/src/pages/comments/__tests__/index.spec.js` 编写并运行失败的权限、筛选、详情抽屉、确认框、版本冲突和局部错误测试。

### 实现

- [ ] T038 [US3] 在 `backend/src/services/comment_service.py` 实现后台 cursor 列表、详情、状态转换、置顶互斥、软删除和 `expectedVersion` 乐观锁；在同一事务写入 `CommentAction` 与既有 `AuditLog` 摘要。
- [ ] T039 [US3] 创建 `backend/src/api/v1/admin_comments.py`，实现 `/admin/comments` 列表、详情和 PATCH 动作接口，逐路由使用 `require_permission("comments.read/write")`，不返回手机号/身份证号/规则词条。
- [ ] T040 [US3] 在 `manageSystem/src/api/comments.js` 封装列表、详情和动作 API，统一处理权限失效、40910、受控中文错误和 cursor。
- [ ] T041 [US3] 在 `manageSystem/src/router/index.js` 增加 `/comments` 路由，在 `manageSystem/src/App.vue` 接入按 `comments.read` 的菜单显示，并保留路由守卫服务端权限控制。
- [ ] T042 [US3] 创建 `manageSystem/src/pages/comments/index.vue`，实现筛选栏、cursor 表格、内容摘要、状态/审查标签、详情抽屉、动作时间线、写权限控制、危险操作确认、空态和局部重试。
- [ ] T043 [US3] 运行 US3 后端契约/单元和管理后台组件测试，确认只读账号不可写、置顶唯一、版本冲突和软删除行为通过。

**Checkpoint**：后台管理员可独立完成待审评论处理，前台公开列表实时遵守后台状态。

## Phase 6: User Story 4 - 本地审查与风险反馈（Priority: P1）

**目标**：评论在进入公开列表前经过后端本地审查，至少覆盖色情、暴力、政治；明确违规或不确定内容不公开，用户得到不泄露规则细节的提示。

**独立验收**：通过内容变为 visible；命中规则进入 rejected/pending；规则加载异常进入 pending 或受控失败；后台能看到分类、规则版本和动作时间线但看不到命中片段。

### 先写测试（必须先失败）

- [ ] T044 [P] [US4] 在 `backend/tests/unit/test_comment_moderation.py` 编写并运行失败的归一化和输入测试：NFKC、全角/大小写、空白/标点穿插、控制字符、HTML、链接、图片/语音标记、长度边界。
- [ ] T045 [P] [US4] 在 `backend/tests/unit/test_comment_moderation.py` 编写并运行失败的规则测试：sexual/violence/political/other 分类、明确命中、疑似命中、规则版本和规则配置异常不公开。
- [ ] T046 [P] [US4] 在 `backend/tests/integration/test_comment_moderation_flow.py` 编写并运行失败的完整流程测试：自动通过、待审、受控拒绝、人工 approve/reject 及公开列表隔离。
- [ ] T047 [P] [US4] 在 `miniProgram/tests/integration/article-comments-flow.test.js` 增加失败的审查状态提示测试：通过立即展示、pending 显示审核提示、拒绝保留草稿且不显示正文。

### 实现

- [ ] T048 [US4] 创建 `backend/src/services/comment_moderation.py`，实现本地版本化规则、Unicode 归一化、类别匹配、纯文本安全校验和受控结果；规则词表只在后端配置，不提供客户端接口。
- [ ] T049 [US4] 将 `comment_moderation.py` 接入 `comment_service.py` 创建流程，写入 moderation 状态/类别/版本/时间，命中或异常时禁止 visible，并生成不含正文/命中片段的动作与审计摘要。
- [ ] T050 [US4] 在 `miniProgram/services/comment-service.js` 与文章详情页映射 `visible/pending/rejected` 受控消息，禁止客户端根据规则词表自行判断或渲染隐藏内容。
- [ ] T051 [US4] 在管理后台评论列表/详情中增加待审筛选、审查状态和分类展示，完整正文仅在 7 天窗口内按权限显示，清理后显示“内容已清理”。
- [ ] T052 [US4] 运行 US4 审查单元、集成、契约和前端流程测试，确认公开列表 100% 只返回通过或人工放行评论。

**Checkpoint**：四个 P1 用户故事全部可验收，评论安全边界和后台处置闭环完成。

## Phase 7: Polish & Cross-Cutting Validation

- [ ] T053 [P] 在 `backend/tests/contract/test_comments.py` 和 `test_admin_comments.py` 增加公开响应隐私快照，确认不包含手机号、身份证号、user ID、token、完整规则词条或点赞用户列表。
- [ ] T054 [P] 在 `miniProgram/pages/article-detail/index.*` 和 `manageSystem/src/pages/comments/index.vue` 做纯文本渲染/输入注入检查，确认不使用 `v-html` 或客户端 HTML 解析评论。
- [ ] T055 [P] 对评论公开列表和后台列表执行索引/分页性能测试，确认 limit 上限、cursor 稳定性和文章下架后的不泄露行为。
- [ ] T056 运行 `specs/020-article-comments/quickstart.md` 中的迁移、后端、管理后台、小程序测试及生产构建，修复所有回归。
- [ ] T057 更新必要的 API/权限说明和运行文档，核对 `.env.example` 无需新增第三方审核密钥，确认本地规则版本和清理任务可观测但不记录正文。

## Dependencies & Execution Order

### Phase dependencies

- Phase 1 无依赖；必须先完成基线和失败测试骨架。
- Phase 2 依赖 Phase 1，阻塞所有用户故事；迁移、模型、权限和清理基础必须先通过。
- Phase 3–6 均依赖 Phase 2；US1 是 MVP 基础，US2 依赖 US1 的评论展示模型，US3 依赖模型和服务但可与 US2 并行，US4 的审查服务必须在 US1 的创建流程最终验收前接入。
- Phase 7 依赖所有目标用户故事完成。

### User story dependencies

- **US1**：Phase 2 后可开始；提供评论列表和创建基础。
- **US2**：依赖 US1 的可见评论响应和详情页列表状态；后端点赞服务可在 US1 API 完成后并行开发。
- **US3**：依赖 Phase 2 的模型、权限和服务；与 US2 前端工作可并行，但动作接口必须接入同一评论状态机。
- **US4**：测试和 moderation service 可与 US1/US3 的非审查页面并行；创建评论的最终验收依赖 T048–T049。

### Parallel opportunities

- Phase 1 的三个测试骨架可并行。
- Phase 2 的模型测试、迁移测试、RBAC 测试和清理测试可并行；实现阶段 T009–T012 可并行，T013 依赖模型。
- US1 中后端契约、服务单元、小程序契约可并行先写；后端实现完成后小程序页面接入。
- US3 后端契约、后台 API 测试和页面测试可并行先写；页面不得绕过 API 直接实现业务规则。
- US4 的 moderation 单元测试与前端状态测试可并行。

## Implementation Strategy

### MVP first

1. 完成 Phase 1–2，确保数据库和权限基础可用。
2. 完成 US1：登录后读取/发表、审核状态和前端评论区。
3. 运行 US1 独立验收，先交付可读可发但受审查保护的评论 MVP。

### Incremental delivery

1. 加入 US2 点赞/取消点赞，验证并发计数。
2. 加入 US3 后台管理，形成审核和运营闭环。
3. 完成 US4 本地风险分类、待审和规则异常降级。
4. 完成 Phase 7 的隐私、性能、清理和全量构建检查。

### Completion rule

只有当所有测试先红后绿、迁移成功、公开接口隐私快照通过、后台权限边界通过、小程序文章正文/分享回归通过后，才允许进入提交和合并流程。
