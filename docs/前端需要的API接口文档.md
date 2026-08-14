# 北京儒泰小程序 API 接口文档

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | 北京儒泰小程序 API 接口文档 |
| 文档版本 | v1.0-draft |
| 接口版本 | v1 |
| 适用范围 | 北京儒泰微信小程序、北京儒泰业务服务端、哈尔滨儒泰对接服务 |
| 文档状态 | 接口评审稿 |
| 更新时间 | 2026-07-29 |

本文档根据现有小程序页面、页面状态、业务流程和 PRD 整理。接口地址、字段命名和返回结构可作为北京侧后端开发基线；哈尔滨儒泰提供的接口字段仍需双方联调确认。

---

## 2. 系统边界

### 2.1 小程序直接调用

小程序只调用北京儒泰业务服务端，不直接调用哈尔滨儒泰服务端。

```text
北京儒泰小程序
    -> 北京儒泰 API
        -> 用户、资质、推广、客户、绑定、跟进、贡献等业务模块
        -> 哈尔滨儒泰接口适配模块
            -> bindBjUser
            -> getBindUser
            -> getUserBill
            -> getAllUsersBill
```

### 2.2 接口前缀

```text
生产环境：https://api.example.com/api/v1
测试环境：https://test-api.example.com/api/v1
```

域名仅为占位示例，上线前替换为完成微信后台配置和备案的正式 HTTPS 域名。

---

## 3. 公共协议

### 3.1 请求头

| 请求头 | 必填 | 示例 | 含义 |
|---|---:|---|---|
| `Authorization` | 是 | `Bearer eyJ...` | 登录成功后获得的访问令牌；登录、刷新令牌接口除外 |
| `Content-Type` | 是 | `application/json` | JSON 请求使用该值 |
| `X-Request-Id` | 写接口必填 | `01J...` | 客户端生成的唯一请求号，用于链路追踪 |
| `Idempotency-Key` | 关键写接口必填 | `bind_01J...` | 幂等键，防止重复提交；绑定、资质提交、反馈提交必须传 |
| `X-Client-Version` | 建议 | `1.0.0` | 小程序版本号 |
| `X-Platform` | 建议 | `wechat-mini-program` | 客户端平台 |

### 3.2 成功响应

所有接口统一使用以下外层结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "requestId": "01J2ABCDEF",
  "serverTime": "2026-07-29T10:30:00+08:00"
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `code` | integer | `0` 表示成功，非 `0` 表示业务或系统错误 |
| `message` | string | 用户安全的结果说明，不返回堆栈或敏感信息 |
| `data` | object/array/null | 业务数据 |
| `requestId` | string | 服务端链路追踪 ID |
| `serverTime` | string | 服务端响应时间，ISO 8601 格式 |

### 3.3 错误响应

```json
{
  "code": 400201,
  "message": "该客户已存在有效绑定关系",
  "data": {
    "errorType": "CUSTOMER_ALREADY_BOUND",
    "retryable": false
  },
  "requestId": "01J2ABCDEF",
  "serverTime": "2026-07-29T10:30:00+08:00"
}
```

### 3.4 常用错误码

| HTTP 状态 | 业务码 | 含义 |
|---:|---:|---|
| 400 | `400001` | 请求参数错误 |
| 400 | `400002` | 幂等键缺失或格式错误 |
| 401 | `401001` | 未登录或访问令牌失效 |
| 403 | `403001` | 当前角色无权访问 |
| 403 | `403002` | 账号未激活 |
| 403 | `403003` | 资质状态不允许执行该操作 |
| 404 | `404001` | 数据不存在 |
| 409 | `409001` | 数据版本冲突 |
| 409 | `409201` | 客户已绑定 |
| 409 | `409202` | 绑定申请正在处理中 |
| 422 | `422001` | 业务校验未通过 |
| 429 | `429001` | 请求过于频繁 |
| 500 | `500001` | 服务内部异常 |
| 502 | `502001` | 儒泰接口调用失败 |
| 503 | `503001` | 服务暂时不可用 |

### 3.5 分页规则

列表接口统一使用游标分页：

| 参数 | 类型 | 必填 | 默认值 | 含义 |
|---|---|---:|---|---|
| `cursor` | string | 否 | 空 | 上一页返回的 `nextCursor` |
| `pageSize` | integer | 否 | `20` | 每页数量，范围 `1-100` |

分页返回：

```json
{
  "items": [],
  "nextCursor": "eyJpZCI6MTAwfQ==",
  "hasMore": true,
  "total": 36
}
```

`total` 仅在页面确实需要总数时返回，避免大数据量统计影响接口性能。

### 3.6 数据格式

| 数据类型 | 约定 |
|---|---|
| 时间 | ISO 8601，例如 `2026-07-29T10:30:00+08:00` |
| 日期 | `YYYY-MM-DD` |
| 月份 | `YYYY-MM` |
| 金额 | 服务端内部使用“分”为单位的整数，例如 `12800` 表示 128 元 |
| 贡献值 | JSON 中使用字符串，例如 `"1200.00"`，避免浮点精度问题 |
| 手机号 | 列表和详情默认返回脱敏值，例如 `138****1028` |
| 身份证号 | 默认返回脱敏值，例如 `1101********1234` |
| 枚举 | 使用稳定的英文小写值，中文只用于展示字段 |

---

## 4. 公共业务状态

### 4.1 账号状态

| 状态 | 含义 |
|---|---|
| `active` | 已激活，可按角色和资质使用功能 |
| `inactive` | 待激活 |
| `disabled` | 已禁用 |

### 4.2 资质状态

| 状态 | 含义 |
|---|---|
| `draft` | 草稿 |
| `reviewing` | 审核中 |
| `approved` | 审核通过 |
| `rejected` | 审核驳回 |
| `expiring` | 即将到期 |
| `expired` | 已过期 |

### 4.3 绑定状态

| 状态 | 前端文案 | 含义 |
|---|---|---|
| `pending_match` | 待匹配 | 已提交北京侧，等待调用或等待儒泰匹配 |
| `matching` | 匹配中 | 儒泰正在匹配 |
| `bound` | 已绑定 | 已取得儒泰用户 ID 并建立有效归属 |
| `no_consume` | 已绑定无消费 | 已绑定，但暂无账单 |
| `retrying` | 处理中 | 外部接口异常，系统自动重试 |
| `manual_review` | 待人工处理 | 多用户命中或自动重试失败 |
| `abnormal` | 异常 | 无法自动处理 |
| `unbound` | 已解绑 | 管理后台解除绑定 |
| `transferred` | 已转移 | 已转移到其他拓展人 |

### 4.4 贡献状态

| 状态 | 含义 |
|---|---|
| `pending` | 待确认或待结算 |
| `confirmed` | 已确认 |
| `settled` | 已结算 |
| `reversed` | 已冲正 |
| `cancelled` | 已取消 |

---

## 5. 公共数据对象

后续接口通过对象名称引用本节字段，避免多个接口重复定义后产生不一致。

### 5.1 `UserSession`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `userId` | string | 是 | 北京侧用户唯一 ID |
| `accountIdMasked` | string | 是 | 脱敏账号编号 |
| `identityType` | enum | 是 | `promoter`、`doctor` |
| `identityLabel` | string | 是 | 角色展示名称 |
| `activationStatus` | enum | 是 | 账号状态 |
| `qualificationStatus` | enum | 是 | 当前资质状态 |
| `profileCompleted` | boolean | 是 | 是否完成首次资料补全 |
| `name` | string | 是 | 用户姓名 |
| `phoneMasked` | string | 是 | 脱敏手机号 |
| `organization` | string | 是 | 所属机构 |
| `avatarUrl` | string | 否 | 头像地址 |
| `capabilities` | object | 是 | 服务端计算出的功能权限 |

