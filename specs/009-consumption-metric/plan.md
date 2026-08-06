# Implementation Plan: 业绩贡献口径统一为消费金额（移除业绩贡献值体系）

**Branch**: `009-consumption-metric` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-consumption-metric/spec.md`

> 说明：本计划为回顾性文档（实现已完成、未提交），与当前工作区实际改动一致。代码位于 `009-consumption-metric` 分支工作区。

## Summary

移除独立的「业绩贡献值」体系，全系统统一以**消费金额**（绑定客户账单实付金额）作为业绩口径：

- **统一口径**：业绩贡献 = 消费金额 = 某分销员周期内其绑定客户 `PAID` 账单 `paid_amount_cent` 之和（整数分），排除 `REFUNDED`/`CANCELLED`；`PARTIALLY_REFUNDED` 全额计入。口径收敛到新增的 `consumption_service.py`，全系统唯一实现（FR-001/FR-002）。
- **删除贡献体系**：`contribution_records` / `settlement_logs` / `contribution_coefficient` 三表及其模型、`contribution_service`、贡献系数逻辑、旧的 `batch_settle` 贡献结算任务（FR-003~FR-005）。
- **存量迁移**：Alembic 012 破坏性迁移——无账单且贡献值 > 0 的手工/团队记录合成为消费账单（生成「历史消费」合成客户），保证历史数据在新口径下可见；随后删除三表（FR-006/FR-010）。
- **业绩查询重写**：后台消费业绩页（看板/趋势/排名/最新明细）、工作台、客户详情、组织绩效、报表、团队视图、结算任务全部改为从账单实时聚合（FR-008）。
- **前端口径切换**：管理后台与小程序从「贡献值（分）/已结算/待结算」切换为「消费金额（元）/已支付/待支付」（FR-008）。

**技术路线**：新增 `consumption_service`（`consumption_by_distributor`/`consumption_by_customer`）作为唯一聚合口径；各 API/服务改为引用该 helper；删除贡献模型/服务/系数/结算；迁移 012 合成账单并删表；前端数值字段从 `points` 改为 `*AmountCent`（整数分）并展示为元。

## Technical Context

**Language/Version**: Python 3.11+（backend）、Vue 3 + Vite（manageSystem）、WeChat Mini-Program
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、MySQL 8.0、pytest + pytest-asyncio、APScheduler、Element Plus、Pinia、axios
**Storage**: MySQL 8.0（腾讯云，TLS）；本迭代无新增文件存储需求
**Testing**: pytest + pytest-asyncio（contract / integration / unit）
**Target Platform**: Linux server（Docker）、Vue 管理后台（浏览器）、微信小程序
**Project Type**: 多端 Web 服务（backend REST API + Vue admin SPA + WeChat 小程序）
**Performance Goals**: 看板/排名/趋势实时聚合，中小数据量下 2 秒内返回（SC-006）；迁移脚本一次性执行
**Constraints**: 统一响应格式 `{code,message,data,requestId,serverTime}`；路径版本化 `/api/v1`；URL 路径兼容（保留 `/contributions/*` 等）；金额以整数分存储/传输，前端展示元；迁移 012 为破坏性，升级前需备份
**Scale/Scope**: 组织/分销员规模中小（数十组织、数百人）；账单数千行；单次迁移一次性执行

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 合规 | 检查点 |
|------|------|--------|
| I. TDD（强制） | ✅ | 新增 `consumption_service` 有 unit 测试（`test_consumption_service.py`：求和、排除退款/取消、周期过滤、空输入、按客户分组）；既有 contract/integration/unit 测试全部同步更新并全绿（353 passed） |
| II. API-First | ✅ | 各 API 响应字段变更有对应 contract 测试同步；URL 路径保持兼容；前端仅消费后端 API |
| III. 分离关注点 | ✅ | 口径计算在后端 `consumption_service`；管理端/小程序端只做展示切换；删除逻辑集中在迁移脚本与服务层 |
| IV. 数据库完整性 | ✅ | schema 变更走 Alembic 迁移（012）；破坏性删除前合成历史数据并明示备份；无敏感字段新增（脱敏策略不变） |
| V. 简化（YAGNI） | ✅ | 只做「统一口径 + 移除贡献体系」；口径 helper 单一实现，无重复聚合代码 |

Gate 结果：**通过**，无违规项。Phase 1 完成后重新检查。

## Project Structure

### Documentation (this feature)

```text
specs/009-consumption-metric/
├── plan.md              # 本文件 (/speckit-plan)
├── research.md          # Phase 0 输出 (/speckit-plan)
├── data-model.md        # Phase 1 输出 (/speckit-plan)
├── quickstart.md        # Phase 1 输出 (/speckit-plan)
├── contracts/           # Phase 1 输出 (/speckit-plan)
│   └── api-fields.md    # 业绩相关接口响应字段变更契约
├── checklists/          # /speckit-specify 输出
│   └── requirements.md
└── tasks.md             # Phase 2 输出 (/speckit-tasks - 未创建)
```

### Source Code (repository root) —— 已实现的实际改动清单

```text
backend/src/
├── services/
│   ├── consumption_service.py          # 新增：唯一口径 helper（by_distributor / by_customer / period_start_end）
│   ├── contribution_service.py         # 删除：贡献计算服务
│   ├── contribution_query_service.py   # 重命名内部类：ContributionQueryService → ConsumptionQueryService，查询改为账单
│   ├── contribution_dashboard_service.py # 重写：从 bills 聚合（stats monthly/totalAmountCent、trend amountCent、最新30条账单、排名）
│   ├── sharing_service.py              # 删除：贡献系数 get/update_coefficient
│   ├── sync_service.py                 # 删除：账单→贡献创建 / 退款冲正逻辑（口径由状态过滤天然覆盖）
│   ├── team_service.py                 # 改：团队消费查询（consumption_by_distributor）
│   ├── org_performance_service.py      # 改：组织绩效按消费金额（整数分），移除 Decimal 格式化
│   ├── report_service.py               # 改：报表按账单聚合
│   ├── commission_service.py           # 改：复用 consumption_by_distributor（与 008 同口径）
│   ├── org_migration.py                # 改：移除 contribution 引用
│   └── settlement_task.py              # 改：移除 batch_settle，月度任务直接 compute_commission
├── models/
│   ├── contribution.py                 # 删除：ContributionRecord / SettlementLog
│   ├── sharing.py                      # 删除：ContributionCoefficient
│   ├── distributor.py                  # 删除：contribution_records 关系
│   └── __init__.py                     # 删除对应导出
├── schemas/
│   ├── contribution.py                 # 删除
│   ├── sharing.py                      # 删除：CoefficientUpdateRequest / CoefficientResponse
│   └── org_performance.py              # 改：this_month/cumulative 改整数分
├── api/v1/
│   ├── contributions.py                # 重写：overview/trend/list/detail 按账单；删除 /composition；detail 改 bill_id
│   ├── customers.py                    # 改：客户详情 monthly/totalConsumptionCent、客户消费记录为账单
│   ├── customer_analysis.py            # 改：移除 contribution 导入
│   ├── workbench.py                    # 改：metrics.myMonthlyConsumption；contribution-summary 返回 totalAmountCent/count，删除 breakdown
│   └── admin_contributions.py          # 不变：URL 与调用保持，看板/排名字段随 dashboard service 自动变为 amountCent
├── migrations/versions/
│   └── 012_drop_contribution_records.py # 新增：合成历史账单 → 删除贡献三表（破坏性）
└── scripts/
    └── verify_migration.py             # 改：移除 contribution_records 孤值检查

backend/tests/
├── unit/test_consumption_service.py    # 新增：口径单元测试
├── unit/test_contribution_service.py   # 删除
└── contract|integration|unit           # 同步更新：contributions / org_performance / report / sync / commission / dashboard

manageSystem/src/
├── pages/contributions/index.vue       # 改：消费业绩页（stats/趋势/排名/最新明细 → amountCent + ¥）
├── pages/dashboard/index.vue           # 改：本月消费（¥）替代本月业绩（分）
├── pages/customers/detail.vue          # 改：消费记录 tab（账单）
├── App.vue                             # 改：菜单「业绩贡献」→「消费业绩」
├── router/index.js                     # 改：路由标题「消费业绩」
└── constants/permissions.js            # 改：权限模块标签「消费业绩」

miniProgram/
├── pages/contribution/index.*          # 改：分/已结算 → ¥/已支付；删除来源筛选与构成
├── pages/contribution-detail/index.*   # 改：贡献明细 → 消费明细（¥）
├── pages/home/index.wxml               # 改：我的贡献 → 我的消费
├── pages/org-performance/index.wxml    # 改：成员/下级组织消费金额（¥）
├── pages/customer-detail/index.wxml    # 改：消费记录
├── pages/profile/index.js              # 改：指标口径
├── models/*.js                         # 改：mock/fixtures 金额与状态文案
├── services/org-performance-service.js # 改：消费金额（分）mock 与注释
└── app.json / navigation.js / help-feedback.js # 改：文案
```

**Structure Decision**: 三端分离，与 Constitution III 一致。口径计算收敛到后端 `consumption_service` 单一实现；管理端与小程序端仅做字段与文案切换。删除逻辑（模型/服务/迁移）集中在后端。URL 与文件命名保持 `contribution` 兼容，避免前端大面积改动路由。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无 Constitution 违规项。`consumption_service` 与迁移 012 是 FR-001/FR-006 明确要求（统一口径 + 存量迁移），非过度设计；删除贡献体系（模型/服务/系数/批处理）是 FR-003~FR-005 明确要求。无需在复杂度表中额外论证。

---

## 设计决策摘要（详见 research.md / data-model.md / contracts/）

- **统一口径实现**：`consumption_service.consumption_by_distributor`（按分销员周期聚合绑定客户账单实付金额）与 `consumption_by_customer`（按客户聚合）；`period_start_end` 解析 'YYYY-MM'。排除 `REFUNDED`/`CANCELLED`，`PARTIALLY_REFUNDED` 全额计入（与 006/008 绩效计算同口径）。
- **URL/字段兼容**：保留 `/contributions/*`、`/admin/contributions/*`、`/workbench/contribution-summary`、`/customers/{id}/contributions` 路径；数值字段从 `points`（分，字符串/浮点）改为 `*AmountCent`（整数分）。后端传分、前端展示元。
- **退款处理**：删除 sync_service 中的贡献创建与冲正逻辑；消费口径通过 `transaction_status` 过滤天然覆盖退款，无需冲正记录。
- **结算任务**：移除 `batch_settle`（旧贡献结算批处理），月度任务直接调用 `compute_commission`（008 的绩效核算）；`commission_service` 复用同一消费口径。
- **存量迁移（012，破坏性）**：对 `contribution_records` 中 `bill_id IS NULL` 且 `points > 0`、状态非 `REVERSED/CANCELLED` 的记录：按分销员惰性创建「历史消费」合成客户（`rutai_user_id = legacy-cust-{dist}`），按 `points × 100` 生成合成账单（`transaction_id = legacy-contrib-{id}`）；随后 drop `contribution_coefficient` / `settlement_logs` / `contribution_records`。downgrade 清理合成数据并重建空表（原贡献行不可恢复）。升级前需备份。
- **看板聚合**：admin 消费业绩页 stats（`monthlyAmountCent`/`totalAmountCent`）、趋势（逐月 `consumption_by_distributor` 汇总）、最新 30 条账单、组织/个人消费排名——全部实时从 bills 聚合，复用 `consumption_service`。
- **权限**：不新增权限点，沿用既有 `contributions.read`；仅权限模块标签改为「消费业绩」。
