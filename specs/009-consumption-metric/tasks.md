# Tasks: 业绩贡献口径统一为消费金额（移除业绩贡献值体系）

**Input**: Design documents from `/specs/009-consumption-metric/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Constitution I 强制 TDD —— 测试先于实现（先写失败测试，再实现变绿）。每个 Story 的测试任务必须在其实现任务之前完成。

**Organization**: Tasks are grouped by user story (US1-US3) to enable independent implementation and testing.

> 说明：本任务清单为**回顾性**记录（功能已实现、未提交），所有任务标记 `[X]` 完成，与实际改动文件一致。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: 确认既有代码基线可运行，作为后续 TDD 的红/绿基准。

- [X] T001 Run existing backend test suite (`cd backend && pytest tests/`) to establish a green baseline before any changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 统一口径 helper `consumption_service`，US1-US3 的前置。

- [X] T002 [P] Unit test consumption_service（求和/排除退款取消/周期过滤/空输入/按客户分组）in `backend/tests/unit/test_consumption_service.py`
- [X] T003 [P] Implement `consumption_service.py`（`consumption_by_distributor` / `consumption_by_customer` / `period_start_end`）in `backend/src/services/consumption_service.py`（depends on T002）

**Checkpoint**: 全系统唯一口径 helper 可用，单测通过。

---

## Phase 3: User Story 1 - 管理后台：业绩展示统一为消费金额 (Priority: P1) 🎯 MVP

**Goal**: 管理员在管理后台看到的业绩数据（消费业绩页/工作台/客户详情/组织绩效/报表）全部按消费金额（分→元）口径展示。

**Independent Test**: 进入消费业绩页 → 本月/累计消费金额（¥）与月度趋势 → 工作台「本月消费」与客户详情「消费记录」 → 与账单实付金额手算一致。

### Tests for User Story 1

- [X] T004 [P] [US1] Update contract tests for promoter consumption endpoints（overview/trend/list/detail → `*AmountCent`）in `backend/tests/contract/test_contributions.py`
- [X] T005 [P] [US1] Update contract test for admin dashboard/rankings（`monthlyAmountCent`/`totalAmountCent`/`amountCent`）in `backend/tests/contract/test_admin_contribution_dashboard.py`
- [X] T006 [P] [US1] Update contract test for org performance（thisMonth/cumulative 整数分）in `backend/tests/contract/test_org_performance.py`
- [X] T007 [P] [US1] Update unit test for dashboard service（bills 聚合）in `backend/tests/unit/test_contribution_dashboard_service.py`
- [X] T008 [P] [US1] Update unit test for org performance service in `backend/tests/unit/test_org_performance_service.py`

### Implementation for User Story 1

- [X] T009 [P] [US1] Rewrite query service（`ContributionQueryService` → `ConsumptionQueryService`，账单口径）in `backend/src/services/contribution_query_service.py`（depends on T004）
- [X] T010 [P] [US1] Rewrite dashboard service（bills 聚合：stats/trend/最新30条/排名 → `amountCent`）in `backend/src/services/contribution_dashboard_service.py`（depends on T005）
- [X] T011 [P] [US1] Rewrite promoter endpoints（overview/trend/list/detail 按账单；删除 `/composition`）in `backend/src/api/v1/contributions.py`
- [X] T012 [P] [US1] Update customer endpoints（`monthlyConsumptionCent`/`totalConsumptionCent`、消费记录为账单）in `backend/src/api/v1/customers.py`
- [X] T013 [P] [US1] Update workbench endpoints（`myMonthlyConsumption`、`contribution-summary` 返回 `totalAmountCent`/count）in `backend/src/api/v1/workbench.py`
- [X] T014 [P] [US1] Update consumption-based services（`team_service.py` / `org_performance_service.py` / `report_service.py` / `commission_service.py` 复用 `consumption_by_distributor`）in `backend/src/services/`
- [X] T015 [P] [US1] Update schema（`this_month`/`cumulative` 整数分）in `backend/src/schemas/org_performance.py`
- [X] T016 [P] [US1] Update admin 消费业绩页（stats/趋势/排名/最新明细 → `amountCent` + ¥）in `manageSystem/src/pages/contributions/index.vue`
- [X] T017 [P] [US1] Update admin dashboard（本月消费 ¥ 替代本月业绩分）in `manageSystem/src/pages/dashboard/index.vue`
- [X] T018 [P] [US1] Update customer detail 消费记录 tab in `manageSystem/src/pages/customers/detail.vue`
- [X] T019 [P] [US1] Update admin wiring（菜单/路由/权限标签「业绩贡献」→「消费业绩」）in `manageSystem/src/App.vue`、`router/index.js`、`constants/permissions.js`

**Checkpoint**: US1 独立可用——管理后台业绩数据全部为消费金额。

---

## Phase 4: User Story 2 - 小程序：贡献展示统一为消费金额 (Priority: P1)

**Goal**: 小程序各入口「贡献值（分）/已结算/待结算」统一改为「消费金额（¥）/已支付/待支付」，与管理后台同口径。

**Independent Test**: 小程序贡献明细页 → 「本月消费 ¥…」→ 明细状态「已支付/待支付」→ 首页「我的消费」→ 与后台同一分销员消费金额一致。

### Implementation for User Story 2

- [X] T020 [P] [US2] Update mini-program models/mock fixtures（金额去 `+`、状态文案）in `miniProgram/models/contribution-detail.js`、`customer-detail.js`
- [X] T021 [P] [US2] Update contribution page（分/已结算 → ¥/已支付；删除来源筛选与构成）in `miniProgram/pages/contribution/index.*`
- [X] T022 [P] [US2] Update contribution-detail page（贡献明细 → 消费明细）in `miniProgram/pages/contribution-detail/index.*`
- [X] T023 [P] [US2] Update home page（我的贡献 → 我的消费）in `miniProgram/pages/home/index.wxml`
- [X] T024 [P] [US2] Update org-performance page + service（成员/下级组织消费金额 ¥）in `miniProgram/pages/org-performance/index.wxml`、`services/org-performance-service.js`
- [X] T025 [P] [US2] Update customer-detail & profile in `miniProgram/pages/customer-detail/index.wxml`、`pages/profile/index.js`
- [X] T026 [P] [US2] Update tab 文案与 FAQ（tab「贡献」→「消费」）in `miniProgram/app.json`、`models/navigation.js`、`mock/foundation-fixtures.js`、`models/help-feedback.js`

**Checkpoint**: US1 AND US2 独立可用——小程序展示消费金额。

---

## Phase 5: User Story 3 - 存量数据迁移与贡献体系移除 (Priority: P1)

**Goal**: 迁移 012 将存量无账单贡献记录合成为消费账单（保证历史数据可见），随后删除贡献三表及对应模型/服务/接口能力。

**Independent Test**: 备份 → `alembic upgrade head` → 存量贡献记录以消费账单可见（金额一致）→ 三表已删除 → 代码无贡献体系残留。

### Tests for User Story 3

- [X] T027 [P] [US3] Delete obsolete contribution unit test in `backend/tests/unit/test_contribution_service.py`
- [X] T028 [P] [US3] Update integration tests（账单口径/移除贡献引用）in `backend/tests/integration/test_contribution_calc.py`、`test_contribution_view_flow.py`、`test_report_flow.py`、`test_sync_flow.py`
- [X] T029 [P] [US3] Update unit test for commission service（复用消费口径）in `backend/tests/unit/test_commission_service.py`

### Implementation for User Story 3

- [X] T030 [P] [US3] Create migration 012（合成历史账单 + 删除贡献三表，破坏性）in `backend/migrations/versions/012_drop_contribution_records.py`
- [X] T031 [P] [US3] Delete contribution model/service/schema in `backend/src/models/contribution.py`、`schemas/contribution.py`、`services/contribution_service.py`
- [X] T032 [P] [US3] Update models（移除贡献/系数模型与分销员关系）in `backend/src/models/__init__.py`、`sharing.py`、`distributor.py`
- [X] T033 [P] [US3] Remove contribution coefficient（schema + service）in `backend/src/schemas/sharing.py`、`services/sharing_service.py`
- [X] T034 [P] [US3] Remove 账单→贡献创建 / 退款冲正逻辑 in `backend/src/services/sync_service.py`
- [X] T035 [P] [US3] Remove contribution references & `batch_settle` in `backend/src/services/org_migration.py`、`tasks/settlement_task.py`
- [X] T036 [P] [US3] Update migration verification script（移除 contribution_records 检查）in `backend/scripts/verify_migration.py`

**Checkpoint**: US1, US2 AND US3 独立可用——贡献体系已移除，历史数据以消费账单保留。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 跨 Story 的收尾与验证。

- [X] T037 [P] Update feature docs（spec/plan/research/data-model/contracts/quickstart + CLAUDE.md SPECKIT 指向）in `specs/009-consumption-metric/`、`CLAUDE.md`
- [X] T038 Run full backend test suite（`cd backend && pytest tests/`，353 passed）+ grep 确认无 `ContributionRecord`/`ContributionCoefficient`/`batch_settle` 残留

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — green baseline
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories（口径 helper 是所有业绩查询的前置）
- **User Stories (Phase 3+)**: All depend on Foundational
  - US1 / US2 / US3 can proceed sequentially (P1) or in parallel (staff permitting)
- **Polish (Phase 6)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (P1)**: After Foundational（consumption_service）；无其他 story 依赖
- **US2 (P1)**: After Foundational；独立于 US1 的接口（展示同源数据）
- **US3 (P1)**: After Foundational；迁移删除贡献表不阻塞 US1/US2 的账单查询，但需在移除模型/服务前完成（T030 依赖被删模型的降级顺序——实际一次性完成）

### Within Each User Story

- Tests written FIRST and FAILING before implementation（TDD）
- 后端服务 → API → 前端展示

### Parallel Opportunities

- Foundational T002/T003（不同文件）
- US1 tests T004~T008 并行；impl T009~T015（后端）与 T016~T019（前端）并行
- US2 T020~T026 全并行（不同文件）
- US3 tests T027~T029 并行；impl T030~T036 并行（不同文件）

---

## Parallel Example: User Story 1

```bash
# Launch all tests together (TDD red phase):
Task: "Update contract tests for promoter consumption endpoints (amountCent)"
Task: "Update contract test for admin dashboard/rankings"
Task: "Update unit test for dashboard service"

