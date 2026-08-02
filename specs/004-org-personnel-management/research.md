# Research Document: 组织人员管理（组织架构 + 分销员 + 组织管理员业绩视图）

**Branch**: `004-org-personnel-management` | **Date**: 2026-08-02
**Purpose**: Phase 0 research — 将现有"层级/拓展人"体系重构为"组织/分销员"体系的技术决策、模式与实现策略。

---

## 1. 组织树数据模型（任意深度）

### Decision

继续采用**邻接表**（`organizations.parent_id` 自引用），去掉现有 `hierarchy_service.MAX_LEVEL = 6` 的硬编码上限；`org_type` 由固定枚举改为后台可配置的字符串类型。树深度不做硬性上限，但后台可配置最大深度用于误操作防护。

### Rationale

- 现有 `hierarchy_nodes` 已是邻接表，子树迁移 = 更新 FK，成本最低。
- 任意深度下"查直接子节点"与"整体迁移子树"仍是最常见操作，邻接表完全胜任。
- 组织树深度实际很小（业务组织层级，通常 < 20 层），全路径/祖先链可用应用层递归或 SQL 递归 CTE，性能可接受。
- `org_type` 改为字符串（`headquarters`/`region`/`branch` 等作为 seed，允许后台自定义），满足"层级类型由后台定义"（FR-005）。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 物化路径（materialized path） | 子树迁移需批量重写路径列；组织树深度小，收益低 |
| 闭包表（closure table） | 冗余关联行多，插入/删除维护复杂，深度查询在本规模下无必要 |
| 嵌套集（nested sets） | 频繁插入/迁移场景下重编号成本高，模型难以维护 |

### Implementation Notes

- 复用现有 `HierarchyNode` 的自引用结构，新增 `org_type` 与 `sort_order` 列，保留 `status`（正常/停用）。
- 环路检测沿用现有 `hierarchy_service` 的递归校验逻辑（`_get_node_or_404` + 祖先链检查），迁移到 `organization_service`。
- 最大深度校验改为读取后台配置（无配置则不限制）。

---

## 2. 演进策略：新表 + 数据迁移（vs 原表改造）

### Decision

为组织/分销员/组织资质建立**新表**（`organizations`、`distributors`、`org_qualifications`），通过 Alembic 迁移脚本完成建表 + 数据迁移 + 新外键切换，旧表（`hierarchy_nodes`、`promoters`、`qualifications`）在迁移完成后废弃。历史数据不清空、不丢失。

### Rationale

- 新模型结构与旧表差异大（分销员含账户字段、组织含类型配置、资质改为组织级），原表原地改造会产生大量 nullable 列与混乱语义。
- 迁移脚本可在单个事务内完成，保证原子性与可回滚；配合迁移测试校验 100% 数据保留（SC-009）。
- 客户/推广码/账单/贡献值等外键从 `promoters.id` 迁移到 `distributors.id`，用新表做"切表"比原地改外键清晰可控。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 原表重命名 + ALTER 加列 | 结构差异大、外键引用面广，迁移脚本复杂易错，且遗留大量语义混乱的列 |
| 保留旧表 + 新模型并存双写 | 双写一致性与迁移窗口复杂度高，本系统规模不需要 |

### Implementation Notes

- 迁移顺序：建 `organizations` → 迁移 `hierarchy_nodes` 树 → 建 `distributors` → 迁移 `promoters` 并回填 `org_id` → 建 `org_qualifications` → 迁移资质 → 切客户/推广码/账单/贡献值外键 → 废弃旧表。
- 每步对应独立 Alembic 版本，保证可分步验证与回滚。

---

## 3. 分销员账户与登录认证

### Decision

保留 `users` 作为统一账户表，新增 `password_hash`、`phone`（登录标识）等字段；`distributors` 作为扩展表（`user_id` 唯一 FK + `org_id` + `org_role` + 状态）。登录：手机号+密码校验 `users`；**首次登录强制绑定微信**（写入 `users.openid`），绑定后支持微信授权快速登录。

### Rationale

- 现有 mini-program 认证、`user_tokens` 会话、`auth_service` 全部围绕 `users` 构建，复用成本最低，微信绑定天然落在 `users.openid` 上。
- 迁移时现有微信用户（旧 promoter）保留原 openid，无需重新绑定，符合"迁移后正常运作"（SC-010）。
- 新增分销员由后台创建（FR-009），密码初始值由后台生成/设置，首登引导绑定微信（FR-027）。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| `distributors` 独立账户表（自带密码/会话） | 需重做认证与会话体系，与现有 auth/token 逻辑脱节，回归风险高 |
| 仅微信登录，不引入账密 | 与"后台新建账户"语义不符；无账密则无法独立于微信创建账号 |

