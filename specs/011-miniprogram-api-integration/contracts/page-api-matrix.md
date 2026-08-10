# 小程序页面—API 契约矩阵

**日期**: 2026-08-08
**范围**: `miniProgram/` 消费 `backend/` 当前 `/api/v1`；本文只记录，不授权修改后端。

## 状态定义

- **READY**：当前后端端点和字段足以进行前端接入。
- **ADAPT**：可通过纯字段/枚举/格式 adapter 安全接入。
- **FRONTEND**：后端可用，但小程序缺少页面或 service，属于本分支前端工作。
- **BLOCKED**：涉及后端字段、权限、持久化或业务语义，前端不可安全补偿。
- **DEFER**：非当前注册页面或非本期主链路，待依赖明确后实施。

## 1. 会话与入口

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 启动分流 | `GET /api/v1/app/bootstrap` | 可选 Bearer；`session`/featureFlags | ADAPT | 当前 bootstrap 的 entry/摘要为空；只用于轻启动，不替代 session 恢复 |
| 手机号密码登录 | `POST /api/v1/auth/distributor-login` | phone/password → tokens、requiresWechatBinding、distributor | READY | 当前 `auth-service` 已局部接入，迁移到统一请求层 |
| 微信快捷登录 | `POST /api/v1/auth/wechat-login` | wx code → tokens、user | READY | 仅已绑定/已建档账户作为本期完整主链路；见 B-008 |
| 首登绑定微信 | `POST /api/v1/auth/bind-wechat` | Bearer + wx code → 新 tokens | READY | 成功后必须原子替换 token 对 |
| 当前会话 | `GET /api/v1/auth/session` | user、permissions、tokenExpiresAt | BLOCKED | B-002：缺少 orgRole/Distributor/激活/绑定信息，重启后管理员入口不可可靠恢复 |
| Token 刷新 | `POST /api/v1/auth/refresh` | refreshToken → 新 token 对 | READY | 统一请求层单飞刷新 |
| 退出登录 | `POST /api/v1/auth/logout` | Bearer → data null | READY | 无论网络结果如何均清本地；未知结果需提示 |
| 微信手机号授权 | `POST /api/v1/auth/phone-bind` | getPhoneNumber code → masked phone | READY | 只使用响应脱敏值 |

## 2. 首页与个人中心

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 首页主摘要 | `GET /api/v1/workbench` | metrics.myCustomers/myBindings/myMonthlyConsumption/pendingFollowups | ADAPT | 替换 home fixtures；按 role adapter 映射 |
| 首页通知 | `GET /api/v1/workbench/notices` | notices[] | READY | 空数组显示空态 |
| 最近绑定 | `GET /api/v1/workbench/recent-bindings` | items[] | READY | 映射当前首页记录卡片 |
| 本月消费摘要 | `GET /api/v1/workbench/contribution-summary` | month/totalAmountCent/count | ADAPT | 仅当前月使用；历史月份结束边界实现需后端确认 |
| 我的页账户摘要 | `GET /api/v1/me/account-summary` | name/avatar/role/qualificationStatus/unreadNotifications | READY | 组织管理员入口仍依赖 B-002 |
| 我的页指标 | `GET /api/v1/workbench` | 同首页 metrics | READY | 与首页共用 service/cache，不复制请求 |
| 账号信息查看 | `GET /api/v1/me/profile` | 脱敏资料、editableFields、version | ADAPT | 可查看；phone raw fallback 风险需测试数据确认 |
| 账号资料保存 | `PUT /api/v1/me/profile` | name/organization/avatar/version | BLOCKED | B-001：version 请求 int、响应 ISO string，无法满足校验 |
| 头像上传授权 | `POST /api/v1/me/avatar/upload-token` | file metadata → upload info | FRONTEND | service 已接入；页面尚未接通微信文件上传与持久化，资料保存仍受 B-001 影响 |
| 退出登录按钮 | `POST /api/v1/auth/logout` | Bearer | READY | 替换 demo.resetDemoControl |

