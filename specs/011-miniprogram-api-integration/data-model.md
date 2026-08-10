# Phase 1 Data Model: 小程序 API 集成客户端状态

本功能不新增数据库表。这里定义的是小程序内存/本地存储状态和后端 DTO 到页面 ViewModel 的边界。

## 1. ApiEnvelope

所有成功响应的最外层结构：

| 字段 | 类型 | 规则 |
|------|------|------|
| code | integer | `0` 表示业务成功；非 0 转为 ApiError |
| message | string | 可用于安全、简洁的用户提示；不得假定始终中文 |
| data | any | 由具体 service/adapter 校验 |
| requestId | string | 诊断关联 ID，可记录；不得记录请求敏感正文 |
| serverTime | ISO string | 服务端时间；不作为业务字段替代值 |

若 HTTP 2xx 但缺少统一包，视为 `MALFORMED_RESPONSE`，不自动接受裸数据。

## 2. ClientSession

| 字段 | 类型 | 来源 | 持久化 |
|------|------|------|--------|
| accessToken | string | 登录/刷新 | 安全本地 key，不进入 Page.data |
| refreshToken | string | 登录/刷新 | 安全本地 key，不进入 Page.data |
| expiresAt | number/string | expiresIn 或 session | 可持久化 |
| userId | string | auth session | 可持久化非敏感摘要 |
| displayName | string | auth/profile | 可持久化摘要 |
| avatarUrl | string/null | auth/profile | 可持久化摘要 |
| phoneMasked | string/null | auth/profile | 仅脱敏值 |
| role | string | auth session | 可持久化摘要 |
| distributorId | string/null | distributor login/session | 可持久化摘要 |
| orgId | string/null | distributor login/session | 可持久化摘要 |
| orgName | string/null | distributor login/session | 可持久化摘要 |
| orgRole | `admin/member` | distributor login/session | 可持久化摘要 |
| permissions | string[] | session | 可持久化摘要 |
| wechatBound | boolean | login/session | 可持久化摘要 |

**不变量**：Token 不进入页面响应、日志或分享；退出/刷新失败/账户切换时整个 ClientSession 原子清除。

### Session 状态机

```text
anonymous
  -> authenticating
  -> binding_wechat (手机号登录且未绑定)
  -> authenticated
  -> refreshing
  -> authenticated | expired
authenticated -> logging_out -> anonymous
```

`expired` 必须清理真实会话后进入 `anonymous`，不能转成 Demo Session。

## 3. RequestOptions

| 字段 | 说明 |
|------|------|
| path | `/api/v1` 下路径，调用方不可传完整任意生产 URL |
| method | GET/POST/PUT/PATCH/DELETE |
| data | Query 或 JSON body |
| auth | 是否要求登录，默认 true |
| idempotencyKey | 写动作的稳定 key，可选但绑定必填 |
| timeoutMs | 默认统一超时，必要时上传单独配置 |
| retryAfterRefresh | 是否允许一次 401 刷新重试 |
| requestTag | 页面查询版本/取消标识 |

## 4. ApiError

| 字段 | 示例 | 页面处理 |
|------|------|----------|
| kind | NETWORK/TIMEOUT/AUTH/FORBIDDEN/NOT_FOUND/CONFLICT/VALIDATION/SERVER/MALFORMED | 选择页面状态与是否可重试 |
| code | 40100/40300/40901 | 精确业务分支，不以 message 文本判断 |
| message | 脱敏提示 | Toast 或 page-state |
| requestId | 服务端请求 ID | 用户反馈时可提供 |
| retryable | boolean | 控制重试按钮 |
| httpStatus | integer/null | 诊断，不直接展示 |

## 5. PageLoadState

```text
idle -> loading -> success | empty | error | forbidden
error -> loading (retry)
success -> refreshing -> success | error-with-stale-data
```

- 账户切换时禁止保留 stale data。
- 初次加载错误显示整页状态；已有数据刷新失败可以保留脱敏旧数据并提示，但不得跨账户。
- 每次查询携带 queryVersion，只有最新版本可以提交 setData。

## 6. CursorPage<T>

| 字段 | 类型 | 规则 |
|------|------|------|
| items | T[] | 首次查询替换，加载更多追加并按 id 去重 |
| nextCursor | string/null | 原样回传，不自行解码 |
| hasMore | boolean | false 时禁止继续请求 |
| loadingMore | boolean | 防止同游标并发 |
| queryKey | string | 搜索/筛选/月份组合，变化即重置 |

## 7. Domain ViewModels

### WorkbenchView

- `welcomeMessage`
- `myCustomers`
- `myBindings`
- `myMonthlyConsumptionCent`
- `pendingFollowups`
- `notices[]`
- `recentBindings[]`

### CustomerListItem

- `id`, `name`, `phoneMasked`, `bindingStatus`, `statusLabel`
- `promoterName`, `note`, `updatedAtDisplay`

不接收或生成明文身份证/手机号。

### CustomerDetailView

- 客户脱敏基本信息
- `monthlyConsumptionCent`, `totalConsumptionCent`
- `serviceCount`, `followupCount`
- 三个独立 CursorPage：服务记录、消费记录、跟进记录

### BindingView

- 请求输入：目标分销员、客户信息、授权记录、来源类型
- 展示：`requestId`, `status`, `statusLabel`, `retryCount`, `failureReason`, 脱敏客户信息、事件
- 状态 adapter 负责把后端枚举映射为现有 UI tone/icon/action；未知枚举进入受控错误或通用状态，不映射成成功

### ConsumptionView

- Overview：`monthlyAmountCent`, `totalAmountCent`, `growthRate`
- Trend：`categories[]`, `valuesCent[]`
- Bill：`id`, `title`, `amountCent`, `status`, `occurredAt`, `customerName`, `refundAmountCent?`

页面可使用兼容字段名，但 adapter 必须明确由上述字段生成，不能读取旧 `points` Mock。

### PerformanceView

- 当前月 `estimate`
- 历史月份 `confirmed[]`
- 每项金额：`baseCent`, `commissionCent`; 比例仅展示，不由前端重新计算提成

## 8. IdempotencyContext

| 字段 | 说明 |
|------|------|
| action | binding/followup/profile/feedback/privacy/promotion-refresh 等 |
| entityKey | 客户/请求/页面流程标识 |
| key | 首次提交生成，未知结果重试复用 |
| state | idle/submitting/unknown/succeeded/failed |

明确业务校验失败后可重新生成 key；超时或断网属于 unknown，重试必须复用。

## 9. 本地存储规则

- 允许：Token、会话非敏感摘要、明确的开发环境开关、未提交表单草稿（不得含完整身份证等敏感字段）。
- 禁止：完整客户敏感信息、后端响应快照、生产账号密码、API 密钥、COS 密钥、日志正文。
- Demo keys 与真实 keys 分离；生产初始化忽略并可清理旧 Demo key。
