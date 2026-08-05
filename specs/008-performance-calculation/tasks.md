# Tasks: 绩效计算模块（月度核算 + 审核确认 + 小程序展示 + 导出）

**Input**: Design documents from `/specs/008-performance-calculation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Constitution I 强制 TDD —— 测试先于实现（先写失败测试，再实现变绿）。每个 Story 的测试任务必须在其实现任务之前完成。

**Organization**: Tasks are grouped by user story (US1-US4) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: 确认既有代码基线可运行，作为后续 TDD 的红/绿基准。

- [X] T001 Run existing backend test suite (`cd backend && pytest tests/`) to establish a green baseline before any changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 结算批次模型 + 迁移 + 权限点，US1-US4 的前置。

- [X] T002 [P] Create `PerformanceSettlement` model (period unique, status enum pending/reviewed/rejected, reviewed_by/reviewed_at/reject_reason) in `backend/src/models/performance_settlement.py`
- [X] T003 Create Alembic migration adding `performance_settlements` table + `commission_results.rule_snapshot` JSON column in `backend/migrations/` (depends on T002)
- [X] T004 [P] Add `performance.settle` to `_ALL_PERMISSIONS` in `backend/src/services/seed_service.py`
- [X] T005 [P] Add `performance` permission module with `performance.settle` to `manageSystem/src/constants/permissions.js`

**Checkpoint**: 迁移可 `alembic upgrade head` 成功；seed 同步系统管理员权限；前端权限表新增模块。

---

## Phase 3: User Story 1 - 绩效计算页：组织结构树 + 当月绩效估算 (Priority: P1) 🎯 MVP

**Goal**: 管理员进入"绩效计算"页，看到组织结构树与选中组织每人当月绩效估算（默认当前月、默认根组织），支持切组织/月份。

**Independent Test**: 打开绩效计算页 → 组织树默认根组织 → 右侧显示每人估算 → 切换组织/月份 → 估算更新且与当前绩效规则一致。

### Tests for User Story 1

- [X] T006 [P] [US1] Contract test for `GET /api/v1/admin/performance/estimates` (request/response shape, permission `sharing_rules.read`) in `backend/tests/contract/test_admin_performance.py`
- [X] T007 [P] [US1] Unit test locking estimate computation matches current rule tiers (base/ratio/commission from `preview_org_commission`) in `backend/tests/unit/test_performance_estimate.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement `GET /api/v1/admin/performance/estimates` (reuse `commission_service.preview_org_commission`, permission `sharing_rules.read`) in `backend/src/api/v1/admin_performance.py` and register router in `backend/src/main.py` (depends on T006)
- [X] T009 [US1] Build 绩效计算 page (org tree + person estimate table, period selector) in `manageSystem/src/pages/performance/settlement.vue` (depends on T008)
- [X] T010 [US1] Wire up route `/performance` + sidebar menu「绩效计算」+ store in `manageSystem/src/router/index.js`, `manageSystem/src/App.vue`, `manageSystem/src/stores/performance.js`

**Checkpoint**: US1 独立可用——管理后台能看到组织树与每人当月估算。

---

## Phase 4: User Story 2 - 月度核算与审核确认（冻结 + 规则快照） (Priority: P1)

**Goal**: 月度核算进入待审核；管理员确认后冻结（不再重算）并保留规则快照；支持打回（记录原因）后重算再审核。

**Independent Test**: 触发核算 → 批次 pending → 小程序不展示已确认 → 确认 → 批次 reviewed → 修改规则后重算 → 已确认月份数字不变（快照生效）。

### Tests for User Story 2

- [X] T011 [P] [US2] Contract tests for review/reject/recompute/settlements endpoints (`POST /api/v1/admin/performance/settlements/{period}/review|reject|recompute`, `GET .../settlements`) in `backend/tests/contract/test_admin_performance.py`
- [X] T012 [P] [US2] Unit test settlement state machine (pending→reviewed, pending→rejected→pending via recompute; reviewed frozen; edge: distributor deactivated/left handled by period ownership & business data) in `backend/tests/unit/test_settlement_service.py`
- [X] T013 [P] [US2] Unit test `compute_commission` skips reviewed periods and writes `rule_snapshot` in `backend/tests/unit/test_commission_freeze.py`
- [X] T014 [US2] Integration test full journey (settle→pending→confirm→freeze→rule change→unchanged) in `backend/tests/integration/test_performance_settlement_flow.py`

### Implementation for User Story 2

- [X] T015 [US2] Implement `settlement_service.py` (review/reject/recompute with conditional UPDATE, idempotent confirm) in `backend/src/services/settlement_service.py` (depends on T002/T003, T012)
- [X] T016 [US2] Extend `commission_service.compute_commission` to skip reviewed periods + write `rule_snapshot` into each result in `backend/src/services/commission_service.py` (depends on T015, T013)
- [X] T017 [US2] Implement review/reject/recompute/settlements endpoints (permission `performance.settle`) in `backend/src/api/v1/admin_performance.py` (depends on T015); monthly results query reuses existing `GET /api/v1/admin/commission-results` (006) — no duplicate endpoint
- [X] T018 [US2] Update `monthly_settlement_job` to create/ensure `pending` settlement batch after auto-compute in `backend/src/tasks/settlement_task.py`
- [X] T019 [US2] Add review actions (确认/打回/重算) + settlement status banner to 绩效计算 page in `manageSystem/src/pages/performance/settlement.vue`

**Checkpoint**: US1 AND US2 独立可用——管理后台可审核、冻结、打回，已确认月份不被重算。

---

