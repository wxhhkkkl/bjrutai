# Phase 1 Data Model: 业绩贡献口径统一为消费金额

基于 spec.md 与既有数据模型。所有 schema 变更通过 Alembic 迁移（012）。

## 实体总览

| 实体 | 类型 | 说明 |
|------|------|------|
| bills | 既有表（口径来源） | 消费金额唯一数据来源，`paid_amount_cent` + `transaction_status` |
| customers | 既有表（新增合成行） | 迁移时生成「历史消费」合成客户 |
| contribution_records | 删除表 | 贡献记录（手工/团队加分），迁移后删除 |
| settlement_logs | 删除表 | 旧贡献结算日志，迁移后删除 |
| contribution_coefficient | 删除表 | 贡献系数（全局设置），迁移后删除 |

## 1. bills（既有，口径唯一来源）

消费金额 = 某分销员周期内其绑定客户的 `PAID` 账单 `paid_amount_cent` 之和。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK |
| customer_id | int | 关联 customers.id（绑定客户） |
| transaction_id | str | 交易号（合成账单为 `legacy-contrib-{record_id}`） |
| transaction_time | datetime | 归属月份依据 |
| paid_amount_cent | int | 实付金额（分），统计口径取值 |
| total_amount_cent / medicine_fee_cent / consultation_fee_cent / discount_amount_cent / refund_amount_cent | int | 账单明细 |
| transaction_status | enum | `PAID` / `PARTIALLY_REFUNDED` / `REFUNDED` / `CANCELLED` 等 |
| rutai_user_id | str | 客户关联的儒泰用户（合成客户为 `legacy-cust-{distributor_id}`） |

**统计过滤**：`transaction_status NOT IN (REFUNDED, CANCELLED)`；`PARTIALLY_REFUNDED` 计入全额；按 `transaction_time` 归属月份。

## 2. customers（既有，迁移新增合成行）

迁移 012 对「无账单且贡献值 > 0」的贡献记录，按分销员惰性创建合成客户，用于挂接合成账单，使历史业绩在新口径下可见。

| 字段 | 说明 |
|------|------|
| name | 「历史消费」 |
| distributor_id | 记录归属分销员 |
| rutai_user_id | `legacy-cust-{distributor_id}`（可追溯） |
| binding_status | BOUND |

**说明**：合成客户**不是**真实业务客户，仅承载历史消费数据；不参与真实的绑定/服务流程。

## 3. 合成账单（迁移产物，非新表）

由贡献记录生成的 `bills` 行：

| 属性 | 值 |
|------|-----|
| transaction_id | `legacy-contrib-{record_id}`（可追溯回原贡献记录） |
| paid_amount_cent | `round(points × 100)` |
| transaction_status | `PAID` |
| 金额字段 | 仅 `total_amount_cent` / `paid_amount_cent` 有值，其余为 0 |

**合成来源条件**：`bill_id IS NULL` 且 `points > 0` 且状态非 `REVERSED/CANCELLED`。

## 4. 已删除表（迁移 012）

| 表 | 原用途 | 删除方式 |
|------|--------|----------|
| contribution_records | 贡献记录（类别绑定/服务/随访/账单/调整，points 字符串，状态机 pending→confirmed→settled→reversed→cancelled） | drop（先合成历史账单） |
| settlement_logs | 旧贡献批次结算日志（running/completed/failed） | drop |
| contribution_coefficient | 全局贡献系数（0~1，生效时间） | drop |

**downgrade**：清理合成数据（`DELETE FROM bills WHERE transaction_id LIKE 'legacy-contrib-%'`；`DELETE FROM customers WHERE rutai_user_id LIKE 'legacy-cust-%'`）并重建空表（原贡献行不可恢复）。

## 5. 业务校验规则（来自 spec）

- 统一口径：全系统业绩数字均来自 `consumption_service` 对 bills 的聚合（FR-001/FR-002，SC-001）。
- 排除规则：`REFUNDED`/`CANCELLED` 不计入；`PARTIALLY_REFUNDED` 全额计入（FR-001，SC-002）。
- 迁移幂等：`ON DUPLICATE KEY UPDATE transaction_id` 防止重复执行重复合成（迁移只执行一次）。
- 破坏性：升级前必须备份数据库（FR-010）。

## 6. 查询视角

- **管理端消费业绩页**：stats（本月/累计 `consumption_by_distributor` 汇总）、趋势（逐月汇总）、最新 30 条账单、组织/个人消费排名——均从 bills 实时聚合。
- **工作台**：`myMonthlyConsumption` = 本人当月 `consumption_by_distributor`；`contribution-summary` 返回 `totalAmountCent`/`count`（管理员=全系统，分销员=本人）。
- **客户详情**：`monthlyConsumptionCent`/`totalConsumptionCent` = `consumption_by_customer`；消费记录 = 该客户 bills 分页。
- **组织绩效/团队/报表/绩效计算（008）**：复用同一 `consumption_by_distributor` 口径。
