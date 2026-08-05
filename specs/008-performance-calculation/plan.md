# Implementation Plan: 绩效计算模块（月度核算 + 审核确认 + 小程序展示 + 导出）

**Branch**: `008-performance-calculation` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-performance-calculation/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

在既有绩效规则模块（006）与核算引擎（`commission_service` / `monthly_settlement_job`）之上新增**绩效核算与审核工作流**：

- **审核 + 冻结 + 规则快照**：每月核算结果进入「待审核」状态；管理员**确认**后冻结（不再重算）并保留当时使用的规则快照；支持**打回**（记录原因）后重算再审核。冻结单元为「月」（整体确认）。
- **管理后台绩效计算页**：进入展示组织结构树 + 选中组织每人当月绩效估算；含月份/组织切换、审核操作（确认/打回/重算）、月度明细导出（CSV）。
- **小程序双态展示**：推广员看本人、组织管理员看所管组织的**当月预估**（实时按当前规则）与**历史已确认月份**（冻结结果），仅展示提成金额明细（基数/比例/金额），不含业绩贡献值。
- **权限**：新增独立权限点 `performance.settle` 控制审核/导出，与 `sharing_rules.*`（规则编辑）分离。

**技术路线**：复用现有 `compute_commission`（核算引擎）与 `preview_org_commission`（实时预估）；新增结算批次表 `performance_settlements`（按月状态机）+ 在 `commission_results` 上增加 `rule_snapshot`；冻结通过 `compute_commission` 跳过已确认周期实现；规则快照在核算落库时写入每个结果行。

## Technical Context

**Language/Version**: Python 3.11+（backend）、Vue 3 + Vite（manageSystem）、WeChat Mini-Program
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、MySQL 8.0、pytest + pytest-asyncio、APScheduler、Element Plus、Pinia、axios、csv（标准库）
**Storage**: MySQL 8.0（腾讯云，TLS）；本迭代无文件存储需求
**Testing**: pytest + pytest-asyncio（contract / integration / unit）；Vitest（管理端，如需）
**Target Platform**: Linux server（Docker）、Vue 管理后台（浏览器）、微信小程序
**Project Type**: 多端 Web 服务（backend REST API + Vue admin SPA + WeChat 小程序）
**Performance Goals**: 绩效计算页 2 秒内展示组织树与估算（SC-001）；导出在中小数据量下即时返回
**Constraints**: 统一响应格式 `{code,message,data,requestId,serverTime}`；路径版本化 `/api/v1`；TDD 强制（先测试后代码）；本迭代无敏感字段（不涉及脱敏）；沿用既有月度结算节奏；冻结后已确认周期不得重算
**Scale/Scope**: 组织/分销员规模中小（数十组织、数百人）；月度核算全量一次；单月核算结果行数千级

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 合规 | 检查点 |
|------|------|--------|
| I. TDD（强制） | ✅ | 所有新端点必须有 contract 测试；结算状态机与核算逻辑必须有 unit 测试；完整用户旅程必须有 integration 测试 |
| II. API-First | ✅ | contracts/ 先行定义后再实现；统一响应格式；路径 `/api/v1` 版本化；前端仅消费后端 API |
| III. 分离关注点 | ✅ | 业务逻辑在后端；管理端/小程序端只做展示与表单；审核状态机在后端服务层集中实现 |
| IV. 数据库完整性 | ✅ | schema 变更走 Alembic 迁移；无敏感字段（不涉脱敏）；审核确认/打回留痕（reviewer/time/reason）即审计 |
| V. 简化（YAGNI） | ✅ | 只做 spec 要求的能力；规则快照是 FR-007 明确要求（非投机）；不引入无谓抽象 |

Gate 结果：**通过**，无违规项。Phase 1 完成后重新检查。

## Project Structure

### Documentation (this feature)

```text
specs/008-performance-calculation/
├── plan.md              # 本文件 (/speckit-plan)
├── research.md          # Phase 0 输出 (/speckit-plan)
├── data-model.md        # Phase 1 输出 (/speckit-plan)
├── quickstart.md        # Phase 1 输出 (/speckit-plan)
├── contracts/           # Phase 1 输出 (/speckit-plan)
│   ├── admin-performance.md
│   └── miniprogram-performance.md
└── tasks.md             # Phase 2 输出 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/src/
├── models/
│   ├── performance_settlement.py    # 新增：月度核算批次（状态机）
│   └── commission_result.py         # 修改：+ rule_snapshot
├── services/
│   ├── settlement_service.py        # 新增：审核/打回/重算/导出
│   └── commission_service.py        # 修改：冻结跳过 + 规则快照 + 重算
├── api/v1/
│   ├── admin_performance.py         # 新增：管理端绩效计算/审核/导出
│   └── my_performance.py            # 新增：小程序本人/组织绩效
# 注：settlement_task.py 无需修改——compute_commission 内部自动创建/恢复 pending 批次
├── services/seed_service.py         # 修改：+ performance.settle 权限
└── main.py                          # 修改：挂载新路由
backend/tests/
├── contract/                        # 新增：审核/导出/小程序绩效 contract 测试
├── integration/                     # 新增：核算→审核→冻结 全流程测试
└── unit/                            # 新增：状态机、快照、冻结逻辑测试

manageSystem/src/
├── pages/performance/settlement.vue # 新增：绩效计算页（组织树+估算+审核+导出）
├── router/index.js                  # 修改：+ 绩效计算路由
├── constants/permissions.js         # 修改：+ performance.settle
└── App.vue                          # 修改：+ 绩效计算菜单
# 注：未新建 Pinia store——复用 api/performance.js 服务 + 页面本地状态（与绩效规则页一致，更简）

miniProgram/
├── pages/performance/               # 新增：本人绩效页（预估+已确认）
├── pages/org-performance/           # 修改：增加提成预估/已确认区块
└── services/commission-service.js   # 新增：绩效接口封装
```

**Structure Decision**: 三端分离，与 Constitution III 一致。新功能逻辑集中在 backend 服务层（`settlement_service` + 扩展 `commission_service`），管理端与小程序端分别新增页面与服务。后端迁移走 Alembic。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无 Constitution 违规项。规则快照（`rule_snapshot`）与结算批次表是 spec 的 FR-007/FR-012 明确要求，属功能必需而非过度设计，无需在复杂度表中额外论证。

---

## 设计决策摘要（详见 research.md / data-model.md / contracts/）

- **冻结机制**：`performance_settlements`（period 唯一）状态机 `pending → reviewed / pending → rejected → pending`；`compute_commission` 在已 `reviewed` 周期直接跳过。
- **规则快照**：核算落库时把当时生效规则的 `{ruleType, tiers, version}` 写入 `commission_results.rule_snapshot`。
- **审核/导出权限**：`performance.settle`（新增），加入 seed 全量权限与前端权限表；估算查看沿用 `sharing_rules.read`。
- **导出格式**：CSV（标准库），按周期/组织树范围导出核算明细。
- **并发审核**：条件 UPDATE（`WHERE period=? AND status='pending'`）乐观控制，重复确认幂等拒绝。
- **小程序接口**：复用 `get_current_user`，按分销员/组织管理员身份返回本人/所管组织数据。
