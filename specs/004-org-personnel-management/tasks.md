---

description: "Task list for 组织人员管理（组织架构 + 分销员 + 组织管理员业绩视图）"
---

# Tasks: 组织人员管理（组织架构 + 分销员 + 组织管理员业绩视图）

**Input**: Design documents from `/specs/004-org-personnel-management/`
**Prerequisites**: [plan.md](./plan.md)（必需）、[spec.md](./spec.md)（必需）、[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/](./contracts/)、[quickstart.md](./quickstart.md)

**Tests**: 项目宪法 Principle I（TDD）为 NON-NEGOTIABLE —— 每个生产模块必须测试先行（先写失败测试再实现）。因此每个用户故事阶段均含 **contract + integration + unit** 测试任务；单元测试覆盖各业务服务模块的 happy path、边界与错误条件；所有测试须在对应实现之前完成并确认失败（Red）。

**Format**: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无依赖）
- **[Story]**: 所属用户故事（US1-US6）
- 描述含精确文件路径

## Path Conventions

- 后端：`backend/src/`、`backend/tests/`
- 管理后台：`manageSystem/src/`
- 小程序：`miniProgram/`
- 迁移：`backend/migrations/versions/`

---

## Phase 1: Setup（共享环境基线）

**Purpose**: 现有系统已搭建，本阶段确认开发环境与基线，避免在损坏基线上叠加重构

- [X] T001 运行后端基线测试并确认全绿：`cd backend && pytest`（记录基线结果，后续重构以基线为回归锚点）
- [X] T002 [P] 确认管理后台可构建运行：`cd manageSystem && npm run dev` 可正常启动
- [X] T003 [P] 确认 Alembic 迁移基线一致：`cd backend && alembic current` 与最新版本一致

**Checkpoint**: 基线就绪，可开始模型与 schema 演进

---

## Phase 2: Foundational（阻塞性前置：新表与模型层）

**Purpose**: 新增组织/分销员/组织资质三张表及 ORM 模型、用户登录字段、RBAC 权限点与迁移骨架。所有用户故事依赖本阶段完成。

**⚠️ CRITICAL**: 本阶段未完成前不得开始任何用户故事实现。

- [X] T004 创建 `Organization` 模型于 `backend/src/models/organization.py`（邻接表 parent_id 自引用、org_type/level/sort_order/status，依据 data-model.md §2.1）
- [X] T005 [P] 创建 `Distributor` 模型于 `backend/src/models/distributor.py`（user_id UNIQUE、org_id FK、org_role member/admin、status，依据 §2.2）
- [X] T006 [P] 创建 `OrganizationQualification` 模型于 `backend/src/models/org_qualification.py`（org_id FK、文件/有效期/状态/审核字段，依据 §2.4）
- [X] T007 [P] 为 `users` 增加 `password_hash` 列：修改 `backend/src/models/user.py`（依据 §2.3）
- [X] T008 更新角色权限种子：在 `backend/src/services/seed_service.py` 中新增 `org:manage`、`distributor:manage`、`org_admin:assign`，`hierarchy:manage` 由 `org:manage` 取代（依据 data-model.md §2.5/§5）
- [X] T009 在 `backend/src/api/deps.py` 增加 `require_permission(perm)` 依赖，供后台接口按权限点鉴权（SC-011）
- [X] T010 编写首个 Alembic 迁移（新三表 + users.password_hash）于 `backend/migrations/versions/`，执行 `alembic upgrade head` 验证
- [X] T011 在 `backend/src/main.py` 注册新增的 admin 路由模块（本仓库路由注册于 `main.py`，而非 `api/v1/__init__.py`）——随各故事阶段的路由创建同步注册

**Checkpoint**: 新表与模型就绪，US1 与 US6（迁移）可并行开始

---

## Phase 3: User Story 1 - 组织结构建立与管理 (Priority: P1) 🎯 MVP

**Goal**: 后台建立任意深度组织树，支持创建/编辑/删除/排序/整体迁移/环路检测/操作留痕，取代现有层级管理。

