# Research: 后台管理 RBAC 权限管理

**Feature**: 002-admin-rbac
**Date**: 2026-07-31

## 1. Role `is_system` 字段设计

**Decision**: 在 `roles` 表新增 `is_system` 布尔字段，默认 `False`，通过 Alembic 迁移添加。

**Rationale**:
- 简单直接，符合 YAGNI 原则
- 后端删除角色 API 检查此字段，拒绝删除系统角色
- 前端根据此字段隐藏系统角色的删除按钮和名称编辑入口
- 替代方案（硬编码角色名称判断）脆弱且不可扩展

**Alternatives considered**:
- 硬编码检查 `name == "系统管理员"`：简单但脆弱，改名即失效
- 新增 `role_type` 枚举字段：过度设计，当前只需区分"系统/自定义"

## 2. 权限列表定义策略

**Decision**: 权限列表在前端常量文件 `manageSystem/src/constants/permissions.js` 中定义，后端角色 API 保持现有的 JSON 透传模式。

**Rationale**:
- 权限定义本质上是前端 UI 控制需求（哪些菜单/按钮可见），应由前端定义
- 后端已支持 `{ "permissions": [...] }` 格式的 JSON 透传，无需新增 Permission 表
- 避免前后端权限列表不同步问题——前端作为权限定义的唯一来源
- 符合 YAGNI：当前无服务端按权限维度鉴权的需求

**Alternatives considered**:
- 新增 `permissions` 数据库表 + CRUD API：增加了需要维护的实体数量，且当前权限仅用于前端 UI 控制
- 配置文件定义权限：与前端常量本质上相同，但常量文件更接近消费方

## 3. 权限树组件方案

**Decision**: 基于 Element Plus `el-tree` 组件封装 `PermissionTree.vue`，支持按模块分组、全选/取消全选、父子节点关联。

**Rationale**:
- Element Plus `el-tree` 原生支持 checkbox 模式、`check-strictly`（父子独立）和 `default-expand-all`
- 权限配置本质上是嵌套选择，Tree 组件是最自然的交互
- 自定义节点渲染支持模块名（一级）和权限描述（二级）

**Alternatives considered**:
- 手写 checkbox 嵌套列表：代码量大，交互一致性差
- 使用 `el-transfer`（穿梭框）：不适合层级结构

## 4. 菜单子菜单实现方案

**Decision**: 利用 Vue Router 的 `children` 路由 + Element Plus `el-menu` 的 `el-sub-menu` 组件实现带折叠展开的子菜单。

**Rationale**:
- Vue Router `children` 路由天然支持嵌套路径（`/accounts` → `/accounts/admins`、`/accounts/roles`）
- Element Plus `el-menu` 的 `el-sub-menu` 与 router 集成良好
- 现有布局组件 `App.vue` 中已有 `el-menu` 结构，扩展现有模式即可

**Alternatives considered**:
- Tabs 切换：不符合菜单导航惯例，深层嵌套时 URL 不可直达

## 5. 默认数据播种策略

**Decision**: 在 `main.py` lifespan 中调用 seed 逻辑，检查 `roles` 表是否为空或 `is_system` 角色是否存在，若不存在则创建"系统管理员"角色（全权限）并关联 admin 账户。

**Rationale**:
- 复用现有 admin 播种模式（已在 lifespan 中播种 admin 账户）
- 播种逻辑幂等：使用 `SELECT ... WHERE is_system = TRUE` 检查是否已存在
- 系统管理员权限列表与前端常量保持同步（见 contracts/admin-rbac.md）

**Alternatives considered**:
- Alembic data migration：适合 schema + data 一起变更，但首次部署时可能跳过 migration 直接建表
- 独立 seed 脚本：需要手动执行，增加部署步骤

## 6. 前端子菜单默认路由跳转

**Decision**: 点击"账户管理"父菜单时自动跳转到第一个子菜单（管理员列表），而非展开/折叠。

**Rationale**:
- 用户体验：点击父菜单即展示内容，减少一次点击
- 与 Element Plus 默认行为一致（`el-menu` 的父级点击默认展开子菜单，需通过 router 重定向）

**Implementation**: 在路由配置中为 `/accounts` 添加 `redirect: '/accounts/admins'`。