# After tests pass (green), implementation:
Task: "Rewrite query service (ConsumptionQueryService)"
Task: "Rewrite dashboard service (bills aggregation)"
Task: "Rewrite promoter endpoints"
```

---

## Implementation Strategy

> 本功能已实现（回顾性记录）。以下保留标准策略供参考。

### MVP First (User Story 1 Only)

1. Complete Phase 1 (baseline) + Phase 2 (foundational)
2. Complete Phase 3: US1（管理后台消费金额）
3. **STOP and VALIDATE**: 管理后台业绩数据全部为消费金额
4. Deploy/demo if ready

### Incremental Delivery

1. Foundation ready（consumption_service 统一口径）
2. US1 管理后台 → test → demo
3. US2 小程序 → test → demo
4. US3 迁移与删表 → test → demo（需先备份库）

### Parallel Team Strategy

With multiple developers after Foundational:
- Developer A: US1（管理后台）
- Developer B: US2（小程序）
- Developer C: US3（迁移与删除）

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- 本清单为回顾性记录，全部任务已完成（`[X]`），代码位于 `009-consumption-metric` 分支工作区（未提交）
- 迁移 012 为破坏性迁移，`alembic upgrade head` 前必须备份数据库（quickstart.md 有步骤）
- Commit 建议：按 Phase 分组提交（foundational → US1 → US2 → US3 → polish）
