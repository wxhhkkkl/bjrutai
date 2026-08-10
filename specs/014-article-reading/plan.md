# Implementation Plan: 小程序文章资讯与阅读

**Branch**: `014-article-reading` | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/014-article-reading/spec.md`

## Summary

复用后端已经上线的公开文章列表与详情接口，在原生微信小程序中补齐文章发现、列表分页和富文本阅读链路。首页在“业务概览”之后新增独立加载的“文章资讯”区域，最多展示 3 篇最新发布文章；“我的—我的服务”增加稳定入口；新增文章列表与文章详情两个二级页面。

技术方案不修改后台管理端和文章数据库：小程序新增 article service 与纯数据适配模型，统一消费现有响应封装；列表使用服务端游标，详情用原生安全富文本容器展示后台 HTML。首页文章请求拥有独立状态和请求版本，失败不会改变工作台核心状态。具体数据契约见 [contracts/api.md](./contracts/api.md)，页面与导航约束见 [contracts/ui-flow.md](./contracts/ui-flow.md)。

## Technical Context

**Language/Version**: 微信小程序 JavaScript（CommonJS）/ WXML / WXSS；后端现状为 Python 3.11+，本功能原则上不修改后端  
**Primary Dependencies**: 微信小程序原生 SDK、原生富文本组件、Vant Weapp 1.11.7、现有 `request-service` / `page-state` / `flow-navigation`  
**Storage**: 小程序不新增持久化存储；文章、发布状态与浏览量继续由现有 MySQL 文章表管理  
**Testing**: Node.js `node:test`（小程序 unit/contract/integration）；pytest 文章合同测试作为既有后端回归  
**Target Platform**: 微信小程序 WebView 渲染器，代表性 iOS 与 Android 微信环境  
**Project Type**: Existing mobile mini-program consuming an existing REST API  
**Performance Goals**: 正常网络下文章列表/详情 95% 在 2 秒内出现内容或明确状态；首页文章请求不增加核心工作台完成时间；单页 20 条、首页 3 条  
**Constraints**: 只展示 published；统一响应封装；不执行正文脚本/事件/嵌入程序；正文图片不得横向溢出；不新增依赖、缓存正文、Mock 回退或后台管理改造  
**Scale/Scope**: 2 个既有入口页面改动、2 个新二级页面、1 个 service、1 个 adapter model、1 个文章入口图标；验收数据至少 50 篇，单篇正文最大沿用后端 100,000 字符限制

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Pre-design | Post-design | Evidence |
|-----------|------------|-------------|----------|
| I. TDD (NON-NEGOTIABLE) | PASS | PASS | 先写文章适配、服务合同、分页去重、导航和端到端阅读流的失败测试，再实现 service/model/pages；保留并运行后端现有文章合同测试。 |
| II. API-First Design | PASS | PASS | [contracts/api.md](./contracts/api.md) 固化现有公开列表/详情契约；小程序只消费 `/api/v1` 统一响应，不调用管理接口或数据库。 |
| III. Separation of Concerns | PASS | PASS | 发布状态、排序、分页和浏览量仍由后端决定；小程序 service 只发请求，model 只适配展示，page 只管理交互状态。 |
| IV. Database Integrity | PASS | PASS | 无 schema 或迁移变化；客户端不保存正文或用户阅读关系，不接触数据库凭证；只展示公开发布内容。 |
| V. Simplicity (YAGNI) | PASS | PASS | 不新增框架、HTML 解析依赖、全局 store、搜索/收藏/评论；直接使用既有请求层、原生富文本和两个页面。 |

**Gate result**: ALL PASS — Phase 0 research and Phase 1 design complete. No constitutional exception requires justification.

## Project Structure

### Documentation (this feature)

```text
specs/014-article-reading/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md
│   └── ui-flow.md
├── checklists/
│   └── requirements.md
└── tasks.md                     # /speckit.tasks 生成，本阶段不创建
```

### Source Code (planned changes)

```text
miniProgram/
├── app.json                                  # MODIFY: 注册文章列表和详情页面
├── assets/images/
│   └── profile-article-icon.png              # NEW: 与服务宫格一致的文章图标
├── models/
│   ├── article.js                            # NEW: 列表/详情适配、格式化、分页去重
│   └── navigation.js                         # MODIFY: article-list 导航目标
├── services/
│   └── article-service.js                    # NEW: 公开列表与详情请求
├── pages/
│   ├── home/
│   │   ├── index.js                          # MODIFY: 与工作台隔离地加载首页文章
│   │   ├── index.wxml                        # MODIFY: 业务概览后增加文章资讯区
│   │   └── index.wxss                        # MODIFY: 最新文章卡片样式
│   ├── profile/
│   │   └── index.js                          # MODIFY: 服务宫格增加文章入口
│   ├── articles/
│   │   ├── index.js                          # NEW: 首屏、游标分页、刷新、重试
│   │   ├── index.json                        # NEW: 二级页组件与下拉刷新
│   │   ├── index.wxml                        # NEW: 文章列表与状态
│   │   └── index.wxss                        # NEW: 移动端文章列表布局
│   └── article-detail/
│       ├── index.js                          # NEW: 参数校验、单次详情加载、重试
│       ├── index.json                        # NEW: 二级页组件
│       ├── index.wxml                        # NEW: 元信息、封面、安全富文本
│       └── index.wxss                        # NEW: 阅读排版和图片适配
└── tests/
    ├── unit/
    │   └── article.test.js                   # NEW: 适配、日期、缺省值、去重
    ├── contract/
    │   ├── article-api-contract.test.js      # NEW: 路径、查询、响应边界
    │   ├── navigation-contract.test.js       # MODIFY: 新页面和 action
    │   └── page-framework-contract.test.js   # MODIFY: 二级页导航/状态约束
    └── integration/
        ├── article-reading-flow.test.js      # NEW: 首页/我的→列表→详情主链路
        └── workbench-pages.test.js           # MODIFY: 文章失败不拖垮首页

