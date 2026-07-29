---
description: "四 Tab 基础工程与角色工作台实施任务"
---

# Tasks: 四 Tab 基础工程与角色工作台

**Input**: `specs/001-four-tab-foundation/`

**Prerequisites**: `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/`

## Phase 0: Pre-Implementation Analysis Gate

- [x] T001 [US1][US2][US3] 在 `specs/001-four-tab-foundation/spec.md`、`plan.md`、`tasks.md` 和 `contracts/` 运行 `$speckit-analyze`，修正阻断问题后再实施

## Phase 1: Setup

- [ ] T002 [US1][US2][US3] 在 `project.config.json` 固定经微信开发者工具验证的稳定基础库版本
- [ ] T003 [FR-006] 在 `assets/icons/.gitkeep`、`assets/images/.gitkeep`、`models/.gitkeep`、`services/.gitkeep`、`mock/.gitkeep`、`tests/contract/.gitkeep`、`tests/unit/.gitkeep` 创建基础目录标记
- [ ] T004 [P] [FR-006][FR-011] 在 `app.wxss` 建立颜色、字号、间距、圆角、阴影和安全区设计变量
- [ ] T005 [US1][US2][US3] 在 `README.md` 补充微信开发者工具导入、编译、稳定基础库和验证步骤

## Phase 2: Foundational

- [ ] T006 [FR-001][FR-003][FR-010][FR-013] 在 `models/navigation.js` 定义四 Tab、账户/角色/资质入口和路由目标常量
- [ ] T007 [P] [FR-007][SC-006] 在 `models/view-state.js` 定义五种公共页面状态及校验函数
- [ ] T008 [P] [FR-003][FR-008][FR-009] 在 `mock/foundation-fixtures.js` 建立无真实个人信息的账户、角色、资质和摘要模拟数据
- [ ] T009 [P] [FR-003][FR-007][SC-006] 在 `mock/demo-control.js` 和 `tests/unit/demo-control.test.js` 实现仅开发环境可用的模拟身份与页面状态切换
- [ ] T010 [FR-003][FR-012] 在 `services/session-service.js` 实现模拟会话读取、未激活/未知值降级和入口映射
- [ ] T011 [FR-001][FR-010][FR-013][SC-001][SC-007] 在 `services/navigation-service.js` 实现 Tab、二级目标、权限前置校验和重复点击保护
- [ ] T012 [P] [FR-007][SC-006] 在 `components/page-state/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现加载、空、错误和无权限公共组件
- [ ] T013 [P] [FR-006] 在 `components/status-tag/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现统一状态标签组件
- [ ] T014 [P] [FR-006][FR-011] 在 `components/app-icon/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现 1:1 大圆角方形图标容器
- [ ] T015 [FR-001][FR-003][FR-010][FR-013] 在 `tests/contract/navigation-contract.test.js` 校验四 Tab、账户/角色入口和路由契约

## Phase 3: User Story 1 - 按账户、角色与资质进入正确工作台 (P1)

**Goal**: 模拟身份进入拓展人首页、医生工作台、资质状态、资料补全或登录入口。

**Independent Test**: 按 quickstart Scenario 1 切换账户、角色和资质状态并重新编译。

- [ ] T016 [P] [US1][FR-003][FR-012] 在 `tests/unit/session-service.test.js` 编写账户激活、资料补全、角色与资质映射测试
- [ ] T017 [US1][FR-003][FR-012] 在 `pages/index/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现启动分流并处理损坏或未知模拟会话
- [ ] T018 [P] [US1][FR-003][FR-005][FR-006] 在 `pages/home/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现拓展人和医生一级工作台，以及即将过期续期提醒
- [ ] T019 [P] [US1][FR-003][FR-006][FR-011] 在 `pages/qualification/status/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现未激活、待审核、驳回和即将过期状态
- [ ] T020 [P] [US1][FR-012] 在 `pages/auth/login/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现登录授权占位页
- [ ] T021 [P] [US1][FR-012] 在 `pages/auth/profile-setup/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现首次资料补全占位页
- [ ] T022 [US1][FR-003][FR-012] 在 `app.json` 注册启动、首页、登录、资料补全和资质状态页面
- [ ] T023 [US1][SC-002] 按 `specs/001-four-tab-foundation/quickstart.md` 的 Scenario 1 完成账户、角色与资质入口验收

## Phase 4: User Story 2 - 四个一级页面稳定切换 (P1)

**Goal**: 首页、客户、贡献、我的可通过自定义 Tab Bar 一次点击切换。

**Independent Test**: 按 quickstart Scenario 2 遍历四个 Tab 和二级页返回。

