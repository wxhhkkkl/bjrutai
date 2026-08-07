# Tasks: 绩效计算模块月度核算（未核算月份选择 + 数据报表展示 + 审核冻结/打回）

**Input**: Design documents from `/specs/010-monthly-settlement/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Constitution I 强制 TDD —— 测试先于实现（先写失败测试，再实现变绿）。每个 Story 的测试任务必须在其实现任务之前完成。

**Organization**: Tasks are grouped by user story (US1-US3) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: 确认既有代码基线可运行，作为后续 TDD 的红/绿基准。

- [X] T001 Run existing backend test suite (`cd backend && pytest tests/`) to establish a green baseline before any changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `reports` 表支持核算来源记录（source/period/status）+ 报表记录生成机制，US1-US3 的前置。

- [X] T002 [P] Add `source` (String(32), server_default 'reconciliation') / `period` (String(7), nullable, index) / `status` (String(16), nullable) columns to `Report` model in `backend/src/models/report.py`
- [X] T003 Create Alembic migration 013 adding `reports.source` (NOT NULL default 'reconciliation') / `reports.period` / `reports.status` columns in `backend/migrations/versions/013_reports_settlement_source.py` (depends on T002)
- [X] T004 [P] Unit test `ReportService.ensure_settlement_report` (idempotent upsert by source='performance_settlement'+period; sections built from `commission_results` with 汇总/明细; status param reflected) in `backend/tests/unit/test_report_service.py` (new file)
- [X] T005 Implement `ReportService.ensure_settlement_report(db, period, status)` in `backend/src/services/report_service.py` (depends on T002/T003, T004)

**Checkpoint**: 迁移可 `alembic upgrade head` 成功；`ensure_settlement_report` 幂等生成/更新核算报表记录。

---

## Phase 3: User Story 1 - 月度核算：选定未核算月份并发起核算 (Priority: P1) 🎯 MVP

**Goal**: 管理员在绩效计算页通过月份选择器仅看到可核算月份（无核算记录/已打回），选定并发起核算，成功后该月进入待审核并从可核算列表消失。

**Independent Test**: 进入绩效计算页 → 月份选择器仅列出可核算月份 → 选定某月发起核算 → 提示成功、该月进入待审核 → 再次打开选择器该月不可选；已冻结月份不可选。

### Tests for User Story 1

- [X] T006 [P] [US1] Contract tests for `GET /api/v1/admin/performance/settleable-periods` (returns `{periods:[...]}`, permission `sharing_rules.read`) and `POST /api/v1/admin/performance/settlements/{period}/settle` (success → pending; error on non-settleable: pending/reviewed/future month; permission `performance.settle`) in `backend/tests/contract/test_admin_performance.py`
- [X] T007 [P] [US1] Unit test `settlement_service.settleable_periods` (derives months from bills, excludes future/pending/reviewed, includes rejected) and `settle` (rejects non-settleable, computes + ensures pending batch + report record) in `backend/tests/unit/test_settlement_service.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement `settlement_service.settleable_periods(db)` + `settle(db, period, operator_id)` (validate in settleable, call `compute_commission`, call `ReportService.ensure_settlement_report(period, pending)`) in `backend/src/services/settlement_service.py` (depends on T005/T006/T007)
- [X] T009 [US1] Implement `GET /admin/performance/settleable-periods` (permission `sharing_rules.read`) + `POST /admin/performance/settlements/{period}/settle` (permission `performance.settle`) in `backend/src/api/v1/admin_performance.py` (depends on T008)
- [X] T010 [US1] Add `settleablePeriods()` + `settle(period)` to `manageSystem/src/api/performance.js`
- [X] T011 [US1] Restrict 绩效计算页 month selector to settleable periods (from `GET settleable-periods`) + add「发起核算」button (calls `settle`, requires `performance.settle`) in `manageSystem/src/pages/performance/settlement.vue` (depends on T009/T010)
- [X] T012 [US1] Add 月度核算状态列表 (reuse `GET /admin/performance/settlements` no-period list: period + status) to 绩效计算页 so auto-pending months (monthly task) can be opened for review in `manageSystem/src/pages/performance/settlement.vue`

