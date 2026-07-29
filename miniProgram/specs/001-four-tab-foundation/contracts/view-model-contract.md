# Top-Level View Model Contract

## Common Shape

```json
{
  "state": "success",
  "title": "页面标题或工作台名称",
  "metrics": [],
  "actions": [],
  "updatedAt": "2026-07-27T09:30:00+08:00",
  "error": null
}
```

## Rules

- `state` 只能是 `loading`、`success`、`empty`、`recoverable-error`、`forbidden`。
- `metrics[].value` 是展示值，不在视图层进行贡献或业务计算。
- `actions[].target` 必须存在于导航契约。
- 模拟客户姓名使用“王女士”等虚构称呼，手机号必须脱敏。
- `error` 仅包含用户安全的错误分类和重试提示，不得包含敏感请求参数。
- Mock 视图状态仅由开发环境的 `DemoStateControl` 读取；生产数据源不得暴露调试切换入口。

## Role Fixture Shape

```json
{
  "userId": "demo-promoter-001",
  "role": "promoter",
  "activationStatus": "active",
  "qualificationStatus": "approved",
  "profileCompleted": true
}
```

真实用户标识、手机号、身份证号、医保账户和资质编号禁止进入模拟文件。