### Implementation Notes

- `users` 现有 `user_type`、`phone`、`openid` 字段保留；`password_hash` 为 nullable（兼容仅微信用户）。
- 新增接口：`POST /api/v1/auth/distributor-login`（手机号+密码）、`POST /api/v1/auth/bind-wechat`（首登绑微信）。
- 登录成功后沿用现有 `user_tokens` 机制签发访问/刷新令牌。

---

## 4. 组织资质建模与个人资质迁移规则

### Decision

`org_qualifications` 挂 `org_id`，字段沿用现有 `qualifications`（文件类型、文件地址、有效期、状态、审核人/时间）。**迁移规则**：对每个组织，取其下全部旧拓展人资质中 `created_at` 最新的一条作为该组织的资质记录，状态保持原状；若该组织无任何历史资质，则不创建资质（组织按"无资质"处理）。

### Rationale

- 保持业务连续性：迁移后组织资质状态不倒退，避免业务中断（SC-010）。
- 资质已确认挂组织级（spec Q2-A / FR-008），个人资质语义由组织资质取代。
- 取"最新一条"避免同组织多拓展人资质重复导致的归属歧义。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 同组织多资质全部迁入并保留多条 | 同组织下多资质并列的"当前有效"语义复杂，且后续审核流程按单条资质推进 |
| 全部置为"审核中"强制重审 | 中断既有业务，与迁移后立即正常运作的目标冲突 |

### Implementation Notes

- 沿用现有资质审核流程（上传 → 审核中 → 通过/驳回）+ 到期 30 天提醒（FR-007）。
- 组织资质被驳回/过期时暂停该组织下分销员业务（FR-008），历史业绩不受影响。

---

## 5. 组织业绩子树聚合

### Decision

复用现有 `contribution_records`（主体外键迁移为 `distributor_id`）。组织业绩 = 组织子树下所有分销员个人贡献值之和（递归含子组织）。按需聚合，不做常驻物化汇总。

### Rationale

- 组织规模为"数百人"级（spec 边界场景），按需聚合查询（本月/累计）可满足 < 5s 目标（SC-002）。
- 避免引入汇总表的写入与一致性维护复杂度，符合 YAGNI。
- 数据来源与个人贡献值一致，天然满足 SC-006（核对偏差为 0）。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 物化汇总表/缓存 | 引入冗余写入与一致性风险，量级不需要 |
| 常驻快照按组织预聚合 | 增加迁移与维护成本，聚合延迟目标未达阈值 |

### Implementation Notes

- 组织业绩接口：`GET /api/v1/org/performance`（组织管理员）。先取授权组织子树 id 集合，再对 `contribution_records` 按 `distributor_id` 汇总本月/累计贡献值，返回组织汇总 + 各分销员贡献值，**不含客户级明细**（FR-015）。
- 子树 id 集合通过 `organizations` 邻接表递归获取；数据量级下 SQL 递归 CTE 或应用层递归均可。

---

## 6. 组织管理员身份建模

### Decision

`distributors.org_role ENUM('member','admin')`。单组织归属（spec Q1-A）下，组织管理员身份是分销员在该组织内的一种身份，无需独立关联表。

### Rationale

- 单组织归属使"分销员 → 组织"唯一，管理员身份用一列即可表达。
- 设置/撤销 = 更新 `org_role`，即时生效（FR-014）。
- 授权仅由后台管理员执行（FR-026），不涉及小程序端写操作。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 独立 `org_admins` 关联表 | 为多组织归属预留的模型，本特性单组织归属下冗余 |

---

## 7. RBAC 细分权限点

### Decision

权限 JSON 中新增：`org:manage`（组织树管理）、`distributor:manage`（分销员管理）、`org_admin:assign`（组织管理员设置）；组织资质审核**复用** `qualification:review`。旧 `hierarchy:manage` 由 `org:manage` 取代。Seed：超级管理员全开；管理员（Admin）赋 `org:manage`、`distributor:manage`、`org_admin:assign`、`qualification:review`。

### Rationale

- 与现有权限矩阵的细粒度风格一致（Q3-B 已确认）。
- 组织管理/分销员管理/管理员设置三操作可独立授权，未来可灵活开放给运营等角色。
- 组织资质审核沿用 `qualification:review`，语义一致，无需新权限点。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 复用 `hierarchy:manage` | 无法区分组织/分销员/管理员设置三类操作，授权粒度不足 |
| 仅超级管理员 | 与现有 Admin 角色的操作范围不符，灵活性差 |