`capabilities` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `qualification` | boolean | 是否可访问资质功能 |
| `promotion` | boolean | 是否可使用推广码 |
| `customerBinding` | boolean | 是否可绑定客户 |
| `customerAnalysis` | boolean | 是否可查看客户分析 |
| `contribution` | boolean | 是否可查看贡献 |
| `teamContribution` | boolean | 是否可查看团队贡献 |

### 5.2 `Qualification`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `qualificationId` | string | 是 | 资质记录 ID |
| `legalEntity` | string | 是 | 法人主体名称 |
| `qualificationType` | enum | 是 | `business_license`、`legal_person_certificate`、`medical_institution_license` |
| `qualificationTypeLabel` | string | 是 | 资质类型中文名称 |
| `creditCodeMasked` | string | 是 | 脱敏统一社会信用代码 |
| `expiresAt` | string | 是 | 有效期截止日期 |
| `status` | enum | 是 | 资质状态 |
| `statusLabel` | string | 是 | 状态中文文案 |
| `submittedAt` | string/null | 是 | 最近提交时间 |
| `approvedAt` | string/null | 是 | 审核通过时间 |
| `rejectedReason` | string/null | 是 | 驳回原因 |
| `remainingDays` | integer/null | 否 | 剩余有效天数 |
| `file` | object | 是 | 当前资质文件 |
| `version` | integer | 是 | 乐观锁版本号 |

`file` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `fileId` | string | 文件 ID |
| `fileName` | string | 原始文件名 |
| `fileType` | string | `pdf`、`jpg`、`jpeg`、`png` |
| `fileSize` | integer | 文件字节数 |
| `previewUrl` | string | 短期有效的预览地址 |

### 5.3 `BindingRequest`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `bindingRequestId` | string | 是 | 绑定申请 ID |
| `customerId` | string/null | 是 | 北京侧客户 ID |
| `rutaiUserIdMasked` | string/null | 是 | 脱敏儒泰用户 ID |
| `customerName` | string | 是 | 客户姓名 |
| `phoneMasked` | string | 是 | 脱敏手机号 |
| `idCardMasked` | string | 是 | 脱敏身份证号 |
| `promoterId` | string | 是 | 归属拓展人 ID |
| `promoterName` | string | 是 | 归属拓展人姓名 |
| `sourceType` | enum | 是 | `manual`、`promotion_code`、`rutai_marked` |
| `status` | enum | 是 | 绑定状态 |
| `statusLabel` | string | 是 | 状态展示文案 |
| `matchLevel` | enum/null | 是 | `strong`、`medium`、`weak` |
| `retryCount` | integer | 是 | 已重试次数 |
| `nextRetryAt` | string/null | 是 | 下次自动重试时间 |
| `failureReason` | string/null | 是 | 用户安全的失败原因 |
| `submittedBy` | object | 是 | 提交人摘要 |
| `submittedAt` | string | 是 | 提交时间 |
| `boundAt` | string/null | 是 | 成功绑定时间 |
| `updatedAt` | string | 是 | 最后更新时间 |

### 5.4 `CustomerSummary`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `customerId` | string | 是 | 北京侧客户 ID |
| `name` | string | 是 | 客户姓名 |
| `phoneMasked` | string | 是 | 脱敏手机号 |
| `avatarUrl` | string/null | 是 | 头像地址 |
| `bindingStatus` | enum | 是 | 当前绑定状态 |
| `bindingStatusLabel` | string | 是 | 状态中文文案 |
| `followupStatus` | enum | 是 | `none`、`pending`、`completed` |
| `latestServiceText` | string/null | 是 | 最近服务摘要 |
| `nextFollowupAt` | string/null | 是 | 下次跟进时间 |
| `ownerId` | string | 是 | 当前归属拓展人 ID |
| `ownerName` | string | 是 | 当前归属拓展人姓名 |
| `updatedAt` | string | 是 | 最后更新时间 |

### 5.5 `CustomerDetail`

包含 `CustomerSummary` 全部字段，并增加：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `idCardMasked` | string | 是 | 脱敏身份证号 |
| `medicalAccountMasked` | string | 是 | 脱敏医保账户 |
| `familyPhoneMasked` | string | 是 | 脱敏家属手机号 |
| `rutaiUserIdMasked` | string/null | 是 | 脱敏儒泰用户 ID |
| `boundAt` | string/null | 是 | 绑定时间 |
| `note` | string | 是 | 客户备注 |
| `serviceCount` | integer | 是 | 服务记录数量 |
| `followupCount` | integer | 是 | 跟进记录数量 |
| `monthlyContribution` | string | 是 | 本月贡献值 |
| `totalContribution` | string | 是 | 累计贡献值 |
| `editableFields` | string[] | 是 | 当前用户允许修改的字段 |
| `version` | integer | 是 | 乐观锁版本号 |

### 5.6 `FollowupRecord`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `followupId` | string | 是 | 跟进记录 ID |
| `customerId` | string | 是 | 客户 ID |
| `method` | enum | 是 | `phone`、`wechat`、`in_person`、`other` |
| `methodLabel` | string | 是 | 跟进方式中文名称 |
| `result` | enum | 是 | `connected`、`waiting`、`unanswered` |
| `resultLabel` | string | 是 | 跟进结果中文名称 |
| `content` | string | 是 | 跟进内容 |
| `reminderEnabled` | boolean | 是 | 是否设置下次提醒 |
| `reminderAt` | string/null | 是 | 下次提醒时间 |
| `reminderStatus` | enum | 是 | `none`、`pending`、`completed`、`cancelled` |
| `createdBy` | object | 是 | 创建人摘要 |
| `createdAt` | string | 是 | 创建时间 |
| `updatedAt` | string | 是 | 更新时间 |
| `version` | integer | 是 | 乐观锁版本号 |

### 5.7 `ContributionRecord`

| 字段 | 类型 | 必返 | 含义 |
|---|---|---:|---|
| `contributionId` | string | 是 | 贡献记录 ID |
| `customerId` | string | 是 | 客户 ID |
| `customerName` | string | 是 | 客户脱敏展示名称 |
| `phoneMasked` | string | 是 | 脱敏手机号 |
| `category` | enum | 是 | `binding`、`service`、`followup`、`bill`、`adjustment` |
| `title` | string | 是 | 贡献事件名称 |
| `points` | string | 是 | 贡献值，保留两位小数 |
| `status` | enum | 是 | 贡献状态 |
| `statusLabel` | string | 是 | 状态中文文案 |
| `sourceType` | string | 是 | 原始业务来源类型 |
| `sourceId` | string | 是 | 原始业务记录 ID |
| `ruleVersion` | string | 是 | 计算时使用的规则版本 |
| `occurredAt` | string | 是 | 贡献产生时间 |
| `settledAt` | string/null | 是 | 结算时间 |
| `reversedRecordId` | string/null | 否 | 冲正关联记录 ID |

---

## 6. 接口总览

### 6.1 P0：一期核心接口

