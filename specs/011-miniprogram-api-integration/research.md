# Phase 0 Research: 小程序前后端 API 集成与 Mock 替换

本研究基于 `miniProgram/` 当前页面和 service、`backend/src/api/v1/` 当前路由、001/004/005/008/009 规格及 Constitution 2.0。研究只决定前端方案，不授权修改后端。

## R1 — 联调边界

**Decision**: 本功能只修改 `miniProgram/` 与 `specs/011-miniprogram-api-integration/`。后端实际实现用于只读核对；不匹配登记为阻塞。

**Rationale**: 用户负责小程序模块并明确禁止修改后端逻辑。权限、脱敏和数据口径不能由客户端可靠补偿。

**Alternatives considered**:
- 联调时顺手改 FastAPI：超出责任边界，且可能掩盖契约评审。
- 页面兼容所有旧新响应：形成不可追踪的双套逻辑，后续难以删除。

## R2 — 统一请求层

**Decision**: 新建一个基于 `wx.request` 的 `request-service`，所有业务 service 复用它；页面不得直接调用 `wx.request`。

**Rationale**: 当前 `auth-service`、`commission-service`、`org-performance-service` 各自封装请求但错误处理不一致，且不支持刷新、超时和幂等。新增十余业务域后继续复制会造成行为漂移。

**Alternatives considered**:
- 每个 service 自己封装：重复 Token 和错误逻辑。
- 引入 Axios/第三方请求库：微信端仍需适配器，增加依赖但不能解决会话语义。

## R3 — Token 刷新策略

**Decision**: 使用单飞刷新 Promise。受保护请求遇到一次 401 时等待同一刷新；刷新成功仅重试原请求一次，失败统一清理会话并重启到登录页。

**Rationale**: Tab 页面常并发请求，多次刷新会触发 refresh token 轮换与撤销，导致随机退出。单飞可保证确定性并阻止无限循环。

**Alternatives considered**:
- 每个请求独立刷新：并发时旧 refresh token 相互失效。
- 仅根据本地过期时间提前刷新：仍需处理服务端撤销和时钟偏差。

## R4 — 真实会话与 Demo 隔离

**Decision**: 真实会话使用独立 key 和内存状态；`session-service` 不再导入 `mock/demo-control`。Demo 仅在明确开发开关下由入口选择，不能成为真实请求失败的 fallback。

**Rationale**: 当前真实登录最终仍调用 `setDemoSession`，页面状态和账户数据可能被旧 Demo 缓存污染。

**Alternatives considered**:
- 继续复用 Demo key：账户切换和生产安全不可验证。
- 删除全部 Mock：会破坏独立 UI 演示能力，没有必要。

## R5 — DTO 到 ViewModel 的适配位置

**Decision**: API service 返回经过最小契约校验的 DTO；纯 adapter/model 将 DTO 映射为现有页面 ViewModel。WXML 不直接依赖后端原始字段。

**Rationale**: 当前 UI 字段仍包含 `points`、`settled`、演示日期等旧语义。集中适配可保持现有 UI，同时明确按 009 映射 `amountCent` 和账单状态。

**Alternatives considered**:
- 页面内随处重命名字段：难测试且页面之间口径易漂移。
- 修改所有 WXML 完全匹配 DTO：改动面大，破坏已确认 UI 模型。

## R6 — 金额与日期

**Decision**: 金额始终保留整数分，只有展示函数转换成元字符串；ISO 8601 时间只在显示层格式化，筛选参数保持 `YYYY-MM` 等契约格式。

**Rationale**: 避免浮点累计误差，保持与 009/008 一致；避免将中文日期字符串回传后端。

## R7 — 列表竞态与分页

**Decision**: 每次筛选/搜索生成查询序号；仅最新序号可写页面。游标分页保存在当前查询上下文，筛选变化时清空 items/cursor/hasMore。

**Rationale**: 微信请求不可假设按发出顺序返回；快速搜索和月份切换可能被旧响应覆盖。

## R8 — 幂等与重复点击

**Decision**: 写动作在首次提交时生成稳定业务请求 key，未知结果重试复用该 key；明确失败或用户重新开始业务流程时生成新 key。按钮 pending 只是 UI 防重，不能替代 key。

**Rationale**: 绑定接口强制 `Idempotency-Key`；其余写接口即使当前未校验，也可携带安全 header，便于后端后续支持且保证客户端语义一致。

## R9 — 环境配置

**Decision**: 环境模块只暴露非敏感 API Base 和构建环境；本地默认 `http://127.0.0.1:8000`，体验/生产必须显式配置 HTTPS 地址，不能从页面动态输入生产地址。

**Rationale**: 当前 `app.js` 硬编码 localhost，无法区分体验和生产。小程序合法域名要求也需要固定环境配置。

## R10 — 上传策略

**Decision**: 头像和反馈附件按“获取后端上传授权 → 上传文件 → 将 file key/URL 提交业务接口”的三步流程；临时本地路径不能作为保存值。

**Rationale**: 当前账号页将 `tempFilePath` 当头像保存；关闭小程序后失效。客户端不能持有 COS 密钥。

## R11 — 测试方案

**Decision**: 继续使用 Node 内置测试，通过依赖注入或全局 `wx` stub 验证请求；页面测试以 service stub 驱动状态，不引入小程序测试框架。

**Rationale**: 现有 90+ Node 测试已经形成低成本模式，引入新框架不符合 YAGNI。

## R12 — 后端不匹配处理

**Decision**: 安全/权限/持久化差异必须阻塞；展示字段差异可由 adapter 处理；缺少页面但接口可用属于前端任务；缺少接口或接口不可安全使用属于后端阻塞。

**Rationale**: 明确区分可适配与不可适配，避免联调完成度失真。

## 已确认的后端差异摘要

- `B-001`：`PUT /me/profile` 请求 `version` 声明为整数，但 `GET /me/profile` 返回 ISO 时间字符串，前端无法构造合法乐观锁版本。
- `B-002`：`GET /auth/session` 缺少 `orgRole`、分销员组织详情、`wechatBound` 和激活信息，重新启动后无法可靠恢复组织管理员入口。
- `B-003`：客户的 service-records、binding-history、contributions、followups 子资源只校验客户存在，未见与客户详情一致的当前用户范围校验。
- `B-004`：`GET /contributions/{bill_id}` 按 bill id 查询但未携带当前用户范围到 service，存在越权读取风险。
- `B-005`：service-records 响应读取 Bill 上不确定存在的 `bill_no/title/amount/status`，可能返回大量空字段，无法支撑现有服务记录 UI。
- `B-006`：当前小程序未注册资质页面，后端也没有面向当前分销员的资质提交端点；只有管理端组织资质 API。
- `B-007`：客户编辑页面包含身份证/医保字段，但小程序客户 PATCH 仅支持 name/phone/note/familyPhone。
- `B-008`：微信新用户登录可创建 User，但当前没有对应的小程序端接口将其完整建成 Distributor；本期主链路应使用后台已创建的分销员账户。

完整影响与处理见 [contracts/page-api-matrix.md](contracts/page-api-matrix.md)。