### Implementation Notes

- 后台接口鉴权：`get_admin_user` + 权限校验依赖（`require_permission("org:manage")` 等）。
- 迁移时更新 `roles` 表中的权限数据（`hierarchy:manage` → `org:manage` 等），或由 seed 迁移脚本处理。

---

## 8. 数据迁移原子性与切换

### Decision

全部 schema 变更与数据迁移放入 Alembic 版本序列，迁移在事务内完成；迁移前做数据备份/快照；迁移后运行一致性校验脚本（对比新旧表行数、贡献值求和、客户绑定数、推广码数），校验通过视为迁移成功。

### Rationale

- 满足 SC-009（历史数据 100% 保留、数值一致）与 SC-010（迁移后功能正常）。
- 单事务迁移避免数据分叉（spec 边界场景）；校验脚本把"迁移正确"变成可测试、可验证的目标。

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| 双写过渡 + 灰度切换 | 一致性维护复杂，本系统单团队规模不需要 |

### Implementation Notes

- 迁移测试：用 seed 数据构建历史场景 → 执行迁移 → 断言新旧结构行数、外键对应关系、贡献值总和一致。
- 大表（`contribution_records`）外键切换按需分批，具体批处理策略写入 tasks。

---

## 9. 管理后台前端改版

### Decision

`manageSystem` 新增组织模块页面：组织树管理、组织详情（含资质文件页签）、组织内分销员列表/新建、组织管理员设置；原 `hierarchy` 页面改版为组织人员管理或移除。复用现有 Element Plus 组件、`http.js` 与路由结构。

### Rationale

- 与现有后台模块化结构一致；组织管理取代层级管理（spec 主题）。
- 组织详情聚合"资质文件 + 分销员 + 管理员设置"三个页签，对应 US2/US3/US4。

### Implementation Notes

- 路由新增 `/org`（组织人员管理）；页面按 spec US1-US4 拆分子视图。
- 权限控制：菜单/接口按细分权限点显隐。

---

## 10. 小程序端改造

### Decision

`miniProgram` 认证流程新增手机号+密码登录与微信绑定；新增组织业绩页面（组织管理员入口）。复用现有会话服务与自定义导航。

### Rationale

- 首登强制绑微信（R2-Q1-B）要求认证流程扩展。
- 组织业绩视图（US5）需小程序端新页面；其余现有页面保持（迁移后数据主体变化由 API 适配，前端基本不变）。

### Implementation Notes

- 登录：账密登录 → 校验成功 → 引导微信绑定 → 进入首页；绑定后微信授权直接登录。
- 组织业绩页按组织管理员身份显示入口，非组织管理员不显示（FR-016）。

---

## 11. 分账规则与对账报表适配

### Decision

`sharing_rules` 的层级维度适配为组织层级/组织类型维度；对账报表维度增加组织维度。新规则对新数据生效，历史数据不回溯（US6-AC5/6）。

### Rationale

- spec Q2-A 明确全部适配；分账/对账是现有核心功能，需随组织模型迁移。
- "新规则对新数据、历史不回溯"沿用现有分账规则语义，避免破坏已结算数据。

### Implementation Notes

- `sharing_rules` 现有"层级"字段改为引用组织层级/类型；报表聚合查询按组织维度分组。
- 适配范围在 tasks 中按现有 sharing_service/report_service 的改动面拆解。

---

## 12. 测试策略

### Decision

按 TDD 宪法编写测试，覆盖以下关键风险点：

- **迁移正确性**：seed 历史数据 → 迁移 → 断言行数/数值/外键一致（SC-009/010）。
- **组织树**：创建/编辑/迁移/环路拦截/删除非空拦截（SC-004）。
- **登录与绑定**：手机号+密码登录、首登强制绑微信、绑定后微信快速登录（contract 测试）。
- **组织资质**：上传/审核/到期提醒/过期暂停（SC-005）。
- **组织业绩**：子树聚合正确性（SC-006）、越权不可见（SC-007）、撤销后入口消失（SC-008）。
- **权限拦截**：无权限角色操作被拒（SC-011）。

### Rationale

- TDD 宪法强制测试先行；本特性含大规模迁移与重构，回归安全依赖测试网。
- 上述测试直接验证 spec 的可量化成功标准。

### Implementation Notes

- 测试目录沿用 `backend/tests/{unit,integration,contract}`；迁移测试置于 `integration`。
- 组织业绩聚合一致性测试通过"同一时段组织汇总 = 各分销员贡献之和"断言（SC-006）。
