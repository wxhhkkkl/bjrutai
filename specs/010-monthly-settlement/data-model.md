# Phase 1 Data Model: 绩效计算模块月度核算

基于 spec.md 与既有数据模型。所有 schema 变更通过 Alembic 迁移（013）。

## 实体总览

| 实体 | 类型 | 说明 |
|------|------|------|
| reports | 修改表 | + `source` / `period` / `status` 三列，承载核算报表记录 |
| performance_settlements | 既有（复用） | 月度核算批次状态机（008），不变 |
| commission_results | 既有（复用） | 月度核算明细（含规则快照），核算报表记录的数据来源 |
| performance_rules | 既有（不变） | 绩效规则配置（快照来源） |
| organization / distributor / bill / customer | 既有（不变） | 组织树、人员、账单（可核算月份推导的数据来源） |

## 1. reports（修改）

既有对账报表表，新增三列以承载**核算来源报表记录**：

| 字段 | 类型 | 约束/说明 |
|------|------|-----------|
| source | String(32) | NOT NULL, server_default 'reconciliation'。`reconciliation`（手工对账报表）/ `performance_settlement`（自动核算报表） |
| period | String(7) | nullable, index。核算报表的来源月份 'YYYY-MM'；对账报表为 NULL |
| status | String(16) | nullable。核算报表的审核状态 `pending`(待审核) / `reviewed`(已确认冻结) / `rejected`(已打回)；对账报表为 NULL |
| （其余字段不变） | | id / start_date / end_date / dimensions(JSON) / sections(JSON) / generated_by / generated_at / created_at |

**约束**：
- `source='performance_settlement'` 时：`period` 必填且 `start_date/end_date` 为该月首末日期；`dimensions=['performance']`；`sections` 含 `{"performance": {title, summary, details}}`。
- `source='reconciliation'` 时：`period/status` 为 NULL（既有行为不变）。
- 每个 `(source='performance_settlement', period)` 唯一（同月只保留一条核算报表记录，幂等 upsert）。

### 迁移

```text
alembic revision --autogenerate -m "add reports.source/period/status for settlement reports"
```

## 2. 业务校验规则（来自 spec）

- **可核算月份**：有账单业务数据、非未来月、且 `performance_settlements` 状态非 `pending/reviewed` 的月份；`rejected` 月份可重算（FR-002）。
- **发起核算**：仅可核算月份可 `settle`；`pending/reviewed`/未来月拒绝（FR-002）。
- **报表记录生成**：核算成功 / 审核确认 / 打回 / 重算 / 月度任务自动核算后，`ensure_settlement_report` 幂等 upsert 该月核算报表记录（FR-005）。
- **报表记录状态同步**：核算成功 → `pending`；审核确认 → `reviewed`；打回 → `rejected`；重算 → 回到 `pending`（FR-005/FR-007/FR-009）。
- **冻结**：`reviewed` 月份不得再次核算（FR-008，复用 008 `compute_commission` 冻结跳过）。
- **权限**：查看/导出核算报表记录需 `sharing_rules.read`；发起核算/审核/打回/重算需 `performance.settle`（FR-011）。

## 3. 查询视角

- **可核算月份列表**：`bills.transaction_time` 去重月份（≤当前月）排除 `pending/reviewed` 月份。
- **核算报表记录列表/详情/导出**：`reports` 按 `source='performance_settlement'` 过滤；详情/导出读取 `sections["performance"]`（汇总+明细）。
- **核算明细数据源**：`commission_results`（period + distributor + rule_type），与绩效计算页同源。