backend/tests/
├── contract/test_articles.py                 # EXISTING: 回归公开可见性/分页/详情
└── integration/test_article_flow.py          # EXISTING: 回归发布与下架闭环
```

**Structure Decision**: 变更集中在现有 `miniProgram/`，不建立新应用或共享包。后端现有 `articles.py` 和 `article_service.py` 已满足契约，只有联调证明实际响应违约时才允许做最小后端修复，并先更新合同测试。

## Implementation Sequence

1. **合同与适配 Red**：先增加公开文章 service 合同测试和 article model 单元测试，覆盖统一响应、缺省字段、非法 ID、列表分页与去重。
2. **请求与模型 Green**：实现 `article-service.js` 与 `models/article.js`，列表请求显式 `auth:false`，游标视为不透明值，禁止 Mock 回退。
3. **稳定入口 Red → Green**：先扩展导航合同，再注册两页、增加 `article-list` action，并在“我的”服务宫格加入文章入口。
4. **文章列表 Red → Green**：实现加载、空、错误、刷新、追加和分页错误保留；用请求版本阻止迟到响应覆盖刷新结果。
5. **文章详情 Red → Green**：只在 `onLoad` 或用户重试时请求详情；校验文章 ID，渲染安全富文本，处理 404/网络失败并防重复导航。
6. **首页隔离集成**：增加独立 `articleState/articleItems/articleRequestVersion`；工作台成功不等待文章，文章失败不改写首页 `state`。
7. **视觉与全量回归**：按确认设计复核首页和“我的”布局，在 iOS/Android 代表视口检查安全区、文字截断、图片宽度和返回位置；运行小程序全量测试及后端既有文章回归。

## Complexity Tracking

*(No violations — table intentionally empty.)*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
