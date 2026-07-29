# Research: 四 Tab 基础工程与角色工作台

## Decision 1: 继续使用原生微信小程序

**Decision**: 保持 WXML、WXSS、JavaScript、Skyline 和 glass-easel，不引入
TypeScript 或跨端应用框架。

**Rationale**: 当前工程已经是原生骨架；功能规模不需要跨端框架，原生能力更容易处理
微信胶囊、安全区、自定义 Tab Bar 和小程序生命周期。

**Alternatives considered**:

- Taro/React：会增加构建链和运行时抽象，当前没有跨端需求。
- uni-app/Vue：同样引入额外工程转换，无法证明收益。

## Decision 2: 使用自定义 Tab Bar

**Decision**: 使用微信自定义 Tab Bar 承载首页、客户、贡献、我的四个入口。

**Rationale**: 已确认设计对选中图标、颜色、间距和安全区有明确要求，系统默认 Tab Bar
无法完整匹配。

**Alternatives considered**:

- 默认 Tab Bar：实现更快，但视觉自由度不足。
- 页面内模拟 Tab：会破坏原生 Tab 生命周期和返回行为。

## Decision 3: 基础工程只使用模拟数据

**Decision**: 本功能通过集中式模拟会话和页面摘要完成验收，不接真实接口。

**Rationale**: 角色、导航和 UI 基础可以独立验证，避免接口不稳定阻塞前端骨架。

**Alternatives considered**:

- 直接接入登录和业务接口：范围过大，无法独立交付。
- 在各页面散落硬编码数据：不利于切换状态和后续替换。

## Decision 4: 纯逻辑使用 Node 内置测试

**Decision**: 路由、角色映射、脱敏和状态转换使用无运行时依赖的 Node 测试；
页面表现使用微信开发者工具验收。

**Rationale**: 当前没有包管理配置，内置测试足以覆盖纯函数，并遵守最小依赖原则。

**Alternatives considered**:

- 引入 Jest：生态成熟，但对当前基础阶段过重。
- 完全手工测试：无法稳定回归角色和路由映射。

## Decision 5: 固定稳定基础库

**Decision**: 开发开始前在微信开发者工具中选择团队支持的稳定基础库，并将
`project.config.json` 的 `libVersion` 从 `trial` 改为具体版本。

**Rationale**: `trial` 会随环境变化，无法形成可重复验收基线。

**Alternatives considered**:

- 保留 `trial`：短期省事，但可能产生不可复现行为。
- 直接猜测版本号：没有经过本地开发者工具验证，不可靠。

## Decision 6: 允许按需使用 Vant Weapp

**Decision**: Vant Weapp（npm 包 `@vant/weapp`）作为唯一预批准的第三方 UI
组件库，但当前四 Tab 基础功能不需要立即安装。后续功能只有在计划明确列出所需组件后
才引入，并固定版本、按页面注册组件、记录微信开发者工具的 npm 构建步骤。

**Rationale**: 标准弹窗、轻提示、加载、选择器等成熟组件可以降低重复实现和交互一致性
风险；业务页面布局、品牌视觉和自定义 Tab 仍由原生 WXML/WXSS 按确认稿实现。

**Alternatives considered**:

- 全量默认引入 Vant Weapp：会增加包体和样式覆盖成本，且当前基础功能无法证明需要。
- 完全禁止 UI 库：后续标准交互会产生不必要的重复开发。
- 使用其他 UI 库：不在当前批准的技术栈内，需要单独修改 Constitution。

## Decision 7: 使用受控 Mock 状态完成页面验收

**Decision**: 通过 `mock/demo-control.js` 定义仅开发环境可用的本地状态控制键，
在不编辑页面源码的前提下切换角色、账户/资质状态和五种一级页面状态。

**Rationale**: 这使角色分流、空态、错误态和无权限状态可以重复演示，同时不引入
真实接口、真实个人信息或生产调试入口。

**Alternatives considered**:

- 在每个页面手工修改模拟常量：无法满足“无需修改代码即可演示”的验收标准。
- 增加面向普通用户的调试开关：会污染生产体验并存在误用风险。
