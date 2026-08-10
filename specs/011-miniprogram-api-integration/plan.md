# Implementation Plan: 小程序前后端 API 集成与 Mock 替换

**Branch**: `api-link` | **Date**: 2026-08-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-miniprogram-api-integration/spec.md`

## Summary

在不修改 `backend/` 业务逻辑、不重做已确认 UI 的前提下，将 `miniProgram/` 从演示数据驱动改造成真实 API 驱动的小程序。实施采用“统一请求基础设施 → 真实会话 → P1 页面纵向切片 → P2 辅助功能 → 生产 Mock 门禁”的顺序：

- 新建小程序统一请求层，集中处理环境地址、统一响应包、Bearer Token、单飞刷新、超时、错误分类、幂等标识和安全日志。
- 将真实会话与 `mock/demo-control.js` 完全隔离，登录、微信绑定、恢复会话和退出登录只读写真实会话存储。
- 每个业务域建立轻量 API service 和纯数据适配函数，页面保留现有 WXML/WXSS 与交互模型，替换固定数据源。
- 以 004（登录/组织）、008（绩效）、009（消费金额）为新契约优先级，001 仅作为未被覆盖的基础契约。
- 后端不匹配全部登记在 [page-api-matrix.md](contracts/page-api-matrix.md)；前端只实现安全、可追踪的适配。需要后端权限或字段修正的能力标记为阻塞，不在前端伪造成功。

## Technical Context

**Language/Version**: JavaScript（微信原生小程序；CommonJS）
**Primary Dependencies**: 微信原生 API、WXML、WXSS、Glass-easel、Vant Weapp 1.11.7、ECharts for WeChat
**Storage**: 微信本地存储，仅保存 Token、非敏感会话摘要、开发环境开关；业务数据以后端为准
**Testing**: Node `node:test` + `assert/strict`；小程序 API 通过可注入 `wx` stub 测试；微信开发者工具与真机联调
**Target Platform**: 微信小程序，微信基础库 3.17.0；iOS/Android 微信客户端
**Project Type**: 独立客户端模块（`miniProgram/`），仅消费现有 `/api/v1` REST API
**Performance Goals**: 首屏请求不串行加载非关键数据；列表一次 20 条；交互请求 10 秒内进入成功或受控失败；避免同端点重复并发
**Constraints**: 不修改 `backend/`；不直连数据库、哈尔滨儒泰或 COS 密钥；生产禁用 Mock；敏感数据不落日志；金额使用整数分
**Scale/Scope**: 23 个注册页面，其中约 18 个需要真实 API；当前 3 个局部 API service，需覆盖登录、工作台、客户、绑定、消费、绩效、资料、隐私、反馈、推广码与通知

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| 原则 | 结论 | 本计划落实方式 |
|------|------|----------------|
| I. TDD | ✅ PASS | 每个 service/adapter 先写失败测试；请求层覆盖刷新、错误、幂等和并发；P1 旅程提供集成测试 |
| II. API-First | ✅ PASS | 页面不直接拼接接口；先冻结页面—接口矩阵；字段冲突先登记，不通过页面假数据掩盖 |
| III. Separation of Concerns | ✅ PASS | 仅改 `miniProgram/`；页面负责交互，service 负责请求，adapter/model 负责 DTO→ViewModel；不复制后端业务算法 |
| IV. Database Integrity | ✅ PASS | 小程序不接数据库；敏感信息只使用后端脱敏值；Token 与敏感字段不写日志或页面快照 |
| V. Simplicity | ✅ PASS | 使用一个请求层和按域 service；不引入新框架、状态库或第三方 HTTP 依赖 |

**边界检查**：已发现的后端差异仅记录为 `B-*` 阻塞项。本计划和后续 tasks 不得包含 `backend/`、数据库迁移或后端测试文件修改。

Gate 结果：**通过**。Phase 1 设计复查后仍通过，无 Constitution 违规项。

## Project Structure

### Documentation (this feature)

```text
specs/011-miniprogram-api-integration/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   └── page-api-matrix.md
└── tasks.md                 # /speckit-tasks 阶段生成
```

### Source Code (`miniProgram/` only)

```text
miniProgram/
├── config/
│   └── env.js                       # local/trial/production API 配置与 Mock 门禁
├── services/
│   ├── request-service.js           # 统一包、Token、刷新、超时、错误、幂等
│   ├── auth-service.js              # 收敛既有登录并补 session/refresh/logout
│   ├── session-service.js           # 真实会话，不再依赖 demo-control
│   ├── workbench-service.js
│   ├── customer-service.js
│   ├── binding-service.js
│   ├── consumption-service.js
│   ├── profile-service.js
│   ├── compliance-service.js
│   ├── promotion-service.js
│   ├── feedback-service.js
│   ├── notification-service.js
│   ├── commission-service.js        # 迁移至统一请求层
│   └── org-performance-service.js   # 迁移至统一请求层
├── models/
│   ├── api-error.js                 # 可展示/可重试错误模型
│   ├── session.js                   # 真实会话规范化与入口映射
│   └── existing domain models       # 增加纯 DTO→ViewModel 适配，保留校验
├── utils/
│   ├── money.js                     # 整数分→元展示
│   ├── date-time.js                 # ISO 时间→页面格式
│   └── request-key.js               # 业务提交幂等标识
├── pages/                            # 只替换数据加载/提交和状态，不重做 UI
└── tests/
    ├── contract/                    # 响应包与 DTO adapter 契约
    ├── integration/                 # 登录、客户、绑定、消费纵向旅程
    └── unit/                        # request/session/service/model
