# Tasks: 绩效规则模块

**Input**: Design documents from `/specs/006-performance-rules/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/performance-rules.md](./contracts/performance-rules.md), [quickstart.md](./quickstart.md)

**Tests**: 本项目宪法（`.specify/memory/constitution.md` 原则 I）强制 TDD——所有生产代码先写测试、每个 API 端点必须有契约测试。因此每个用户故事均含测试任务，按 TDD 先红后绿执行。

**Organization**: 任务按用户故事分组 + 跨切面的提成计算引擎阶段，支持独立实现与独立验收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)；提成计算引擎为跨切面阶段（无故事标签）
- Include exact file paths in descriptions

## Path Conventions

Web app 三独立层：`backend/src/`（FastAPI）、`manageSystem/src/`（Vue 3 admin）、`miniProgram/`（本迭代不改小程序）。

---

## Phase 1: Setup（基线校验）

**Purpose**: 改动前确认既有代码库基线可用

- [X] T001 Verify baseline: run full backend test suite green（`cd backend && ./venv/Scripts/python.exe -m pytest -q`）before any changes
- [X] T002 [P] Verify baseline: manageSystem build passes（`cd manageSystem && npm run build`）before any changes

---

## Phase 2: Foundational（阻塞性前置）

**Purpose**: 绩效规则/提成结果数据层与 API 骨架。本阶段完成前不得开始任何用户故事。

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create `PerformanceRule` + `PerformanceRuleChangeLog` models in `backend/src/models/performance_rule.py`（org_id FK→organizations ON DELETE CASCADE，rule_type enum `intra_org`/`org_management`，tiers JSON，status `active`/`inactive`，version，created_by；change_log：rule_id FK CASCADE + changed_by + old/new_value JSON，见 [data-model.md §2](data-model.md)）
- [X] T004 [P] Create `CommissionResult` model in `backend/src/models/commission_result.py`（period `YYYY-MM`，distributor_id FK，org_id，rule_type，base_cent，ratio，commission_cent，computed_at；unique (period, distributor_id, rule_type)，见 [data-model.md §2.3](data-model.md)）
- [X] T005 Register new models in `backend/src/models/__init__.py`（create_all 需注册）
- [X] T006 Create migration `009_performance_rules` in `backend/migrations/versions/009_performance_rules.py`（3 张表，SQL 见 data-model.md）
- [X] T007 Create migration `010_demote_duplicate_admins` in `backend/migrations/versions/010_demote_duplicate_admins.py`（每组织保留 id 最小的一名 `admin`，其余降为 `member`）
- [X] T008 [P] Create request schemas in `backend/src/schemas/performance_rule.py`（`Tier` {minCent≥0, maxCent>minCent 或 null, ratio∈(0,1]}，`PerformanceRuleUpdateRequest` {tiers 1-20 项}，period `YYYY-MM` 校验）
- [X] T009 [P] Create `backend/src/services/performance_service.py` scaffold: `validate_tiers`（升序、区间不重叠、首项 minCent=0、末项 maxCent=null）+ rule 序列化 + 变更日志写入 helper
- [X] T010 Create `backend/src/api/v1/admin_performance_rules.py` router scaffold（`/admin/orgs/{org_id}/performance-rules` + `/admin/commission-results`，`sharing_rules.read`/`write` 权限依赖）and register in `backend/src/main.py`
- [X] T011 [P] Create `manageSystem/src/api/performance.js`（getRules/saveRule/history/preview/commissionResults，复用 [org.js](manageSystem/src/api/org.js) payload 模式）

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 绩效规则页与组织结构树 (Priority: P1) 🎯 MVP

**Goal**: "分成规则"改名"绩效规则"，页面左侧组织树 + 右侧展示选中组织两种提成方式状态。

**Independent Test**: 导航显示"绩效规则"（无"分成规则"）；左树默认根组织；切换组织右侧展示对应配置状态。

### Tests for User Story 1（TDD：先写、先红）⚠️

- [X] T012 [P] [US1] Contract test `GET /admin/orgs/{orgId}/performance-rules` in `backend/tests/contract/test_admin_performance_rules.py`（返回两种方式、未配置为 null、无 `sharing_rules.read` 权限 40300）
- [X] T013 [P] [US1] Unit test `get_rules_for_org` in `backend/tests/unit/test_performance_service.py`

### Implementation for User Story 1

- [X] T014 [US1] Implement `get_rules_for_org` in `backend/src/services/performance_service.py`（返回 `{orgId, intraOrg, orgManagement, summary}`，未配置为 null）
- [X] T015 [US1] Implement `GET /admin/orgs/{org_id}/performance-rules` endpoint in `admin_performance_rules.py`（require `sharing_rules.read`）
- [X] T016 [US1] Create `manageSystem/src/pages/performance-rules/index.vue` with left org tree + right panel（复用 [org-tree.vue](manageSystem/src/pages/org/org-tree.vue)/005 客户管理的树模式与默认选中根逻辑；展示两种提成方式状态）
- [X] T017 [US1] Rename router `/sharing-rules` → `/performance-rules` in `manageSystem/src/router/index.js` and menu "分成规则"→"绩效规则" in `manageSystem/src/App.vue`

**Checkpoint**: US1 独立可用——导航改名、左树右配置状态

---

## Phase 4: User Story 2 - 组织内绩效提成配置 (Priority: P1)

**Goal**: 为选中组织配置"组织内绩效提成"阶梯（消费金额区间→百分比），保存留痕。

**Independent Test**: 配置组织内阶梯→保存生效→版本递增、变更历史可查；区间重叠被拒。

### Tests for User Story 2（TDD：先写、先红）⚠️

- [X] T018 [P] [US2] Contract test `PUT /admin/orgs/{orgId}/performance-rules/intra_org` in `backend/tests/contract/test_admin_performance_rules.py`（首次创建、再次保存 version+1、写变更日志、阶梯非法 40000、无 `sharing_rules.write` 40300）
- [X] T019 [P] [US2] Unit test `save_rule` (intra_org) in `backend/tests/unit/test_performance_service.py`

### Implementation for User Story 2

- [X] T020 [US2] Implement `save_rule`（upsert：存在则 version+1 + 变更日志，否则创建）in `performance_service.py`（调 `validate_tiers`）
- [X] T021 [US2] Implement `PUT /admin/orgs/{org_id}/performance-rules/intra_org` endpoint in `admin_performance_rules.py`（require `sharing_rules.write`）
- [X] T022 [US2] Add 组织内绩效提成 tiers editor（动态阶梯行 min/max/ratio + 校验提示）to `performance-rules/index.vue`

**Checkpoint**: US1 + US2 均独立可用

---

## Phase 5: User Story 3 - 组织管理绩效提成配置 (Priority: P1)

**Goal**: 为选中组织配置"组织管理绩效提成"阶梯（基数=管理子树消费总额）。

**Independent Test**: 配置组织管理阶梯→保存生效；与组织内提成共用同一保存路径，仅 rule_type 不同。

### Tests for User Story 3（TDD：先写、先红）⚠️

- [X] T023 [P] [US3] Contract test `PUT /admin/orgs/{orgId}/performance-rules/org_management` in `backend/tests/contract/test_admin_performance_rules.py`（保存成功、独立于 intra_org 配置）
- [X] T024 [P] [US3] Unit test `save_rule` (org_management) in `backend/tests/unit/test_performance_service.py`

### Implementation for User Story 3

- [X] T025 [US3] Ensure `save_rule` + PUT endpoint accept `org_management`（复用 T020/T021 通用路径，rule_type 参数化）
- [X] T026 [US3] Add 组织管理绩效提成 tiers editor（复用 T022 阶梯编辑器组件）to `performance-rules/index.vue`

**Checkpoint**: US1-US3 均独立可用

---

## Phase 6: 提成计算引擎（月度落库 + 实时预览）(Priority: P1 跨切面)

**Goal**: 计算引擎按各组织绩效规则计算提成：非管理员按自身消费金额×组织内阶梯，管理员按管理子树消费总额×组织管理阶梯；月度结算落库 + 实时预览。

**Independent Test**: 实时预览某周期成员/管理员提成与规则一致；月度结算后结果落库可查；退款/取消不计入。

### Tests（TDD：先写、先红）⚠️

- [X] T027 [P] Contract test `GET /admin/orgs/{orgId}/performance-rules/preview` + `GET /admin/commission-results` in `backend/tests/contract/test_admin_performance_rules.py`
- [X] T028 [P] Unit test `compute_commission` in `backend/tests/unit/test_commission_service.py`（成员自身消费×intra_org；管理员子树总额×org_management；refunded/cancelled 排除；阶梯边界；幂等重算覆盖）
- [X] T029 [P] Unit test settlement hook（`monthly_settlement_job` 调用 `compute_commission`，提成失败不阻断贡献结算）

### Implementation

- [X] T030 Implement `compute_commission(db, period)` in `backend/src/services/commission_service.py`（bills JOIN customers 按 distributor 聚合消费金额，周期按 `transaction_time`；子树 org_ids 复用 `organization_service.get_subtree`+`_collect_org_ids`；阶梯匹配；upsert `commission_results`）
- [X] T031 Implement `GET /admin/orgs/{org_id}/performance-rules/preview?period=` endpoint（实时计算不落库，返回 intraOrg/orgManagement 明细 + unconfigured）
- [X] T032 Implement `GET /admin/commission-results?period=&orgId=&page=&pageSize=` endpoint（月度结果分页）
- [X] T033 Modify `backend/src/tasks/settlement_task.py` `monthly_settlement_job`：`batch_settle` 后调用 `compute_commission`（独立 try/except 隔离，失败仅记日志）
- [X] T034 Add 预览/月度结果 tabs to `performance-rules/index.vue`

**Checkpoint**: 配置 + 计算引擎闭环可用（SC-008/SC-009）

---

## Phase 7: User Story 4 - 一个组织仅一个组织管理员 (Priority: P1)

**Goal**: 收紧约束：每组织至多一名管理员；设置第二名被拒，撤销后可设；存量多管理员迁移清理。

**Independent Test**: 组织已有管理员时设第二管理员被拒；撤销后可设；迁移后每组织至多一名。

### Tests for User Story 4（TDD：先写、先红）⚠️

- [X] T035 [P] [US4] Contract test `PUT /admin/distributors/{id}/role` second-admin rejection in `backend/tests/contract/test_admin_distributors.py`（设置第二管理员 40000；撤销不受限）
- [X] T036 [P] [US4] Unit test `set_role` constraint in `backend/tests/unit/test_distributor_service.py`

### Implementation for User Story 4

- [X] T037 [US4] Modify `set_role` in `backend/src/services/distributor_service.py`（目标组织已存在 `admin` 时设 admin 被拒："该组织已有管理员，请先撤销"；撤销 member 不受限）
- [X] T038 [US4] Update `manageSystem/src/pages/org/org-tree.vue` 设为管理员按钮：组织已有管理员时禁用并提示（或依赖后端错误提示）

**Checkpoint**: SC-003/SC-004 满足

---

## Phase 8: User Story 5 - 现有分成规则机制处理 (Priority: P2)

**Goal**: 移除旧"分成规则"配置入口与后端接口；旧数据废弃不参与计算。

**Independent Test**: 后台无旧"分成规则"入口；旧接口不可访问；新提成计算不受旧规则影响。

### Implementation for User Story 5

- [X] T039 [US5] Remove `/admin/sharing-rules` + coefficient endpoints from `backend/src/api/v1/sharing_rules.py`（删除文件 + `main.py` 注册移除）
- [X] T040 [US5] Remove old sharing-rules frontend（删除 `manageSystem/src/pages/sharing-rules/`、`manageSystem/src/stores/sharing.js`、`manageSystem/src/components/sharing-rules/RuleForm.vue`，确认无其他引用后删除）
- [X] T041 [US5] Remove/update sharing contract tests in `backend/tests/contract/test_sharing.py`

**Checkpoint**: 旧机制入口与接口移除干净（SC-006）

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 全量回归、构建验证、文档

- [X] T042 [P] Run full backend pytest suite（`cd backend && ./venv/Scripts/python.exe -m pytest -q`）; fix regressions
- [X] T043 Run manageSystem build + manual verification per [quickstart.md](./quickstart.md)（SC-001~SC-009）
- [X] T044 Update `specs/006-performance-rules/quickstart.md` / `contracts/performance-rules.md` if behavior drifted

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify baseline first
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all stories + 计算引擎
- **US1 (Phase 3)**: Depends on Foundational（页面展示依赖 GET 端点）
- **US2 (Phase 4)**: Depends on Foundational + US1 页面骨架（编辑器挂到页面）
- **US3 (Phase 5)**: Depends on US2 的 save_rule 通用路径
- **计算引擎 (Phase 6)**: Depends on Foundational（表/规则服务）+ US2/US3 配置可被计算引用；可先于前端页面
- **US4 (Phase 7)**: Depends on Foundational - 独立（改 set_role）
- **US5 (Phase 8)**: 依赖 US1（路由/菜单已改名）后再删旧页面/store
- **Polish (Phase 9)**: Depends on all

### User Story Dependencies

- US1: Foundational 后可开始 - 无其他依赖（MVP）
- US2: US1 页面骨架（T016/T017）后挂编辑器
- US3: 复用 US2 后端路径（T020/T021）
- US4: 独立于绩效配置，可与 US2/US3 并行
- US5: US1 改名后清理旧前端

### Within Each Phase

- 测试先写并确认 FAIL（Red），再实现使其 PASS（Green）
- Models/schemas → services → endpoints → 前端
- 计算引擎（Phase 6）与配置（US2/US3）共享 `validate_tiers`/`rule 序列化`（T009）

### Parallel Opportunities

- Setup：T001/T002 并行
- Foundational：T003/T004/T008/T009/T011 并行（不同文件）；T005 依赖 T003/T004；T006/T007 依赖模型；T010 依赖 T009
- US4（T035-T038）与 US2/US3/计算引擎完全独立，可并行
- 前端（T016/T022/T026/T034）与后端不同文件可并行
- Phase 6 计算引擎与 US4 独立，可并行

---

## Parallel Example: 计算引擎

```bash
# Launch all calc-engine tests together:
Task: "Contract test preview + commission-results in backend/tests/contract/test_admin_performance_rules.py"
Task: "Unit test compute_commission in backend/tests/unit/test_commission_service.py"
Task: "Unit test settlement hook in backend/tests/unit/test_commission_service.py"

