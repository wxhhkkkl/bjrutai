# Research: 业绩贡献页面增强

**Branch**: `007-contribution-dashboard` | **Date**: 2026-08-04
**目的**: 解决 Technical Context 中的技术决策/未知项，供 Phase 1 设计与 Phase 2 任务分解依据。

## 决策清单

### D1: 新增 admin 级聚合端点（不改造个人端点）
- **Decision**: 新增 `/admin/contributions` 路由（`get_admin_user` + `require_permission("contributions.read")`）：`/dashboard`、`/rankings/orgs`、`/rankings/persons`、`/rankings/bindings`
- **Rationale**: 现有 `/contributions` 为个人视角（`_get_promoter` 按 user_id 查分销员），admin 调用 404；新看板需全局/组织树聚合
- **Alternatives considered**: 在个人端点加 admin 分支 → 破坏个人契约；改造 `ContributionQueryService` 全局化 → 双语义混杂

### D2: 聚合查询（统计/趋势/排名/绑定数）
- **Decision**: `contribution_dashboard_service.py` 提供：
  - **dashboard**：统计（当月总业绩、累计业绩、组织数、人员数、绑定用户数）+ 月度趋势（近 N 月，`SUM(points)` 按月分组）+ 最新 30 条明细（`ORDER BY occurred_at DESC, id DESC LIMIT 30`）
  - **orgs ranking**：`contribution_records JOIN distributors` 按 `d.org_id` 分组 SUM(points)（当月），全局列表 + 可选 `orgId` 过滤其子树
  - **persons ranking**：按 `distributor_id` 分组 SUM(points)（当月），含人员姓名/组织，Top-N + 分页
  - **bindings ranking**：个人 = 每分销员已绑定（BOUND）客户数；组织 = 组织及全部下级人员的绑定客户总数；scope 参数切换
- **Rationale**: 复用既有表即时聚合；`occurred_at` 为贡献发生时间（非创建时间）
- **Alternatives considered**: 预聚合表 → 需同步维护，数据量小无需（宪法 V）

### D3: points 字符串 CAST 数值聚合
- **Decision**: 聚合用 `SUM(CAST(points AS DECIMAL(20,2)))`（MySQL）/ SQLite 兼容写法；响应仍以字符串或数值返回
- **Rationale**: `points` 为 String 列（沿用现状）；CAST 保证求和正确
- **Alternatives considered**: 改列类型 → 迁移存量字符串数据，风险大

### D4: 组织树筛选
- **Decision**: 排名端点接受 `orgId`，用 `organization_service.get_subtree` + `distributor_service._collect_org_ids` 取子树 org_ids；前端用树选择器（`el-tree-select`）过滤
- **Rationale**: spec Q1 确认"全局列表 + 树筛选"；复用既有子树工具
- **Alternatives considered**: 左树固定面板 → 与"全局列表"主视图冲突，用树选择器更贴合

### D5: 前端看板重构
- **Decision**: 重构 `contributions/index.vue`：筛选栏（时间范围 + 月份 + 组织树选择器）+ 统计行 + 趋势图 + 排名 tab（组织/个人/绑定数量）+ 最新 30 条明细；数据源切换为 `/admin/contributions/*`；保留月度结算按钮
- **Rationale**: 满足"一进入看趋势/统计"与各排名需求；沿用 Element Plus 组件
- **Alternatives considered**: 在旧页打补丁 → 个人视角数据失效，重构更干净

### D6: 绑定数口径
- **Decision**: 个人 = 该分销员名下 `binding_status='bound'` 客户数（累计）；组织 = 组织及全部下级人员名下绑定客户总数（`_collect_org_ids` 子树）
- **Rationale**: spec Q2 确认个人与组织两维度；"当前累计已绑定"语义
- **Alternatives considered**: 仅当月新绑定 → 与"绑定用户数量"常用语义不符

### D7: 排名口径
- **Decision**: 组织/个人业绩排名按**可选月份**（默认当月）贡献值从高到低；并列同排名；支持 Top-N/分页
- **Rationale**: spec US2/US3 "当月" + "选择当月"；数据量增长时需限制
- **Alternatives considered**: 仅当月固定 → 无法回看历史月

## 未知项状态

所有 NEEDS CLARIFICATION 已在 specify 阶段解决（组织排名=全局+树筛选、绑定排名=个人+组织）。本轮无新增未知项。

## 依赖与风险

- **points CAST**: SQLite（测试）与 MySQL 的 CAST 语法差异需在服务层统一处理（`func.sum(func.cast(points, Numeric))`）
- **既有贡献页失效**: 现 `/contributions` 个人端点在 admin 下 404，本次切换为 admin 端点；需确认小程序端个人贡献仍走 `/contributions`（不受影响）
- **数据量**: 聚合在组织/人员/记录规模下可满足 2s；趋势/排名需限制返回条数
- **月度结算**: 现有 `/contributions` 的结算端点（`/settle`）由前端调用，重构时保留入口
