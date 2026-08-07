# Phase 0 Research: 绩效计算模块月度核算（未核算月份选择 + 数据报表展示 + 审核冻结/打回）

技术未知点与决策，依据 spec.md（含 2026-08-07 澄清）与现有代码（`commission_service.py`、`settlement_service.py`、`report.py`、`report_service.py`、`reports.py`、`admin_performance.py`、`settlement_task.py`）得出。

## R1 — 可核算月份（settleable periods）的推导

**Decision**: `settlement_service.settleable_periods(db)` 返回**有业务数据（账单）且未冻结/未待审核**的月份列表：从 `bills.transaction_time` 取去重 `YYYY-MM`，排除 `> 当前月`（未来月不可选，FR-002 边界），再排除 `performance_settlements` 中 `status ∈ {pending, reviewed}` 的月份；`rejected` 月份包含在内（打回待重算，FR-002）。返回按月份升序。
**Rationale**: 月份选择器需要「可选核算」的明确口径。账单月份即业务发生的月份，是最自然的候选来源；`pending/reviewed` 已进入核算/冻结流程不可重复发起；`rejected` 可重算。未来月无业务数据不可选。
**Alternatives considered**:
- 任意月均可选、后端校验：违反 FR-002「仅列出可核算月份」，前端体验差（可选后报错）。
- 用系统存在月历（如最早至今全部月份）：会列出大量无业务月份，噪音大，且无业务月份核算结果为 0，无核算价值。

## R2 — 发起核算动作（settle）与审核动作的关系

**Decision**: 新增 `POST /admin/performance/settlements/{period}/settle`，权限 `performance.settle`（FR-011）。`settlement_service.settle(db, period, operator_id)`：
1. 校验 `period` 在 `settleable_periods` 中（不在则 400：已核算/冻结/未来月）。
2. 调用 `compute_commission(period)`（008 复用；内部 `_ensure_pending_settlement` 创建/恢复 `pending` 批次）。
3. 调用 `ReportService.ensure_settlement_report(db, period, pending)` 生成/更新核算报表记录（R3）。
4. 返回 `{period, status: pending, computed}`。

审核确认/打回/重算**复用** 008 既有 `settlement_service.review/reject/recompute`（FR-007/008/009），仅在状态变更后同步报表记录状态（R3）。`rejected` 月重算后回到 `pending`，报表记录状态同步回待审核。
**Rationale**: 澄清 Q2=A——复用增强既有核算引擎，不重复建设状态机。「发起核算」是新入口（008 只有月度任务自动核算 + `recompute` 手动重算，无「从未核算月份发起」的端点），故新增 `settle`；审核闭环完全复用。
**Alternatives considered**:
- 复用 `recompute` 承担发起核算：`recompute` 仅允许 `pending/rejected`，对「无核算记录」月份返回 404，语义不符；单独 `settle` 语义清晰、校验明确。

## R3 — 核算报表记录在 `reports` 表的建模

**Decision**: 复用 `reports` 表，新增三列（Alembic 013）：
- `source` String(32)，`server_default='reconciliation'`，NOT NULL——区分手工对账报表与自动核算报表（`performance_settlement`）。
- `period` String(7)，nullable，index——核算报表的来源月份 `YYYY-MM`。
- `status` String(16)，nullable——核算报表的审核状态（`pending/reviewed/rejected`）。

核算报表记录数据形态：`dimensions=['performance']`，`start_date/end_date` 为该月首末日期（保证日期范围展示），`sections={"performance": {title, summary, details}}`，`generated_by` 记录发起人。`ReportService.ensure_settlement_report(db, period, status)` 幂等 upsert（按 `source='performance_settlement' AND period` 查找，有则更新 sections/status，无则新建）。在**核算成功、审核确认、打回、重算、月度任务自动核算**五个入口调用，保证报表记录与核算结果状态实时一致（FR-005/FR-006）。
**Rationale**: FR-005 要求"自动生成该月核算报表记录，展示在数据报表历史报表列表，带待审核状态标记，可查看明细与导出"。复用 `reports` 表与其既有列表/详情/导出链路（report_service + reports.py + 前端 reports 页）是最小改动，避免新建一套报表体系（Constitution V）。`source/period/status` 三列即可区分来源、绑定月份、反映审核状态。
**Alternatives considered**:
- 新建 `settlement_reports` 表：需新列表/详情/导出端点 + 前端新页面，重复建设。
- 只加 `period` 列、用 `dimensions` 标记来源：`source` 列语义更明确，避免依赖 dimensions 约定隐式判断。
- 不存 sections、详情实时算：存储快照可复用既有导出与详情链路，且与「冻结」语义一致（reviewed 后数据不再变）；实时算增加复杂度且与既有报表存储模式不一致。

## R4 — 核算报表记录的权限控制