## 3. 客户与跟进

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 客户列表/搜索/筛选 | `GET /api/v1/customers` | status/keyword/cursor/pageSize → items/page | READY | 替换 summaries.customers；状态枚举 adapter |
| 客户详情 | `GET /api/v1/customers/{id}` | 脱敏信息、绑定、消费金额、counts | READY | 主详情本身包含当前用户范围校验 |
| 客户编辑 | `PATCH /api/v1/customers/{id}` | name/phone/note/familyPhone/changeReason | ADAPT | 仅接后端支持字段；身份证/医保编辑见 B-007 |
| 服务记录 | `GET /api/v1/customers/{id}/service-records` | cursor/pageSize | BLOCKED | B-003 权限 + B-005 字段可能为空；不可安全上线 |
| 消费记录 | `GET /api/v1/customers/{id}/contributions` | amountCent/status/occurredAt | BLOCKED | B-003：缺少与客户详情一致的范围校验 |
| 跟进列表 | `GET /api/v1/customers/{id}/followups` | cursor/pageSize | BLOCKED | B-003：缺少客户范围校验 |
| 新增跟进 | `POST /api/v1/customers/{id}/followups` | method/result/content/reminderAt | BLOCKED | B-003：只校验客户存在；前端防重不能替代服务端授权 |
| 保存跟进草稿 | `POST /api/v1/customers/{id}/followup-drafts` | method/content | BLOCKED | 同 B-003 |
| 更新跟进 | `PUT /api/v1/followups/{id}` | version + fields | BLOCKED | 当前路由仅校验记录存在，未见所有权校验 |
| 客户分析 | `GET /api/v1/customer-analysis` | period → overview/trend/sourceDistribution | READY | 前端适配 ECharts 数据 |

## 4. 客户绑定

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 可选分销员 | `GET /api/v1/promoters/selectable` | keyword/cursor/limit | READY | 替换当前固定 owner |
| 记录客户授权 | `POST /api/v1/consents` | agreementId/scene/confirmed/evidence | READY | submit binding 前取得 consentRecordId |
| 提交绑定 | `POST /api/v1/binding-requests` | Idempotency-Key；promoterId/customerInfo/consentRecordId | READY | 与当前表单字段基本匹配 |
| 绑定记录 | `GET /api/v1/binding-requests` | status/role/cursor/limit/keyword/sort | READY | 映射 bound/matching/processing 等 UI 状态 |
| 绑定详情/结果 | `GET /api/v1/binding-requests/{id}` | customerInfo/events/status/retry | BLOCKED | 路由未将当前用户传入 service 做范围校验，需后端确认 |
| 绑定汇总 | `GET /api/v1/binding-summary` | counts | READY | 替换固定 summary |
| 失败重试 | `POST /api/v1/binding-requests/{id}/retry` | Idempotency-Key | BLOCKED | 与详情相同的范围问题，且属于副作用 |
| 补正客户信息 | `PUT /api/v1/binding-requests/{id}/customer-info` | Idempotency-Key + version | BLOCKED | 路由未见当前用户范围传递；先不开放 |

## 5. 消费与绩效

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 消费概览 | `GET /api/v1/contributions/overview` | month → monthlyAmountCent/totalAmountCent/growthRate | READY | 009 最新口径 |
| 消费趋势 | `GET /api/v1/contributions/trend` | period → categories/values | READY | values 为整数分 |
| 消费明细列表 | `GET /api/v1/contributions` | month/status/cursor/pageSize | READY | 替换旧 category/settled Mock |
| 消费明细详情 | `GET /api/v1/contributions/{bill_id}` | Bill detail | BLOCKED | B-004：未按当前用户/分销员限制 bill |
| 个人绩效 | `GET /api/v1/my/performance/commission` | month → estimate/confirmed | READY | 现有 service 迁移到统一请求层 |
| 组织消费 | `GET /api/v1/org/performance` | month → summary/members/children | READY | 仅组织管理员；真实入口恢复受 B-002 影响 |
| 组织绩效 | `GET /api/v1/org/performance/commission` | month → estimate/confirmed | READY | 同上 |

## 6. 隐私、推广、反馈、通知与资质

