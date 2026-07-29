# Data Model: 四 Tab 基础工程与角色工作台

## UserSession

| Field | Type | Rules |
|---|---|---|
| `userId` | string | 模拟环境使用虚构标识，不含真实客户信息 |
| `role` | enum | `promoter`、`doctor`、`unknown` |
| `activationStatus` | enum | `active`、`inactive` |
| `qualificationStatus` | enum | `approved`、`reviewing`、`rejected`、`expiring` |
| `profileCompleted` | boolean | 未完成时进入首次资料补全 |

### Entry Transition

```text
unknown session -> 登录授权
profileCompleted=false -> 首次资料补全
role=doctor -> 医生工作台
activationStatus=inactive -> 账号待激活状态
role=promoter + qualificationStatus=approved/expiring -> 拓展人首页
role=promoter + qualificationStatus=reviewing/rejected -> 资质状态
```

## NavigationTab

| Field | Type | Rules |
|---|---|---|
| `id` | enum | `home`、`customers`、`contribution`、`profile` |
| `label` | string | 首页、客户、贡献、我的 |
| `pagePath` | string | 必须对应已注册一级页面 |
| `icon` | string | 未选中图标资源 |
| `selectedIcon` | string | 选中图标资源 |
| `order` | integer | 固定为 1-4 |

## WorkbenchSummary

| Field | Type | Rules |
|---|---|---|
| `metrics` | array | 指标标题、显示值、状态和目标路由 |
| `primaryAction` | object | 当前工作台唯一主操作 |
| `notices` | array | 仅使用虚构或通用提示 |
| `updatedAt` | datetime | 可显示数据新鲜度 |

## DemoStateControl

| Field | Type | Rules |
|---|---|---|
| `sessionKey` | string | 仅开发环境的模拟身份存储键 |
| `viewStateKey` | string | 仅开发环境的一级页状态存储键 |
| `viewState` | enum | `loading`、`success`、`empty`、`recoverable-error`、`forbidden` |

模拟状态通过本地存储或开发配置切换；生产会话与生产接口不得读取这些键。

## PageViewState

| State | Meaning | Required User Action |
|---|---|---|
| `loading` | 首次或刷新加载 | 无，展示进度 |
| `success` | 数据可用 | 正常操作 |
| `empty` | 无数据但非错误 | 展示说明和可用入口 |
| `recoverable-error` | 暂时失败 | 提供重试 |
| `forbidden` | 当前角色无权 | 返回可访问入口 |

## NavigationTarget

| Field | Type | Rules |
|---|---|---|
| `actionId` | string | 页面内唯一 |
| `targetPage` | string | 对应页面注册表 |
| `requiresRole` | enum[] | 空数组表示所有角色 |
| `requiresQualification` | boolean | 受限能力必须校验 |
| `implementationStatus` | enum | `ready`、`placeholder`、`blocked` |
