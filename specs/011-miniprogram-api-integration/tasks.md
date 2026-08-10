# Tasks: 小程序前后端 API 集成与 Mock 替换

**Input**: Design documents from `/specs/011-miniprogram-api-integration/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [page-api-matrix.md](contracts/page-api-matrix.md), [quickstart.md](quickstart.md)

**Scope boundary**: 所有生产代码任务只允许修改 `miniProgram/`。不得修改 `backend/`、数据库迁移或后端测试。发现不匹配时更新 `contracts/page-api-matrix.md` 的 `B-*` 记录并保持前端受控门禁。

**Tests**: Constitution I 强制 TDD。每组生产代码前必须先完成对应测试任务并确认失败，再写最小实现使其通过。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可在不同文件上并行，不依赖未完成任务
- **[US1-US6]**: 对应 spec.md 用户故事
- **[BLOCKED]**: 只实现前端安全门禁/错误状态；后端依赖解除前不得伪造成功

## Phase 1: Setup — 环境、格式化与测试骨架

**Purpose**: 建立前端联调所需的环境配置和纯工具，不接业务页面。

- [x] T001 [P] Add failing environment contract tests for local/trial/production API base, HTTPS requirement and production Mock prohibition in `miniProgram/tests/unit/env.test.js`
- [x] T002 Implement explicit environment resolution and Mock gate in `miniProgram/config/env.js`, then update `miniProgram/app.js` to expose resolved non-secret config instead of hard-coded `apiBase`
- [x] T003 [P] Add failing integer-cent/date formatting tests covering zero, negative refund, large values, invalid dates and timezone display in `miniProgram/tests/unit/money.test.js` and `miniProgram/tests/unit/date-time.test.js`
- [x] T004 Implement integer-cent-only display helpers and ISO display formatting in `miniProgram/utils/money.js` and `miniProgram/utils/date-time.js`
- [x] T005 [P] Add failing API error normalization tests for NETWORK/TIMEOUT/AUTH/FORBIDDEN/NOT_FOUND/CONFLICT/VALIDATION/SERVER/MALFORMED in `miniProgram/tests/unit/api-error.test.js`
- [x] T006 Implement safe `ApiError` normalization without request/body/token leakage in `miniProgram/models/api-error.js`
- [x] T007 Document Node 18+ test command, WeChat project root and environment selection in `miniProgram/README.md`

**Checkpoint**: 环境与纯工具可独立测试，生产配置无法启用 Mock。

---

## Phase 2: Foundational — 统一请求与真实会话（阻塞所有用户故事）

**Purpose**: 所有页面接入前必须完成的请求、Token、会话和数据边界。

**⚠️ CRITICAL**: Phase 2 完成前不得把业务页面切换到真实接口。

### Tests first

- [x] T008 [P] Add failing request contract tests for URL construction, methods, query/body, unified envelope, Bearer header and malformed responses in `miniProgram/tests/contract/request-service-contract.test.js`
- [x] T009 [P] Add failing request failure tests for HTTP errors, business codes, timeout, network failure and safe requestId propagation in `miniProgram/tests/unit/request-service.test.js`
- [x] T010 [P] Add failing single-flight refresh tests covering concurrent 401, one retry only, rotated token pair, refresh failure and one login redirect in `miniProgram/tests/unit/request-refresh.test.js`
- [x] T011 [P] Add failing idempotency tests for stable key reuse after unknown result and new key after explicit restart in `miniProgram/tests/unit/request-key.test.js`
- [x] T012 [P] Add failing real-session tests for atomic token storage, normalization, logout/account-switch cleanup and Demo-key isolation in `miniProgram/tests/unit/real-session.test.js`
- [x] T013 [P] Add failing production-boundary contract test that rejects direct `wx.request` calls outside the shared request service in `miniProgram/tests/contract/api-boundary-contract.test.js`

### Implementation

- [x] T014 Implement shared Promise-based request client with envelope validation, timeout, safe errors, Bearer injection and one retry hook in `miniProgram/services/request-service.js`
- [x] T015 Implement single-flight refresh coordination and terminal auth callback in `miniProgram/services/request-service.js`, using refresh functions exposed by `miniProgram/services/auth-service.js`
- [x] T016 Implement stable client-generated idempotency keys and unknown-result reuse in `miniProgram/utils/request-key.js`
- [x] T017 Refactor `miniProgram/services/session-service.js` to use real-session storage keys and normalized `ClientSession`, removing its production import of `miniProgram/mock/demo-control.js`
- [x] T018 Refactor `miniProgram/services/auth-service.js` to use the shared request client and expose distributorLogin/wechatLogin/bindWechat/getSession/refresh/logout/phoneBind without its own `wx.request`
- [x] T019 Migrate `miniProgram/services/commission-service.js` and `miniProgram/services/org-performance-service.js` to the shared request client without changing their public page-facing behavior
- [x] T020 Add explicit development-only Demo entry isolation in `miniProgram/mock/demo-control.js` and startup routing; production startup must ignore Demo storage and never fall back after API failure
- [x] T021 Align the two stale contribution page assertions in `miniProgram/tests/contract/page-framework-contract.test.js` with 009 (composition and category filter were removed), then run all Phase 1-2 tests plus existing unit/contract tests and fix only front-end regressions

**Checkpoint**: 所有真实 API 只能经过共享请求层；Token 刷新和真实会话可独立验收。

---

## Phase 3: User Story 1 — 真实登录与可靠会话 (Priority: P1) 🎯 MVP

**Goal**: 已创建的分销员可完成手机号登录、首次微信绑定、微信快捷登录、会话恢复和退出。

**Independent Test**: 按 quickstart Scenario A/B 完成全流程，关闭 Mock 后仍工作；刷新失败只回登录一次。

### Tests first

- [x] T022 [P] [US1] Add failing auth service contract tests for all seven mini-program auth endpoints, request bodies and token replacement in `miniProgram/tests/contract/auth-api-contract.test.js`
- [x] T023 [P] [US1] Add failing integration test for phone login → requires binding → bind WeChat → home in `miniProgram/tests/integration/auth-binding-flow.test.js`
- [x] T024 [P] [US1] Add failing integration tests for bound-user WeChat login, startup session restore, invalid refresh and logout cleanup in `miniProgram/tests/integration/auth-session-flow.test.js`
- [x] T025 [P] [US1] Extend session normalization tests for promoter/distributor role names, conservative missing-orgRole handling and no stale admin capability in `miniProgram/tests/unit/session-service.test.js`

### Implementation

- [x] T026 [US1] Wire `miniProgram/pages/auth/login/index.js` to the unified auth service, preserve form input on retry and remove any Demo success path
- [x] T027 [US1] Wire `miniProgram/pages/auth/bind-wechat/index.js` to rotated tokens and a verified real session before switching Tab
- [x] T028 [US1] Update `miniProgram/pages/index/index.js` to restore real session, attempt refresh when appropriate and route once without Demo identity
- [x] T029 [US1] Handle B-002 conservatively in `miniProgram/services/session-service.js`: never infer org admin from stale/default values; expose a diagnosable limited session state until backend contract is confirmed
- [x] T030 [US1] Handle B-008 in `miniProgram/pages/auth/profile-setup/index.js`: show a controlled onboarding-unavailable state for a new WeChat-only User instead of persisting a fake distributor profile
- [x] T031 [US1] Replace Demo logout in `miniProgram/pages/profile/index.js` with server logout plus unconditional local session/cache cleanup and one `reLaunch`
- [ ] T032 [US1] Execute quickstart Scenario A/B with test accounts and record B-002/B-008 outcomes in `specs/011-miniprogram-api-integration/contracts/page-api-matrix.md`

**Checkpoint**: 普通已建档分销员真实登录闭环独立可用；组织管理员冷启动能力如仍受 B-002 影响则保持受控限制。

---

## Phase 4: User Story 2 — 工作台与个人中心真实数据 (Priority: P1)

**Goal**: 首页和我的页使用真实账户摘要、工作台指标、通知摘要和最近绑定数据。

**Independent Test**: 普通分销员登录后首页与我的页数值和后端一致；断网不显示固定 36/演示金额。

### Tests first

- [x] T033 [P] [US2] Add failing workbench service contract tests for workbench/notices/recent-bindings/contribution-summary/account-summary in `miniProgram/tests/contract/workbench-api-contract.test.js`
- [x] T034 [P] [US2] Add failing workbench DTO adapter tests for role variants, amount cents, empty lists and unknown fields in `miniProgram/tests/unit/workbench-adapter.test.js`
- [x] T035 [P] [US2] Add failing page integration tests for loading/success/empty/error/forbidden and stale response protection in `miniProgram/tests/integration/workbench-pages.test.js`

### Implementation

- [x] T036 [P] [US2] Implement typed workbench/account-summary calls in `miniProgram/services/workbench-service.js`
- [x] T037 [P] [US2] Implement pure backend DTO → existing home/profile ViewModel adapters in `miniProgram/models/workbench.js`
- [x] T038 [US2] Replace fixtures and Demo page state in `miniProgram/pages/home/index.js` with workbench, notices and recent-binding loading while preserving WXML/WXSS
- [x] T039 [US2] Replace fixtures and fixed metrics in `miniProgram/pages/profile/index.js` with real account/workbench data and permission-based service entries
- [x] T040 [US2] Ensure home/profile page requests share safe cached in-flight data only within the same user session and clear on account switch in `miniProgram/services/workbench-service.js`
- [ ] T041 [US2] Verify ordinary distributor home/profile and B-002-limited org-admin behavior using quickstart Scenario C

**Checkpoint**: 首页和我的页不再读取演示账户、客户数或消费金额。

---

## Phase 5: User Story 3 — 客户、绑定与跟进真实闭环 (Priority: P1)

**Goal**: 接入安全可用的客户列表/详情/编辑/分析和绑定提交/列表；危险后端差异保持前端门禁。

**Independent Test**: 客户列表分页搜索、本人客户详情、支持字段编辑、授权后绑定提交和绑定记录均使用真实数据；B-003/B-005 阻塞能力不发请求。

### Customer tests first

- [x] T042 [P] [US3] Add failing customer service contracts for list/detail/PATCH/analysis with exact query/body fields in `miniProgram/tests/contract/customer-api-contract.test.js`
- [x] T043 [P] [US3] Add failing customer adapters for masked fields, binding statuses, amount cents, cursor pages and unsupported edit fields in `miniProgram/tests/unit/customer-api-adapter.test.js`
- [x] T044 [P] [US3] Add failing integration tests for search race, cursor pagination, detail authorization errors and edit retry/input retention in `miniProgram/tests/integration/customer-flow.test.js`

### Customer implementation

- [x] T045 [P] [US3] Implement READY/ADAPT customer and customer-analysis calls only in `miniProgram/services/customer-service.js`
- [x] T046 [P] [US3] Extend `miniProgram/models/customer-list.js`, `customer-detail.js`, `customer-edit.js` and `customer-analysis.js` with pure DTO adapters while retaining existing form validation
- [x] T047 [US3] Replace customer fixtures with real cursor search/filter/list loading in `miniProgram/pages/customers/index.js`
- [x] T048 [US3] Load only authorized customer main detail in `miniProgram/pages/customer-detail/index.js`; mark service/consumption/followup tabs unavailable while B-003/B-005 remain blocked and never fill them with Mock
- [x] T049 [US3] Wire `miniProgram/pages/customer-edit/index.js` to PATCH only name/phone/note/familyPhone; hide or disable idCard/medicalAccount edits under B-007 and require changeReason for phone
- [x] T050 [US3] Wire `miniProgram/pages/customer-analysis/index.js` to real period data and ECharts, including empty/error states and request-version protection
- [x] T051 [US3] [BLOCKED] Replace save/submit actions in `miniProgram/pages/followup-record/index.js` with a clear backend-permission-blocked state while B-003 is open; do not call followup endpoints or retain fake success

### Binding tests first

- [x] T052 [P] [US3] Add failing binding service contracts for selectable promoters, consent, submit, list and summary including required Idempotency-Key in `miniProgram/tests/contract/binding-api-contract.test.js`
- [x] T053 [P] [US3] Add failing binding status adapter tests for backend enums, unknown enum, masked info and summary counts in `miniProgram/tests/unit/binding-api-adapter.test.js`
- [x] T054 [P] [US3] Add failing integration test for selectable promoter → consent → one binding submission → list result, including repeated taps in `miniProgram/tests/integration/binding-flow.test.js`

### Binding implementation

- [x] T055 [P] [US3] Implement READY binding/consent operations in `miniProgram/services/binding-service.js`; do not expose blocked detail/retry/update operations while access control is unresolved
- [x] T056 [P] [US3] Extend `miniProgram/models/customer-binding.js`, `binding-records.js` and `binding-result.js` with real DTO/status adapters
- [x] T057 [US3] Replace fixed owner and local success in `miniProgram/pages/customer-binding/index.js` with selectable promoter, consent and idempotent binding submission
- [x] T058 [US3] Replace fixed records/summary in `miniProgram/pages/binding-records/index.js` with cursor list, backend filters and binding summary
- [x] T059 [US3] [BLOCKED] Make `miniProgram/pages/binding-result/index.js` render the immediate safe submit response or a blocked detail state; do not call detail/retry until matrix access-control status changes
- [ ] T060 [US3] Execute quickstart Scenario D/E and update B-003/B-005/B-007 status evidence in the contract matrix

**Checkpoint**: 安全的客户与绑定主链路使用真实数据；被阻塞子资源没有越权请求或 Mock 成功。

---

## Phase 6: User Story 4 — 消费业绩与绩效统一真实口径 (Priority: P1)

**Goal**: 消费概览、趋势、账单列表及个人/组织绩效使用真实整数分数据；危险账单详情保持关闭。

**Independent Test**: 同一账户同一月份在首页、消费页和绩效页的可比金额与后端偏差为 0。

### Tests first

- [x] T061 [P] [US4] Add failing consumption service contracts for overview/trend/list and blocked detail policy in `miniProgram/tests/contract/consumption-api-contract.test.js`
- [x] T062 [P] [US4] Add failing consumption adapter tests for amountCent, PAID/PARTIALLY_REFUNDED/REFUNDED/CANCELLED, grouping and unknown status in `miniProgram/tests/unit/consumption-adapter.test.js`
- [ ] T063 [P] [US4] Extend commission/org service tests for shared request behavior, estimate/confirmed semantics and integer cents in `miniProgram/tests/contract/performance-api-contract.test.js`
- [ ] T064 [P] [US4] Add failing integration test for month switch races, cursor paging and cross-page amount reconciliation in `miniProgram/tests/integration/consumption-performance-flow.test.js`

### Implementation

- [x] T065 [P] [US4] Implement overview/trend/list calls in `miniProgram/services/consumption-service.js`; withhold bill-detail call while B-004 is unresolved
- [x] T066 [P] [US4] Replace old points/category adapters in `miniProgram/models/contribution-detail.js` and contribution page model with bill/amountCent/status adapters
- [x] T067 [US4] Replace fixtures in `miniProgram/pages/contribution/index.js` with real overview, trend and first page of bills; reset cursor on month/status changes
- [x] T068 [US4] [BLOCKED] Make `miniProgram/pages/contribution-detail/index.js` show a controlled unavailable state for B-004 rather than reading local contribution records or requesting arbitrary bill IDs
- [x] T069 [US4] Finish shared-request migration and DTO validation in `miniProgram/services/commission-service.js` and `org-performance-service.js`
- [x] T070 [US4] Wire `miniProgram/pages/performance/index.js` and `org-performance/index.js` to loading/empty/error/forbidden states without Mock fallback
- [ ] T071 [US4] Execute quickstart Scenario F and record amount reconciliation results plus B-004 status in the contract matrix

**Checkpoint**: 消费列表和绩效使用真实最新口径，旧 `points`/`settled` Mock 不进入生产页面。

---

## Phase 7: User Story 5 — 资料、隐私、推广、反馈与通知 (Priority: P2)

**Goal**: 接入后端已支持的辅助能力；资料保存和资质功能按阻塞状态处理。

### Tests first

- [ ] T072 [P] [US5] Add failing profile service contracts for profile/account-summary/phone-bind/avatar upload token and blocked update version in `miniProgram/tests/contract/profile-api-contract.test.js`
- [ ] T073 [P] [US5] Add failing compliance service contracts for agreements/consents/privacy settings in `miniProgram/tests/contract/compliance-api-contract.test.js`
- [ ] T074 [P] [US5] Add failing promotion service contracts and adapters for missing QR/poster URLs in `miniProgram/tests/contract/promotion-api-contract.test.js`
- [ ] T075 [P] [US5] Add failing feedback upload/submit/list contracts and draft-retention tests in `miniProgram/tests/contract/feedback-api-contract.test.js`
- [ ] T076 [P] [US5] Add failing notification cursor/unread/read contracts and page-state tests in `miniProgram/tests/contract/notification-api-contract.test.js`

### Implementation

- [x] T077 [P] [US5] Implement profile read, account summary, phone bind and avatar upload authorization in `miniProgram/services/profile-service.js`
- [x] T078 [US5] Wire `miniProgram/pages/account-profile/index.js` to real profile, phone and durable avatar upload; keep save disabled with B-001 explanation until a valid version contract exists
- [x] T079 [P] [US5] Implement agreements, consent and privacy settings calls in `miniProgram/services/compliance-service.js`
- [x] T080 [US5] Replace modal demo agreements in `miniProgram/pages/auth/login/index.js` and local-only privacy state in `miniProgram/pages/privacy-authorization/index.js` with real agreement/consent data
- [x] T081 [P] [US5] Implement promotion API service and DTO adapter in `miniProgram/services/promotion-service.js` and `miniProgram/models/promotion-code.js`
- [x] T082 [US5] Wire `miniProgram/pages/promotion-code/index.js` to real code/statistics/poster, with empty state when URL is absent
- [ ] T083 [P] [US5] Implement feedback upload authorization, file upload and feedback submit/list in `miniProgram/services/feedback-service.js` (当前仅完成 token/submit/list service，微信文件上传待补)
- [ ] T084 [US5] Wire `miniProgram/pages/help-feedback/index.js` to real upload/submit behavior and preserve non-sensitive draft on unknown result (当前仅开放文字反馈，截图入口受控禁用)
- [ ] T085 [P] [US5] Implement notification service and adapters in `miniProgram/services/notification-service.js` and `miniProgram/models/notification.js` (当前 service/page 已接入，独立 adapter 尚未补齐)
- [x] T086 [US5] Create the approved-design notification page under `miniProgram/pages/notifications/` and register it in `miniProgram/app.json`; update navigation target from the feature placeholder
- [ ] T087 [US5] [BLOCKED] Keep qualification entry unavailable with B-006 messaging; do not add a fake submit page or call admin organization qualification APIs
- [ ] T088 [US5] Execute quickstart Scenario G and update B-001/B-006 plus notification frontend status in the matrix

**Checkpoint**: 后端已支持的 P2 能力真实可用；资料保存和资质不会伪装完成。

---

## Phase 8: User Story 6 — 真实网络边界、Mock 清理与交付 (Priority: P2)

**Goal**: 在弱网、错误、账户切换和体验构建中保持安全、可恢复且不回落 Mock。

### Tests first

- [ ] T089 [P] [US6] Add stale-response/account-switch tests across workbench, customer and consumption pages in `miniProgram/tests/integration/request-race-flow.test.js`
- [ ] T090 [P] [US6] Add failure-matrix integration tests for 401/403/404/409/500/timeout/network/malformed responses in `miniProgram/tests/integration/error-boundary-flow.test.js`
- [x] T091 [P] [US6] Add production source contract scanning pages/services for direct Mock imports, fixed business fixtures, direct `wx.request` and sensitive literals in `miniProgram/tests/contract/production-boundary-contract.test.js`

### Implementation and acceptance

- [x] T092 [US6] Remove or development-gate all runtime Mock imports from `miniProgram/pages/`, `miniProgram/services/` and `miniProgram/app.js`; retain assets and pure fixture tests only
- [x] T093 [US6] Remove fixed customer IDs, account names, phones, amounts and success responses from production page initialization; use empty/loading models
- [ ] T094 [US6] Audit all logs, Toasts, modal text, storage and share payloads for Token or sensitive-data leakage in `miniProgram/`
- [x] T095 [US6] Run all Node unit/contract/integration tests with the bundled modern Node runtime and record exact totals in `specs/011-miniprogram-api-integration/quickstart.md`
- [ ] T096 [US6] Compile in WeChat Developer Tools against local/test backend and verify every registered page has loading/empty/error/forbidden behavior as applicable
- [ ] T097 [US6] Execute weak-network, concurrent 401, repeated-tap and account A→B switch scenarios; update matrix evidence without changing backend
- [ ] T098 [US6] Execute at least one iOS or Android WeChat real-device pass for login, home, customers, binding submit, consumption and logout
- [ ] T099 [US6] Reconcile all matrix entries: mark implemented READY/ADAPT items, keep unresolved B-* items blocked, and list deferred release impact in `contracts/page-api-matrix.md`
- [ ] T100 [US6] Update `miniProgram/README.md` with final environment, test, build-NPM, legal-domain and known-backend-blocker instructions

**Checkpoint**: 可安全交付的前端范围验收完成，所有后端阻塞透明可追踪。

---

## Dependencies & Execution Order

```text
Phase 1 Setup
  -> Phase 2 Request + Session Foundation
    -> US1 Auth Session
      -> US2 Workbench/Profile
      -> US3 Customers/Binding
      -> US4 Consumption/Performance
        -> US5 Auxiliary Features
          -> US6 Hardening and Acceptance
