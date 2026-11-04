# Navigation Contract

## Primary Tabs

| Tab ID | Label | Page | Page-Level Navigation |
|---|---|---|---|
| `home` | 首页 | `/pages/home/index` | 保留首页品牌与微信胶囊区域 |
| `customers` | 客户 | `/pages/customers/index` | 禁止返回按钮和页面标题导航 |
| `internet-hospital` | 互联网医院 | `/pages/internet-hospital/index` | 公开的建设中占位内容，保留微信胶囊安全区 |
| `mall` | 商城 | `/pages/mall/index` | 公开的健康主题商品示意列表，占位内容明确标注尚未上架，无页面级返回导航 |
| `profile` | 我的 | `/pages/profile/index` | 禁止返回按钮和页面标题导航 |

Tab 顺序：普通用户为首页 → 互联网医院 → 商城 → 我的；业务成员在首页后保留客户 Tab，即首页 → 客户 → 互联网医院 → 商城 → 我的。

## Business Service Entry

| Entry ID | Label | Page | Access | Page-Level Navigation |
|---|---|---|---|---|
| `contribution-records` | 消费记录 | `/pages/contribution/index` | 具备 `contribution` capability 的业务账号；从“我的服务”打开 | 作为二级页面提供返回导航 |

“消费记录”页的“查看全部”继续打开 `/pages/contribution-detail/index`，展示逐笔账单记录。

## Role Entry Contract

| Condition | Destination |
|---|---|
| 无有效会话 | `/pages/auth/login` |
| 业务成员资料未补全 | `/pages/auth/profile-setup` |
| 普通访客资料未补全 | `/pages/home/index` |
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