```

**Structure Decision**: 保留微信原生小程序现有分层，以一个共享请求层消除三个既有 service 的重复 `wx.request`。按业务域拆 service 是因为每个域有多个页面或动作；DTO 适配继续放在纯 JavaScript model/adapter 中以便 Node 测试。所有生产修改限定在 `miniProgram/`，规格文档限定在本功能目录。

## Implementation Phases

### Phase 0 — Contract freeze and blockers

1. 以 [page-api-matrix.md](contracts/page-api-matrix.md) 为唯一联调清单。
2. 对 `B-*` 差异获取后端负责人确认：可用、后端待修或本期延期。
3. 阻塞项未解决前，相关页面只能展示“暂不可用/接口不匹配”的真实状态，不允许接回 Mock。

### Phase 1 — Shared request and session foundation

1. 环境配置：本地、体验、生产；生产 Mock 强制关闭。
2. 请求层：统一响应校验、授权头、超时、错误类型、请求取消/过期响应保护、幂等头。
3. 单飞 Token 刷新：并发 401 共用一次刷新；失败统一清理并跳转登录。
4. 真实 Session：移除生产路径对 `lutai_demo_session` 的读取，支持账户切换清理。

### Phase 2 — P1 vertical slices

1. **US1 登录会话**：手机号密码 → 微信绑定 → session 恢复 → refresh → logout。
2. **US2 工作台/我的**：workbench、account-summary、真实入口权限。
3. **US3 客户/绑定**：列表、详情、跟进、绑定列表/详情/提交；受后端权限阻塞的子资源不提前上线。
4. **US4 消费/绩效**：overview、trend、bills、个人/组织 commission；金额统一按分转换。

### Phase 3 — P2 auxiliary slices

1. 个人资料与头像（受 `B-001` 阻塞的保存动作延后）。
2. 协议、隐私设置、推广码、反馈和通知。
3. 资质功能受 `B-006` 阻塞：本计划只保留前端接入位，不新增假接口。

### Phase 4 — Mock gate and acceptance

1. 扫描生产页面对 `mock/`、固定客户/账单/账户记录的运行时引用并清零。
2. 自动化测试、微信开发者工具、真机、弱网、账户切换和重复点击验证。
3. 输出后端差异最终状态与未上线页面清单，不以“前端完成”掩盖后端阻塞。

## Testing Strategy

- **TDD 顺序**：adapter/request/session 测试先红，再实现；页面接线前先完成对应 service 契约测试。
- **请求层单测**：统一包成功/业务失败/HTTP 失败/超时、Header、刷新成功/失败、并发 401、幂等、敏感日志。
- **Service 契约测试**：验证 path、method、query/body/header 和 DTO 最小必填字段；不调用真实生产数据。
- **页面集成测试**：用 stub service 驱动 loading/success/empty/error/forbidden，并验证过期响应不覆盖新条件。
- **端到端手测**：使用后端提供的脱敏测试账户执行 quickstart；后端阻塞项只验证受控失败。
- **回归**：保留现有 Node 单测；每完成一个纵向切片运行小程序全量测试。

## Backend Mismatch Policy

1. 每个差异使用稳定 ID `B-001...`，记录证据、影响页面、安全级别和期望契约。
2. 前端允许的适配仅包括字段重命名、空值规范化、枚举映射、日期格式化和整数分展示。
3. 前端禁止补偿权限缺失、伪造后端状态、推算服务端业务金额、返回未脱敏数据或静默读取 Mock。
4. 若差异影响权限、敏感数据、持久化或核心业务语义，相关能力标记为阻塞并交由后端负责人处理。
5. 后端修复不在 `api-link` 的实施范围；前端只在修复后的契约可验证时解除阻塞。

## Complexity Tracking

无 Constitution 违规项。统一请求层是多个现有 `wx.request` 和全部待接页面的真实复用需求；按域 service 与纯 adapter 是当前页面数量所需的最小分层，不引入额外框架。
