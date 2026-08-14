# LuTaiPage

北京儒泰微信小程序原生开发工程。

## Project Inputs

- PRD：`../北京儒泰-哈尔滨儒泰小程序对接_PRD.md`
- 功能清单：`../小程序功能清单与页面梳理.md`
- 页面流转：`../北京儒泰小程序-四大Tab页面流转示意图.md`
- 已确认 UI：`../UI设计稿已确认/`
- UI 规则：`../北京儒泰小程序-UI设计定稿-首页V4.md`

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
- WebView renderer
- Glass-easel component framework
- Vant Weapp（`@vant/weapp`，按功能需要引入）

## Local Development

1. 使用微信开发者工具导入本目录 `miniProgram/`，不要导入仓库根目录。
2. 在本目录安装依赖并使用开发者工具的“工具 → 构建 npm”。生成的 `miniprogram_npm/` 和 `project.private.config.json` 只保留在本机，不提交。
3. 当前开发联调后端地址为 `http://192.168.110.24:8001`，本地联调可在开发者工具中勾选“不校验合法域名”；如果后端 IP 变化，只需同步修改 `config/env.js`。
4. 体验版和正式版必须在 `config/env.js` 配置已备案 HTTPS API 地址；未配置时小程序会报告环境配置错误，且不会回退到 Mock。
5. Mock 默认关闭。只有开发版显式设置本地 `lutai_dev_use_mock=true` 才允许启用，体验版和正式版始终禁用。

## Tests

测试使用 Node 内置的 `node:test`，要求 Node.js 18 或更高版本：

```bash
node --test tests/unit/*.test.js tests/contract/*.test.js
```

联调功能增加集成测试后运行：

```bash
node --test tests/unit/*.test.js tests/contract/*.test.js tests/integration/*.test.js
```

不要使用本机 Node 12 运行测试；它不支持 `node --test`。

## API Integration Boundary

- 小程序只访问北京后端 `/api/v1`，不直连数据库、哈尔滨儒泰接口或腾讯云密钥。
- 金额从后端接收整数分，只在展示时格式化为元。
- 手机号、身份证号、医保账户等敏感字段只展示后端脱敏值，不写入日志或测试快照。
- 发现前后端契约不一致时记录在 `../specs/011-miniprogram-api-integration/contracts/page-api-matrix.md`，不得通过页面假数据掩盖。

## Development Rules

- 不使用 UI 截图作为页面背景。
- Tab 页面不添加返回按钮或页面标题导航。
- 敏感信息默认脱敏，不在日志和模拟数据中放入真实数据。
- 每个功能先完成规格、计划和任务，再进入实现。
- 生产基础库必须固定为稳定版本，不能长期使用 `trial`。
- 业务代码统一使用 JavaScript，不引入 TypeScript 或跨端应用框架。
- Vant Weapp 必须固定版本、按需注册；确认设计稿优先于组件默认样式。