| 模块 | 方法 | 路径 | 功能 |
|---|---|---|---|
| 登录 | POST | `/auth/wechat-login` | 微信登录 |
| 登录 | POST | `/auth/phone-bind` | 绑定微信手机号 |
| 登录 | GET | `/auth/session` | 获取当前会话和页面入口 |
| 登录 | POST | `/auth/refresh` | 刷新访问令牌 |
| 登录 | POST | `/auth/logout` | 退出登录 |
| 初始化 | GET | `/app/bootstrap` | 获取会话、权限、首页基础数据 |
| 资料 | GET | `/me/profile` | 获取个人资料 |
| 资料 | PUT | `/me/profile` | 更新个人资料 |
| 资料 | POST | `/me/avatar/upload-token` | 获取头像上传凭证 |
| 资料 | GET | `/me/account-summary` | 获取账号状态摘要 |
| 资质 | GET | `/qualifications/current` | 获取当前资质 |
| 资质 | POST | `/qualification-files/upload-token` | 获取资质文件上传凭证 |
| 资质 | POST | `/qualifications` | 提交资质 |
| 资质 | PUT | `/qualifications/{id}` | 更新或重新提交资质 |
| 资质 | GET | `/qualifications/{id}/reviews` | 获取资质审核记录 |
| 推广 | GET | `/promotion-code` | 获取个人推广码 |
| 工作台 | GET | `/workbench` | 获取角色工作台数据 |
| 绑定 | GET | `/promoters/selectable` | 获取可选择拓展人 |
| 绑定 | POST | `/binding-requests` | 提交客户绑定 |
| 绑定 | GET | `/binding-requests` | 获取绑定记录 |
| 绑定 | GET | `/binding-requests/{id}` | 获取绑定结果 |
| 绑定 | GET | `/binding-summary` | 获取绑定状态汇总 |
| 客户 | GET | `/customers` | 获取客户列表 |
| 客户 | GET | `/customers/{id}` | 获取客户详情 |
| 客户 | PATCH | `/customers/{id}` | 修改客户资料 |
| 客户 | GET | `/customers/{id}/service-records` | 获取客户服务记录 |
| 客户 | GET | `/customers/{id}/binding-history` | 获取客户绑定历史 |
| 客户 | GET | `/customers/{id}/contributions` | 获取客户贡献记录 |
| 跟进 | GET | `/customers/{id}/followups` | 获取客户跟进记录 |
| 跟进 | POST | `/customers/{id}/followups` | 新增跟进记录 |
| 贡献 | GET | `/contributions/overview` | 获取贡献汇总 |
| 贡献 | GET | `/contributions/trend` | 获取贡献趋势 |
| 贡献 | GET | `/contributions/composition` | 获取贡献构成 |
| 贡献 | GET | `/contributions` | 获取贡献明细 |
| 贡献 | GET | `/contributions/{id}` | 获取单条贡献详情 |
| 合规 | GET | `/agreements/latest` | 获取最新协议 |
| 合规 | GET | `/agreements/{id}` | 获取协议正文 |
| 合规 | POST | `/consents` | 保存授权记录 |
| 合规 | GET | `/me/consents` | 获取授权状态 |
| 合规 | PUT | `/me/privacy-settings` | 更新隐私设置 |
| 反馈 | POST | `/feedback-files/upload-token` | 获取反馈截图上传凭证 |
| 反馈 | POST | `/feedbacks` | 提交问题反馈 |

### 6.2 P1/P2：后续接口

| 优先级 | 模块 | 方法 | 路径 | 功能 |
|---|---|---|---|---|
| P1 | 工作台 | GET | `/workbench/notices` | 独立刷新工作台通知 |
| P1 | 工作台 | GET | `/workbench/recent-bindings` | 独立刷新近期绑定 |
| P1 | 工作台 | GET | `/workbench/contribution-summary` | 独立刷新贡献摘要 |
| P1 | 资质 | POST | `/qualifications/draft` | 保存资质草稿 |
| P1 | 推广 | POST | `/promotion-code/refresh` | 刷新已失效推广码 |
| P1 | 推广 | GET | `/promotion-code/poster` | 获取推广海报 |
| P1 | 推广 | GET | `/promotion-code/statistics` | 获取推广统计 |
| P1 | 绑定 | POST | `/binding-requests/{id}/retry` | 手动重试绑定 |
| P1 | 绑定 | PUT | `/binding-requests/{id}/customer-info` | 修正待匹配资料 |
| P1 | 客户 | GET | `/customer-analysis` | 获取客户分析 |
| P1 | 跟进 | POST | `/customers/{id}/followup-drafts` | 保存跟进草稿 |
| P1 | 跟进 | PUT | `/followups/{id}` | 修改跟进记录 |
| P1 | 跟进 | PUT | `/followups/{id}/reminder` | 修改提醒 |
| P1 | 跟进 | POST | `/followups/{id}/complete` | 完成提醒 |
| P1 | 贡献 | GET | `/team/contributions` | 获取团队贡献 |
| P1 | 贡献 | GET | `/team/contributions/{promoterId}` | 团队贡献下钻 |
| P1 | 通知 | GET | `/notifications` | 获取消息通知 |
| P1 | 通知 | POST | `/notifications/{id}/read` | 标记消息已读 |
| P1 | 反馈 | GET | `/feedbacks` | 获取反馈记录 |
| P2 | 内容 | GET | `/articles` | 获取科普文章 |
| P2 | 内容 | GET | `/articles/{id}` | 获取文章详情 |

---

## 7. 登录与初始化接口

### 7.1 微信登录

```http
POST /api/v1/auth/wechat-login
```

**功能**：接收 `wx.login` 返回的临时 code，在服务端换取微信身份，创建或识别北京侧账号。

**是否鉴权**：否。

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 含义 |
|---|---|---|---:|---|
| `code` | body | string | 是 | `wx.login` 返回的临时登录凭证，只能使用一次 |
| `clientVersion` | body | string | 否 | 小程序版本 |
| `deviceId` | body | string | 否 | 客户端匿名设备标识，不使用硬件敏感标识 |

**请求示例**

```json
{
  "code": "0a3Xxxxxxxxx",
  "clientVersion": "1.0.0",
  "deviceId": "device_01J2ABC"
}
```

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `accessToken` | string | 访问令牌 |
| `expiresIn` | integer | 访问令牌有效秒数 |
| `refreshToken` | string | 刷新令牌 |
| `refreshExpiresIn` | integer | 刷新令牌有效秒数 |
| `isNewUser` | boolean | 是否首次创建账号 |
| `phoneBindingRequired` | boolean | 是否必须授权手机号 |
| `session` | `UserSession` | 当前用户会话 |
| `entry` | object | 登录后推荐进入的页面 |

`entry`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `type` | enum | `reLaunch`、`switchTab` |
| `path` | string | 小程序页面路径 |

**返回示例**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "eyJhbGciOi...",
    "expiresIn": 7200,
    "refreshToken": "rt_01J2ABC",
    "refreshExpiresIn": 2592000,
    "isNewUser": false,
    "phoneBindingRequired": false,
    "session": {
      "userId": "u_10001",
      "accountIdMasked": "RT****4826",
      "identityType": "promoter",
      "identityLabel": "市场拓展人",
      "activationStatus": "active",
      "qualificationStatus": "approved",
      "profileCompleted": true,
      "name": "张小明",
      "phoneMasked": "138****1028",
      "organization": "北京儒泰服务有限公司",
      "avatarUrl": "https://cdn.example.com/avatar/a1.png",
      "capabilities": {
        "qualification": true,
        "promotion": true,
        "customerBinding": true,
        "customerAnalysis": true,
        "contribution": true,
        "teamContribution": true
      }
    },
    "entry": {
      "type": "switchTab",
      "path": "/pages/home/index"
    }
  },
  "requestId": "01J2ABCDEF",
  "serverTime": "2026-07-29T10:30:00+08:00"
}
```

### 7.2 绑定微信手机号

```http
POST /api/v1/auth/phone-bind
```

**功能**：使用微信手机号授权组件返回的 code 获取并绑定手机号。

**请求参数**

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `phoneCode` | string | 是 | `getPhoneNumber` 事件返回的动态 code |

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `phoneMasked` | string | 绑定后的脱敏手机号 |
| `phoneAuthorized` | boolean | 是否完成手机号授权 |
| `session` | `UserSession` | 更新后的会话 |

### 7.3 获取当前会话

```http
GET /api/v1/auth/session
```

**功能**：页面进入、令牌恢复或用户状态可能发生变化时，获取服务端确认的最新身份和入口。

**请求参数**：无。

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `session` | `UserSession` | 当前会话和权限 |
| `entry` | object | 当前状态推荐进入的页面 |
| `tokenExpiresAt` | string | 当前访问令牌过期时间 |

该接口只返回会话；需要同时初始化首页数据时优先使用 `/app/bootstrap`。

### 7.4 刷新访问令牌

```http
POST /api/v1/auth/refresh
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `refreshToken` | string | 是 | 登录接口返回的刷新令牌 |