- [ ] T024 [P] [US2][FR-001][FR-002][FR-011] 在 `custom-tab-bar/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现四项 Tab 和安全区适配
- [ ] T025 [P] [US2][FR-004][FR-006] 在 `pages/customers/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现无页面顶部导航的客户一级页
- [ ] T026 [P] [US2][FR-004][FR-006] 在 `pages/contribution/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现无页面顶部导航的贡献一级页
- [ ] T027 [P] [US2][FR-004][FR-006] 在 `pages/profile/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现无页面顶部导航的我的一级页
- [ ] T028 [US2][FR-001][FR-002] 在 `app.json` 注册自定义 Tab Bar、四个一级页面和路由顺序
- [ ] T029 [US2][FR-002][FR-010][SC-001] 在 `services/navigation-service.js` 补充当前 Tab 恢复和快速重复点击保护
- [ ] T030 [US2][SC-001][SC-002] 按 `specs/001-four-tab-foundation/quickstart.md` 的 Scenario 2 完成四 Tab 验收

## Phase 5: User Story 3 - 一致且安全的一级页面摘要 (P2)

**Goal**: 四个一级页面使用公共设计组件和模拟数据展示主要信息及状态。

**Independent Test**: 按 quickstart Scenario 3 和 Scenario 4 检查状态、视觉与隐私。

- [ ] T031 [P] [US3][FR-007][SC-006] 在 `tests/unit/view-state.test.js` 编写状态切换和错误降级测试
- [ ] T032 [P] [US3][FR-005][FR-006][FR-007][FR-008] 在 `pages/home/index.js`、`index.wxml`、`index.wxss` 接入首页摘要、Mock 状态和公共页面状态
- [ ] T033 [P] [US3][FR-004][FR-007][FR-008][FR-009] 在 `pages/customers/index.js`、`index.wxml`、`index.wxss` 接入客户摘要、脱敏数据和公共页面状态
- [ ] T034 [P] [US3][FR-004][FR-007][FR-008] 在 `pages/contribution/index.js`、`index.wxml`、`index.wxss` 接入贡献摘要和公共页面状态
- [ ] T035 [P] [US3][FR-004][FR-007][FR-008] 在 `pages/profile/index.js`、`index.wxml`、`index.wxss` 接入我的摘要和公共页面状态
- [ ] T036 [US3][FR-013][SC-007] 在 `services/navigation-service.js` 配置已确认主操作的明确目标和权限校验
- [ ] T037 [US3][FR-013][SC-007] 在 `pages/common/feature-placeholder/index.js`、`index.json`、`index.wxml`、`index.wxss` 实现可返回的“功能建设中”占位页
- [ ] T038 [US3][FR-006][FR-009][FR-011][FR-014][SC-003][SC-004][SC-005] 按 `specs/001-four-tab-foundation/quickstart.md` 的 Scenario 3 和 Scenario 4 完成状态、视觉、触控和隐私验收

## Phase 6: Polish and Cross-Cutting Concerns

- [ ] T039 [US1][US2][US3] 在 `README.md` 记录 Spec Kit 工作流和模拟状态切换方法
- [ ] T040 [US1][US2][US3] 运行 `tests/contract/navigation-contract.test.js`、`tests/unit/demo-control.test.js`、`tests/unit/session-service.test.js` 和 `tests/unit/view-state.test.js` 的 Node 内置测试并修复失败项
- [ ] T041 [US1][US2][US3][SC-003][SC-004] 按 `specs/001-four-tab-foundation/quickstart.md` 的 Scenario 4 在微信开发者工具中完成 iOS 与 Android 代表视口编译验收
- [ ] T042 [US3][FR-009][SC-005] 检查 `mock/foundation-fixtures.js`、`mock/demo-control.js`、`pages/home/index.wxml`、`pages/customers/index.wxml`、`pages/contribution/index.wxml` 和 `pages/profile/index.wxml`，确认不存在真实个人信息
- [ ] T043 [US1][US2][US3][SC-008] 按 `specs/001-four-tab-foundation/quickstart.md` 的 Scenario 5 记录四个一级页面首次可交互时间并修复可定位的阻塞项

## Dependencies

```text
Analysis Gate
  -> Setup
    -> Foundational
      -> US1 Role Entry
      -> US2 Four Tabs
        -> US3 Shared Summaries
          -> Polish
```

- US1 和 US2 在 Foundational 完成后可并行。
- US3 依赖一级页面和 Tab 骨架完成。
- MVP 范围为 Analysis Gate + Setup + Foundational + US1 + US2。

## Parallel Opportunities

- T004/T005 可并行。
- T007/T008/T009/T012/T013/T014 可并行。
- T018/T019/T020/T021 可并行。
- T024/T025/T026/T027 可并行。
- T031/T032/T033/T034/T035 可按文件并行。

## Format Validation

- 全部 43 项任务均包含复选框和连续任务 ID。
- 每项任务均包含用户故事或 FR/SC 需求追踪，以及具体文件或验收输入。
- 可并行任务使用 `[P]` 标记。
- T001 是已完成的实施前 Analyze 门禁；后续实现从 T002 开始。