**Independent Test**: 后台创建多级组织 → 编辑 → 整体迁移 → 环路被拦截 → 删除非空组织被拒 → 组织停用后其下分销员受限。

### Tests for User Story 1（TDD，先失败） ⚠️

- [X] T012 [P] [US1] 契约测试：组织树增删改/迁移/环路/删除非空接口请求响应，于 `backend/tests/contract/test_admin_organizations.py`（依据 contracts/org.md）
- [X] T013 [P] [US1] 集成测试：创建多级组织 → 迁移子树 → 层级更新 → 环路拦截 → 非空删除拒绝，于 `backend/tests/integration/test_org_tree.py`
- [X] T014 [P] [US1] 单元测试：`organization_service` 的 create/update/move/delete/环路检测/深度校验 happy path + 边界 + 错误（D1），于 `backend/tests/unit/test_organization_service.py`

### Implementation for User Story 1

- [X] T015 [P] [US1] 创建组织 schema 于 `backend/src/schemas/organization.py`（OrgCreate/OrgUpdate/MigrateRequest 等，依据 contracts/org.md 请求/响应）
- [X] T016 [US1] 实现 `organization_service` 于 `backend/src/services/organization_service.py`：复用 `hierarchy_service` 的递归/环路/深度校验逻辑，去 MAX_LEVEL=6 硬编码、深度改为可配置，含操作历史记录（依赖 T014/T015）
- [X] T017 [US1] 实现后台组织树路由于 `backend/src/api/v1/admin_organizations.py`（GET/POST/PUT/DELETE /admin/orgs、/migrate、/history，权限 `org:manage`，依赖 T009/T016）
- [X] T018 [US1] 管理后台组织树页面于 `manageSystem/src/pages/org/org-tree.vue`（树形展示、增删改、迁移、环路提示）
- [X] T019 [US1] 注册组织管理菜单与 API 客户端：修改 `manageSystem/src/router/index.js`、`manageSystem/src/api/`（org.js）
- [X] T020 [US1] 实现组织停用/启用的约束规则（C1）：组织 `status=disabled` 时其下分销员受限（保留登录与历史查看、停止新推广码生成与贡献值累计，同 FR-008 暂停边界），含集成测试于 `backend/tests/integration/test_org_tree.py`

**Checkpoint**: US1 可独立验收（SC-002/004）

---

## Phase 4: User Story 6 - 现有功能迁移到组织/分销员模型 (Priority: P1)

**Goal**: 将历史层级/拓展人数据迁移到组织/分销员模型，切换客户/推广码/账单/贡献值外键，适配贡献值聚合、分账、对账及现有前端消费者。历史数据 100% 保留、数值一致。

**Independent Test**: 用 seed 历史数据跑迁移 → 校验行数/数值/外键一致 → 迁移后现有功能（个人贡献、推广码、对账）与现有页面在新模型下正常。

### Tests for User Story 6（TDD，先失败） ⚠️

- [X] T021 [P] [US6] 迁移集成测试：seed 历史层级/拓展人/资质/客户/推广码/贡献值 → 执行迁移 → 断言新表行数、贡献值求和、客户绑定数、推广码数一致，于 `backend/tests/integration/test_migration_consistency.py`（SC-009/010）
- [X] T022 [P] [US6] 聚合适配集成测试：迁移后新账单产生的贡献值按组织树逐级汇总正确，于 `backend/tests/integration/test_org_aggregation.py`
- [X] T023 [P] [US6] 单元测试：`contribution_service`/`team_service` 组织树聚合逻辑 happy path + 空组织 + 嵌套子组织（D1），于 `backend/tests/unit/test_contribution_aggregation.py`

### Implementation for User Story 6

