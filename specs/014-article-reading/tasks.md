# Tasks: 小程序文章资讯与阅读

**Input**: Design documents from `/specs/014-article-reading/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 项目 Constitution 强制 TDD。每个故事的测试任务必须先运行并确认因目标能力缺失而失败，再开始对应实现；不得先写页面后补测试。

**Organization**: 任务按用户故事分组。四个故事均为 P1，但为避免入口指向未完成页面，推荐技术顺序为“详情 → 列表 → 我的入口 → 首页入口”。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 前置依赖完成后可与同阶段其他标记任务并行，且不会修改同一文件
- **[Story]**: 对应 `spec.md` 用户故事 US1–US4
- 每项任务包含明确仓库相对路径

---

## Phase 1: Setup (Shared Baseline)

**Purpose**: 固定文章后端和小程序现有行为基线，避免将旧失败误判为本功能回归。

- [x] T001 在修改业务代码前运行后端现有文章合同/集成测试与小程序现有全量测试，记录实际命令和环境偏差到 `specs/014-article-reading/quickstart.md`
- [ ] T002 核对管理端准备的验收文章只使用测试内容，并确认封面/正文图片域名在开发环境可访问，按 `specs/014-article-reading/quickstart.md` 建立已发布、草稿、下架、无封面和富文本样本

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立所有入口和页面共同使用的公开请求、数据适配与分页规则。

**⚠️ CRITICAL**: 本阶段完成前不得开始页面实现。

### Foundational tests (write and fail first)

- [x] T003 [P] 为列表项/详情适配、合法 ID、缺省字段、发布时间、浏览量、published 校验、分页去重和游标异常编写失败单元测试 `miniProgram/tests/unit/article.test.js`
- [x] T004 [P] 为公开列表 `limit/cursor/auth:false`、详情路径、统一响应、404 和 malformed 边界编写失败合同测试 `miniProgram/tests/contract/article-api-contract.test.js`

### Foundational implementation

- [x] T005 [P] 实现 ArticleListItem、ArticleDetail、ArticlePage 适配、日期展示、正整数 ID 校验和按 articleId 分页去重 `miniProgram/models/article.js`
- [x] T006 [P] 通过现有 request-service 实现公开文章列表和详情客户端，显式使用 `auth:false` 且不提供 Mock 回退 `miniProgram/services/article-service.js`
- [x] T007 运行 T003/T004 测试并确认转绿，同时运行 `miniProgram/tests/contract/request-service-contract.test.js` 验证统一请求层无回归

**Checkpoint**: 页面可复用统一 service/model 获取并适配现有公开文章契约，游标、可见性和错误边界已固定。

---

## Phase 3: User Story 4 - 阅读文章富文本详情 (Priority: P1)

**Goal**: 用户可打开一篇当前已发布文章，阅读移动端适配的元信息、封面和安全富文本，并正确处理无效 ID、404 与网络错误。

**Independent Test**: 直接使用合法文章详情地址打开富文本文章，验证只请求一次、浏览量使用服务端值、宽图不溢出；再验证无效 ID 不发请求、已下架 404 不泄露旧正文、网络失败可重试。

### Tests for User Story 4 (write and fail first)

- [x] T008 [P] [US4] 为详情参数校验、首次单次加载、重试、迟到响应丢弃、404 清空旧正文和服务端浏览量编写失败流程测试 `miniProgram/tests/integration/article-reading-flow.test.js`
- [x] T009 [P] [US4] 为详情页注册、flow-navigation、page-state、安全 rich-text、禁止 web-view 与底部安全区编写失败页面合同测试 `miniProgram/tests/contract/page-framework-contract.test.js`

### Implementation for User Story 4

- [x] T010 [US4] 在 `miniProgram/app.json` 注册 `/pages/article-detail/index`，并配置二级页依赖 `miniProgram/pages/article-detail/index.json`
- [x] T011 [US4] 实现详情 ID 校验、仅 onLoad/重试请求、requestVersion 隔离、not-found/recoverable-error 状态和返回动作 `miniProgram/pages/article-detail/index.js`
- [x] T012 [P] [US4] 实现标题、元信息、封面、摘要、空正文和原生安全富文本结构 `miniProgram/pages/article-detail/index.wxml`
- [x] T013 [P] [US4] 实现移动端阅读排版、标题层级、正文行高、图片最大宽度、错误状态和 safe-area `miniProgram/pages/article-detail/index.wxss`
- [ ] T014 [US4] 运行 US4 流程/页面合同/文章单元测试，并按 quickstart D/E 场景在微信开发者工具验证富文本、宽图、404、重试和单次请求

**Checkpoint**: 文章详情可通过直接地址独立验收，未发布/不存在内容不可读，富文本不会执行主动内容。

---

## Phase 4: User Story 3 - 浏览文章列表并加载更多 (Priority: P1)

**Goal**: 用户可浏览按发布时间倒序的全部已发布文章，刷新和连续加载游标分页，分页失败时保留已有内容。

**Independent Test**: 用超过 20 篇已发布文章打开列表，连续触底直至结束并验证无重复遗漏；下拉刷新回到最新首屏；模拟首屏/分页失败、空结果和迟到响应。

### Tests for User Story 3 (write and fail first)

- [x] T015 [P] [US3] 扩展文章流程测试，覆盖首屏替换、游标追加、并发防护、重复 ID 去重、无进展游标停止、刷新丢弃旧响应和详情导航防连点 `miniProgram/tests/integration/article-reading-flow.test.js`
- [x] T016 [P] [US3] 为文章列表页注册、二级导航、下拉刷新、加载/空/首屏错误/分页错误/no-more 状态编写失败页面合同测试 `miniProgram/tests/contract/page-framework-contract.test.js`

### Implementation for User Story 3

- [x] T017 [US3] 在 `miniProgram/app.json` 注册 `/pages/articles/index`，配置二级页组件和下拉刷新 `miniProgram/pages/articles/index.json`
- [x] T018 [US3] 实现首屏、onPullDownRefresh、onReachBottom、游标分页、分页失败保留、requestVersion 隔离和详情防重复导航 `miniProgram/pages/articles/index.js`
- [x] T019 [P] [US3] 实现封面/占位、两行标题摘要、分类/日期元信息、完整卡片触控和各列表状态 `miniProgram/pages/articles/index.wxml`
- [x] T020 [P] [US3] 实现文章卡片、固定比例封面、窄屏截断、分页提示和底部安全区样式 `miniProgram/pages/articles/index.wxss`
- [ ] T021 [US3] 运行 US3 流程/页面合同/适配测试，并按 quickstart C 场景验证 50 篇连续分页、刷新、空状态、分页失败与返回位置

**Checkpoint**: 文章列表和详情构成可独立运行的只读内容链路，但用户可见入口尚未接入既有 Tab 页面。

---

## Phase 5: User Story 2 - 从“我的”页面进入文章中心 (Priority: P1)

**Goal**: 普通用户指定的服务宫格空位显示文章入口，组织管理员保留既有专属入口，二者均进入同一列表。

**Independent Test**: 普通用户进入“我的”看到完整 2×2 宫格并打开文章列表；组织管理员进入页面时组织业绩与文章资讯均存在，分隔线、文字和点击区域正确。

### Tests for User Story 2 (write and fail first)

- [x] T022 [P] [US2] 为 `article-list` action、目标页面注册、无额外 capability 和两入口共享路径编写失败导航合同测试 `miniProgram/tests/contract/navigation-contract.test.js`
- [x] T023 [P] [US2] 为普通用户 2×2 服务顺序、组织管理员保留组织业绩、文章文案和图标资源编写失败页面流程测试 `miniProgram/tests/integration/workbench-pages.test.js`

### Implementation for User Story 2

- [x] T024 [P] [US2] 制作与既有服务图标同尺寸/圆角/柔和底色的文章文档图标 `miniProgram/assets/images/profile-article-icon.png`
- [x] T025 [US2] 新增 `article-list` 导航 action 指向 `/pages/articles/index` 且不增加角色 capability `miniProgram/models/navigation.js`
- [x] T026 [US2] 在消费明细之后加入“文章资讯/阅读最新内容”服务项，保持普通用户指定空位和管理员多行宫格顺序 `miniProgram/pages/profile/index.js`
- [x] T027 [US2] 如多行管理员宫格暴露现有固定分隔线问题，仅做文章入口所需的最小网格边框适配 `miniProgram/pages/profile/index.wxss`
- [ ] T028 [US2] 运行导航/工作台页面测试，并按 quickstart B 在普通用户与组织管理员视口验证入口位置、图标、分隔线和跳转

**Checkpoint**: 用户可从“我的”稳定进入文章列表和详情，形成首个完整可演示 MVP。

---

## Phase 6: User Story 1 - 从首页发现并阅读最新文章 (Priority: P1)

**Goal**: 首页业务概览后展示最多 3 篇最新文章和“查看全部”，文章接口失败不影响工作台核心内容。

**Independent Test**: 首页分别模拟文章成功、空、超时、500 和迟到响应；成功时可打开详情/全部列表，其他情况下工作台、快捷服务、业务概览、通知和最近绑定保持正常。

### Tests for User Story 1 (write and fail first)

- [x] T029 [P] [US1] 为首页独立 articleState、`limit=3`、成功/空/错误、迟到响应和文章失败不改写主 state 编写失败集成测试 `miniProgram/tests/integration/workbench-pages.test.js`
- [x] T030 [P] [US1] 为“业务概览后、通知前”的文章区域、查看全部、条目详情参数和无大块空白编写失败页面合同测试 `miniProgram/tests/contract/page-framework-contract.test.js`

### Implementation for User Story 1

- [x] T031 [US1] 在首页增加独立 articleState/articleItems/articleStateMessage/articleRequestVersion，并与原工作台并行但隔离地调用列表 `limit=3` `miniProgram/pages/home/index.js`
- [x] T032 [US1] 在业务概览后实现文章标题行、查看全部、最多 3 个文章条目及局部空/错误展示 `miniProgram/pages/home/index.wxml`
- [x] T033 [US1] 实现与现有首页圆角、阴影、字号和触控层级一致的文章区域及窄屏截断 `miniProgram/pages/home/index.wxss`
- [ ] T034 [US1] 运行首页集成/页面合同/导航测试，并按 quickstart A 验证成功、空、失败、直接详情和查看全部，确认首页核心状态不受文章故障影响

**Checkpoint**: 首页与“我的”两个入口均接入统一文章列表/详情，四个用户故事完整可验收。

---

## Phase 7: Polish & Cross-Cutting Verification

**Purpose**: 完成安全、视觉、后端兼容与全量回归，不扩展产品范围。

- [x] T035 [P] 检查详情正文只使用原生安全富文本且没有 web-view/脚本执行路径，检查错误/日志不复制完整正文 `miniProgram/pages/article-detail/index.wxml`、`miniProgram/pages/article-detail/index.js`
- [x] T036 [P] 运行后端既有 `backend/tests/contract/test_articles.py` 与 `backend/tests/integration/test_article_flow.py`；若契约失败，先补失败测试并仅做 `specs/014-article-reading/contracts/api.md` 允许的最小修复
- [x] T037 运行小程序 unit/contract/integration 全量测试，修复本功能造成的导航、页面框架、请求或工作台回归 `miniProgram/tests/`
- [ ] T038 按已确认首页 v4、“我的”Tab v2 和 `contracts/ui-flow.md` 在 320px、375px、390px 代表视口检查安全区、普通/管理员宫格、长标题、无封面、宽图和自定义 TabBar
- [ ] T039 按 `specs/014-article-reading/quickstart.md` 完成端到端验收并记录无法自动验证的真机/合法域名项，不通过时不得标记功能完成
- [x] T040 更新 `specs/014-article-reading/tasks.md` 勾选真实完成项，确认 `git diff --check`、无凭证/真实敏感数据、无生成构建产物进入提交范围

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖。
- **Foundational (Phase 2)**: 依赖 Setup，完成后才能开始任何页面故事。
- **US4 Detail (Phase 3)**: 依赖 Foundational；详情是所有文章卡片的最终目标。
- **US3 List (Phase 4)**: 依赖 Foundational 和 US4，列表条目才能进入可用详情。
- **US2 Profile Entry (Phase 5)**: 依赖 US3，避免用户入口指向未完成列表；形成第一个完整 MVP。
- **US1 Homepage (Phase 6)**: 依赖 US3/US4 和导航 action；最后接入以降低首页回归风险。
- **Polish (Phase 7)**: 依赖计划交付的全部故事。

### User Story Dependencies

```text
Foundational service/model
        │
        ▼
