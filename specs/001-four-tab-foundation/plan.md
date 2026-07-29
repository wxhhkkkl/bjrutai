# Implementation Plan: 四 Tab 基础工程与角色工作台

**Branch**: `001-four-tab-foundation` | **Date**: 2026-07-27 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-four-tab-foundation/spec.md`

## Summary

在现有原生微信小程序骨架上建立可扩展的四 Tab 应用外壳，使用模拟角色和摘要数据
完成角色工作台、导航、公共设计变量、页面状态和主操作路由的独立验收。业务 API 和
二级页面完整实现留给后续规格。

## Technical Context

**Language/Version**: JavaScript ES6、WXML、WXSS

**Primary Dependencies**: 微信小程序原生运行时、Skyline、glass-easel；
Vant Weapp（`@vant/weapp@1.11.6`）用于首页的图标组件，按页面注册并在微信开发者工具构建 npm

**Storage**: 微信本地存储，仅保存模拟角色、Tab 状态和非敏感演示偏好

**Testing**: Node 内置测试用于纯函数与契约；微信开发者工具用于页面和设备验收

**Target Platform**: iOS 与 Android 微信小程序

**Project Type**: 原生移动小程序

**Performance Goals**: 一级页面切换无明显阻塞；首次可交互时间不超过 2 秒（本地模拟数据）

**Constraints**: 原生微信小程序、仅使用 JavaScript、四 Tab、微信胶囊安全区、
44 点触控、脱敏模拟数据、稳定基础库

**Scale/Scope**: 4 个一级页面、账户/角色/资质入口状态、5 类公共页面状态和通用占位页

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1.*

- [x] Specification links requirements to PRD, confirmed UI, and page flow.
- [x] Confirmed UI will be implemented as components, not screenshot backgrounds.
- [x] Privacy, masking, authorization, and medical-scope boundaries are documented.
- [x] Loading, empty, success, error, and permission states are identified.
- [x] Binding state semantics are outside this feature and remain governed by the constitution.
- [x] Acceptance checks cover routing, safe areas, touch targets, and text overflow.
- [x] Native WXML/WXSS/JavaScript and Skyline remain the application architecture;
      TypeScript and cross-platform frameworks are not introduced.
- [x] Vant Weapp is limited to `@vant/weapp@1.11.6` 的 `icon` 组件；已记录 npm
      安装、按页面注册和微信开发者工具构建步骤。
- [x] No dependency other than the constitution-approved optional Vant Weapp is introduced.
- [x] A task is included to replace `trial` with a stable pinned base-library version.

## Project Structure

### Documentation

```text
specs/001-four-tab-foundation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── navigation-contract.md
│   └── view-model-contract.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code

```text
app.js
app.json
app.wxss
custom-tab-bar/
components/
├── app-icon/
├── page-state/
├── status-tag/
└── navigation-bar/
pages/
├── index/
├── home/
├── customers/
├── contribution/
├── profile/
├── auth/
│   ├── login/
│   └── profile-setup/
├── qualification/
│   └── status/
└── common/
    └── feature-placeholder/
services/
├── navigation-service.js
└── session-service.js
models/
├── navigation.js
└── view-state.js
mock/
└── foundation-fixtures.js
└── demo-control.js
utils/
assets/
├── icons/
└── images/
tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**: 保留微信原生单工程结构；使用根级自定义 Tab Bar，
一级页面按业务域拆分，共享状态、会话和路由逻辑独立放入 `components/`、`services/`
和 `models/`。

## Phase 0: Research Decisions

研究结论见 [research.md](research.md)。所有技术未知项已解决，无遗留
`NEEDS CLARIFICATION`。

## Phase 1: Design and Contracts

- 数据模型见 [data-model.md](data-model.md)。
- 导航契约见 [contracts/navigation-contract.md](contracts/navigation-contract.md)。
- 页面数据契约见 [contracts/view-model-contract.md](contracts/view-model-contract.md)。
- 端到端验收步骤见 [quickstart.md](quickstart.md)。

## Post-Design Constitution Re-check

- [x] 设计继续使用原生小程序与 JavaScript，无跨端框架。
- [x] 首页按需使用 Vant Weapp 的 `icon` 组件，不替代确认稿的版式与品牌视觉。
- [x] 角色、账户、资质与 Tab 路由均有明确契约。
- [x] 模拟数据与页面状态不包含真实个人信息。
- [x] UI 验收与安全区检查已进入 quickstart 和 tasks。
- [x] 后续业务 API 被明确排除，避免基础工程规格膨胀。

## Complexity Tracking

无 Constitution 违规，不需要复杂度豁免。