- [X] T024 [US6] 编写数据迁移脚本（组织部分）：`hierarchy_nodes` → `organizations`（树结构/类型映射/level 保留）于 `backend/migrations/versions/`
- [X] T025 [US6] 编写数据迁移脚本（分销员部分）：`promoters` → `distributors`（user_id/org_id 回填/org_role=member）于 `backend/migrations/versions/`
- [X] T026 [US6] 编写数据迁移脚本（资质部分）：每组织取其下拓展人最新一条资质 → `org_qualifications`（状态保持）于 `backend/migrations/versions/`（research §4）
- [X] T027 [US6] 切换外键：`customers`/`promotion_codes`/`contribution_records`/`binding_requests` 的 `promoter_id` → `distributor_id`，于 `backend/migrations/versions/`
- [X] T028 [US6] 更新 `roles` 权限数据（`hierarchy:manage` → `org:manage`）于迁移脚本
- [X] T029 [US6] 废弃旧表：`hierarchy_nodes`/`promoters`/`qualifications` 重命名或标记废弃（数据保留）于迁移脚本（I4：与旧层级端点停用同批协调——见 T065，避免表废弃后旧接口报错）
- [ ] T030 [US6] 适配贡献值聚合：修改 `backend/src/services/contribution_service.py`、`backend/src/services/team_service.py`，贡献主体改为分销员、逐级汇总改为按组织树聚合（依赖 T023）
- [ ] T031 [US6] 适配分账规则：修改 `backend/src/services/sharing_service.py`，层级维度改为组织层级/类型，新规则对新数据生效（US6-AC5）
- [ ] T032 [US6] 适配对账报表：修改 `backend/src/services/report_service.py`，增加组织维度汇总（US6-AC6）
- [X] T033 [US6] 迁移一致性校验脚本于 `backend/scripts/verify_migration.py`（行数/求和/绑定数对比，供迁移后运行）
- [ ] T034 [US6] 现有 API 消费者字段适配（C2）：迁移切换外键后，小程序 `miniProgram/pages/`（贡献/推广码/客户绑定等）与管理后台 `manageSystem/src/pages/` 中引用 `promoterId`/层级字段的调用同步改为分销员/组织字段，含回归
- [ ] T035 [US6] 管理后台分账配置/对账报表页面适配（E1）：`manageSystem/src/pages/sharing-rules/`、`reports/` 中"层级"维度列改为组织层级/类型维度（配合 T031/T032）

**Checkpoint**: US6 可独立验收（SC-009/010）；此后 US2/US3/US5 可基于真实迁移数据工作

---

## Phase 5: User Story 2 - 组织资质文件维护 (Priority: P1)

**Goal**: 后台在组织详情维护组织资质文件（上传/查看/审核/历史/到期提醒），组织资质作为业务准入门槛。

**Independent Test**: 组织详情上传资质 → 审核通过 → 组织业务可用；到期 30 天提醒；过期暂停（保留登录与历史查看）。

### Tests for User Story 2（TDD，先失败） ⚠️

- [X] T036 [P] [US2] 契约测试：组织资质列表/上传/审核/历史接口，于 `backend/tests/contract/test_admin_org_qualifications.py`（依据 contracts/org-qualifications.md）
- [X] T037 [P] [US2] 集成测试：上传→审核通过→组织可用、驳回→暂停（边界见 FR-008）、到期提醒/过期暂停，于 `backend/tests/integration/test_org_qualification.py`
- [X] T038 [P] [US2] 单元测试：`org_qualification_service` 上传/审核/到期检测逻辑（D1），于 `backend/tests/unit/test_org_qualification_service.py`

### Implementation for User Story 2

- [X] T039 [P] [US2] 创建组织资质 schema 于 `backend/src/schemas/org_qualification.py`
- [X] T040 [US2] 实现 `org_qualification_service` 于 `backend/src/services/org_qualification_service.py`（上传/审核/到期检测，复用 qualification_service 模式，依赖 T038）
- [X] T041 [US2] 实现后台组织资质路由于 `backend/src/api/v1/admin_org_qualifications.py`（列表/上传需 `org:manage`，审核需 `qualification:review`）
- [X] T042 [US2] 管理后台组织详情资质页签于 `manageSystem/src/pages/org/org-detail.vue`（资质文件列表、上传、历史、状态）
- [X] T043 [US2] 组织资质到期提醒接入现有通知/消息中心（复用 `backend/src/services/notification_service.py`）