**Checkpoint**: US1 独立可用——月份选择器只列可核算月份，可发起核算，核算后进入待审核。

---

## Phase 4: User Story 2 - 数据报表展示：核算成功的结果进入数据报表菜单 (Priority: P1)

**Goal**: 核算成功后自动生成核算报表记录，展示在「数据报表」历史报表列表（带待审核状态标记），可查看汇总/明细与导出 Excel；无 `sharing_rules.read` 者不可见。

**Independent Test**: 核算成功后 → 打开数据报表菜单 → 看到该月核算报表记录（status=pending）→ 查看汇总+明细 → 导出 Excel（含绩效核算 sheet）→ 数据与核算结果一致；无 `sharing_rules.read` 的调用者列表不见该记录、详情/导出 403。

### Tests for User Story 2

- [X] T013 [P] [US2] Contract tests for reports list/detail/export with `source/period/status` fields: settlement report list item carries `status`; detail `sections.performance` has summary+details (含 `generated_by` 记录发起人); export returns Excel with 绩效核算 sheet; caller without `sharing_rules.read` sees filtered list and gets 403 on settlement report detail/export in `backend/tests/contract/test_reports.py`
- [X] T014 [US2] Integration test: seed settlement via `settle` → `GET /reports` shows the period record with `status=pending` → `review` → list `status=reviewed` → `reject` (reason) → `status=rejected` in `backend/tests/integration/test_performance_settlement_flow.py` (depends on T008)

### Implementation for User Story 2

- [X] T015 [US2] Extend `ReportService.list_reports` (include source/period/status), `get_detail` (return source/period/status + performance section), `export_excel` (add `performance`→「绩效核算」sheet to `dimension_sheet_config`) in `backend/src/services/report_service.py` (depends on T013)
- [X] T016 [US2] Update `reports.py` endpoints: pass caller payload; list filters out `source='performance_settlement'` records when caller lacks `sharing_rules.read`; detail/export return 403 for settlement records when caller lacks `sharing_rules.read` in `backend/src/api/v1/reports.py` (depends on T015)
- [X] T017 [US2] Hook `monthly_settlement_job` to call `ReportService.ensure_settlement_report(period, pending)` after auto-compute in `backend/src/tasks/settlement_task.py` (depends on T005)
- [X] T018 [US2] Show 核算来源记录的状态标记（待审核/已确认/已打回）+ 月份在数据报表历史列表 in `manageSystem/src/pages/reports/index.vue`
- [X] T019 [US2] Pass through `source/period/status` in `manageSystem/src/stores/reports.js` + add `performance` dimension label「绩效核算」and section rendering in `manageSystem/src/components/reports/ReportDetail.vue`

**Checkpoint**: US1 AND US2 独立可用——核算结果进入数据报表列表并带状态标记，可查看与导出。

---

## Phase 5: User Story 3 - 审核与冻结：核算结果需审核，通过后不可更改，不通过可打回重算 (Priority: P1)

**Goal**: 审核通过 → 冻结（不可再核算/更改）；审核不通过 → 打回（记录原因）→ 可重新核算 → 再待审核。报表记录状态随之流转。

**Independent Test**: 核算成功（pending）→ 审核通过 → 冻结，再次 settle 被拒绝、数值不变 → 对另一月打回（填原因）→ 可重新核算 → 回到 pending → 报表记录状态同步。

### Tests for User Story 3

- [X] T020 [P] [US3] Contract tests for review/reject/recompute status sync on settlement report record: `review` → report `status=reviewed`; `reject` requires reason → `status=rejected`; `recompute` on pending/rejected → `status=pending`; `review` on frozen month rejected (FR-008) in `backend/tests/contract/test_reports.py`
- [X] T021 [US3] Integration test full loop: settle → report pending → review → frozen (re-settle rejected, values unchanged; `reviewed_by`/`reviewed_at` recorded) → reject another month (reason 必填, `reject_reason` recorded) → recompute → pending → report status matches in `backend/tests/integration/test_performance_settlement_flow.py` (depends on T014)

### Implementation for User Story 3

