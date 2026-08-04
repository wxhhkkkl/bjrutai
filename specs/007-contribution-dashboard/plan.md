# Implementation Plan: 业绩贡献页面增强

**Branch**: `007-contribution-dashboard` | **Date**: 2026-08-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-contribution-dashboard/spec.md`

## Summary

增强管理后台"业绩贡献"页为**业绩分析看板**：按时间范围查询所有人业绩、进入默认展示总体月度趋势与统计、组织当月业绩排名（全局列表 + 组织树筛选）、个人当月业绩排名、绑定用户数量排名（个人/组织两维度）、最新 30 条明细。

关键：现有 `/contributions` 端点是**个人视角**（`_get_promoter` 按 user_id 查分销员），admin 调用即 404——现 admin 业绩贡献页实际失效。本特性新增 **admin 级聚合端点**（`/admin/contributions/*`），按全局/组织树聚合贡献值与绑定数，前端页重构接入。

## Technical Context

**Language/Version**: Python 3.11+（后端）；Vue 3 + Vite（管理后台）
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、Pydantic v2；Element Plus、Pinia、Axios
**Storage**: MySQL 8.0（Tencent Cloud）；无新表（排名/趋势/统计为聚合查询）
**Testing**: pytest + pytest-asyncio（后端 TDD：契约 + 单元）；manageSystem 构建校验
**Target Platform**: Linux 服务器（后端）；浏览器（管理后台）
**Project Type**: web-service + admin-spa
**Performance Goals**: 进入页面 2 秒内展示趋势与统计（SC-001）；排名/明细聚合覆盖当前数据量（组织 ~10、人员 ~10s、贡献记录 ~1000s）
**Constraints**: 贡献值 `points` 为字符串列，聚合需 CAST 数值；排名按可选月份；绑定数为已绑定（BOUND）客户数
**Scale/Scope**: 组织 ~10、人员 ~10s、贡献记录/月 ~100s-1000s

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Test-Driven Development | ✅ PASS | 新聚合端点/服务先写测试；契约测试强制（`test_admin_contribution_dashboard.py`） |
| II. API-First Design | ✅ PASS | 新增 `/admin/contributions` 契约（dashboard/rankings） |
| III. Separation of Concerns | ✅ PASS | 聚合逻辑入 `contribution_dashboard_service.py`，API 层薄，前端只做展示 |
| IV. Database Integrity | ✅ PASS | 本特性不含敏感个人信息（业绩/绑定数均为数值聚合） |
| V. Simplicity (YAGNI) | ✅ PASS | 无新表，复用既有贡献/组织/客户数据聚合；无投机抽象 |

Gate 状态：全部 PASS。继续 Phase 0。

## Project Structure

### Documentation (this feature)

```text
specs/007-contribution-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── contribution-dashboard.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── services/
│   │   └── contribution_dashboard_service.py  # 新增：统计/趋势/排名/绑定数聚合
│   ├── api/v1/
│   │   └── admin_contributions.py             # 新增：/admin/contributions/dashboard + rankings
│   └── main.py                                # 注册路由
└── tests/
    ├── contract/test_admin_contribution_dashboard.py
    └── unit/test_contribution_dashboard_service.py

manageSystem/
├── src/
│   ├── api/contributions.js                   # 新增：admin dashboard API 封装
│   ├── pages/contributions/index.vue          # 重构：统计/趋势/排名/最新30条
│   └── stores/contributions.js                # 改：切换为 admin dashboard API
```

**Structure Decision**: 沿用既有分层。新增 admin 聚合服务与路由（不改造个人视角的 `/contributions`）；前端页重构为看板布局（统计行 + 趋势图 + 排名 tab + 最新明细），保留月度结算等既有操作。

## Complexity Tracking

> 复杂度说明（设计决策理由）。宪法检查无违规。

| Design Choice | Why Needed | Simpler Alternative Rejected Because |
|---------------|------------|-------------------------------------|
| 新增 `/admin/contributions` 聚合端点（而非复用 `/contributions`） | 现有端点为个人视角（`_get_promoter` 按 user_id 查分销员），admin 调用 404，无法展示全局/组织数据 | 改造现有端点兼顾个人/admin → 双语义混杂；在个人端点加 admin 分支 → 破坏其契约 |
| 无新表，聚合查询即时计算 | 排名/趋势/统计数据量小，实时聚合即可满足 2s 要求 | 建预聚合表 → 需同步/增量维护，过度设计（宪法 V） |
| `points` 字符串 CAST 数值聚合 | 贡献值存为字符串（沿用现状），聚合需 `SUM(CAST(points AS DECIMAL))` | 改列类型为数值 → 迁移存量字符串数据，风险与收益不成比例 |
