# Research: 小程序注册自动挂载默认组织顶级部门

**Feature**: 012-register-default-dept
**Date**: 2026-08-08

## R1: 默认组织查询策略

**Decision**: 在每个注册请求中动态查询 `sort_order` 最小且 `parent_id = NULL` 的 Organization 记录。

**Rationale**:
- 无需新增配置表或标志位——最小化 schema 变更（YAGNI）。
- 查询简单高效：`SELECT id FROM organizations WHERE parent_id IS NULL ORDER BY sort_order ASC LIMIT 1`，在 `organizations` 表已有 `sort_order` 索引。
- 管理员的"调整默认组织"本质上是调整根节点的排序值——已有 UI 支持编辑 `sort_order`，无需额外开发。

**Alternatives considered**:
1. `is_default` 标志位 — 需要新增字段 + 迁移 + 管理 UI，违反 YAGNI。
2. 环境变量/配置文件 — 运维负担，不灵活。
3. 默认组织缓存 — 当前规模不需要；如果未来组织数量增长，可以在 `organization_service.py` 中加 `@lru_cache`。

## R2: 手机号+密码自主注册路径

**Decision**: 新增 `POST /api/v1/auth/distributor-register` 端点，与现有 `distributor-login` 分离。

**Rationale**:
- 当前 `distributor_login` 要求 Distributor 已存在（否则返回 "该账号不是分销员"）——语义上 login ≠ register。
- 分离端点的好处：注册需要额外参数（name, password），登录只需要 credentials；符合 REST 语义。
- Clarification Q5 确认两者都需自动挂载 → register 端点中复用同一 `register_distributor()` service 函数。

**Alternatives considered**:
1. 在 `distributor_login` 中内嵌注册逻辑 — 语义混乱，错误处理复杂。
2. 复用 admin `POST /orgs/{org_id}/distributors` — 该端点需要管理员权限，不适合自主注册。

## R3: WeChat 登录流程中自动创建 Distributor 的时机

**Decision**: 在 `wechat_login()` 中，创建 User 后、`await db.flush()` 之前插入 Distributor 创建逻辑。使用同一数据库事务保证原子性。

**Rationale**:
- User 和 Distributor 必须在同一事务中创建（否则 User 创建成功但 Distributor 失败会留下孤儿记录）。
- 在 `await db.flush()` 之前创建 → 使用 `await db.refresh(user)` 后的 user.id 创建 Distributor，确保 FK 有效。
- 与 `create_distributor()` 共享核心逻辑（手机号去重检查、org 存在性验证）。

**Alternatives considered**:
1. 在 API 层面（`auth.py`）调用两个 service — service 间耦合，事务边界模糊。
2. 使用数据库触发器 — 违反 API-First 原则（Principle II），业务逻辑应在 backend 代码中。

## R4: `source_channel` 字段设计

**Decision**: 在 `distributors` 表新增 VARCHAR(32) 的 `source_channel` 字段，可选值：`wechat_register`、`admin_create`、`phone_register`。

**Rationale**:
- 最小化变更：一个字段 + 一个迁移文件。
- 满足 FR-006（标记来源渠道），方便管理员识别。
- 使用字符串枚举而非整数：可读性好，方便调试和报表。
- 默认为 `admin_create`（历史数据兼容）；新注册设为对应的注册渠道。

**Alternatives considered**:
1. 在 `users` 表加字段 — `users.user_type` 已有多种类型，语义上来源渠道属于人员身份（Distributor）。
2. 独立的审计日志表 — 过度设计，当前需求仅需区分来源。

## R5: profile-setup 页面改造方案

**Decision**: 保留 `/pages/auth/profile-setup/index` 页面，改为可选信息完善页。在 `session-service.js` 的 `getEntry()` 中移除 `!profileCompleted → reLaunch to profile-setup` 的强制路由。

**Rationale**:
- 最小化前端变更：不删除现有页面，仅调整路由逻辑和页面内容。
- "跳过"按钮 → 直接进入首页；"提交"按钮 → 保存信息后进入首页。
- profileCompleted 标志不再作为路由守卫条件，仅用于判断是否需要展示完善提示。

**Alternatives considered**:
1. 完全删除 profile-setup 页面 — 丢失收集用户姓名/头像的能力。
2. 在首页弹窗提示完善信息 — 打扰用户体验，不如独立的可选页面。