**Checkpoint**: US2 可独立验收（SC-005）

---

## Phase 6: User Story 3 - 分销员账户创建与管理 (Priority: P1)

**Goal**: 后台在每层组织内创建分销员账户（手机号+密码），支持调整归属/启停用/重置凭证；分销员手机号+密码登录、首登强制绑定微信。

**Independent Test**: 组织内新建分销员 → 手机号+密码登录 → 首登绑微信 → 调整归属/停用/重置凭证全流程。

### Tests for User Story 3（TDD，先失败） ⚠️

- [X] T044 [P] [US3] 契约测试：分销员列表/新建/调整/重置凭证接口 + 登录/绑定接口，于 `backend/tests/contract/test_admin_distributors.py`、`backend/tests/contract/test_auth.py`（依据 contracts/distributors.md、contracts/auth.md）
- [X] T045 [P] [US3] 集成测试：新建账户 → 账密登录 → 首登绑微信 → 绑定后微信快速登录 → 停用拒登，于 `backend/tests/integration/test_distributor_auth.py`
- [X] T046 [P] [US3] 单元测试：`distributor_service`（创建/调整归属/启停用/重置凭证/手机号唯一性）与 `auth_service`（账密校验/微信绑定）逻辑（D1），于 `backend/tests/unit/test_distributor_service.py`、`backend/tests/unit/test_auth_service.py`

### Implementation for User Story 3

- [X] T047 [P] [US3] 创建分销员 schema 于 `backend/src/schemas/distributor.py`（DistributorCreate/Update/ResetPassword 等）
- [X] T048 [US3] 实现 `distributor_service` 于 `backend/src/services/distributor_service.py`（创建/调整归属/启停用/重置凭证，手机号唯一性校验，依赖 T046）
- [X] T049 [US3] 实现后台分销员路由于 `backend/src/api/v1/admin_distributors.py`（GET /admin/orgs/{orgId}/distributors、POST、PUT、reset-password，权限 `distributor:manage`）
- [X] T050 [US3] 扩展登录认证：在 `backend/src/api/v1/auth.py` 与 `backend/src/services/auth_service.py` 实现 `POST /auth/distributor-login`（手机号+密码）与 `POST /auth/bind-wechat`（首登绑微信）
- [X] T051 [US3] 管理后台分销员管理页于 `manageSystem/src/pages/org/distributors.vue`（组织内列表、新建、调整归属、停用、重置凭证）
- [ ] T052 [US3] 小程序登录改造：`miniProgram/pages/auth/` 增加手机号+密码登录与微信绑定流程，更新 `miniProgram/services/session-service.js`

**Checkpoint**: US3 可独立验收（FR-009~012/027）

---

## Phase 7: User Story 4 - 组织管理员设置 (Priority: P1)

**Goal**: 后台将组织内若干分销员设为组织管理员（仅后台授权），设置/撤销即时生效；权限点 `org_admin:assign`。

**Independent Test**: 后台设置分销员为组织管理员 → 小程序出现组织业绩入口 → 撤销后入口即时消失。

### Tests for User Story 4（TDD，先失败） ⚠️

- [X] T053 [P] [US4] 契约测试：`PUT /admin/distributors/{id}/role` 设置/撤销管理员 + 无 `org_admin:assign` 权限被拒，于 `backend/tests/contract/test_admin_distributors.py`（补充 role 场景）
- [X] T054 [P] [US4] 集成测试：设置→授权生效、撤销→权限即时失效、组织迁移后授权跟随，于 `backend/tests/integration/test_org_admin.py`
- [X] T055 [P] [US4] 单元测试：组织管理员角色设置/撤销与权限校验逻辑（D1），于 `backend/tests/unit/test_org_admin_role.py`

### Implementation for User Story 4