# Implementation (sequential, shared service):
Task: "Implement compute_commission in backend/src/services/commission_service.py"
Task: "Implement preview + commission-results endpoints in admin_performance_rules.py"
Task: "Modify monthly_settlement_job in backend/src/tasks/settlement_task.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: 基线校验
2. Phase 2: Foundational（模型/迁移/schemas/服务助手/路由/API）
3. Phase 3: US1 绩效规则页 + 组织树 + 配置状态展示
4. **STOP and VALIDATE**: 导航改名、左树右配置状态

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. US1 绩效规则页 + 组织树 → 独立验证（MVP）
3. US2 组织内提成配置 → 独立验证
4. US3 组织管理提成配置 → 独立验证
5. 计算引擎（月度落库 + 预览）→ 验证 SC-008/SC-009
6. US4 单管理员约束 → 验证 SC-003/SC-004
7. US5 旧机制移除 → 验证 SC-006
8. Polish：全量回归 + 构建

### Parallel Team Strategy

后端 US2/US3 配置路径（共享 save_rule）顺序推进；US4（set_role）、计算引擎（commission_service）、前端页面可分别并行。

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability；计算引擎阶段无故事标签（跨切面）
- 每个用户故事独立可完成、可验收
- 权限沿用 `sharing_rules.read`/`write`（未改名为 performance.*，见 research D9）
- 金额一律以分（cent）存储/传输；比率 ratio 为小数
- 测试确认 FAIL 后再实现；每个 checkpoint 独立验证
- 单管理员约束迁移 010 对存量多管理员数据降级（保留 id 最小者）
