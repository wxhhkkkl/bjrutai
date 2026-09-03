# Phase 0 Research: 后台消费录入

**Feature**: `016-admin-consumption-entry`  
**Date**: 2026-09-02

## R1: 人工消费继续使用 Bill 作为消费事实来源

**Decision**: 人工录入直接创建 `bills` 记录，并为账单增加来源、归属快照、录入人、备注和幂等元数据。

**Rationale**:
- 当前消费总额、趋势、工作台、客户消费和排行均以 `Bill.paid_amount_cent` 为统一口径。
- 直接创建已支付账单可以复用现有统计路径，避免人工数据与同步数据产生两套汇总逻辑。
- 来源字段允许后台明确区分“儒泰同步”和“人工录入”。

**Alternatives considered**:
1. 新建独立人工消费表并在所有统计中做联合查询：会扩大每个消费查询的复杂度并产生双数据源。
2. 仅写审计日志：审计日志不是业务事实，无法可靠进入统计。
3. 伪造儒泰交易号后写入现有字段但不记录来源：无法审计，也容易被误认为外部同步数据。

## R2: 人工消费保存提交时的人员和组织归属快照

**Decision**: 人工账单保存 `attributed_distributor_id`、人员姓名快照、`attributed_org_id` 和组织名称快照；人工消费统计优先使用快照，存量同步账单继续使用客户当前归属。

**Rationale**:
- 规格要求客户后续转移时不改写历史人工消费归属。
- 只保存客户 ID 会使现有 `Bill → Customer → Distributor` 聚合随着客户转移而变化。
- ID 支持排行和筛选，名称快照保证人员或组织改名后仍能还原录入时语义。

**Alternatives considered**:
1. 永远按客户当前归属统计：不满足历史归属不变的假设。
2. 禁止已产生消费的客户转移：会破坏现有客户管理流程。
3. 建立完整归属历史维表并按消费时间回溯：当前仅人工消费需要固定归属，属于过度设计。

## R3: 客户搜索使用消费录入专用只读端点

**Decision**: 在 `/admin/contributions` 下增加客户搜索端点，使用 `contributions.write` 权限，只返回有效绑定客户的脱敏信息、归属和版本。

**Rationale**:
- 现有 `/admin/customers` 强制要求 `orgId` 和 `customers.read`，与消费录入的全局选择场景不匹配。
- 专用返回可以最小化敏感字段，同时避免拥有消费录入权限的角色被迫获得完整客户管理权限。
- 返回客户版本可支持提交前的并发变更检测。

**Alternatives considered**:
1. 复用客户管理列表：会耦合额外权限和组织树选择，且响应字段超出录入所需。
2. 前端加载全部客户后本地搜索：数据量、隐私和性能都不可控。
3. 允许在录入弹窗内创建客户：超出单笔消费录入范围，并绕过现有绑定流程。

## R4: 金额采用整数分，时间采用带时区 ISO 8601

**Decision**: API 接收 `amountCent` 正整数，前端把最多两位小数的人民币金额转换为分；`consumedAt` 必须带时区，后端统一为 UTC 后与当前时间比较并按现有数据库约定保存。

**Rationale**:
- 现有账单和统计全部使用整数分，避免浮点舍入误差。
- 显式时区避免浏览器、服务器和数据库时区不同造成月份归属错误。
- 后端再次校验，不能依赖前端控件保证数据正确。

**Alternatives considered**:
1. API 接收浮点元：存在二进制浮点和四舍五入歧义。
2. 接收无时区本地时间：部署环境变化会改变统计月份。
3. 只做前端校验：可被直接请求绕过。

## R5: 使用业务级持久化幂等，不依赖进程内缓存

**Decision**: 强制 `Idempotency-Key`；账单保存录入管理员、幂等键和规范化请求指纹，并建立 `(created_by_admin_id, idempotency_key)` 唯一约束。相同键和相同内容返回首次结果；相同键但内容不同返回冲突。人工录入端点绕过现有进程内幂等缓存，交由业务服务处理。

**Rationale**:
- 进程内缓存无法跨 worker、重启或多实例保证只创建一次。
- 数据库唯一约束是最终并发防线。
- 请求指纹防止管理员修改表单后误用旧键而获得错误的历史响应。

**Alternatives considered**:
1. 只禁用前端按钮：网络重试和并发请求仍可能重复。
2. 只使用当前内存中间件：生产多实例不可靠。
3. 全局重构幂等中间件：本功能无需扩大到所有写接口。

## R6: 新增 contributions.write 并由后端强制执行

**Decision**: 保留 `contributions.read` 用于查看，新增 `contributions.write` 用于客户搜索和人工录入；系统管理员默认获得该权限，其他角色由角色管理配置。

**Rationale**:
- 人工录入直接影响业绩，风险明显高于只读查看。
- 命名和项目现有 `customers.read/write`、`articles.read/write` 一致。
- 前端隐藏按钮只改善体验，后端权限依赖才构成安全边界。

**Alternatives considered**:
1. 复用 `contributions.read`：无法配置只读财务或运营角色。
2. 只判断管理员身份：所有管理员都可改业绩，权限过宽。
3. 复用 `customers.write`：客户资料编辑与消费录入职责不同。

## R7: 录入和审计在同一事务中完成

**Decision**: 创建账单和 `AuditLog(action=manual_consumption_create)` 使用同一数据库事务；审计行的 `user_id` 留空，管理员 ID 与用户名快照保存在最小化的 detail 中。

**Rationale**:
- 当前 `AuditLog.user_id` 外键指向小程序 `users`，不能安全写入 `admin_accounts.id`。
- detail 可以保留管理员身份而不引入错误外键；账单自身也保存 `created_by_admin_id` 供结构化查询。
- 同一事务防止出现有消费无审计或有审计无消费。

**Alternatives considered**:
1. 把管理员 ID 写入 `AuditLog.user_id`：存在错误外键语义及 ID 碰撞风险。
2. 新建消费审计表：账单元数据加通用 AuditLog 已满足本期追溯要求。
3. 提交后异步写审计：失败时会留下不可追溯记录。

## R8: 后台采用单弹窗表单与最终确认

**Decision**: 在现有消费业绩页增加 `ManualConsumptionDialog`，使用远程客户搜索、只读归属区、日期时间、金额和备注；提交前使用确认摘要，不新增页面和 Pinia store。

**Rationale**:
- 单笔录入字段少，弹窗能保留看板上下文，成功后直接刷新数据。
- 状态仅在当前页面使用，本地组件状态比全局 store 简单。
- Element Plus 已提供远程选择、日期时间、表单校验和确认组件。

**Alternatives considered**:
1. 独立路由页面：增加导航和返回状态管理，但没有对应信息复杂度。
2. 多步骤向导：当前只有选择客户和三个字段，交互过重。
3. 新建 Pinia store：无跨页面消费者。