```

- Phase 2 阻塞全部用户故事。
- US2/US3/US4 在 US1 真实会话完成后可按不同文件并行，但本项目单人负责时建议按编号执行。
- US5 可在 P1 主链路完成后开始。
- US6 的生产 Mock 扫描需在所有目标页面接入后执行。
- B-001/B-002/B-003/B-004/B-005/B-006/B-008 的解除依赖后端负责人确认；本 tasks 不包含解除它们的后端代码任务。

## Parallel Opportunities

- Phase 1 的 env、money/date、ApiError 测试可并行。
- Phase 2 的 request、refresh、idempotency、session 测试可并行。
- 每个用户故事中的 service contract、adapter unit 和 page integration 测试可并行编写，但都必须先于对应实现。
- US3 的客户 READY 范围与绑定 READY 范围可在 Foundation 后并行。
- US5 的 profile/compliance/promotion/feedback/notification service 可按不同文件并行。

## Implementation Strategy

### MVP

1. Phase 1-2：统一请求与真实会话。
2. US1：已建档分销员登录、绑定微信、刷新和退出。
3. US2：首页与我的真实数据。
4. 停止并用 quickstart A-C 独立验收。

### Core business increment

1. US3 先交付安全 READY 的客户列表/详情/编辑/分析和绑定提交/列表。
2. US4 交付消费列表和绩效。
3. 所有 Critical BLOCKED 接口保持禁用，不能为了“链路看起来完整”读取 Mock。

### Completion rule

- 一个 task 只有在测试先失败、实现后通过、且未修改 `backend/` 时才能勾选。
- 一个用户故事只有 READY/ADAPT 范围验收完成并明确列出 BLOCKED 影响后才能报告完成。
- 不得把“接口存在”报告为“真机联调通过”。