**Decision**: 查看/导出核算报表记录要求 `sharing_rules.read`（澄清 Q1=B）；审核/打回/重算/发起核算要求 `performance.settle`（FR-011）。`reports.py` 端点目前用 `require_role("admin","finance")`（角色级）——为满足「查看核算报表记录需 `sharing_rules.read`」：列表返回时**过滤掉 `source='performance_settlement'` 记录**（对无 `sharing_rules.read` 权限的调用者）；详情/导出时若记录为核算来源且调用者无 `sharing_rules.read` → 403。`reports` 列表/详情/导出仍保持角色门槛。
**Rationale**: 核算报表含个人提成明细（资金敏感），查看权限沿用 008 绩效页「查看估算」同权（`sharing_rules.read`）；操作权限沿用 `performance.settle`。与 Constitution IV（资金敏感数据审计）一致。
**Alternatives considered**:
- 整体改为 `sharing_rules.read`：破坏既有手工对账报表的 `admin/finance` 角色门槛，影响面过大。
- 不加权限：敏感提成明细对全部报表查看者开放，不符合澄清结论。

## R5 — 报表记录详情与导出的内容

**Decision**: 核算报表记录的详情/导出内容为该月核算汇总 + 人员明细（FR-006）：`sections["performance"] = {title: "绩效核算", summary: {周期, 状态, 核算人数, 提成总额, 组织数}, details: [{组织, 姓名, 提成类型, 计算基数, 比例, 提成金额}]}`。导出复用 `ReportService.export_excel` 的既有 Excel 链路，为 `performance` 维度新增 sheet「绩效核算」（沿用既有 `dimension_sheet_config` 模式）。数据来源为核算落库的 `commission_results`（与绩效计算页同源，偏差为 0，SC-006）。
**Rationale**: FR-006/FR-012 要求汇总+明细、可导出、同源一致。复用既有 Excel 导出引擎（openpyxl）与 sheet 配置模式，最小改动；数据取自 `commission_results`，与核算结果天然一致。
**Alternatives considered**:
- 独立 CSV 导出：既有核算明细已有 CSV 导出（008 绩效页），但本需求要求的是**报表记录**的导出，复用 reports 的 Excel 链路更一致。

## R6 — 前端「绩效计算」页月份选择与发起核算

**Decision**: `settlement.vue` 月份选择器改为**仅列出可核算月份**（来自 `GET /admin/performance/settleable-periods`，`sharing_rules.read`）；选中可核算月份后展示估算（复用既有 `estimates`）并显示「发起核算」按钮（`performance.settle`）。核算成功后刷新——该月从可核算列表消失、进入待审核，页面展示审核状态与既有「确认/打回/重算/导出」操作。另提供「月度核算状态列表」（复用 `GET /admin/performance/settlements` 不带 period 的返回）以覆盖**由月度任务自动核算、已处于待审核**的月份，供管理员进入审核（US3 全场景可测）。
**Rationale**: FR-002 明确"仅列出可核算月份"。核算入口与审核入口在同一页：选择可核算月发起核算，状态区处理审核/冻结/打回。对非手动发起（月度任务）产生的 `pending` 月，通过状态列表进入审核，保证 US3 闭环可独立测试。
**Alternatives considered**:
- 月份选择器保留全部月份、后端拒绝非可核算月：违反 FR-002 列表语义，体验差。

## R7 — 前端「数据报表」页核算记录展示

**Decision**: `reports/index.vue` 列表项新增来源标记与**审核状态标签**（待审核/已确认/已打回），并为核算来源记录显示月份。`stores/reports.js` 透传 `source/period/status`。详情与导出沿用既有报表查看/下载（`ReportDetail.vue` 支持 `performance` 维度块）。
**Rationale**: FR-005 要求核算报表记录带状态标记展示在数据报表历史列表。前端沿用既有 reports 页结构，最小改动。
**Alternatives considered**:
- 数据报表页新增独立"核算报表"区块：与既有历史报表列表割裂，不符合"展示在历史报表列表内"的澄清结论（Q1=A）。

## R8 — 迁移与既有数据

**Decision**: Alembic 013 为 `reports` 表新增 `source`（默认 `reconciliation`）/`period`（nullable）/`status`（nullable）三列。存量报表行自动获得 `source='reconciliation'`，不受影响；核算报表记录从首个核算动作开始生成，不做历史回溯。
**Rationale**: spec 未要求历史核算数据回溯补报表；`server_default` 保证存量行兼容。与 008 R8（快照不回溯）策略一致。

## R9 — 月度任务（settlement_task）联动

**Decision**: 月度结算任务（`monthly_settlement_job`）在 `compute_commission` 成功后调用 `ReportService.ensure_settlement_report(db, period, pending)`，保证自动核算的月份同样在数据报表中可见（FR-005 的"核算成功即生成报表记录"对自动核算同样成立）。
**Rationale**: 数据报表展示以"核算成功"为准，不区分手动/自动入口；否则自动核算的月份在数据报表缺失，口径不一致。
**Alternatives considered**: 仅手动 `settle` 生成报表记录——自动核算月份缺失，违反 FR-005 全量语义。