US4 文章详情
        │
        ▼
US3 文章列表
      ├────────► US2 我的入口 ──► MVP
      └────────► US1 首页入口
                         │
                         ▼
                    Full acceptance
```

### Within Each User Story

- 测试必须先编写并确认失败。
- 行为 JS 完成后再收敛 WXML/WXSS；不同文件可并行，但必须基于同一合同。
- 页面合同、单元/流程测试和独立人工验收全部通过后才能进入下一 Checkpoint。
- 联调发现后端差异时，以 `contracts/api.md` 为依据，未经失败合同测试不得修改后端逻辑。

---

## Parallel Opportunities

### Foundational

```text
并行 Red：T003 article model tests、T004 article API contract
并行 Green：T005 model、T006 service
```

### Detail / List

```text
US4 并行 Red：T008 flow、T009 page contract
US4 并行 UI：T012 WXML、T013 WXSS（T011 behavior 后对齐）
US3 并行 Red：T015 flow、T016 page contract
US3 并行 UI：T019 WXML、T020 WXSS（T018 behavior 后对齐）
```

### Entrances / Verification

```text
US2 并行 Red：T022 navigation、T023 profile flow
US1 并行 Red：T029 home integration、T030 page contract
Polish 并行：T035 security check、T036 backend regression
```

---

## Implementation Strategy

### MVP

1. 完成 Setup + Foundational。
2. 完成 US4 详情与 US3 列表。
3. 完成 US2“我的”入口。
4. 停止并独立验证“我的 → 列表 → 详情 → 返回”完整路径。

### Full delivery

1. 在 MVP 通过后实现 US1 首页最新文章与故障隔离。
2. 完成后端文章回归、小程序全量测试和确认设计视觉检查。
3. 使用后台发布/下架测试文章完成 quickstart 全链路。

### Scope guardrails

- 不修改后台文章管理 UI、数据库 schema 或发布流程。
- 不增加搜索、分类筛选、收藏、评论、分享、订阅或阅读历史。
- 不引入 WebView、第三方 HTML parser、全局 store 或正文持久化缓存。
- 不调用 `/admin/articles`，不在客户端推断发布状态、排序或浏览量。
- 不使用模拟文章掩盖接口失败。

---

## Notes

- `[P]` 只表示对应前置依赖完成后可并行，不表示可跳过 Red 阶段。
- 每个 Checkpoint 应形成可独立演示、测试和提交的逻辑切片。
- `profile-article-icon.png` 是唯一计划新增的视觉资源；不得重做既有页面图标体系。
- 任何未运行的真机、合法域名或远程图片检查必须在最终报告中明确列出。