| 页面/动作 | Endpoint | 请求/响应重点 | 状态 | 说明 |
|---|---|---|---|---|
| 最新协议 | `GET /api/v1/agreements/latest` | items[] | READY | 替换登录页演示协议文本入口 |
| 协议详情 | `GET /api/v1/agreements/{id}` | contentUrl 等 | READY | 页面展示方式在前端计划中确定 |
| 同意记录 | `POST /api/v1/consents` | scene/evidence | READY | 登录后场景；匿名登录前同意无法调用需仅本地勾选，登录后补记录 |
| 我的授权 | `GET /api/v1/me/consents` | items[] | READY | 隐私页 |
| 隐私设置 | `PUT /api/v1/me/privacy-settings` | maskSensitive/personalized/version | ADAPT | service 已接入；页面暂以受控提示阻止提交，待联调确认 version 来源与回读 |
| 推广码 | `GET /api/v1/promotion-code` | refToken/qrImageUrl/status | READY | 后端可能返回空 qrImageUrl，前端显示受控空态 |
| 刷新推广码 | `POST /api/v1/promotion-code/refresh` | 新 code | READY | 前端 pending + 幂等 key（后端当前未强制） |
| 推广统计/海报 | `GET .../statistics`, `GET .../poster` | counts/URL/share | READY | 真实 URL 才可保存/分享 |
| 反馈上传授权 | `POST /api/v1/feedback-files/upload-token` | file metadata | FRONTEND | service 已接入；页面暂禁用截图上传，文字反馈可提交 |
| 提交/查看反馈 | `POST/GET /api/v1/feedbacks` | type/content/images/page | ADAPT | 文字提交已接入；图片上传和反馈历史页面待补齐 |
| 通知列表/已读 | `GET /api/v1/notifications`, `POST .../{id}/read` | cursor/unread | READY | 已注册正式通知页面，支持列表空态、错误态和已读操作 |
| 资质状态/提交 | 无面向当前用户端点 | — | BLOCKED/DEFER | B-006：当前页面也未注册；不在前端伪造 |

## 后端差异登记

| ID | 严重度 | 差异 | 前端影响 | 前端处理 |
|---|---|---|---|---|
| B-001 | High | ProfileUpdateRequest.version=int，GET profile version=ISO string | 账号资料无法合法保存 | 查看可接；保存动作阻塞并提交后端差异 |
| B-002 | High | auth/session 缺 orgRole、Distributor/组织、wechatBound、激活状态 | 冷启动后入口与权限恢复不完整 | 登录当次可用；重启组织管理员能力阻塞，不本地伪造 |
| B-003 | Critical | 多个 customer 子资源/写操作未见客户归属范围校验 | 可能越权读写客户数据 | 对应页签/写操作不上线，等待后端确认或修复 |
| B-004 | Critical | contribution detail 未按当前用户限制 bill | 可枚举 bill id 越权读取 | 明细列表可接；详情点击阻塞 |
| B-005 | High | service-records 使用不确定的 Bill 展示字段 | 页面可能获得全空服务记录 | 服务记录页签阻塞，不能用 Mock 补齐 |
| B-006 | Medium | 无当前用户资质端点且当前无注册页面 | 资质功能无法联调 | 延期并保留明确占位，不改后端 |
| B-007 | Medium | 客户 PATCH 不支持 idCard/medicalAccount，但页面有编辑入口 | 部分字段无法保存 | 只开放后端支持字段；不发送无效字段 |
| B-008 | Medium | wx 新用户只有 User，缺少完整 Distributor onboarding | 新微信账号无法完成业务账户闭环 | 本期使用后台已建分销员账户；新用户展示受控引导 |

## 契约冻结规则

1. READY/ADAPT 项才可生成实施任务。
2. BLOCKED 项可以生成“受控禁用/错误展示/后端差异文档”任务，不生成后端修复任务。
3. 后端负责人确认并提供可测试响应后，更新本矩阵状态再解除前端功能门禁。
4. 任一实际响应字段变化必须先更新本矩阵或其来源规格，再修改 adapter。
