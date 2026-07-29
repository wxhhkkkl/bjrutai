# LuTaiPage

北京鲁泰微信小程序原生开发工程。

## Project Inputs

- PRD：`../北京鲁泰-哈尔滨儒泰小程序对接_PRD.md`
- 功能清单：`../小程序功能清单与页面梳理.md`
- 页面流转：`../北京鲁泰小程序-四大Tab页面流转示意图.md`
- 已确认 UI：`../UI设计稿已确认/`
- UI 规则：`../北京鲁泰小程序-UI设计定稿-首页V4.md`

## Spec Kit Workflow

本工程使用 GitHub Spec Kit 管理需求到实现的全过程：

```text
$speckit-constitution
  -> $speckit-specify
  -> $speckit-clarify（按需）
  -> $speckit-plan
  -> $speckit-tasks
  -> $speckit-analyze
  -> $speckit-implement
```

项目原则位于 `.specify/memory/constitution.md`，功能规格位于 `specs/`。

## Current Stack

- 微信原生小程序
- WXML / WXSS / JavaScript
- Skyline renderer
- Glass-easel component framework
- Vant Weapp（`@vant/weapp`，按功能需要引入）

## Development Rules

- 不使用 UI 截图作为页面背景。
- Tab 页面不添加返回按钮或页面标题导航。
- 敏感信息默认脱敏，不在日志和模拟数据中放入真实数据。
- 每个功能先完成规格、计划和任务，再进入实现。
- 生产基础库必须固定为稳定版本，不能长期使用 `trial`。
- 业务代码统一使用 JavaScript，不引入 TypeScript 或跨端应用框架。
- Vant Weapp 必须固定版本、按需注册；确认设计稿优先于组件默认样式。