- [X] T056 [US4] 在 `backend/src/api/v1/admin_distributors.py` 实现 `PUT /admin/distributors/{distributorId}/role`（权限 `org_admin:assign`，依赖 T048）
- [X] T057 [US4] 管理后台组织管理员设置页于 `manageSystem/src/pages/org/org-admins.vue`（组织内设置/撤销管理员）

**Checkpoint**: US4 可独立验收（FR-013/014/026）

---

## Phase 8: User Story 5 - 组织管理员业绩贡献查看 (Priority: P2)

**Goal**: 组织管理员在小程序查看授权组织整个子树的业绩汇总与成员贡献值（本月/累计），不含客户明细；越权不可见。

**Independent Test**: 设置组织管理员 → 小程序登录查看组织业绩汇总与成员明细 → 非管理员越权被拒 → 撤销后入口消失。

### Tests for User Story 5（TDD，先失败） ⚠️

- [X] T058 [P] [US5] 契约测试：`GET /api/v1/org/performance` 响应结构与错误码，于 `backend/tests/contract/test_org_performance.py`（依据 contracts/org-performance.md）
- [X] T059 [P] [US5] 集成测试：组织汇总=成员贡献之和（一致性）、子树外数据不可见、非管理员 403、撤销后 403，于 `backend/tests/integration/test_org_performance.py`
- [X] T060 [P] [US5] 单元测试：`org_performance_service` 子树聚合 + 范围校验（含大组织边界）逻辑（D1），于 `backend/tests/unit/test_org_performance_service.py`

### Implementation for User Story 5

- [X] T061 [P] [US5] 创建组织业绩 schema 于 `backend/src/schemas/org_performance.py`（响应结构）
- [X] T062 [US5] 实现 `org_performance_service` 于 `backend/src/services/org_performance_service.py`：取授权组织子树 id 集合 → 聚合 `contribution_records`（distributor_id）本月/累计，不含客户明细（FR-015，依赖 T060）
- [X] T063 [US5] 实现组织业绩路由于 `backend/src/api/v1/org_performance.py`（`GET /api/v1/org/performance`，鉴权：分销员 + `org_role=admin` + 子树范围校验）
- [ ] T064 [US5] 小程序组织业绩页面于 `miniProgram/pages/org-performance/`（组织汇总 + 成员贡献值列表），入口按组织管理员身份显示，新增 API 服务于 `miniProgram/services/`

**Checkpoint**: US5 可独立验收（SC-003/006/007/008）

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 跨故事收尾、回归与文档

- [ ] T065 移除/下架原层级管理入口：删除 `manageSystem/src/pages/hierarchy/index.vue` 相关路由与 `backend/src/api/v1/admin.py` 中 hierarchy 端点（I4：须在 US6 T029 表废弃后立即执行，与迁移发布同批，避免旧表废弃后接口报错）
- [ ] T066 [P] 更新 README/文档：README.md 组织结构描述、`docs/` 相关接口文档同步组织模型
- [X] T067 [P] 安全收尾：核对所有后台组织/分销员/管理员接口权限点校验无遗漏（SC-011）、分销员手机号脱敏
- [X] T068 [P] 性能验证（E2）：组织树操作与组织业绩聚合接口满足 SC-002（5 秒内反映）目标，性能测试于 `backend/tests/performance/`（数百人组织子树场景）
- [X] T069 全量回归：`cd backend && pytest` 全绿 + `cd manageSystem && npm run build` 通过 + 小程序编译检查
- [ ] T070 按 `specs/004-org-personnel-management/quickstart.md` 完成端到端验收走查（SC-001~SC-011）

**Checkpoint**: 本特性完成，可进入发布

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 无依赖
- **Phase 2 (Foundational)**: 依赖 Phase 1 —— BLOCKS 全部用户故事
- **Phase 3-8 (User Stories)**: 依赖 Phase 2 完成
  - US1（Phase 3）与 US6（Phase 4）在 Foundational 后可**并行**
  - US2/US3/US4 依赖组织存在（US1 或 US6 迁移数据）
  - US5 依赖 US1 + US6 + US3 + US4（组织树 + 迁移后贡献数据 + 分销员 + 管理员角色）
