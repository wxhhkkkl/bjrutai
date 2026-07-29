# Navigation Contract

## Primary Tabs

| Tab ID | Label | Page | Page-Level Navigation |
|---|---|---|---|
| `home` | 首页 | `/pages/home/index` | 保留首页品牌与微信胶囊区域 |
| `customers` | 客户 | `/pages/customers/index` | 禁止返回按钮和页面标题导航 |
| `contribution` | 贡献 | `/pages/contribution/index` | 禁止返回按钮和页面标题导航 |
| `profile` | 我的 | `/pages/profile/index` | 禁止返回按钮和页面标题导航 |

## Role Entry Contract

| Condition | Destination |
|---|---|
| 无有效会话 | `/pages/auth/login` |
| 资料未补全 | `/pages/auth/profile-setup` |
| 账号未激活 | `/pages/qualification/status?state=inactive` |
| 医生 | `/pages/home/index?mode=doctor` |
| 已激活拓展人 | `/pages/home/index?mode=promoter` |
| 资质即将过期的拓展人 | `/pages/home/index?mode=promoter&qualification=expiring` |
| 待审核拓展人 | `/pages/qualification/status?state=reviewing` |
| 审核驳回拓展人 | `/pages/qualification/status?state=rejected` |

## Behavior

- Tab 切换必须使用平台 Tab 切换能力。
- 二级页面返回不得重置当前 Tab。
- 受角色或资质限制的目标必须在跳转前校验。
- 尚未实现的二级页面必须显示明确占位状态，不能静默无响应。
- “功能建设中”占位页必须已注册、可返回，并显示用户安全的说明；它不得伪装成业务处理成功。
- 重复快速点击当前 Tab 不得产生重复页面栈。