返回新的 `accessToken`、`expiresIn`，服务端可同时轮换 `refreshToken`。

### 7.5 退出登录

```http
POST /api/v1/auth/logout
```

无业务参数。服务端使当前访问令牌和刷新令牌失效。

### 7.6 应用初始化

```http
GET /api/v1/app/bootstrap
```

**功能**：小程序启动或回到前台时，一次获取当前会话、权限、未读数量和首页必要摘要，减少并发请求。

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `session` | `UserSession` | 当前会话 |
| `entry` | object | 当前状态推荐入口 |
| `unreadNotificationCount` | integer | 未读消息数量 |
| `privacyAgreementVersion` | string | 当前最新隐私协议版本 |
| `workbenchSummary` | object/null | 首页摘要，未完成登录流程时可为空 |
| `featureFlags` | object | 服务端功能开关 |

---

## 8. 个人资料接口

### 8.1 获取个人资料

```http
GET /api/v1/me/profile
```

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `userId` | string | 用户 ID |
| `name` | string | 姓名 |
| `phoneMasked` | string | 脱敏手机号 |
| `organization` | string | 所属机构 |
| `avatarUrl` | string/null | 头像 |
| `identityType` | enum | 身份类型 |
| `identityLabel` | string | 身份展示名称 |
| `activationStatus` | enum | 账号状态 |
| `qualificationStatus` | enum | 资质状态 |
| `wechatBound` | boolean | 是否绑定微信 |
| `editableFields` | string[] | 允许当前用户修改的字段 |
| `version` | integer | 数据版本 |

### 8.2 更新个人资料

```http
PUT /api/v1/me/profile
```

| 参数 | 类型 | 必填 | 限制 | 含义 |
|---|---|---:|---|---|
| `name` | string | 是 | 1-20 字符 | 真实姓名 |
| `organization` | string | 是 | 1-100 字符 | 所属机构 |
| `avatarFileId` | string | 否 | 已完成上传 | 新头像文件 ID |
| `version` | integer | 是 | 大于 0 | 当前数据版本，防止覆盖他人修改 |

返回更新后的个人资料对象。

### 8.3 获取头像上传凭证

