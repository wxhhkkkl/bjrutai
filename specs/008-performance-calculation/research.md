# Phase 0 Research: 绩效计算模块

技术未知点与决策，依据 spec.md（含 2026-08-05 澄清）与现有代码（`commission_service.py`、`commission_result.py`、`admin_performance_rules.py`、`monthly_settlement_job`、`seed_service.py`）得出。

## R1 — 冻结与状态机设计

**Decision**: 新增 `performance_settlements` 表（`period` 唯一），状态 `pending / reviewed / rejected`；`compute_commission` 在已 `reviewed` 周期跳过，冻结已确认月份。
**Rationale**: 审核按「月」整体确认（澄清 Q1=A），以 period 为粒度的批次表天然契合；既有 `commission_results` 的 upsert 逻辑保持不变，只需在入口判断冻结周期。避免给每行结果加状态（行数多、语义重复）。
**Alternatives considered**:
- 仅给 `commission_results` 加状态列：每行独立状态与"整月冻结"语义不符，且确认/打回需批量更新多行，复杂度更高。
- 额外锁表/Redis 锁：中小数据量无必要，条件 UPDATE 足够。

## R2 — 规则快照存储

**Decision**: 在 `commission_results` 增加 `rule_snapshot`（JSON，可空），内容 `{ruleType, tiers, version}`；核算落库时写入当时生效规则。
**Rationale**: FR-007 要求"保留当时计算的规则"。快照随结果行保存，历史追溯无需回查规则表；规则表本身支持版本与变更历史，快照是其在核算时刻的副本。
**Alternatives considered**:
- 只存规则 id/版本：规则可能被删除/修改，回查无法保证还原当时配置。
- 单独快照表：每周期一份规则快照，查询时 join——多一层关联，且结果行已天然按周期分组，直接冗余在结果行更简单。

## R3 — 权限点

**Decision**: 新增 `performance.settle` 权限，控制审核确认/打回/重算/导出；估算与明细查看沿用 `sharing_rules.read`。加入 `seed_service._ALL_PERMISSIONS` 与 `manageSystem/src/constants/permissions.js`（新 module `performance`）。
**Rationale**: 澄清 Q1=B——审核/导出为资金敏感操作，与规则编辑权限分离（职责分离）。系统管理员角色通过 seed 幂等同步自动获得。
**Alternatives considered**:
- 复用 `sharing_rules.write`：无法区分"编辑规则"与"确认资金数据"。

## R4 — 导出格式

**Decision**: CSV（Python 标准库 `csv`），按周期（可选组织树范围）导出核算明细；包含人员、组织、规则类型、基数、比例、金额、快照版本、状态。
**Rationale**: FR-010 仅要求"表格文件"；CSV 零依赖、可被 Excel 打开，最简实现。
**Alternatives considered**: openpyxl 生成 xlsx（增加依赖）；xlsxwriter（同）。无实际需求差异，CSV 满足。

## R5 — 并发与幂等

**Decision**: 审核确认/打回使用条件 UPDATE（`UPDATE ... SET status=? WHERE period=? AND status='pending'`）并校验影响行数；重复确认/打回返回明确的业务错误（幂等拒绝）。
**Rationale**: 保证并发审核下同月只被确认一次；不引入分布式锁。
**Alternatives considered**: SELECT FOR UPDATE 行锁——同一请求事务内可，但条件 UPDATE 更简洁且天然幂等。

## R6 — 小程序身份与接口

**Decision**: 复用 `get_current_user`；推广员返回本人（含当月预估 + 已确认月份列表），组织管理员返回所管理组织子树。新增专用接口（不混入既有贡献值接口 `/org/performance`），仅返回提成金额明细（基数/比例/金额）。
**Rationale**: 澄清 Q2/Q3——展示内容仅提成金额、对象含两类角色；与既有业绩贡献值接口语义分离，避免破坏现网小程序页面。
**Alternatives considered**: 扩展既有 `/org/performance` 返回值——耦合两套数值体系，影响现网页面。

## R7 — 重算触发

**Decision**: `pending` 或 `rejected` 周期的核算可由管理员手动触发重算；`reviewed` 周期拒绝。月度结算任务（`monthly_settlement_job`）在自动核算后为上一周期创建/更新 `pending` 批次。
**Rationale**: FR-008 要求待审核可重算；自动核算沿用既有节奏，不新增计划任务。
**Alternatives considered**: 仅自动核算不可手动重算——无法满足打回后重算闭环。

## R8 — 现有历史数据处理

**Decision**: 存量 `commission_results` 行的 `rule_snapshot` 为空；不对存量周期自动生成快照。存量周期若在 `pending`（无批次记录）状态被重算，将补齐快照与批次。
**Rationale**: spec 未要求历史数据回溯；避免一次性大迁移。新增批次表无存量数据，从首个新核算周期开始生效。