- **Phase 9 (Polish)**: 依赖所有用户故事完成

### User Story Dependencies

- **US1 (P1)**: Foundational 后即可开始；不依赖其他故事
- **US6 (P1)**: Foundational 后即可开始；与 US1 并行；**I4 注意**：T029（旧表废弃）须与 Polish T065（旧端点移除）同批协调
- **US2 (P1)**: 依赖 US1 或 US6（组织存在）
- **US3 (P1)**: 依赖 US1 或 US6（组织存在）；登录改造可独立开发
- **US4 (P1)**: 依赖 US3（分销员账户）
- **US5 (P2)**: 依赖 US1/US6/US3/US4（组织树 + 迁移贡献数据 + 分销员 + 管理员）

### Within Each User Story

- 测试先行（Red）→ 实现（Green）→ 重构；先 contract/integration/unit 测试，后 Models/Schemas → Services → Endpoints → 前端 UI → 集成
- 单元测试（D1 补充）覆盖各业务服务模块，是宪法 Principle I 的强制要求
- 每个故事在 Checkpoint 处独立验收

### Parallel Opportunities

- Phase 2 中 T005/T006/T007 可并行；T010/T011 可并行
- US1 与 US6 整体可并行（不同文件域）
- 各故事测试任务 [P] 可并行；同故事内 unit/contract/integration 测试 [P] 可并行
- 不同用户故事由不同开发者并行时，US2/US3 需等待组织数据（US1/US6）就绪

---

## Parallel Example: Foundational + US1

```bash
# Phase 2 (并行):
Task: "创建 Organization 模型于 backend/src/models/organization.py"        # T004
Task: "创建 Distributor 模型于 backend/src/models/distributor.py"          # T005
Task: "创建 OrganizationQualification 模型于 backend/src/models/org_qualification.py"  # T006

# US1 测试先行（并行）:
Task: "契约测试 admin_organizations 于 backend/tests/contract/test_admin_organizations.py"  # T012
Task: "集成测试组织树于 backend/tests/integration/test_org_tree.py"        # T013
Task: "单元测试 organization_service 于 backend/tests/unit/test_organization_service.py"  # T014
```

---

## Implementation Strategy

### MVP First（US1 为主干）

1. Phase 1 + Phase 2（Foundational）→ 新表与模型就绪
2. Phase 3（US1 组织树）→ 独立验收（可先以手工建组织演示）
3. Phase 4（US6 迁移）→ 真实历史数据切换到组织模型，并同步停用旧层级端点（T029/T065）
4. **STOP and VALIDATE**: 迁移校验脚本通过（SC-009/010）
5. Phase 5-7（US2/US3/US4）→ 资质/分销员/管理员
6. Phase 8（US5 组织业绩）→ 完整闭环

### Incremental Delivery

- 每个 P1 故事完成后即可独立演示（组织树 → 迁移 → 资质 → 分销员 → 管理员）
- US5（P2）作为最终价值闭环最后交付

### Parallel Team Strategy

- 开发者 A：US1（组织树）+ 前端组织页
- 开发者 B：US6（迁移）+ 聚合适配 + 现有消费者适配
- 开发者 C：US3 登录认证 + US5 组织业绩
- 汇合点：US3/US4/US5 依赖迁移后的分销员/贡献数据，须在 US6 校验通过后联调

---

## Notes

- **[P] 任务** = 不同文件、无依赖
- **[US#] 标签** 映射 spec.md 用户故事（US1-US6）
- 每个用户故事可独立完成与验收
- 迁移（US6）是数据正确性高风险区：必须先写迁移一致性测试（T021），再写迁移脚本
- 单元测试为宪法 Principle I 强制项（D1）：每个新服务模块（organization/distributor/org_qualification/org_performance/auth/contribution 聚合）均有对应 unit 测试任务
- 测试遵循宪法 TDD：先红后绿
- 每完成一个任务或逻辑组提交一次（原子提交）
- 在各 Checkpoint 停下独立验证故事