```http
POST /api/v1/me/avatar/upload-token
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `fileName` | string | 是 | 文件名 |
| `contentType` | string | 是 | `image/jpeg` 或 `image/png` |
| `fileSize` | integer | 是 | 文件字节数 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `fileId` | string | 待上传文件 ID |
| `uploadUrl` | string | 短期有效上传地址 |
| `headers` | object | 上传时需要携带的请求头 |
| `expiresAt` | string | 上传凭证过期时间 |

### 8.4 获取账号摘要

```http
GET /api/v1/me/account-summary
```

**功能**：为“我的”和“账号信息”页面提供轻量状态数据，不返回完整资料。

**请求参数**：无。

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `accountIdMasked` | string | 脱敏账号编号 |
| `identityType` | enum | `promoter`、`doctor` |
| `identityLabel` | string | 身份中文名称 |
| `activationStatus` | enum | 账号状态 |
| `qualificationStatus` | enum | 资质状态 |
| `qualificationStatusLabel` | string | 资质状态文案 |
| `wechatBound` | boolean | 是否绑定微信 |
| `phoneAuthorized` | boolean | 是否授权手机号 |
| `phoneMasked` | string | 脱敏手机号 |
| `unreadNotificationCount` | integer | 未读消息数量 |

---

## 9. 工作台接口

### 9.1 获取角色工作台

```http
GET /api/v1/workbench
```

**功能**：根据医生、拓展人及资质状态返回不同首页内容。

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `workbenchType` | enum | `promoter`、`doctor`、`qualification_pending` |
| `greeting` | string | 问候文案 |
| `updatedAt` | string | 数据更新时间 |
| `primaryAction` | object | 当前角色主操作 |
| `metrics` | array | 首页指标 |
| `recentBindings` | `BindingRequest[]` | 医生近期绑定 |
| `notices` | array | 审核、到期、异常通知 |

`metrics[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | string | 指标标识 |
| `label` | string | 指标名称 |
| `value` | string | 已格式化展示值 |
| `target` | string/null | 点击跳转页面 |

### 9.2 获取工作台通知

```http
GET /api/v1/workbench/notices
```

**功能**：在不刷新整个工作台时独立更新审核、资质到期、绑定异常等通知。

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `limit` | integer | 否 | 返回数量，默认 5，最大 20 |

返回项：

| 字段 | 类型 | 含义 |
|---|---|---|
| `noticeId` | string | 通知 ID |
| `category` | enum | `qualification`、`binding`、`system` |
| `title` | string | 标题 |
| `summary` | string | 摘要 |
| `target` | string/null | 目标页面 |
| `createdAt` | string | 创建时间 |

### 9.3 获取近期绑定

```http
GET /api/v1/workbench/recent-bindings
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `limit` | integer | 否 | 返回数量，默认 5，最大 20 |

返回 `BindingRequest[]`，仅包含当前用户有权查看的记录。

### 9.4 获取工作台贡献摘要

```http
GET /api/v1/workbench/contribution-summary
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `month` | string | 否 | 月份，默认当前月 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `monthlyPoints` | string | 本月个人贡献 |
| `totalPoints` | string | 个人累计贡献 |
| `teamMonthlyPoints` | string/null | 团队本月贡献，无权限时为空 |
| `directMemberCount` | integer/null | 直属成员数 |
| `pendingCount` | integer | 待处理贡献数量 |
| `updatedAt` | string | 数据更新时间 |

---

## 10. 资质接口

### 10.1 获取当前资质

```http
GET /api/v1/qualifications/current
```

返回 `Qualification`；没有资质记录时返回：

```json
{
  "qualification": null,
  "canSubmit": true
}
```

### 10.2 获取资质文件上传凭证

```http
POST /api/v1/qualification-files/upload-token
```

| 参数 | 类型 | 必填 | 限制 | 含义 |
|---|---|---:|---|---|
| `fileName` | string | 是 | 含扩展名 | 原始文件名 |
| `contentType` | string | 是 | PDF/JPG/PNG | 文件 MIME 类型 |
| `fileSize` | integer | 是 | 不超过 10MB | 文件字节数 |
| `sha256` | string | 建议 | 64 位十六进制 | 文件摘要，用于完整性校验 |

返回 `fileId`、`uploadUrl`、`headers`、`expiresAt`。

### 10.3 首次提交资质

```http
POST /api/v1/qualifications
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `legalEntity` | string | 是 | 法人主体 |
| `qualificationType` | enum | 是 | 资质类型 |
| `creditCode` | string | 是 | 18 位统一社会信用代码 |
| `expiresAt` | string | 是 | 有效期截止日期 |
| `fileId` | string | 是 | 已上传完成的文件 ID |
| `truthConfirmed` | boolean | 是 | 是否确认资料真实有效，必须为 `true` |

返回新建的 `Qualification`，初始状态为 `reviewing`。

### 10.4 更新或重新提交资质

```http
PUT /api/v1/qualifications/{qualificationId}
```

请求参数与首次提交一致，额外增加：

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `version` | integer | 是 | 当前资质版本 |

仅 `rejected`、`approved`、`expiring`、`expired` 状态可根据业务规则更新；`reviewing` 状态默认禁止重复提交。

### 10.5 获取审核记录

```http
GET /api/v1/qualifications/{qualificationId}/reviews
```

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `reviewId` | string | 审核记录 ID |
| `action` | enum | `submitted`、`approved`、`rejected` |
| `comment` | string/null | 审核意见 |
| `operatorName` | string | 审核人脱敏名称 |
| `createdAt` | string | 操作时间 |

### 10.6 保存资质草稿

```http
POST /api/v1/qualifications/draft
```

**功能**：跨设备保存未提交的资质资料。仅保存在当前设备时可继续使用小程序本地草稿，无需调用该接口。

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `legalEntity` | string | 否 | 法人主体 |
| `qualificationType` | enum | 否 | 资质类型 |
| `creditCode` | string | 否 | 统一社会信用代码 |
| `expiresAt` | string | 否 | 有效期 |
| `fileId` | string | 否 | 已上传文件 ID |

返回 `draftId`、`savedAt` 和服务端保存后的草稿内容。草稿不得触发审核或改变用户资质状态。

---

## 11. 推广码接口

### 11.1 获取个人推广码

```http
GET /api/v1/promotion-code
```

**权限**：账号已激活且资质为 `approved` 或 `expiring`。

**返回 `data`**

| 字段 | 类型 | 含义 |
|---|---|---|
| `promotionCodeId` | string | 推广码记录 ID |
| `status` | enum | `available`、`disabled`、`expired` |
| `statusLabel` | string | 状态文案 |
| `refToken` | string | 不可猜测的推广短令牌 |
| `sourceCode` | string | 固定为 `BJTR` |
| `qrImageUrl` | string | 二维码图片地址 |
| `shareTitle` | string | 分享标题 |
| `sharePath` | string | 分享路径或儒泰落地路径 |
| `expiresAt` | string/null | 过期时间 |
| `disabledReason` | string/null | 停用原因 |

### 11.2 获取推广海报

```http
GET /api/v1/promotion-code/poster
```

| 参数 | 位置 | 类型 | 必填 | 含义 |
|---|---|---|---:|---|
| `template` | query | string | 否 | 海报模板 ID |

返回 `posterUrl`、`expiresAt`。

### 11.3 获取推广统计

```http
GET /api/v1/promotion-code/statistics?period=30d
```

| 参数 | 类型 | 必填 | 可选值 | 含义 |
|---|---|---:|---|---|
| `period` | string | 否 | `7d`、`30d`、`3m` | 统计周期 |

返回扫码次数、来源线索数、成功绑定数和转化率。

### 11.4 刷新推广码

```http
POST /api/v1/promotion-code/refresh
```

**功能**：在推广码已过期、疑似泄露或被后台允许重新生成时，废止旧令牌并创建新推广码。

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `reason` | enum | 是 | `expired`、`suspected_leak`、`manual_refresh` |
| `currentPromotionCodeId` | string | 是 | 当前推广码 ID |

返回与“获取个人推广码”相同的数据结构。旧 `refToken` 必须立即失效；频繁刷新应受到限流和审计。

---

## 12. 客户绑定接口

### 12.1 获取可选择拓展人

```http
GET /api/v1/promoters/selectable
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `keyword` | string | 否 | 按姓名、编号搜索 |
| `cursor` | string | 否 | 分页游标 |
| `pageSize` | integer | 否 | 每页数量 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `promoterId` | string | 拓展人 ID |
| `name` | string | 姓名 |
| `accountIdMasked` | string | 脱敏编号 |
| `level` | string | 层级，例如 `L3` |
| `organization` | string | 所属机构 |
| `active` | boolean | 当前是否允许绑定客户 |

服务端必须按医生权限过滤可选范围，不能返回全部拓展人后由前端过滤。

### 12.2 提交客户绑定

```http
POST /api/v1/binding-requests
```

**权限**：具有 `customerBinding` 能力。

**请求头**：必须传 `Idempotency-Key`。

**请求参数**

| 参数 | 类型 | 必填 | 限制 | 含义 |
|---|---|---:|---|---|
| `customer.name` | string | 是 | 1-20 字符 | 客户姓名 |
| `customer.phone` | string | 是 | 11 位手机号 | 客户手机号 |
| `customer.idCard` | string | 是 | 15 或 18 位 | 客户身份证号 |
| `customer.medicalAccount` | string | 否 | 最长 30 字符 | 医保账户 |
| `customer.familyPhone` | string | 否 | 11 位手机号 | 家属手机号 |
| `promoterId` | string | 是 | 有效且可选 | 归属拓展人 ID |
| `sourceType` | enum | 是 | `manual`、`promotion_code`、`rutai_marked` | 绑定来源 |
| `sourceLeadId` | string | 条件必填 | 来源线索存在时必填 | 儒泰来源线索 ID |
| `refToken` | string | 否 | 推广码来源时填写 | 推广短令牌 |
| `consentRecordId` | string | 是 | 有效授权记录 | 客户授权记录 ID |

**请求示例**

```json
{
  "customer": {
    "name": "王女士",
    "phone": "13800138000",
    "idCard": "110101199001011234",
    "medicalAccount": "YB20260718001",
    "familyPhone": "18600186000"
  },
  "promoterId": "p_10001",
  "sourceType": "manual",
  "sourceLeadId": null,
  "refToken": null,
  "consentRecordId": "consent_10001"
}
```

**返回 `data`**

返回 `BindingRequest`。接口只保证申请已受理，不保证同步等待儒泰最终完成。

**返回示例**

```json
{
  "code": 0,
  "message": "绑定申请已提交",
  "data": {
    "bindingRequestId": "br_10001",
    "customerId": "c_10001",
    "rutaiUserIdMasked": null,
    "customerName": "王女士",
    "phoneMasked": "138****8000",
    "idCardMasked": "1101********1234",
    "promoterId": "p_10001",
    "promoterName": "张小明",
    "sourceType": "manual",
    "status": "pending_match",
    "statusLabel": "待匹配",
    "matchLevel": null,
    "retryCount": 0,
    "nextRetryAt": null,
    "failureReason": null,
    "submittedBy": {
      "userId": "u_20001",
      "name": "李医生"
    },
    "submittedAt": "2026-07-29T10:30:00+08:00",
    "boundAt": null,
    "updatedAt": "2026-07-29T10:30:00+08:00"
  },
  "requestId": "01J2ABCDEF",
  "serverTime": "2026-07-29T10:30:00+08:00"
}
```

### 12.3 获取绑定记录

```http
GET /api/v1/binding-requests
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `status` | string | 否 | 绑定状态，多个状态使用逗号分隔 |
| `keyword` | string | 否 | 姓名、脱敏手机号后四位等 |
| `sort` | enum | 否 | `recent`、`name`、`status` |
| `submittedByMe` | boolean | 否 | 是否只查询本人提交 |
| `cursor` | string | 否 | 分页游标 |
| `pageSize` | integer | 否 | 每页数量 |

返回分页的 `BindingRequest[]`。

### 12.4 获取绑定结果

```http
GET /api/v1/binding-requests/{bindingRequestId}
```

返回完整 `BindingRequest`，前端可在结果页短时轮询。建议轮询间隔不低于 3 秒，最多持续 30 秒，之后由用户进入绑定记录查看。

### 12.5 获取绑定汇总

```http
GET /api/v1/binding-summary
```

返回：

```json
{
  "total": 36,
  "bound": 32,
  "matching": 3,
  "processing": 1,
  "manualReview": 0
}
```

### 12.6 手动重试绑定

```http
POST /api/v1/binding-requests/{bindingRequestId}/retry
```

无业务参数。仅 `abnormal`、`manual_review` 且后台允许前端重试时可调用。返回更新后的 `BindingRequest`。

### 12.7 修正待匹配资料

```http
PUT /api/v1/binding-requests/{bindingRequestId}/customer-info
```

请求参数与 `customer` 对象一致，额外传：

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `reason` | string | 是 | 修正原因 |
| `version` | integer | 是 | 绑定申请数据版本 |

修改后重新进入 `pending_match`。已绑定记录禁止通过该接口修改。

---

## 13. 客户接口

### 13.1 获取客户列表

```http
GET /api/v1/customers
```

| 参数 | 类型 | 必填 | 可选值/格式 | 含义 |
|---|---|---:|---|---|
| `status` | string | 否 | `bound`、`matching`、`followup` | 页面筛选状态 |
| `keyword` | string | 否 | 最长 50 字符 | 姓名、手机号后四位 |
| `sort` | string | 否 | `recent`、`name` | 排序方式 |
| `cursor` | string | 否 | 游标 | 分页游标 |
| `pageSize` | integer | 否 | 1-100 | 每页数量 |

返回分页的 `CustomerSummary[]`。

### 13.2 获取客户详情

```http
GET /api/v1/customers/{customerId}
```

返回 `CustomerDetail`。服务端根据角色和归属范围进行数据权限校验。

### 13.3 修改客户资料

```http
PATCH /api/v1/customers/{customerId}
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `name` | string | 否 | 客户姓名 |
| `phone` | string | 否 | 新手机号；敏感字段变更可能进入复核 |
| `idCard` | string | 否 | 新身份证号；敏感字段变更可能进入复核 |
| `medicalAccount` | string | 否 | 新医保账户 |
| `familyPhone` | string | 否 | 新家属手机号 |
| `note` | string | 否 | 客户备注 |
| `changeReason` | string | 修改敏感字段时必填 | 修改原因 |
| `version` | integer | 是 | 客户数据版本 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `customer` | `CustomerDetail` | 更新后的客户数据 |
| `reviewRequired` | boolean | 敏感字段修改是否需要后台复核 |
| `changeRequestId` | string/null | 变更申请 ID |

### 13.4 获取服务记录

```http
GET /api/v1/customers/{customerId}/service-records
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `type` | string | 否 | `binding`、`service_package`、`followup`、`other` |
| `cursor` | string | 否 | 分页游标 |
| `pageSize` | integer | 否 | 每页数量 |

返回项：

| 字段 | 类型 | 含义 |
|---|---|---|
| `serviceRecordId` | string | 服务记录 ID |
| `type` | string | 服务类型 |
| `title` | string | 服务标题 |
| `status` | string | 服务状态 |
| `statusLabel` | string | 状态文案 |
| `plannedAt` | string/null | 计划时间 |
| `completedAt` | string/null | 完成时间 |
| `operatorName` | string/null | 操作人 |

### 13.5 获取客户绑定历史

```http
GET /api/v1/customers/{customerId}/binding-history
```

返回绑定、解绑、转移记录：

| 字段 | 类型 | 含义 |
|---|---|---|
| `operationId` | string | 操作记录 ID |
| `operationType` | enum | `bind`、`unbind`、`transfer` |
| `previousPromoterName` | string/null | 原拓展人 |
| `newPromoterName` | string/null | 新拓展人 |
| `reason` | string/null | 操作原因 |
| `operatedAt` | string | 操作时间 |

小程序仅查询，不提供解绑和转移操作。

### 13.6 获取客户贡献记录

```http
GET /api/v1/customers/{customerId}/contributions
```

支持 `status`、`category`、`cursor`、`pageSize`，返回分页的 `ContributionRecord[]`。

---

## 14. 客户跟进接口

### 14.1 获取跟进记录

```http
GET /api/v1/customers/{customerId}/followups
```

支持 `cursor`、`pageSize`，返回分页的 `FollowupRecord[]`。

### 14.2 新增跟进记录

```http
POST /api/v1/customers/{customerId}/followups
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `method` | enum | 是 | `phone`、`wechat`、`in_person`、`other` |
| `result` | enum | 是 | `connected`、`waiting`、`unanswered` |
| `content` | string | 是 | 跟进内容，1-500 字符 |
| `reminderEnabled` | boolean | 是 | 是否设置下次提醒 |
| `reminderAt` | string | 条件必填 | 开启提醒时必填，必须晚于当前时间 |

返回新建的 `FollowupRecord`。

### 14.3 保存跟进草稿

```http
POST /api/v1/customers/{customerId}/followup-drafts
```

参数与新增跟进记录一致，但允许 `content` 为空。返回 `draftId`、`savedAt`。

### 14.4 修改跟进记录

```http
PUT /api/v1/followups/{followupId}
```

参数与新增接口一致，增加 `version`。返回更新后的 `FollowupRecord`。

### 14.5 修改跟进提醒

```http
PUT /api/v1/followups/{followupId}/reminder
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `reminderEnabled` | boolean | 是 | 是否启用提醒 |
| `reminderAt` | string/null | 是 | 提醒时间；关闭时传 `null` |
| `version` | integer | 是 | 数据版本 |

### 14.6 完成跟进提醒

```http
POST /api/v1/followups/{followupId}/complete
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `completionNote` | string | 否 | 完成说明 |

返回更新后的 `FollowupRecord`。

---

## 15. 客户分析接口

### 15.1 获取客户分析

```http
GET /api/v1/customer-analysis?period=30d
```

| 参数 | 类型 | 必填 | 可选值 | 含义 |
|---|---|---:|---|---|
| `period` | string | 否 | `30d`、`3m`、`year` | 分析周期 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `period` | string | 当前周期 |
| `overview.total` | integer | 客户总数 |
| `overview.added` | integer | 周期内新增 |
| `overview.bound` | integer | 已绑定 |
| `overview.matching` | integer | 待匹配 |
| `overview.followup` | integer | 待跟进 |
| `trend.categories` | string[] | 图表横轴 |
| `trend.values` | integer[] | 客户数量趋势 |
| `followup.completed` | integer | 已完成跟进 |
| `followup.pending` | integer | 待跟进 |
| `followup.idle` | integer | 尚未跟进 |
| `sources` | array | 来源分布 |
| `updatedAt` | string | 数据更新时间 |

`sources[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `sourceType` | enum | `manual`、`promotion_code` |
| `label` | string | 来源名称 |
| `value` | integer | 客户数量 |
| `percent` | number | 百分比，0-100 |

---

## 16. 贡献值接口

### 16.1 获取贡献汇总

```http
GET /api/v1/contributions/overview?month=2026-07
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `month` | string | 否 | 查询月份，默认当前月 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `month` | string | 查询月份 |
| `monthlyPoints` | string | 本月贡献 |
| `totalPoints` | string | 累计贡献 |
| `growthRate` | string/null | 相比上一周期增长率 |
| `totalCount` | integer | 明细总数 |
| `pendingCount` | integer | 待结算数量 |
| `settledCount` | integer | 已结算数量 |
| `updatedAt` | string | 数据更新时间 |

### 16.2 获取贡献趋势

```http
GET /api/v1/contributions/trend?period=6m
```

| 参数 | 类型 | 必填 | 可选值 | 含义 |
|---|---|---:|---|---|
| `period` | string | 否 | `6m`、`year` | 趋势周期 |

返回：

```json
{
  "period": "6m",
  "categories": ["2月", "3月", "4月", "5月", "6月", "7月"],
  "values": ["7200.00", "8100.00", "9200.00", "9860.00", "10420.00", "12680.00"]
}
```

### 16.3 获取贡献构成

```http
GET /api/v1/contributions/composition?month=2026-07
```

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `category` | enum | 贡献分类 |
| `label` | string | 分类名称 |
| `points` | string | 分类贡献值 |
| `percent` | number | 占比 |

### 16.4 获取贡献明细

```http
GET /api/v1/contributions
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `month` | string | 否 | 月份，默认当前月 |
| `status` | string | 否 | `pending`、`confirmed`、`settled`、`reversed` |
| `category` | string | 否 | 贡献分类 |
| `customerId` | string | 否 | 指定客户 |
| `cursor` | string | 否 | 分页游标 |
| `pageSize` | integer | 否 | 每页数量 |

返回分页的 `ContributionRecord[]`。

### 16.5 获取单条贡献详情

```http
GET /api/v1/contributions/{contributionId}
```

返回 `ContributionRecord`，并增加：

| 字段 | 类型 | 含义 |
|---|---|---|
| `calculationBase` | string | 计算基数说明，不向无权限用户展示金额 |
| `coefficient` | string | 换算系数 |
| `calculationDescription` | string | 用户可理解的计算说明 |
| `adjustmentReason` | string/null | 人工调整原因 |

### 16.6 获取团队贡献

```http
GET /api/v1/team/contributions?month=2026-07
```

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `teamMonthlyPoints` | string | 团队本月贡献 |
| `teamTotalPoints` | string | 团队累计贡献 |
| `directMemberCount` | integer | 直属成员数 |
| `members` | array | 直属成员汇总 |

`members[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `promoterId` | string | 拓展人 ID |
| `name` | string | 姓名 |
| `level` | string | 层级 |
| `monthlyPoints` | string | 本月贡献 |
| `totalPoints` | string | 累计贡献 |
| `childCount` | integer | 直属下级数 |
| `canDrillDown` | boolean | 是否允许继续下钻 |

### 16.7 团队贡献下钻

```http
GET /api/v1/team/contributions/{promoterId}?month=2026-07
```

返回结构与团队贡献一致。服务端必须验证目标拓展人属于当前用户的下级分支。

---

## 17. 隐私协议与授权接口

### 17.1 获取最新协议

```http
GET /api/v1/agreements/latest
```

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `agreements` | array | 最新协议列表 |
| `consentRequired` | boolean | 当前用户是否需要重新同意 |

`agreements[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `agreementId` | string | 协议 ID |
| `type` | enum | `user_agreement`、`privacy_policy`、`collection_list`、`sharing_list` |
| `title` | string | 协议标题 |
| `version` | string | 协议版本 |
| `summary` | string | 协议摘要 |
| `contentUrl` | string | 协议正文地址 |
| `effectiveAt` | string | 生效时间 |

### 17.2 获取协议正文

```http
GET /api/v1/agreements/{agreementId}
```

返回协议 ID、类型、标题、版本、HTML 正文、发布时间和生效时间。

### 17.3 保存授权记录

```http
POST /api/v1/consents
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `subjectType` | enum | 是 | `account_user`、`customer` |
| `subjectId` | string | 条件必填 | 已有主体时填写 |
| `scene` | enum | 是 | `login`、`customer_binding`、`data_sharing` |
| `agreementVersions` | object | 是 | 各协议类型及用户同意的版本 |
| `scopes` | string[] | 是 | 授权范围 |
| `confirmed` | boolean | 是 | 必须为 `true` |
| `evidenceType` | enum | 是 | `self_confirmed`、`customer_confirmed`、`paper_authorization` |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `consentRecordId` | string | 授权记录 ID |
| `status` | string | `valid` |
| `consentedAt` | string | 同意时间 |
| `expiresAt` | string/null | 授权过期时间 |

绑定客户时必须传有效的 `consentRecordId`，不能只传布尔值。

### 17.4 获取本人授权状态

```http
GET /api/v1/me/consents
```

返回微信绑定、手机号授权、协议同意、媒体权限和订阅消息授权状态。

### 17.5 保存隐私设置

```http
PUT /api/v1/me/privacy-settings
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `maskSensitive` | boolean | 是 | 是否默认增强脱敏展示 |
| `personalized` | boolean | 是 | 是否允许个性化内容 |
| `version` | integer | 是 | 设置版本 |

---

## 18. 反馈与通知接口

### 18.1 获取反馈截图上传凭证

```http
POST /api/v1/feedback-files/upload-token
```

参数与头像上传凭证一致，单次最多为 3 张图片中的一张。

### 18.2 提交反馈

```http
POST /api/v1/feedbacks
```

| 参数 | 类型 | 必填 | 限制 | 含义 |
|---|---|---:|---|---|
| `type` | enum | 是 | `issue`、`suggestion`、`other` | 反馈类型 |
| `content` | string | 是 | 10-500 字符 | 问题描述 |
| `imageFileIds` | string[] | 否 | 最多 3 个 | 已上传截图 ID |
| `contactAllowed` | boolean | 是 | 是否允许客服联系 |

返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `feedbackId` | string | 反馈 ID |
| `status` | enum | `submitted` |
| `createdAt` | string | 提交时间 |
| `expectedReplyText` | string | 预计处理说明 |

### 18.3 获取反馈记录

```http
GET /api/v1/feedbacks
```

支持 `status`、`cursor`、`pageSize`，返回：

| 字段 | 类型 | 含义 |
|---|---|---|
| `feedbackId` | string | 反馈 ID |
| `type` | string | 类型 |
| `contentSummary` | string | 内容摘要 |
| `status` | enum | `submitted`、`processing`、`resolved`、`closed` |
| `reply` | string/null | 客服回复 |
| `createdAt` | string | 提交时间 |
| `resolvedAt` | string/null | 处理完成时间 |

### 18.4 获取通知

```http
GET /api/v1/notifications
```

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `category` | string | 否 | `qualification`、`binding`、`contribution`、`system` |
| `unreadOnly` | boolean | 否 | 是否仅获取未读 |
| `cursor` | string | 否 | 分页游标 |
| `pageSize` | integer | 否 | 每页数量 |

返回通知 ID、分类、标题、摘要、目标页面、是否已读、创建时间。

### 18.5 标记通知已读

```http
POST /api/v1/notifications/{notificationId}/read
```

无业务参数，返回 `read=true`、`readAt`。

---

## 19. 科普内容接口（P2）

### 19.1 获取文章列表

```http
GET /api/v1/articles
```

支持 `categoryId`、`keyword`、`cursor`、`pageSize`，返回文章 ID、标题、封面、摘要、分类、发布时间。

### 19.2 获取文章详情

```http
GET /api/v1/articles/{articleId}
```

返回标题、富文本正文、视频地址、分类、作者、发布时间和更新时间。仅返回已发布且未下架内容。

---

## 20. 北京服务端与儒泰服务端对接接口

本节接口只允许服务端之间调用，小程序不得直调。接口应使用 HTTPS、服务端鉴权、HMAC-SHA256 签名、时间戳、随机数和请求幂等键。

以下字段是北京侧建议协议，最终以双方接口联调确认结果为准。

### 20.1 匹配儒泰用户：`bindBjUser`

```http
POST /integration/v1/bindBjUser
```

**提供方**：哈尔滨儒泰。  
**调用方**：北京儒泰服务端。

**请求参数**

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `request_id` | string | 是 | 北京侧唯一请求号和幂等键 |
| `patient_name` | string | 是 | 患者姓名 |
| `patient_phone` | string | 建议必填 | 患者手机号 |
| `id_card` | string | 建议必填 | 身份证号 |
| `medical_account` | string | 否 | 医保账户 |
| `family_phone` | string | 否 | 家属手机号 |
| `source` | string | 是 | 固定为 `BJTR` |
| `ref_token` | string | 否 | 推广短令牌 |

**建议返回**

| 字段 | 类型 | 含义 |
|---|---|---|
| `request_id` | string | 原请求号 |
| `match_status` | enum | `matched`、`not_found`、`multiple_matches`、`pending` |
| `match_level` | enum/null | `strong`、`medium`、`weak` |
| `matched_by` | string[] | 命中的匹配字段 |
| `hrb_user_id` | string/null | 儒泰用户唯一 ID |
| `marked_source` | string/null | 用户来源标记 |
| `message` | string | 结果说明 |

禁止仅凭姓名唯一命中就自动建立正式绑定；仅姓名命中应返回 `multiple_matches` 或 `pending` 进入人工复核。

### 20.2 增量获取北京来源用户：`getBindUser`

```http
GET /integration/v1/getBindUser
```

**调用频率**：北京侧每分钟调用。

**请求参数**

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `cursor` | string | 否 | 上次成功同步的游标 |
| `start_time` | string | 否 | 补拉开始时间 |
| `end_time` | string | 否 | 补拉结束时间 |
| `page_size` | integer | 否 | 每页数量，建议 1-200 |
| `source` | string | 是 | 固定为 `BJTR` |

**建议返回**

| 字段 | 类型 | 含义 |
|---|---|---|
| `items` | array | 北京来源用户 |
| `next_cursor` | string/null | 下一页游标 |
| `has_more` | boolean | 是否还有数据 |

`items[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `hrb_user_id` | string | 儒泰用户 ID |
| `phone_masked` | string | 脱敏手机号 |
| `marked_status` | enum | `marked`、`pending` |
| `bind_method` | enum | `scan`、`manual` |
| `ref_token` | string/null | 推广短令牌 |
| `marked_at` | string | 来源标记时间 |
| `updated_at` | string | 数据更新时间 |

不能只提供“最近 50 条”且没有游标，否则任务失败或数据量超过 50 条时可能漏数。

### 20.3 获取指定用户账单：`getUserBill`

```http
GET /integration/v1/getUserBill
```

**请求参数**

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `hrb_user_id` | string | 是 | 儒泰用户 ID |
| `updated_since` | string | 否 | 仅获取该时间后更新的账单 |
| `cursor` | string | 否 | 分页游标 |
| `page_size` | integer | 否 | 每页数量 |

**建议返回**

| 字段 | 类型 | 含义 |
|---|---|---|
| `hrb_user_id` | string | 儒泰用户 ID |
| `items` | array | 账单明细 |
| `next_cursor` | string/null | 下一页游标 |
| `has_more` | boolean | 是否还有数据 |

`items[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `transaction_id` | string | 交易流水号，作为北京侧幂等键 |
| `transaction_time` | string | 交易时间 |
| `consultation_fee_cent` | integer | 诊费，单位分 |
| `medicine_fee_cent` | integer | 医药费，单位分 |
| `total_amount_cent` | integer | 合计金额，单位分 |
| `discount_amount_cent` | integer | 折扣金额，单位分 |
| `paid_amount_cent` | integer | 实付金额，单位分 |
| `refund_amount_cent` | integer | 已退款金额，单位分 |
| `transaction_status` | enum | `paid`、`partially_refunded`、`refunded`、`cancelled` |
| `updated_at` | string | 账单最后更新时间 |

### 20.4 按日期获取全部北京来源账单：`getAllUsersBill`

```http
GET /integration/v1/getAllUsersBill
```

**功能**：用于日终补偿和对账，不能替代 `getUserBill` 的日常增量查询。

**请求参数**

| 参数 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `bill_date` | string | 否 | 账单日期，默认当天 |
| `updated_since` | string | 否 | 获取更新时间后的变更 |
| `source` | string | 是 | 固定为 `BJTR` |
| `cursor` | string | 否 | 分页游标 |
| `page_size` | integer | 否 | 每页数量 |

返回结构与 `getUserBill` 类似，但每条账单额外包含 `hrb_user_id`。

---

## 21. 页面与接口对应关系

| 小程序页面 | 主要接口 |
|---|---|
| 登录页 | `/auth/wechat-login`、`/auth/phone-bind`、`/agreements/latest`、`/consents` |
| 首次资料补全 | `/me/profile` |
| 首页 | `/app/bootstrap`、`/workbench` |
| 客户 Tab | `/customers`、`/binding-summary` |
| 客户分析 | `/customer-analysis` |
| 客户绑定 | `/promoters/selectable`、`/consents`、`/binding-requests` |
| 绑定记录 | `/binding-requests`、`/binding-summary` |
| 绑定结果 | `/binding-requests/{id}`、`/binding-requests/{id}/retry` |
| 客户详情 | `/customers/{id}`、服务记录、跟进记录、客户贡献 |
| 编辑客户 | `PATCH /customers/{id}` |
| 跟进记录 | `/customers/{id}/followups` |
| 贡献 Tab | 贡献汇总、趋势、构成和明细接口 |
| 贡献明细 | `/contributions`、`/contributions/{id}` |
| 我的推广码 | `/promotion-code`、`/promotion-code/poster` |
| 资质状态 | `/qualifications/current`、审核记录接口 |
| 更新资质 | 资质文件上传、提交和更新接口 |
| 账号信息 | `/me/profile`、头像上传接口 |
| 隐私授权 | 协议、授权记录、隐私设置接口 |
| 帮助与反馈 | 反馈截图上传、`/feedbacks` |

---

## 22. 安全与合规要求

1. 小程序不得保存身份证、医保账户和完整手机号明文到本地缓存。
2. 列表和详情接口默认返回脱敏数据；确需查看明文时必须单独鉴权并记录审计日志。
3. 资质文件和反馈截图使用短期上传凭证，不经过小程序业务 JSON 接口传 Base64。
4. 客户绑定必须关联有效授权记录。
5. 绑定、资质提交和反馈提交必须支持幂等。
6. 服务端日志不得记录访问令牌、身份证明文、完整手机号和医保账户。
7. 医生只能查看其业务权限范围内的客户；拓展人只能查看本人及被授权的下级汇总。
8. 团队贡献接口不返回下级客户就诊、账单或敏感明细。
9. 所有敏感数据修改、客户归属变更和贡献调整必须留存审计记录。
10. 儒泰接口调用密钥仅保存在服务端，严禁下发到小程序。

---

## 23. 待业务和联调确认

| 优先级 | 待确认问题 | 影响 |
|---|---|---|
| P0 | 推广二维码是否确定携带 `ref_token` | 决定是否能自动识别具体拓展人 |
| P0 | 医生可选择本人、直属团队还是全部拓展人 | 决定 `/promoters/selectable` 权限 |
| P0 | 儒泰能否返回稳定的 `hrb_user_id` | 决定用户映射可靠性 |
| P0 | `getBindUser` 是否支持游标、分页和时间窗口 | 决定是否会漏数据 |
| P0 | `getUserBill` 是否支持按更新时间增量查询 | 决定后续消费和退款能否同步 |
| P0 | 儒泰退款、部分退款、撤销的字段和状态 | 决定贡献冲正和对账 |
| P0 | 客户授权由客户本人确认还是医生代确认 | 决定授权证据模型 |
| P0 | 贡献值仅按实付金额计算，还是也包含绑定和随访事件 | 决定贡献规则和页面分类 |
| P0 | 医生是否需要资质审核，以及能否查看贡献 | 决定角色权限矩阵 |
| P1 | 客户敏感信息修改是否需要后台复核 | 决定客户编辑接口流程 |
| P1 | 团队贡献允许下钻的最大层级 | 决定团队查询范围 |

---

## 24. 一期联调建议

建议按以下顺序联调：

1. 微信登录、手机号绑定、会话和权限。
2. 个人资料、资质上传、提交和状态查询。
3. 推广码和可选择拓展人。
4. 客户授权、绑定提交、绑定状态查询和绑定记录。
5. 客户列表、详情、编辑和跟进。
6. 儒泰 `bindBjUser`、`getBindUser`、`getUserBill`。
7. 贡献汇总、趋势和明细。
8. 反馈、通知、客户分析和团队贡献。

联调验收时必须覆盖正常、重复提交、已绑定、未匹配、外部接口超时、自动重试、无消费、退款和无权限场景。
