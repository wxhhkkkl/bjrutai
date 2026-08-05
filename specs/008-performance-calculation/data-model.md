# Phase 1 Data Model: 绩效计算模块

基于 spec.md 与既有数据模型。所有 schema 变更通过 Alembic 迁移。

## 实体总览

| 实体 | 类型 | 说明 |
|------|------|------|
| performance_settlements | 新增表 | 月度核算批次，审核状态机主体 |
| commission_results | 修改表 | 增加 `rule_snapshot` 列 |
| performance_rules | 既有（不变） | 绩效规则配置（快照来源） |
| organization / distributor | 既有（不变） | 组织树与人员 |

## 1. performance_settlements（新增）

月度核算批次，`period` 唯一，作为「按月整体确认」的冻结单元。

| 字段 | 类型 | 约束/说明 |
|------|------|-----------|
| id | int | PK, autoincrement |
| period | str(7) | NOT NULL, UNIQUE, index, 'YYYY-MM' |
| status | enum | NOT NULL, `pending`(待审核) / `reviewed`(已确认) / `rejected`(已打回) |
| reviewed_by | int | nullable, 审核操作的管理员 AdminAccount.id |
| reviewed_at | datetime | nullable, 最近一次确认/打回时间 |
| reject_reason | str(500) | nullable, 打回原因（打回必填） |
| created_at | datetime | NOT NULL, default utcnow |
| updated_at | datetime | NOT NULL, onupdate utcnow |

**约束**：`period` 唯一。`rejected` 必有 `reject_reason` 与 `reviewed_at`；`reviewed` 必有 `reviewed_by` 与 `reviewed_at`。

### 状态机

```text
                确认(review)
  pending ────────────────────► reviewed（冻结，不可再变）
    │  ▲
    │  │ 重算(recompute) 后回到 pending
    │  │
    └──┴──────── 打回(reject, 必填原因) ──► rejected
```

- `pending`：有核算结果，待审核。可「确认」「打回」「重算」。
- `reviewed`：已确认冻结。不可确认/打回/重算。
- `rejected`：已打回。可「重算」（结果更新后回 `pending`，清除打回原因）。

### 迁移

```text
alembic revision --autogenerate -m "add performance_settlements + commission_results.rule_snapshot"
```

## 2. commission_results（修改）

既有按月核算明细（period + distributor + rule_type 唯一），增加快照列：

| 字段 | 类型 | 约束/说明 |
|------|------|-----------|
| rule_snapshot | JSON | nullable。`{ruleType, tiers:[{minCent,maxCent,ratio}], ruleVersion}` 核算时生效规则副本 |
| （其余字段不变） | | period / distributor_id / org_id / rule_type / base_cent / ratio / commission_cent / computed_at |

**说明**：
- 快照在 `compute_commission` 落库时随 `_upsert_result` 写入。
- 存量行 `rule_snapshot` 为空（R8：不回溯），重算后补齐。
- 冻结周期（settlement.status=reviewed）不会被 upsert 覆盖。

## 3. 业务校验规则（来自 spec）

- 冻结：`compute_commission` 对 `reviewed` 周期直接返回，不计算不写入（FR-006）。
- 快照：每次核算写入当时生效 `ACTIVE` 规则的 tiers 与版本（FR-007）。
- 重算：仅 `pending` / `rejected` 周期允许；`reviewed` 拒绝（FR-008）。
- 打回：必须提供原因（FR-013）；仅 `pending` 允许。
- 确认：仅 `pending` 允许；`reviewed` 重复确认幂等拒绝（FR-012/SC-004）。
- 幂等确认：条件 UPDATE 校验影响行数（R5）。

## 4. 查询视角

- **管理端估算**（实时）：复用 `preview_org_commission(org_id, period)`，不落库。
- **管理端核算明细**：`commission_results` 按 period（+org 子树）查询，附结算批次状态。
- **管理端结算状态**：`performance_settlements` 按 period 查询。
- **小程序本人/组织**：当月预估 = 实时预览（当前规则）；历史已确认 = `commission_results` join `performance_settlements(status=reviewed)`。
