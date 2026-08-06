# Phase 0 Research: 业绩贡献口径统一为消费金额

技术决策记录。依据 spec.md 与现有代码（`bill.py`、`contribution.py`（已删）、`contribution_dashboard_service.py`、`org_performance_service.py`、`sync_service.py`、`settlement_task.py`）得出。本功能已实现，以下决策与实现一致。

## R1 — 统一口径的实现形态

**Decision**: 新增 `consumption_service.py`，提供 `consumption_by_distributor`（按分销员周期聚合绑定客户账单实付金额）与 `consumption_by_customer`（按客户聚合），`period_start_end` 解析 'YYYY-MM'。全系统唯一口径。
**Rationale**: FR-001/FR-002 要求全系统同口径且单一实现。此前贡献值口径散落在 `contribution_service`、`workbench`、`org_performance_service`、`team_service`、看板等多处，重复且不一致；收敛为一个 helper 后，各消费方（工作台/看板/组织绩效/报表/团队/绩效计算）统一引用。
**Alternatives considered**:
- 保留多处独立 SQL 查询：重复代码、口径漂移风险，违背 FR-002。
- 建物化表/缓存：实时口径无需，中小数据量直接聚合即可。

## R2 — 口径计算规则（排除/计入边界）

**Decision**: 业绩贡献 = 消费金额 = 某分销员周期内其绑定客户 `PAID` 账单 `paid_amount_cent` 之和。排除 `REFUNDED`/`CANCELLED`；`PARTIALLY_REFUNDED` 按全额计入。按账单 `transaction_time` 归属月份。
**Rationale**: 与绩效计算（006/008）同口径，保证「业绩贡献 = 消费金额」在绩效与看板间一致（SC-001/SC-008）。退款不产生负值扣减，而是直接不计入，语义更简洁。
**Alternatives considered**:
- 退款金额作为负贡献：需要区分已计入月份的冲正语义，复杂且与绩效计算不一致。
- 部分退款按净额计入：与绩效计算口径不符，会造成跨模块偏差。

## R3 — 删除贡献体系的范围

**Decision**: 删除 `contribution_records` / `settlement_logs` / `contribution_coefficient` 三表，以及 `ContributionRecord`/`SettlementLog`/`ContributionCoefficient` 模型、`contribution_service`、`schemas/contribution`、分销员上的贡献关联、共享规则中的系数逻辑、`sync_service` 中账单→贡献创建与退款冲正逻辑、`settlement_task` 中 `batch_settle`。
**Rationale**: FR-003~FR-005。贡献体系是独立于账单的第二套业绩数值（类别绑定/服务/随访等手工加分 + 系数调节 + 批次结算），与「业绩贡献 = 消费金额」口径直接冲突；保留会导致双口径并存、前端展示混乱。
**Alternatives considered**:
- 保留贡献表但不再写入：历史表成为死数据，仍需迁移兼容，且模型/服务残留无收益。
- 仅停用不删除：违背「移除贡献记录/系数/结算配套能力」的需求，数据库保留废弃结构。

## R4 — 存量数据迁移策略

**Decision**: 迁移 012 对 `contribution_records` 中 `bill_id IS NULL` 且 `points > 0`、状态非 `REVERSED/CANCELLED` 的记录，按分销员惰性创建「历史消费」合成客户（`rutai_user_id = legacy-cust-{dist}`），以 `points × 100` 生成合成账单（`transaction_id = legacy-contrib-{id}`，`PAID`）；随后删除三表。downgrade 清理合成数据并重建空表（原贡献行不可恢复）。
**Rationale**: FR-006/FR-010 + US3。「测试分销 150」这类无账单的手工/团队贡献值若直接删除，历史业绩在新口径下不可见；合成账单使其以消费金额形式保留，且可追溯（legacy 前缀）。
**Alternatives considered**:
- 直接删除贡献行不做合成：历史业绩丢失，SC-003 不满足。
- 保留贡献表只迁移不删表：需求明确要求移除三表。

## R5 — URL 与字段兼容策略

**Decision**: 保留 `/contributions/*`、`/admin/contributions/*`、`/workbench/contribution-summary`、`/customers/{id}/contributions` 路径；响应数值字段从 `points`（字符串/浮点分）改为 `*AmountCent`（整数分）。后端传分、前端展示元。
**Rationale**: FR-007 + 假设。URL 兼容避免前端大面积改路由与小程序现网页面 break；字段改名使语义清晰（贡献值→消费金额），且整数分消除浮点误差。
**Alternatives considered**:
- 保留 `points` 字段名仅改含义：前端难以区分新旧语义，字段名与内容不符。
- URL 全部改名：小程序/管理端大改路由，收益低（内部系统无对外契约）。

## R6 — 退款/冲正处理

**Decision**: 删除 sync_service 中的贡献创建与冲正记录逻辑；退款由消费口径的 `transaction_status` 过滤天然排除，无需冲正记录。
**Rationale**: FR-009。旧体系为退款生成 REVERSED 贡献行冲正；新口径对退款账单直接不计入统计，无冲正概念。
**Alternatives considered**: 保留冲正逻辑兼容：无必要，口径本身已覆盖。

## R7 — 结算任务与绩效计算的关系

**Decision**: 移除 `batch_settle`（旧贡献结算批处理），月度结算任务直接调用 `compute_commission`（008 的绩效核算）；`commission_service` 复用 `consumption_by_distributor` 作为计算基数。
**Rationale**: FR-005。绩效计算（008）本就是月度自动核算；贡献结算与绩效结算是两套并行任务，移除贡献结算后月任务聚焦绩效核算，且基数与看板同口径（SC-001）。
**Alternatives considered**: 保留两个任务并行：重复、口径需维护一致。

## R8 — 前端展示切换

**Decision**: 管理后台（消费业绩页/工作台/客户详情/组织绩效）与小程序（贡献明细页/首页/组织绩效/客户详情）从「贡献值（分）/已结算/待结算」切换为「消费金额（元）/已支付/待支付」；小程序底部标签文案「贡献」→「消费」，tab id 与页面/文件命名保留 `contribution` 兼容。
**Rationale**: FR-008 + 假设。分→元由前端 `fmtYuan(cent)`（除以 100 保留两位）实现；已结算/待结算是贡献批次状态，账单只有已支付/待支付语义。
**Alternatives considered**: 保留「分/已结算」文案：与消费金额口径不符，用户误解。
