# Implementation Plan: 绩效规则模块

**Branch**: `006-performance-rules` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-performance-rules/spec.md`

## Summary

"分成规则"页改名"绩效规则"并重构为**按组织配置**两种绩效提成方式：
- **组织内绩效提成**（阶梯百分比）：适用于本组织除管理员外成员，基数 = 成员自身业务产生的消费金额（`Bill.paid_amount_cent`）。
- **组织管理绩效提成**（阶梯百分比）：适用于组织管理员，基数 = 管理组织及全部下级组织人员业务消费金额总额。

**配置 + 计算引擎**：月度结算任务按规则计算提成并落库（`commission_results`），后台可按周期查看、可审计；同时提供按当前规则实时重算预览。另收紧约束：**每组织至多一名组织管理员**。旧按层级的 `SharingRule`/`ContributionCoefficient` 机制废弃（配置入口移除、数据不参与计算）。

## Technical Context

**Language/Version**: Python 3.11+（后端）；Vue 3 + Vite（管理后台）
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、Pydantic v2、APScheduler（既有月度结算）；Element Plus、Pinia、Axios
**Storage**: MySQL 8.0（Tencent Cloud，Alembic 迁移）
**Testing**: pytest + pytest-asyncio（后端 TDD：契约 + 单元）；manageSystem 构建校验
**Target Platform**: Linux 服务器（后端）；浏览器（管理后台）
**Project Type**: web-service + admin-spa
**Performance Goals**: 切换组织后绩效规则 2 秒内展示（SC-002）；月度提成计算覆盖百~千级账单可批处理完成
**Constraints**: 提成基数 = 消费金额（`Bill.paid_amount_cent`，分）；每组织至多一名组织管理员（收紧 004）；新绩效规则取代旧分成机制
**Scale/Scope**: 组织 ~10、每组织成员 ~10s、月账单 ~100s-1000s

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Test-Driven Development | ✅ PASS | 新端点/计算引擎先写测试；契约测试强制（`test_admin_performance_rules.py`、`test_commission_service.py`） |
| II. API-First Design | ✅ PASS | 新增 `/admin/performance-rules`、`/admin/commission-results` 契约 |
| III. Separation of Concerns | ✅ PASS | 配置服务 `performance_service.py`、计算引擎 `commission_service.py` 分层，API 层薄 |
| IV. Database Integrity | ✅ PASS | 本特性不含敏感个人信息（提成为金额数据）；无加密/脱敏冲突 |
| V. Simplicity (YAGNI) | ✅ PASS | 新表聚焦（rules/change_logs/results）；旧 `SharingRule` 机制**移除**（简化而非叠加） |

Gate 状态：全部 PASS。继续 Phase 0。

## Project Structure

### Documentation (this feature)

```text
specs/006-performance-rules/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── performance-rules.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   │   ├── performance_rule.py      # 新增：绩效提成方式 + 变更日志
│   │   └── commission_result.py     # 新增：提成结果（月度）
│   ├── schemas/
│   │   └── performance_rule.py      # 新增：配置请求/响应
│   ├── services/
│   │   ├── performance_service.py   # 新增：配置 CRUD + 阶梯校验 + 变更历史
│   │   └── commission_service.py    # 新增：计算引擎（月度落库 + 实时预览）
│   ├── api/v1/
│   │   └── admin_performance_rules.py  # 新增：/admin/performance-rules、/admin/commission-results
│   ├── tasks/settlement_task.py     # 改：月度结算后附加提成计算
│   └── services/distributor_service.py  # 改：set_role 强制单管理员约束
├── migrations/versions/
│   ├── 009_performance_rules.py     # 新增 3 表
│   └── 010_demote_duplicate_admins.py # 存量多管理员降级（保留一名）
└── tests/
    ├── contract/test_admin_performance_rules.py
    ├── unit/test_commission_service.py
    └── contract/test_admin_distributors.py  # 改：单管理员用例

manageSystem/
├── src/
│   ├── pages/performance-rules/index.vue   # 重命名+重构：左树右配置+预览/结果
│   ├── router/index.js                     # 改：/performance-rules（原 /sharing-rules）
│   ├── App.vue                             # 改：菜单"绩效规则"
│   ├── api/performance.js                  # 新增：绩效规则 API 封装
│   └── stores/                             # 移除 sharing store（或迁移到 performance store）
```

**Structure Decision**: 沿用既有分层。配置与计算分离两个服务；新增独立表承载规则/变更/结果（旧 `SharingRule` 机制移除，不共用其表）。前端页面重命名 + 重构，复用组织树模式（同 005 客户管理）。

## Complexity Tracking

> 复杂度说明（设计决策理由）。宪法检查无违规。

| Design Choice | Why Needed | Simpler Alternative Rejected Because |
|---------------|------------|-------------------------------------|
| 新增 `commission_results` 表 | 月度提成结果需按周期落库、可审计追溯（FR-013） | 仅实时计算不落库 → 无历史、不可审计，违反 FR-013 |
| 计算引擎独立 `commission_service.py` | 提成（金额基数）与贡献值（积分）是两套独立体系 | 塞入既有 `sharing_service`/`contribution_service` → 职责混杂 |
| 单管理员约束在 `set_role` 强制 + 存量数据迁移 010 | FR-008 收紧既有允许多管理员的行为 | 仅前端限制 → 可被 API 绕过，违反约束 |
| 移除旧 `SharingRule` 机制（页面/API） | FR-010 新规则取代旧机制 | 保留并行 → 两套提成体系语义重叠 |