- [X] T022 [US3] Update `settlement_service.review_settlement` / `reject_settlement` / `recompute_settlement` to call `ReportService.ensure_settlement_report(period, <new status>)` after state change in `backend/src/services/settlement_service.py` (depends on T005/T020)
- [X] T023 [US3] Ensure `compute_commission` frozen-skip guard stays intact (reviewed period returns `frozen=True`, no upsert) — verify + add regression assertion in `backend/tests/unit/test_commission_freeze.py`
- [X] T024 [US3] Confirm 绩效计算页 review actions (确认/打回/重算) still drive freeze/reject/recompute after settle flow, and month re-enters pending on recompute in `manageSystem/src/pages/performance/settlement.vue`

**Checkpoint**: 全部 3 个 User Story 独立可用——审核冻结/打回闭环完整，报表记录状态实时同步。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 跨 Story 的收尾与验证。

- [X] T025 [P] Verify sidebar/menu + permission gating for 绩效计算页 (view `sharing_rules.read` / actions `performance.settle`) and 数据报表页 (核算记录查看 `sharing_rules.read`) in `manageSystem/src/App.vue`, `manageSystem/src/router/index.js`
- [X] T026 Run `specs/010-monthly-settlement/quickstart.md` validation path against SC-001~SC-008, asserting settleable-periods list correctness (SC-001), 核算结果与规则一致 (SC-002), report visible within 2s (SC-003/SC-007), frozen unchanged (SC-004), reject→recompute→pending (SC-005), report data consistency (SC-006), audit trail (SC-008)
- [X] T027 [P] Update feature docs if implementation diverges from `specs/010-monthly-settlement/plan.md` / `research.md` / `contracts/admin-settlement-reports.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — green baseline
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (reports columns + migration + ensure_settlement_report)
- **User Stories (Phase 3+)**: All depend on Foundational
  - US1 / US2 / US3 can proceed sequentially (P1) or in parallel (staff permitting)
- **Polish (Phase 6)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (P1)**: After Foundational (T002-T005); settle triggers `ensure_settlement_report` (mechanism from T005)
- **US2 (P1)**: After Foundational; report display + permission + monthly-task hook. Integration T014 depends on US1's settle (T008) to seed the settlement
- **US3 (P1)**: After Foundational; reuses 008 review/reject/recompute endpoints + adds report-status sync; integration T021 depends on US1 settle + US2 report display
- All three are independently testable at contract/unit level; integration journeys chain in order US1 → US2 → US3

### Within Each User Story

- Tests written FIRST and FAILING before implementation (TDD, Constitution I)
- Service logic → endpoints → frontend wiring

### Parallel Opportunities

- Foundational T002/T004 (different files); T003 after T002; T005 after T004
- US1 tests T006/T007 parallel; impl T008 → T009 → T010/T011/T012
- US2 tests T013 parallel, T014 after T008; impl T015 → T016 → T017/T018/T019
- US3 tests T020 parallel, T021 after T014; impl T022 → T023/T024
- Polish T025/T027 parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests together (TDD red phase):
Task: "Contract tests for settleable-periods + settle endpoints"
Task: "Unit test settleable_periods derivation + settle validation"

# After tests pass (green), implementation:
Task: "Implement settleable_periods + settle in settlement_service"
Task: "Implement GET settleable-periods + POST settle endpoints"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (baseline) + Phase 2 (foundational)
2. Complete Phase 3: US1（未核算月份选择 + 发起核算）
3. **STOP and VALIDATE**: 月份选择器只列可核算月份、可发起核算、核算后进入待审核
4. Deploy/demo if ready

### Incremental Delivery

1. Foundation ready (reports columns + migration + ensure_settlement_report)
2. US1 未核算月份选择 + 发起核算 → test → demo（MVP）
3. US2 数据报表展示（状态标记/详情/导出）→ test → demo
4. US3 审核冻结/打回 + 报表状态同步 → test → demo

### Parallel Team Strategy

With multiple developers after Foundational:
- Developer A: US1（settleable-periods + settle）
- Developer B: US2（报表记录展示 + 权限 + 月度任务联动）
- Developer C: US3（审核状态同步 + 冻结回归）

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD: verify tests fail before implementing (Constitution I)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
