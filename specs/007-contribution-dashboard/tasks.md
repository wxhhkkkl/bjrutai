# Tasks: 业绩贡献页面增强

**Input**: Design documents from `/specs/007-contribution-dashboard/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/contribution-dashboard.md](./contracts/contribution-dashboard.md), [quickstart.md](./quickstart.md)

**Tests**: 本项目宪法（`.specify/memory/constitution.md` 原则 I）强制 TDD——所有生产代码先写测试、每个 API 端点必须有契约测试。

**Organization**: 任务按用户故事分组，支持独立实现与独立验收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
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

**Purpose**: 看板聚合服务与 admin 路由骨架。本阶段完成前不得开始任何用户故事。

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create `backend/src/services/contribution_dashboard_service.py` scaffold: helpers `_month_bounds(month)`、`_points_sum()`（`func.sum(func.cast(points, Numeric))`）、`_subtree_org_ids(db, org_id)`（复用 `organization_service.get_subtree` + `distributor_service._collect_org_ids`）
- [X] T004 Create `backend/src/api/v1/admin_contributions.py` router scaffold（`prefix="/admin/contributions"`，`get_admin_user` + `require_permission("contributions.read")`）and register in `backend/src/main.py`
- [X] T005 [P] Create `manageSystem/src/api/contributions.js`（dashboard/orgsRanking/personsRanking/bindingsRanking，复用 [org.js](manageSystem/src/api/org.js) payload 模式）

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 业绩总览（按月查询 + 趋势 + 统计）(Priority: P1) 🎯 MVP

**Goal**: 进入页面默认展示月度趋势 + 统计数据；支持按月查询所有人的业绩；数据源为 `/admin/contributions`。

**Independent Test**: 进入页 2s 内看到统计与趋势；切换月份后数据随之更新且与明细一致。

### Tests for User Story 1（TDD：先写、先红）⚠️

- [X] T006 [P] [US1] Contract test `GET /admin/contributions/dashboard` in `backend/tests/contract/test_admin_contribution_dashboard.py`（stats/trend/latest、orgId 子树过滤、无 `contributions.read` 权限 40300）
- [X] T007 [P] [US1] Unit test `get_dashboard` in `backend/tests/unit/test_contribution_dashboard_service.py`（当月总业绩=当月明细之和；累计；orgCount/personCount/boundUserCount；趋势近 N 月）

### Implementation for User Story 1

- [X] T008 [US1] Implement `get_dashboard(db, month, period, org_id)` in `contribution_dashboard_service.py`（stats：monthlyPoints/totalPoints/orgCount/personCount/boundUserCount；trend 近 N 月按月 SUM；latest 30 条按 `occurred_at` 倒序，含 personName/orgName）
- [X] T009 [US1] Implement `GET /admin/contributions/dashboard` endpoint in `admin_contributions.py`（month 必填、period 默认 12m、orgId 可选）
- [X] T010 [US1] Rebuild `manageSystem/src/pages/contributions/index.vue`：筛选栏（月份 + 组织树选择器 `el-tree-select`）+ 统计行 + 趋势图，数据源切换为 `/admin/contributions/*`（保留月度结算按钮；确认旧 `stores/contributions.js` 引用后移除）

**Checkpoint**: US1 独立可用——进入见趋势/统计、时间查询可用（SC-001/SC-002）

---

## Phase 4: User Story 2 - 组织当月业绩排名 (Priority: P1)

**Goal**: 全局组织业绩排名列表 + 组织树筛选（某组织及子树）。

**Independent Test**: 查看组织当月业绩排名 → 与各组织贡献值汇总一致；选组织后限缩到子树。

### Tests for User Story 2（TDD：先写、先红）⚠️

- [X] T011 [P] [US2] Contract test `GET /admin/contributions/rankings/orgs` in `test_admin_contribution_dashboard.py`（全局排名、orgId 子树过滤、并列 rank、分页）
- [X] T012 [P] [US2] Unit test `org_ranking` in `test_contribution_dashboard_service.py`

### Implementation for User Story 2

- [X] T013 [US2] Implement `org_ranking(db, month, org_id, page, page_size)` in `contribution_dashboard_service.py`（`contribution_records JOIN distributors` 按 org_id 分组 SUM，month 内，并列同 rank，Top-N/分页）
- [X] T014 [US2] Implement `GET /admin/contributions/rankings/orgs` endpoint in `admin_contributions.py`
- [X] T015 [US2] Add 组织业绩排名 section（表格 + 组织树选择器过滤）to `contributions/index.vue`

**Checkpoint**: US1 + US2 均独立可用（SC-003）

---

## Phase 5: User Story 3 - 个人当月业绩排名 (Priority: P1)

**Goal**: 各人员当月业绩贡献排名（按贡献值从高到低）。

**Independent Test**: 查看个人当月业绩排名 → 与个人贡献记录汇总一致。

### Tests for User Story 3（TDD：先写、先红）⚠️

- [X] T016 [P] [US3] Contract test `GET /admin/contributions/rankings/persons` in `test_admin_contribution_dashboard.py`（排名/姓名/组织、orgId 过滤、并列 rank）
- [X] T017 [P] [US3] Unit test `persons_ranking` in `test_contribution_dashboard_service.py`

### Implementation for User Story 3

- [X] T018 [US3] Implement `persons_ranking(db, month, org_id, page, page_size)` in `contribution_dashboard_service.py`（按 distributor_id 分组 SUM，含姓名/组织，并列同 rank）
- [X] T019 [US3] Implement `GET /admin/contributions/rankings/persons` endpoint in `admin_contributions.py`
- [X] T020 [US3] Add 个人业绩排名 section to `contributions/index.vue`

**Checkpoint**: US1-US3 均独立可用（SC-004）

---

## Phase 6: User Story 4 - 绑定用户数量排名 (Priority: P1)

**Goal**: 绑定客户数量排名，个人与组织两维度可切换。

**Independent Test**: 查看个人/组织绑定数量排名 → 与实际已绑定客户数一致。

### Tests for User Story 4（TDD：先写、先红）⚠️

- [X] T021 [P] [US4] Contract test `GET /admin/contributions/rankings/bindings` in `test_admin_contribution_dashboard.py`（scope=person：每分销员 bound 客户数；scope=org：子树绑定总数；orgId 过滤）
- [X] T022 [P] [US4] Unit test `bindings_ranking` in `test_contribution_dashboard_service.py`

### Implementation for User Story 4

- [X] T023 [US4] Implement `bindings_ranking(db, scope, org_id, page, page_size)` in `contribution_dashboard_service.py`（person：`customers WHERE binding_status='bound' GROUP BY distributor_id`；org：子树人员绑定总数）
- [X] T024 [US4] Implement `GET /admin/contributions/rankings/bindings?scope=person|org` endpoint in `admin_contributions.py`
- [X] T025 [US4] Add 绑定数量排名 section（person/org 切换）to `contributions/index.vue`

**Checkpoint**: US1-US4 均独立可用（SC-005）

---

## Phase 7: User Story 5 - 最新业绩贡献明细 30 条 (Priority: P2)

**Goal**: 页面默认直接展示最新 30 条业绩贡献明细。

**Independent Test**: 进入页面默认看到最新 30 条明细，确为最近发生记录。

### Tests for User Story 5（TDD：先写、先红）⚠️

- [X] T026 [P] [US5] Unit test `dashboard.latest` 在 `test_contribution_dashboard_service.py`（≤30 条、按 `occurred_at` 倒序、含 personName/orgName）

### Implementation for User Story 5

- [X] T027 [US5] Ensure `get_dashboard` 的 `latest` 字段返回最新 30 条（occurred_at 倒序）——由 T008 实现，此处补充验收断言
- [X] T028 [US5] Add 最新业绩明细 section（30 条表格）to `contributions/index.vue`

**Checkpoint**: SC-006 满足

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 全量回归、构建验证、清理旧前端 store、文档

- [X] T029 [P] Remove orphaned `manageSystem/src/stores/contributions.js`（确认无其他引用后删除）
- [X] T030 [P] Run full backend pytest suite（`cd backend && ./venv/Scripts/python.exe -m pytest -q`）; fix regressions
- [X] T031 Run manageSystem build + manual verification per [quickstart.md](./quickstart.md)（SC-001~SC-006）
- [X] T032 Update `specs/007-contribution-dashboard/quickstart.md` / `contracts/contribution-dashboard.md` if behavior drifted

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify baseline first
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all stories
- **US1 (Phase 3)**: Depends on Foundational（dashboard 端点 + 前端看板骨架）
- **US2 (Phase 4)**: Depends on Foundational + US1 前端筛选栏（组织树选择器）
- **US3 (Phase 5)**: Depends on Foundational + US1 前端骨架
- **US4 (Phase 6)**: Depends on Foundational + US1 前端骨架
- **US5 (Phase 7)**: Depends on US1（dashboard.latest 由 T008 实现）
- **Polish (Phase 8)**: Depends on all

### User Story Dependencies

- US1: Foundational 后可开始（MVP）
- US2/US3/US4: 后端独立于 US1；前端挂到 US1 重构后的页面
- US5: 复用 US1 dashboard.latest

### Within Each Phase

- 测试先写并确认 FAIL（Red），再实现使其 PASS（Green）
- Service → endpoint → 前端集成
- 前端 `contributions/index.vue` 为共享文件，跨故事按序编辑

### Parallel Opportunities

- Setup：T001/T002 并行
- Foundational：T003/T005 并行；T004 依赖 T003
- US2/US3/US4 后端（T013/T018/T023）与 US1 后端可并行（不同聚合方法）
- 各故事契约测试 [P] 并行

---

## Parallel Example: US1

```bash
# Launch all US1 tests together:
Task: "Contract test dashboard in backend/tests/contract/test_admin_contribution_dashboard.py"
Task: "Unit test get_dashboard in backend/tests/unit/test_contribution_dashboard_service.py"

# Implementation (sequential, shared service):
Task: "Implement get_dashboard in backend/src/services/contribution_dashboard_service.py"
Task: "Implement GET /admin/contributions/dashboard in admin_contributions.py"
Task: "Rebuild contributions/index.vue dashboard layout"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: 基线校验
2. Phase 2: Foundational（服务助手 + 路由 + API 模块）
3. Phase 3: US1 业绩总览（统计 + 趋势 + 时间查询）
4. **STOP and VALIDATE**: 进入见趋势/统计、时间查询可用

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. US1 业绩总览 → 独立验证（MVP）
3. US2 组织排名 → 独立验证
4. US3 个人排名 → 独立验证
5. US4 绑定数量排名 → 独立验证
6. US5 最新明细 → 独立验证
7. Polish：全量回归 + 构建 + 清理旧 store

### Parallel Team Strategy

US2/US3/US4 后端聚合方法相互独立可并行；前端共享 `contributions/index.vue` 顺序编辑；测试任务并行。

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- 现有 `/contributions`（个人视角）不改造，小程序端个人贡献继续使用；管理后台切换到 `/admin/contributions`
- `points` 为字符串列，聚合统一 `CAST(points AS DECIMAL)`（D3）
- 排名按可选月份、并列同 rank、Top-N/分页（D7）
- 测试确认 FAIL 后再实现；每个 checkpoint 独立验证
