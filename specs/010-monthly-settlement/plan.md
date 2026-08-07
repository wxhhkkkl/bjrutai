# Implementation Plan: 绩效计算模块月度核算（未核算月份选择 + 数据报表展示 + 审核冻结/打回）

**Branch**: `010-monthly-settlement` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-monthly-settlement/spec.md`

## Summary

在既有绩效计算模块（008）之上增强**月度核算**的两项能力：

- **未核算月份选择**：绩效计算页的月份选择器仅列出**可核算月份**（无核算记录 / 已打回待重算），待审核与已审核冻结/已确认的月份不可选；管理员选定后可**发起核算**，核算成功后该月进入待审核。
- **数据报表展示**：核算成功后系统**自动生成该月核算报表记录**，展示在「数据报表」历史报表列表内，带**待审核状态标记**，可查看汇总/明细与导出；审核通过后状态变为已确认/冻结，打回后体现打回状态。
- **审核冻结/打回闭环**：审核通过 → 冻结不可再改；审核不通过 → 打回（记录原因）→ 重新核算 → 再待审核。**复用 008 既有 `performance_settlements` 状态机**，不重复建设。

**技术路线**：
- 复用 008 的核算/审核/冻结/打回引擎（`commission_service.compute_commission`、`settlement_service`）。
- 新增「可核算月份」查询能力：从既有账单数据推导存在业务数据的月份，排除待审核/已冻结月份，作为月份选择器的可选项。
- 新增「发起核算」动作：选定可核算月份后调用核算引擎，生成/恢复 `pending` 批次，并**自动落一条核算报表记录**（复用 `reports` 表，标记来源与状态）。
- 数据报表：扩展 `ReportService`，支持核算来源报表记录的生成、列表、详情（汇总+明细）、导出（复用既有 Excel 导出），并在列表/详情携带审核状态。
- 权限：查看核算报表记录沿用 `sharing_rules.read`；审核/打回/重算/发起核算沿用 `performance.settle`（已确认）。

## Technical Context

**Language/Version**: Python 3.11+（backend）、Vue 3 + Vite（manageSystem）
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、MySQL 8.0、pytest + pytest-asyncio、openpyxl（报表导出）、APScheduler
**Storage**: MySQL 8.0（腾讯云，TLS）
**Testing**: pytest + pytest-asyncio（contract / integration / unit）
**Target Platform**: Linux server（Docker）、Vue 管理后台（浏览器）
**Project Type**: 多端 Web 服务（backend REST API + Vue admin SPA + 微信小程序）
**Performance Goals**: 绩效计算页 2 秒内展示估算与月份选择（SC-001/SC-003）；核算成功到数据报表可见 2 秒内（SC-007）
**Constraints**: 统一响应格式 `{code,message,data,requestId,serverTime}`；路径版本化 `/api/v1`；TDD 强制；冻结后已确认周期不得重算；不涉及小程序端
**Scale/Scope**: 组织/分销员规模中小（数十组织、数百人）；单月核算结果行数千级

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 合规 | 检查点 |
|------|------|--------|
| I. TDD（强制） | ✅ | 新增端点（可核算月份、发起核算）必须有 contract 测试；可核算月份推导逻辑、报表记录状态流转必须有 unit 测试；「核算→报表→审核→冻结/打回」完整旅程必须有 integration 测试 |
| II. API-First | ✅ | contracts/ 先行定义；统一响应格式；路径 `/api/v1` 版本化；前端仅消费后端 API |
| III. 分离关注点 | ✅ | 业务逻辑在后端（核算引擎/报表服务/权限）；管理端只做展示与表单；审核状态机沿用既有 `settlement_service` 集中实现 |
| IV. 数据库完整性 | ✅ | schema 变更走 Alembic 迁移（013：`reports` 加来源/周期/状态列）；无敏感字段（不涉脱敏）；审核/打回留痕沿用既有 `performance_settlements` 审计字段 |
| V. 简化（YAGNI） | ✅ | 复用 008 核算/审核引擎与 `reports` 导出能力；不新增独立核算引擎、不引入新外部依赖；「可核算月份」从既有账单数据推导，不建额外表 |

Gate 结果：**通过**，无违规项。Phase 1 设计完成后重新检查：仍合规——复用既有核算引擎与 `reports` 链路（III/V）、迁移走 Alembic 013（IV）、所有新增端点有 contract 测试与状态流转 unit/integration 测试（I/II），无需新增违规项。

## Project Structure

### Documentation (this feature)

```text
specs/010-monthly-settlement/
├── plan.md              # 本文件 (/speckit-plan)
├── research.md          # Phase 0 输出 (/speckit-plan)
├── data-model.md        # Phase 1 输出 (/speckit-plan)
├── quickstart.md        # Phase 1 输出 (/speckit-plan)
├── contracts/           # Phase 1 输出 (/speckit-plan)
│   └── admin-settlement-reports.md
└── tasks.md             # Phase 2 输出 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/src/
├── models/
│   └── report.py                    # 修改：+ source（默认 'reconciliation'）/ period / status 列
├── services/
│   ├── settlement_service.py        # 修改：+ 可核算月份推导、+ 发起核算（生成报表记录）
│   ├── report_service.py            # 修改：+ 核算报表记录的生成/列表/详情/导出（含状态）
│   └── commission_service.py        # 修改：无（复用 compute_commission）
├── api/v1/
│   ├── admin_performance.py         # 修改：+ GET settleable-periods、+ POST settle
│   └── reports.py                   # 修改：+ 核算报表记录的状态字段返回
├── migrations/versions/
│   └── 013_reports_settlement_source.py  # 新增：reports 加 source/period/status 列
└── services/seed_service.py         # 修改：无（复用既有 sharing_rules.read / performance.settle）

backend/tests/
├── contract/                        # 新增/修改：settleable-periods、settle、核算报表记录 contract 测试
├── integration/                     # 新增：核算→报表→审核→冻结/打回 全流程测试
└── unit/                            # 新增：可核算月份推导、报表记录状态流转测试

manageSystem/src/
├── api/performance.js               # 修改：+ settleablePeriods()、+ settle()
├── pages/performance/settlement.vue # 修改：月份选择器仅列可核算月份；+ 发起核算按钮
├── pages/reports/index.vue          # 修改：+ 核算报表记录的状态标记展示
├── stores/reports.js                # 修改：+ 核算来源状态字段透传
└── constants/permissions.js         # 修改：无（复用既有权限点）
```

**Structure Decision**: 三端分离，与 Constitution III 一致。核算逻辑复用既有 `commission_service`/`settlement_service`；「可核算月份」与「发起核算」集中到 `settlement_service`（新增能力）+ `admin_performance` 端点；核算报表记录复用 `reports` 表与 `ReportService`（扩展来源支持），避免新建一套报表体系。前端绩效计算页与数据报表页分别增强展示。数据库迁移走 Alembic（013）。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无 Constitution 违规项。`reports` 表新增来源/周期/状态列与「可核算月份」推导均为 spec（FR-002/FR-005）明确要求，属功能必需而非过度设计，无需在复杂度表中额外论证。
