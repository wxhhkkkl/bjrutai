# Research: 绩效规则模块

**Branch**: `006-performance-rules` | **Date**: 2026-08-03
**目的**: 解决 Technical Context 中的技术决策/未知项，供 Phase 1 设计与 Phase 2 任务分解依据。

## 决策清单

### D1: 数据模型（三张新表）
- **Decision**: 新增 `performance_rules`（提成方式）、`performance_rule_change_logs`（变更历史）、`commission_results`（月度提成结果）
- **Rationale**: 规则按组织配置（org_id + rule_type 唯一），变更需留痕（FR-007），结果需落库可审计（FR-013）；旧 `SharingRule` 按层级、字段不匹配，不复用
- **Alternatives considered**: 复用 `SharingRule` 改造 → 层级/固定比例语义与新阶梯语义冲突，改造复杂

### D2: 阶梯存储与校验
- **Decision**: `performance_rules.tiers` 用 JSON 列存阶梯数组 `[{minCent, maxCent, ratio}]`（金额分、比率小数 0-1）；服务层校验区间不重叠、升序、ratio ∈ (0,1]
- **Rationale**: 阶梯数量不固定，JSON 灵活；校验在服务层保证数据合法性（FR-006）
- **Alternatives considered**: 子表 `performance_rule_tiers` → 单组织单规则下阶梯数有限，子表增加复杂度（宪法 V）

### D3: 提成基数 = 消费金额（账单实付）
- **Decision**: 成员消费金额 = 该成员名下绑定客户在周期内 `Bill.paid_amount_cent` 之和（按 `transaction_time` 过滤周期；`refunded`/`cancelled` 账单不计入）；组织管理基数 = 组织及全部下级组织所有成员消费金额之和
- **Rationale**: 已确认"消费金额"为基数；`paid_amount_cent` 是实际支付金额（分）
- **Alternatives considered**: 用贡献积分 → 用户已确认用金额；用 `total_amount_cent` → 未剔除折扣/退款，不符合实付语义

### D4: 计算引擎（成员 vs 管理员）
- **Decision**: `commission_service.compute_commission(db, period)`：① 非管理员成员按其自身消费金额匹配所属组织"组织内绩效提成"阶梯；② 组织管理员按其管理子树消费总额匹配"组织管理绩效提成"阶梯；同一成员若既是管理员（不适用组织内）只取组织管理
- **Rationale**: FR-011；管理员与成员提成互斥（管理员不按组织内提成）
- **Alternatives considered**: 管理员同时计两种 → 与 spec"本组织内除管理员外人员按组织内提成"矛盾

### D5: 月度结算任务接入
- **Decision**: 扩展 `monthly_settlement_job`：`batch_settle` 完成后调用 `compute_commission(db, period)` 落库 `commission_results`
- **Rationale**: FR-013"月度结算落库"；复用既有月度调度与周期口径
- **Alternatives considered**: 新独立 job → 两套调度周期，维护成本高

### D6: 实时预览
- **Decision**: `GET /admin/performance-rules/preview?orgId=&period=` 调用同一计算引擎即时计算（不落库）返回成员/管理员提成预览
- **Rationale**: FR-013"按当前规则实时重算预览"；复用引擎避免重复逻辑
- **Alternatives considered**: 单独实现预览逻辑 → 与落库逻辑可能漂移

### D7: 单管理员约束（set_role + 数据迁移）
- **Decision**: ① 改 `distributor_service.set_role`：目标组织已有管理员时设 admin 被拒（提示先撤销）；撤销不受限。② 迁移 010：存量多管理员组织保留 id 最小的一名，其余降为 member
- **Rationale**: FR-008 强制后端约束（防 API 绕过）；存量数据需清理以满足约束
- **Alternatives considered**: 仅前端限制 → 可绕过；不处理存量 → 违反 SC-003/SC-004

### D8: 旧机制移除
- **Decision**: 移除 `sharing_rules.py` 路由 + 前端 `/sharing-rules` 页/菜单 + `sharing store`；`SharingRule`/`ContributionCoefficient` 表与模型保留（数据废弃不参与计算）
- **Rationale**: FR-010/FR-012 新规则取代旧机制；表保留避免破坏既有迁移与历史数据，仅停用计算与入口
- **Alternatives considered**: 删除旧表 → 破坏历史审计数据，风险大；保留入口并行 → 违反 FR-010

### D9: 前端重构
- **Decision**: 新 `pages/performance-rules/index.vue`：左组织树（复用 005 客户管理树模式）+ 右面板展示该组织两种提成方式（配置卡片 + 阶梯表格 + 变更历史 + 预览/结果 tab）；`router`/`App.vue` 改名"绩效规则"
- **Rationale**: 页面改名 + 按组织浏览是 US1；复用组织树模式避免重复实现
- **Alternatives considered**: 在旧 sharing 页上打补丁 → 层级语义残留，重构更干净

## 未知项状态

所有 NEEDS CLARIFICATION 已在 specify/clarify 阶段解决（配置+计算引擎、新规则取代旧机制、基数=消费金额、月度落库+实时预览）。本轮无新增未知项。

## 依赖与风险

- **账单口径**: 消费金额按 `paid_amount_cent`（实付）取数；退款/取消不计入，需在契约与测试中明确
- **既有测试影响**: 移除 `sharing_rules` 路由会影响 `tests/contract/test_sharing.py`；`set_role` 收紧会影响 `test_admin_distributors.py`，需同步更新
- **单管理员迁移**: 迁移 010 对存量多管理员数据降级，需在验收数据中核对（当前 dev 库组织 2 已有管理员 1 名，无多管理员场景）
- **月度任务**: `monthly_settlement_job` 扩展后若提成计算失败不应阻断贡献结算（需容错：提成计算独立 try/except 记录日志）