## Phase 5: User Story 3 - 小程序绩效展示：当月预估 + 已确认结果 (Priority: P1)

**Goal**: 推广员看本人、组织管理员看所管组织的当月提成预估（实时）与历史已确认月份（冻结），仅提成金额明细。

**Independent Test**: 小程序进入绩效页 → 当月显示预估 → 已确认月份显示冻结结果 → 未确认月份不显示为已确认。

### Tests for User Story 3

- [X] T020 [P] [US3] Contract tests for `GET /api/v1/my/performance/commission` and `GET /api/v1/org/performance/commission` in `backend/tests/contract/test_miniprogram_performance.py`
- [X] T021 [P] [US3] Unit test confirmed-month filtering (only `reviewed` settlements returned; estimate is real-time) and assert `/api/v1/my/performance/commission` current-month estimate equals `/api/v1/admin/performance/estimates` baseCent/commissionCent for same distributor (SC-008) in `backend/tests/unit/test_miniprogram_performance.py`

### Implementation for User Story 3

- [X] T022 [US3] Implement `GET /api/v1/my/performance/commission` and `GET /api/v1/org/performance/commission` (get_current_user; promoter own / org-admin subtree; confirmed = reviewed settlements) in `backend/src/api/v1/my_performance.py` and register router in `backend/src/main.py` (depends on T020)
- [X] T023 [P] [US3] Add mini-program service `commission-service.js` + promoter performance page (estimate + confirmed months) in `miniProgram/services/commission-service.js`, `miniProgram/pages/performance/`
- [X] T024 [US3] Add commission estimate/confirmed section to org-performance page for org admins in `miniProgram/pages/org-performance/`

**Checkpoint**: US1, US2 AND US3 独立可用——小程序展示预估与已确认。

---

## Phase 6: User Story 4 - 管理员导出月度核算详情 (Priority: P2)

**Goal**: 管理员导出某月核算明细为 CSV 表格文件，数据与页面一致。

**Independent Test**: 选择某月 → 导出 → 下载 CSV → 与接口/页面数据一致；无数据时明确提示。

### Tests for User Story 4

- [X] T025 [P] [US4] Contract test for `GET /api/v1/admin/performance/settlements/{period}/export` (CSV content columns, permission `performance.settle`) in `backend/tests/contract/test_admin_performance.py`

### Implementation for User Story 4

- [X] T026 [US4] Implement export endpoint returning CSV (columns: period/org/distributor/ruleType/baseCent/ratio/commissionCent/computedAt; empty-data handling) in `backend/src/api/v1/admin_performance.py` (depends on T025)
- [X] T027 [US4] Add export button + download handling on 绩效计算 page in `manageSystem/src/pages/performance/settlement.vue`

**Checkpoint**: 全部 4 个 User Story 独立可用。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 跨 Story 的收尾与验证。

- [X] T028 [P] Verify sidebar menu gating for 绩效计算 page (`sharing_rules.read` view / `performance.settle` review-export) in `manageSystem/src/App.vue`, `manageSystem/src/router/index.js`
- [X] T029 Run `specs/008-performance-calculation/quickstart.md` validation path against SC-001~SC-008, asserting 绩效计算 page (org tree + estimates) loads within 2 seconds (SC-001)
- [X] T030 [P] Update feature docs if implementation diverges from `specs/008-performance-calculation/plan.md` / `research.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — green baseline
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (model + migration + permission)
- **User Stories (Phase 3+)**: All depend on Foundational
  - US1 / US2 / US3 / US4 can proceed sequentially (P1 → P2) or in parallel (staff permitting)
- **Polish (Phase 7)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (P1)**: After Foundational; no deps on other stories (estimates reuse existing preview engine)
- **US2 (P1)**: After Foundational (T002/T003); core freeze/snapshot logic
- **US3 (P1)**: After Foundational (migration for confirmed months); independent of US1/US2 UI, but confirmed data requires US2 review endpoints (tests seed reviewed settlements directly)
- **US4 (P2)**: After Foundational (settlement model + results); independent of US1-US3

### Within Each User Story

- Tests written FIRST and FAILING before implementation (TDD)
- Endpoint → service → UI wiring

### Parallel Opportunities

- Foundational T002/T004/T005 (different files)
- US1 tests T006/T007; US1 impl T008 then T009/T010
- US2 tests T011/T012/T013 parallel, then T014
- US3 tests T020/T021 parallel; impl T022 then T023/T024
- US4 test T025 then impl T026/T027

---

## Parallel Example: User Story 2

```bash
# Launch all tests together (TDD red phase):
Task: "Contract tests for review/reject/recompute/settlements endpoints"
Task: "Unit test settlement state machine"
Task: "Unit test compute_commission freeze + snapshot"

# After tests pass (green), implementation:
Task: "Implement settlement_service.py"
Task: "Extend commission_service.compute_commission (freeze + snapshot)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (baseline) + Phase 2 (foundational)
2. Complete Phase 3: US1 (绩效计算页 + 估算)
3. **STOP and VALIDATE**: 组织树 + 每人当月估算可用
4. Deploy/demo if ready

### Incremental Delivery

1. Foundation ready (settlement model + migration + permission)
2. US1 估算页 → test → demo（MVP）
3. US2 审核/冻结 → test → demo
4. US3 小程序预估/已确认 → test → demo
5. US4 导出 → test → demo

### Parallel Team Strategy

With multiple developers after Foundational:
- Developer A: US1（估算页）
- Developer B: US2（审核/冻结/快照）
- Developer C: US3（小程序）+ US4（导出）

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD: verify tests fail before implementing (Constitution I)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
