# Tasks: 北京儒泰分销管理后端与API

**Input**: Design documents from `/specs/001-distribution-management-api/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: INCLUDED — TDD is constitutionally mandated (NON-NEGOTIABLE). Tests MUST be written FIRST and FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/src/`, `backend/tests/`
- **Admin Frontend**: `admin/src/`
- Based on plan.md project structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic scaffolding for both backend and admin

- [x] T001 Create backend project directory structure per plan.md in backend/
- [x] T002 [P] Initialize Python project with requirements.txt (FastAPI, SQLAlchemy, Alembic, Pydantic, httpx, APScheduler, pytest, pytest-asyncio, asyncmy) in backend/requirements.txt
- [x] T003 [P] Create admin Vue 3 + Vite project with Element Plus, Pinia, Axios, Vue Router, Vitest in admin/
- [x] T004 [P] Configure backend linting (ruff) and formatting (black) in backend/pyproject.toml
- [x] T005 [P] Configure admin linting (ESLint) and formatting (Prettier) in admin/.eslintrc.js and admin/.prettierrc
- [x] T006 Create .env.example with all required environment variables (DATABASE_URL, WECHAT_APP_ID, WECHAT_APP_SECRET, JWT_SECRET_KEY, RUTAI_API_*, COS_*, ADMIN_DEFAULT_*) in backend/.env.example
- [x] T007 Initialize Alembic configuration and create initial migration directory in backend/alembic.ini and backend/migrations/
- [x] T008 [P] Create Dockerfile for backend in backend/Dockerfile
- [x] T009 [P] Create Dockerfile for admin nginx deployment in admin/Dockerfile

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database & Models (All Entities)

- [x] T010 Create core config module with typed settings from environment in backend/src/core/config.py
- [x] T011 Create async database engine, session factory, and Base model in backend/src/core/database.py
- [x] T012 [P] Create User and AdminAccount models in backend/src/models/user.py
- [x] T013 [P] Create Role model with JSON permissions field in backend/src/models/role.py
- [x] T014 [P] Create Promoter and HierarchyNode models with self-referential relationship in backend/src/models/hierarchy.py
- [x] T015 [P] Create Qualification model with status enum in backend/src/models/qualification.py
- [x] T016 [P] Create Customer, BindingRequest, and BindingChangeLog models in backend/src/models/binding.py
- [x] T017 [P] Create PromotionCode model in backend/src/models/promotion.py
- [x] T018 [P] Create Bill model with transaction_id unique constraint in backend/src/models/bill.py
- [x] T019 [P] Create ContributionRecord and SettlementLog models in backend/src/models/contribution.py
- [x] T020 [P] Create SharingRule model with effective time support in backend/src/models/sharing.py
- [x] T021 [P] Create Article model in backend/src/models/article.py
- [x] T022 [P] Create FollowupRecord model in backend/src/models/followup.py
- [x] T023 [P] Create ConsentRecord and Agreement models in backend/src/models/consent.py
- [x] T024 [P] Create Notification model in backend/src/models/notification.py
- [x] T025 [P] Create ApiCallLog and AuditLog models with partitioning support in backend/src/models/audit.py
- [x] T026 [P] Create IdempotencyKey model with TTL support in backend/src/models/idempotency.py
- [x] T027 Create models __init__.py importing all models in backend/src/models/__init__.py

### Core Infrastructure

- [x] T028 Create security utilities (JWT encode/decode, password hashing with bcrypt, token generation) in backend/src/core/security.py
- [x] T029 [P] Create custom exception classes with error codes and HTTP status mapping in backend/src/core/exceptions.py
- [x] T030 [P] Create global exception handler translating exceptions to unified response format in backend/src/core/error_handler.py
- [x] T031 [P] Create dependency injection utilities (get_db session, get_current_user from JWT) in backend/src/api/deps.py
- [x] T032 [P] Create RBAC permission checker dependency with role-based access control in backend/src/api/deps.py (same file, add PermissionChecker class)
- [x] T033 [P] Create idempotency middleware checking Idempotency-Key header and replaying stored responses in backend/src/core/idempotency_middleware.py
- [x] T034 [P] Create request logging middleware recording request_id, method, path, status, duration in backend/src/core/logging_middleware.py
- [x] T035 [P] Create CORS middleware configuration for admin frontend origin in backend/src/main.py
- [x] T036 Create FastAPI app instance with middleware stack, router includes, and lifespan events in backend/src/main.py

### Database Setup

- [x] T037 Generate initial Alembic migration from all models in backend/migrations/versions/
- [x] T038 [P] Create seed script for default admin account, roles (admin/finance/ops), and L1 root hierarchy node in backend/src/seed.py

### Admin Frontend Foundation

- [x] T039 Create Axios instance with base URL, JWT interceptor, token refresh queue, and error handling in admin/src/api/http.js
- [x] T040 [P] Create Vue Router with auth guard (redirect to /login if no token) and route definitions in admin/src/router/index.js
- [x] T041 [P] Create Pinia auth store (login, logout, token refresh, user state) in admin/src/stores/auth.js
- [x] T042 [P] Create admin App.vue with router-view and basic layout shell (sidebar + header + content) in admin/src/App.vue

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — 登录与身份认证 (Priority: P1) 🎯 MVP

**Goal**: WeChat mini-program login and admin backend login both work with JWT tokens, session management, and role-based access

**Independent Test**: Start backend, call POST /auth/wechat-login with test code → get tokens → call GET /auth/session → verify session. Call POST /auth/admin-login → get tokens → access admin endpoints.

### Tests for User Story 1 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T043 [P] [US1] Contract test: POST /api/v1/auth/wechat-login (success, invalid code, expired code) in backend/tests/contract/test_auth.py
- [x] T044 [P] [US1] Contract test: POST /api/v1/auth/admin-login (success, wrong password, locked account) in backend/tests/contract/test_auth.py
- [x] T045 [P] [US1] Contract test: POST /api/v1/auth/phone-bind (success, already bound) in backend/tests/contract/test_auth.py
- [x] T046 [P] [US1] Contract test: GET /api/v1/auth/session (valid token, expired token, missing token) in backend/tests/contract/test_auth.py
- [x] T047 [P] [US1] Contract test: POST /api/v1/auth/refresh (valid refresh, reused refresh token detection) in backend/tests/contract/test_auth.py
- [x] T048 [P] [US1] Contract test: POST /api/v1/auth/logout (token invalidation) in backend/tests/contract/test_auth.py
- [x] T049 [P] [US1] Contract test: GET /api/v1/app/bootstrap (valid session, new user, phone not bound) in backend/tests/contract/test_auth.py
- [x] T050 [P] [US1] Integration test: Full WeChat login flow (code → tokens → session → bootstrap) in backend/tests/integration/test_auth_flow.py

### Implementation for User Story 1

- [x] T051 [P] [US1] Create WeChat API client (jscode2session, phone number exchange) in backend/src/integrations/wechat_client.py
- [x] T052 [US1] Implement auth service (wechat_login, admin_login, phone_bind, refresh_token, logout, session) in backend/src/services/auth_service.py
- [x] T053 [P] [US1] Create Pydantic schemas for auth requests/responses in backend/src/schemas/auth.py
- [x] T054 [US1] Implement auth API router (6 endpoints: wechat-login, admin-login, phone-bind, session, refresh, logout) in backend/src/api/v1/auth.py
- [x] T055 [P] [US1] Implement app bootstrap endpoint returning session + workbench summary in backend/src/api/v1/app.py
- [x] T056 [P] [US1] Create admin login page component in admin/src/pages/login/index.vue
- [x] T057 [US1] Implement router auth guard with token validation and redirect in admin/src/router/index.js (update existing)

**Checkpoint**: Login fully functional — users can authenticate via WeChat (mini-program) and password (admin). Bootstrap returns correct session and permissions.

---

## Phase 4: User Story 4 — 拓展人层级体系管理 (Priority: P1) 🎯 MVP

**Goal**: Admin can create and manage 6-level hierarchy tree, with cycle detection, branch migration, and historical snapshots

**Independent Test**: POST create nodes → GET hierarchy tree → verify tree structure → POST migrate branch → verify migration → POST cycle → verify rejection

### Tests for User Story 4 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T058 [P] [US4] Contract test: GET /api/v1/admin/hierarchy (tree structure, depth, node count) in backend/tests/contract/test_hierarchy.py
- [x] T059 [P] [US4] Contract test: POST /api/v1/admin/hierarchy/nodes (create, invalid parent, duplicate) in backend/tests/contract/test_hierarchy.py
- [x] T060 [P] [US4] Contract test: POST /api/v1/admin/hierarchy/nodes/{id}/migrate (success, cycle detection, invalid target) in backend/tests/contract/test_hierarchy.py
- [x] T061 [P] [US4] Integration test: Full hierarchy lifecycle (create → build tree → migrate branch → verify snapshot) in backend/tests/integration/test_hierarchy_flow.py
- [x] T062 [P] [US4] Unit test: Cycle detection algorithm with deep nested trees in backend/tests/unit/test_hierarchy_service.py

### Implementation for User Story 4

- [x] T063 [US4] Implement hierarchy service (create_node, update_node, get_tree, get_subtree, detect_cycle, migrate_branch, get_ancestors, get_descendants) in backend/src/services/hierarchy_service.py
- [x] T064 [P] [US4] Create Pydantic schemas for hierarchy requests/responses in backend/src/schemas/hierarchy.py
- [x] T065 [US4] Implement hierarchy admin API router (CRUD nodes, get tree, migrate branch, snapshots) in backend/src/api/v1/admin.py (hierarchy section)
- [x] T066 [P] [US4] Create admin hierarchy tree page with expandable tree view in admin/src/pages/hierarchy/index.vue
- [x] T067 [P] [US4] Create admin hierarchy node form (create/edit modal) in admin/src/components/hierarchy/NodeForm.vue
- [x] T068 [P] [US4] Create admin hierarchy migration dialog (select target branch, confirm) in admin/src/components/hierarchy/MigrateDialog.vue

**Checkpoint**: Hierarchy tree fully manageable — admin can create, view, edit, and migrate nodes with cycle protection.

---

## Phase 5: User Story 2 — 资质上传与审核管理 (Priority: P1) 🎯 MVP

**Goal**: Promoters upload qualification files, admins review and approve/reject, auto expiry reminders generated

**Independent Test**: POST upload-token → get upload URL → POST submit qualification → admin GET pending → POST review approve → verify promoter activated. Test reject flow separately.

### Tests for User Story 2 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T069 [P] [US2] Contract test: POST /api/v1/qualification-files/upload-token (valid request, invalid file type, oversized) in backend/tests/contract/test_qualifications.py
- [x] T070 [P] [US2] Contract test: POST /api/v1/qualifications (submit, missing file, duplicate submit while reviewing) in backend/tests/contract/test_qualifications.py
- [x] T071 [P] [US2] Contract test: GET /api/v1/qualifications/current (no qualification, reviewing, approved, expired) in backend/tests/contract/test_qualifications.py
- [x] T072 [P] [US2] Contract test: PUT /api/v1/qualifications/{id} (resubmit after reject, version conflict) in backend/tests/contract/test_qualifications.py
- [x] T073 [P] [US2] Contract test: POST /api/v1/admin/qualifications/{id}/review (approve, reject with reason) in backend/tests/contract/test_qualifications.py
- [x] T074 [P] [US2] Integration test: Full qualification lifecycle (upload → submit → review → approve → activate → expire) in backend/tests/integration/test_qualification_flow.py

### Implementation for User Story 2

- [x] T075 [P] [US2] Create Tencent Cloud COS client (generate pre-signed upload URL) in backend/src/integrations/cos_client.py
- [x] T076 [US2] Implement qualification service (upload_token, submit, resubmit, get_current, get_reviews, admin_review, check_expiry) in backend/src/services/qualification_service.py
- [x] T077 [P] [US2] Create Pydantic schemas for qualification requests/responses in backend/src/schemas/qualification.py
- [x] T078 [US2] Implement qualification API router (upload-token, submit, get current, update, reviews, draft) in backend/src/api/v1/qualifications.py
- [x] T079 [P] [US2] Implement qualification admin API endpoints (review approve/reject) in backend/src/api/v1/admin.py (qualification section)
- [x] T080 [P] [US2] Create admin qualification review list page in admin/src/pages/qualifications/index.vue
- [x] T081 [P] [US2] Create admin qualification review detail modal (file preview, approve/reject actions) in admin/src/components/qualifications/ReviewModal.vue
- [x] T081a [P] [US2] Create qualification Pinia store (upload, submit, status polling) in admin/src/stores/qualifications.js

**Checkpoint**: Qualification lifecycle complete — upload → review → approve/reject → expiry tracking all functional.

---

## Phase 6: User Story 10 — 推广码生成与管理 (Priority: P1) 🎯 MVP

**Goal**: Approved promoters get unique QR codes with refToken; codes support refresh and analytics

**Independent Test**: GET promotion-code (approved promoter) → verify QR and refToken → POST refresh → verify old token invalid → GET statistics → verify counts

### Tests for User Story 10 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T082 [P] [US10] Contract test: GET /api/v1/promotion-code (approved, unapproved, no qualification) in backend/tests/contract/test_promotion.py
- [x] T083 [P] [US10] Contract test: POST /api/v1/promotion-code/refresh (success, rate limited) in backend/tests/contract/test_promotion.py
- [x] T084 [P] [US10] Contract test: GET /api/v1/promotion-code/statistics (valid period, empty data) in backend/tests/contract/test_promotion.py
- [x] T085 [P] [US10] Integration test: Promotion code lifecycle (generate → refresh → verify old invalid → statistics update) in backend/tests/integration/test_promotion_flow.py

### Implementation for User Story 10

- [x] T086 [US10] Implement promotion service (generate_code, get_code, refresh_code, track_scan, get_statistics) in backend/src/services/promotion_service.py
- [x] T087 [P] [US10] Create Pydantic schemas for promotion requests/responses in backend/src/schemas/promotion.py
- [x] T088 [US10] Implement promotion API router (get code, refresh, statistics, poster) in backend/src/api/v1/promotions.py
- [x] T089 [P] [US10] Create admin promotion code display page in admin/src/pages/promotions/index.vue (no mini-program component, admin-side management only)

**Checkpoint**: Promotion codes functional — QR codes with BJTR source, refreshable, with usage statistics.

---

## Phase 7: User Story 3 — 客户绑定管理 (Priority: P1) 🎯 MVP

**Goal**: Doctors bind customers to promoters via Rutai API; admins can unbind/transfer with full audit logging

**Independent Test**: POST binding-request → verify pending_match → mock Rutai matched → verify bound. POST unbind → verify unbound + audit log. POST transfer → verify new promoter + audit log.

### Tests for User Story 3 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T090 [P] [US3] Contract test: GET /api/v1/promoters/selectable (keyword search, pagination, permission filter) in backend/tests/contract/test_binding.py
- [x] T091 [P] [US3] Contract test: POST /api/v1/binding-requests (success, duplicate idempotency key, already bound, missing consent) in backend/tests/contract/test_binding.py
- [x] T092 [P] [US3] Contract test: GET /api/v1/binding-requests (list, filter by status, pagination) in backend/tests/contract/test_binding.py
- [x] T093 [P] [US3] Contract test: GET /api/v1/binding-requests/{id} (pending, bound, abnormal states) in backend/tests/contract/test_binding.py
- [x] T094 [P] [US3] Contract test: POST /api/v1/binding-requests/{id}/retry (valid retry, already bound) in backend/tests/contract/test_binding.py
- [x] T095 [P] [US3] Contract test: POST /api/v1/admin/bindings/{id}/unbind (success, reason required, already unbound) in backend/tests/contract/test_binding.py
- [x] T096 [P] [US3] Contract test: POST /api/v1/admin/bindings/{id}/transfer (success, same promoter, unsettled contributions warning) in backend/tests/contract/test_binding.py
- [x] T097 [P] [US3] Contract test: GET /api/v1/binding-summary (counts per status) in backend/tests/contract/test_binding.py
- [x] T098 [P] [US3] Integration test: Full binding lifecycle (select promoter → submit → match → bind → unbind → audit verify) in backend/tests/integration/test_binding_flow.py

### Implementation for User Story 3

- [x] T099 [US3] Create Harbin Rutai API client (bindBjUser with HMAC-SHA256 signing, retry logic, timeout handling) in backend/src/integrations/rutai_client.py
- [x] T100 [US3] Implement binding service (submit_request, match_customer, get_requests, get_detail, retry, unbind, transfer, get_summary, get_selectable_promoters) in backend/src/services/binding_service.py
- [x] T101 [P] [US3] Create Pydantic schemas for binding requests/responses in backend/src/schemas/binding.py
- [x] T102 [US3] Implement binding API router (selectable promoters, binding CRUD, summary, retry) in backend/src/api/v1/binding.py
- [x] T103 [US3] Implement binding admin API endpoints (unbind, transfer) in backend/src/api/v1/admin.py (binding section)
- [x] T104 [P] [US3] Create admin binding management page with status filters in admin/src/pages/customers/binding.vue
- [x] T105 [P] [US3] Create admin unbind dialog (reason required, unsettled warning) in admin/src/components/customers/UnbindDialog.vue
- [x] T106 [P] [US3] Create admin transfer dialog (select new promoter, confirm) in admin/src/components/customers/TransferDialog.vue
- [x] T106a [P] [US3] Create binding Pinia store (submit, list, retry, summary, unbind, transfer) in admin/src/stores/binding.js

**Checkpoint**: Binding flow complete — submit → Rutai match → bind → admin unbind/transfer with full audit trail.

---

## Phase 8: User Story 5 — 数据同步与贡献值计算 (Priority: P1) 🎯 MVP

**Goal**: Automatic polling of getBindUser every 60s, getUserBill per user, contribution calculation and up-tree aggregation

**Independent Test**: Mock Rutai getBindUser response → verify users imported → mock getUserBill → verify bills stored → verify contribution calculated → verify up-tree aggregation

### Tests for User Story 5 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T107 [P] [US5] Contract test: GET /api/v1/admin/sync/retry-binduser (manual retry trigger) in backend/tests/contract/test_sync.py
- [x] T108 [P] [US5] Contract test: GET /api/v1/admin/sync/retry-bill/{userId} (manual retry trigger) in backend/tests/contract/test_sync.py
- [x] T109 [P] [US5] Integration test: getBindUser polling (new users → auto-import → trigger getUserBill) in backend/tests/integration/test_sync_flow.py
- [x] T110 [P] [US5] Integration test: getUserBill sync (new bills → idempotent insert → contribution calculation) in backend/tests/integration/test_sync_flow.py
- [x] T111 [P] [US5] Integration test: Contribution aggregation (personal → L5 → L4 → L3 → L2 → L1 tree walk) in backend/tests/integration/test_contribution_calc.py
- [x] T112 [P] [US5] Integration test: Refund handling (refund bill → contribution reversal) in backend/tests/integration/test_contribution_calc.py
- [x] T113 [P] [US5] Unit test: Contribution calculation formula (edge cases: zero amount, fractional points, rounding) in backend/tests/unit/test_contribution_service.py

### Implementation for User Story 5

- [x] T114 [US5] Implement sync service (poll_bind_users, fetch_user_bill, handle_refund, retry_failed, get_all_users_bill daily reconciliation) in backend/src/services/sync_service.py
- [x] T115 [US5] Implement contribution service (calculate, aggregate_up_tree, reverse_on_refund, adjust_manual) in backend/src/services/contribution_service.py
- [x] T116a [US5] Register sync-bind-users APScheduler task (60s interval) in backend/src/tasks/sync_tasks.py
- [x] T116b [US5] Register sync-user-bills APScheduler task (triggered per new binding, 10min retry interval) in backend/src/tasks/sync_tasks.py
- [x] T116c [P] [US2] Register qualification-expiry-check APScheduler task (cron: 0 9 * * *) in backend/src/tasks/maintenance_tasks.py
- [x] T116d [P] Register retry-failed-sync APScheduler task (10min interval) in backend/src/tasks/sync_tasks.py
- [x] T116e [US5] Register monthly-settlement APScheduler task (cron: 0 5 1 * *, with SELECT FOR UPDATE SKIP LOCKED batch processing) in backend/src/tasks/settlement_task.py
- [x] T117 [P] [US5] Create sync admin endpoints (manual retry triggers) in backend/src/api/v1/admin.py (sync section)
- [x] T118 [P] [US5] Implement notification triggers for sync failures (consecutive 5 failures → message center alert) in backend/src/services/notification_service.py
- [x] T119 [P] [US5] Create admin sync status dashboard showing last poll time, success rate, pending retries in admin/src/pages/dashboard/sync-status.vue
- [x] T119a [P] [US5] Create sync status Pinia store (poll status, retry triggers, failure alerts) in admin/src/stores/sync.js

**Checkpoint**: Data sync engine running — getBindUser polling, getUserBill fetching, contribution calculation + aggregation all automated with retry and alerting.

---

## Phase 9: User Story 7 — 分账规则配置 (Priority: P2)

**Goal**: Admin configures sharing rules per level (fixed ratio/amount/tiered), with effective time scheduling and audit logging

**Independent Test**: POST create rule → verify inactive → wait for effective time → verify active → POST deactivate → POST new same-level rule → verify conflict rejection

### Tests for User Story 7 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T120 [P] [US7] Contract test: GET /api/v1/admin/sharing-rules (list, filter by level, active/inactive) in backend/tests/contract/test_sharing.py
- [x] T121 [P] [US7] Contract test: POST /api/v1/admin/sharing-rules (create, same-level conflict, invalid ratio) in backend/tests/contract/test_sharing.py
- [x] T122 [P] [US7] Contract test: PUT /api/v1/admin/sharing-rules/{id} (update, version conflict) in backend/tests/contract/test_sharing.py
- [x] T123 [P] [US7] Contract test: POST /api/v1/admin/sharing-rules/{id}/deactivate (deactivate, already inactive) in backend/tests/contract/test_sharing.py
- [x] T124 [P] [US7] Integration test: Rule lifecycle (create future → auto-activate → deactivate → audit log verify) in backend/tests/integration/test_sharing_flow.py
- [x] T125 [P] [US7] Unit test: Rule application logic (fixed ratio vs fixed amount vs tiered calculation) in backend/tests/unit/test_sharing_service.py

### Implementation for User Story 7

- [x] T126 [US7] Implement sharing service (create_rule, update_rule, deactivate_rule, get_rules, get_active_rule_for_level, apply_rule_calculation, check_conflicts) in backend/src/services/sharing_service.py
- [x] T127 [P] [US7] Create Pydantic schemas for sharing rule requests/responses in backend/src/schemas/sharing.py
- [x] T128 [US7] Implement sharing admin API endpoints (CRUD, deactivate) in backend/src/api/v1/admin.py (sharing rules section)
- [x] T129 [P] [US7] Implement PUT /api/v1/admin/contribution-coefficient endpoint in backend/src/api/v1/admin.py (coefficient section)
- [x] T130 [P] [US7] Create admin sharing rules list page with level filter in admin/src/pages/sharing-rules/index.vue
- [x] T131 [P] [US7] Create admin sharing rule form (type selector: fixed-ratio/fixed-amount/tiered, effective time picker) in admin/src/components/sharing-rules/RuleForm.vue

**Checkpoint**: Sharing rules fully configurable — CRUD, conflict detection, future effective dates, auto-activation, audit trail.

---

## Phase 10: User Story 6 — 个人与团队贡献值查看 (Priority: P2)

**Goal**: Promoters view personal contributions (overview, trend, details) and team contributions (direct reports with drill-down)

**Independent Test**: GET contributions/overview → verify monthly + total → GET contributions/trend → verify 6 months → GET contributions list → verify pagination → GET team/contributions → verify members → GET team/contributions/{id} → verify drill-down

### Tests for User Story 6 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T132 [P] [US6] Contract test: GET /api/v1/contributions/overview (with month, without month, no data) in backend/tests/contract/test_contributions.py
- [x] T133 [P] [US6] Contract test: GET /api/v1/contributions/trend (6m, 12m, empty data) in backend/tests/contract/test_contributions.py
- [x] T134 [P] [US6] Contract test: GET /api/v1/contributions/composition (categories with percentages) in backend/tests/contract/test_contributions.py
- [x] T135 [P] [US6] Contract test: GET /api/v1/contributions (list with filters: month, status, category, customer) in backend/tests/contract/test_contributions.py
- [x] T136 [P] [US6] Contract test: GET /api/v1/contributions/{id} (detail with calculation info, settled vs pending, adjustment reason) in backend/tests/contract/test_contributions.py
- [x] T137 [P] [US6] Contract test: GET /api/v1/team/contributions (own team, no permission for other branch) in backend/tests/contract/test_contributions.py
- [x] T138 [P] [US6] Contract test: GET /api/v1/team/contributions/{promoterId} (drill-down, unauthorized branch, leaf node) in backend/tests/contract/test_contributions.py
- [x] T139 [P] [US6] Integration test: Contribution viewing flow (calculate → verify overview → verify trend → drill team → verify no amount shown) in backend/tests/integration/test_contribution_view_flow.py

### Implementation for User Story 6

- [x] T140 [US6] Implement contribution query service (get_overview, get_trend, get_composition, list_details, get_detail_with_calculation) in backend/src/services/contribution_query_service.py
- [x] T141 [US6] Implement team contribution service (get_team_summary, drill_down_member, verify_branch_permission) in backend/src/services/team_service.py
- [x] T142 [P] [US6] Create Pydantic schemas for contribution query responses in backend/src/schemas/contribution.py
- [x] T143 [US6] Implement contribution API router (overview, trend, composition, list, detail) in backend/src/api/v1/contributions.py
- [x] T144 [P] [US6] Implement team contribution API router (team summary, member drill-down) in backend/src/api/v1/team.py
- [x] T145 [P] [US6] Create admin contribution overview page (all promoters, settle actions) in admin/src/pages/contributions/index.vue

**Checkpoint**: Contribution data fully visible — personal dashboard, trends, composition, team drill-down, all without showing monetary amounts.

---

## Phase 11: User Story 8 — 多维对账报表 (Priority: P2)

**Goal**: Admin/finance generate multi-dimensional reports and export Excel; data deviation from Rutai ≤ 0.01%

**Independent Test**: POST generate report with date range → verify < 60s → verify dimensions → GET export → verify Excel file

### Tests for User Story 8 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T146 [P] [US8] Contract test: POST /api/v1/reports/generate (valid range, future date, too large range) in backend/tests/contract/test_reports.py
- [x] T147 [P] [US8] Contract test: GET /api/v1/reports (list historical reports) in backend/tests/contract/test_reports.py
- [x] T148 [P] [US8] Contract test: GET /api/v1/reports/{id} (report detail with all dimensions) in backend/tests/contract/test_reports.py
- [x] T149 [P] [US8] Contract test: GET /api/v1/reports/{id}/export (Excel download, unauthorized role) in backend/tests/contract/test_reports.py
- [x] T150 [P] [US8] Integration test: Report generation and data consistency (compare report totals vs raw bill sums) in backend/tests/integration/test_report_flow.py

### Implementation for User Story 8

- [x] T151 [US8] Implement report service (generate_report, list_reports, get_detail, export_excel, verify_consistency_with_rutai) in backend/src/services/report_service.py
- [x] T152 [P] [US8] Create Pydantic schemas for report requests/responses in backend/src/schemas/report.py
- [x] T153 [US8] Implement report API router (generate, list, detail, export) in backend/src/api/v1/reports.py
- [x] T154 [P] [US8] Create admin report generation page (date range picker, dimension selector, generate button) in admin/src/pages/reports/index.vue
- [x] T155 [P] [US8] Create admin report detail view (binding summary, revenue summary, discount summary, allocation by level) in admin/src/components/reports/ReportDetail.vue

**Checkpoint**: Reports fully functional — generation < 60s, all required dimensions, Excel export, data consistency verified.

---

## Phase 12: User Story 9 — 科普内容管理 (Priority: P3)

**Goal**: Ops create/edit/publish/unpublish health articles via CMS; mini-program displays published articles

**Independent Test**: POST create article → verify draft → POST publish → GET articles (public) → verify visible → POST unpublish → verify hidden

### Tests for User Story 9 ⚠️ (WRITE FIRST, ensure they FAIL)

- [x] T156 [P] [US9] Contract test: GET /api/v1/articles (published only, category filter, keyword search, pagination) in backend/tests/contract/test_articles.py
- [x] T157 [P] [US9] Contract test: GET /api/v1/articles/{id} (published, unpublished returns 404, draft) in backend/tests/contract/test_articles.py
- [x] T158 [P] [US9] Contract test: GET /api/v1/admin/articles (all statuses: draft, published, unpublished) in backend/tests/contract/test_articles.py
- [x] T159 [P] [US9] Contract test: POST /api/v1/admin/articles (create with rich text, missing required fields) in backend/tests/contract/test_articles.py
- [x] T160 [P] [US9] Contract test: PUT /api/v1/admin/articles/{id} (update draft, update published) in backend/tests/contract/test_articles.py
- [x] T161 [P] [US9] Contract test: POST /api/v1/admin/articles/{id}/publish and /unpublish (state transitions) in backend/tests/contract/test_articles.py
- [x] T162 [P] [US9] Integration test: Article lifecycle (create → edit → publish → public view → unpublish → verify hidden) in backend/tests/integration/test_article_flow.py

### Implementation for User Story 9

- [x] T163 [US9] Implement article service (create, update, publish, unpublish, list_public, list_admin, get_detail) in backend/src/services/article_service.py
- [x] T164 [P] [US9] Create Pydantic schemas for article requests/responses in backend/src/schemas/article.py
- [x] T165 [US9] Implement article public API router (list published, get detail) in backend/src/api/v1/articles.py
- [x] T166 [US9] Implement article admin API router (CMS: CRUD, publish, unpublish) in backend/src/api/v1/admin.py (articles section)
- [x] T167 [P] [US9] Create admin article list page with status tabs in admin/src/pages/articles/index.vue
- [x] T168 [P] [US9] Create admin article editor with Tiptap rich text editor and media upload in admin/src/components/articles/ArticleEditor.vue

**Checkpoint**: Content CMS complete — full article lifecycle, rich text editing, instant publish/unpublish to mini-program.

---

## Phase 13: Polish & Cross-Cutting Concerns

**Purpose**: Remaining endpoints, cross-cutting improvements, and production readiness

### Remaining API Endpoints

- [x] T169 [P] Implement profile API endpoints (GET/PUT /me/profile, avatar upload-token, account-summary) in backend/src/api/v1/users.py
- [x] T170 [P] Implement customer API endpoints (list, detail, update, service-records, binding-history, contributions, followups) in backend/src/api/v1/customers.py
- [x] T171 [P] Implement followup API endpoints (list, create, draft, update, reminder, complete) in backend/src/api/v1/customers.py (same file, followup section)
- [x] T172 [P] Implement workbench API endpoints (role-based dashboard, notices, recent-bindings, contribution-summary) in backend/src/api/v1/workbench.py
- [x] T173 [P] Implement compliance API endpoints (agreements latest/detail, consents, privacy-settings) in backend/src/api/v1/compliance.py
- [x] T174 [P] Implement feedback API endpoints (upload-token, submit, list) in backend/src/api/v1/feedbacks.py
- [x] T175 [P] Implement notification API endpoints (list, mark-read) in backend/src/api/v1/notifications.py
- [x] T176 [P] Implement customer analysis endpoint in backend/src/api/v1/customer_analysis.py
- [x] T177 [P] Implement admin accounts CRUD endpoints in backend/src/api/v1/admin.py (accounts section)
- [x] T178 [P] Implement admin roles CRUD endpoints in backend/src/api/v1/admin.py (roles section)

### Admin Frontend — Remaining Pages

- [x] T179 [P] Create admin dashboard page with role-specific metrics in admin/src/pages/dashboard/index.vue
- [x] T180 [P] Create admin customer list page with status filter, search, pagination in admin/src/pages/customers/index.vue
- [x] T181 [P] Create admin customer detail page (tabs: profile, binding history, contributions, followups) in admin/src/pages/customers/detail.vue
- [x] T182 [P] Create admin account management page (list, create, assign roles, disable) in admin/src/pages/accounts/index.vue
- [x] T183 [P] Create admin role management page (list, create, permission matrix editor) in admin/src/pages/accounts/roles.vue
- [x] T184 [P] Create admin notification center page (filter by category, mark read, infinite scroll) in admin/src/pages/notifications/index.vue

### Cross-Cutting

- [x] T185 [P] Add comprehensive API logging (request_id, method, path, user_id, status, duration) via middleware in backend/src/core/logging_middleware.py (enhance existing)
- [x] T186 [P] Add rate limiting on auth endpoints (login: 10/min per IP) in backend/src/core/rate_limiter.py
- [x] T187 [P] Configure database connection pooling with Tencent Cloud MySQL TLS in backend/src/core/database.py (enhance existing with pool_size=20, max_overflow=10, pool_recycle=3600)
- [x] T188 [P] Add health check endpoint (GET /api/v1/health) returning DB connectivity and Rutai API status in backend/src/api/v1/health.py
- [x] T189 Verify all contract tests pass with full test suite run (pytest backend/tests/)
- [x] T190 Run quickstart.md validation — follow all setup steps and verify checklist
- [x] T191 [P] Register idempotency key cleanup task (hourly, delete keys older than 24h) in backend/src/tasks/maintenance_tasks.py
- [x] T192 [P] Performance test: Verify 500-promoter concurrent contribution calculation completes within 60s in backend/tests/performance/test_concurrent_contributions.py
- [x] T193 [P] Performance test: Verify contribution query endpoints sustain 100 req/s at p95 < 2s in backend/tests/performance/test_query_load.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — no other story dependency
- **User Story 4 (Phase 4)**: Depends on US1 (auth for admin endpoints)
- **User Story 2 (Phase 5)**: Depends on US1 (auth), US4 (hierarchy for promoter context)
- **User Story 10 (Phase 6)**: Depends on US2 (qualification approval required for codes)
- **User Story 3 (Phase 7)**: Depends on US2 (qualifications), US4 (hierarchy), US10 (promotion codes → refToken)
- **User Story 5 (Phase 8)**: Depends on US3 (binding data feeds sync)
- **User Story 7 (Phase 9)**: Depends on US1 (auth), US4 (hierarchy levels for rules)
- **User Story 6 (Phase 10)**: Depends on US5 (contribution data must exist)
- **User Story 8 (Phase 11)**: Depends on US5 (bill/contribution data), US7 (sharing rules for allocation calc)
- **User Story 9 (Phase 12)**: Depends on Foundational only — independent of other stories
- **Polish (Phase 13)**: Depends on all desired user stories being complete

### User Story Dependency Graph

```
Phase 2 (Foundational)
    │
    ├── US1 (P1: Auth) ─────────────────────────────────────┐
    │       │                                                 │
    │       ├── US4 (P1: Hierarchy) ─────┐                   │
    │       │       │                     │                   │
    │       │       ├── US2 (P1: Qual) ───┤                  │
    │       │       │       │             │                   │
    │       │       │       ├── US10 (P1: Promotion)         │
    │       │       │       │       │                        │
    │       │       │       │       ├── US3 (P1: Binding)    │
    │       │       │       │       │       │                 │
    │       │       │       │       │       ├── US5 (P1: Sync+Contrib)
    │       │       │       │       │       │       │          │
    │       │       │       │       │       │       ├── US6 (P2: View)
    │       │       │       │       │       │       │          │
    │       │       │       │       │       │       ├── US8 (P2: Reports)
    │       │       │       │       │       │       │          │
    │       │       │       │       │       │       │          │
    │       └───────┴───────┴───────┴───────┴── US7 (P2: Sharing)
    │                                                          │
    └── US9 (P3: Content) ─────────────────────────────────┘
```

### Within Each User Story

- Tests (contract, integration, unit) MUST be written and FAIL before implementation
- Schemas (Pydantic) can run in parallel with models (if new models needed)
- Services depend on schemas + models
- API routers depend on services + schemas
- Admin frontend pages depend on API routers being functional
- Story complete before moving to next priority (with exceptions: US7 + US1 can overlap, US9 can run anytime after Foundational)

### Parallel Opportunities

- **Phase 1**: T002, T003, T004, T005, T008, T009 all [P] — can run simultaneously
- **Phase 2**: T012-T026 (all model creation) all [P] — can run simultaneously
- **Phase 2**: T029, T030, T031, T032, T033, T034, T035 all [P] — can run after T028
- **Within each US phase**: All test tasks (contract tests) are [P] and can run simultaneously
- **Within each US phase**: Schemas + some service methods can be parallel
- **US9 (Content)** is completely independent — can run in parallel with any other story
- **US7 (Sharing Rules)** has minimal dependencies (US1 + US4) — can overlap with US2/US10/US3

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 — Login & Auth
4. Complete Phase 4: US4 — Hierarchy
5. Complete Phase 5: US2 — Qualifications
6. Complete Phase 6: US10 — Promotion Codes
7. Complete Phase 7: US3 — Customer Binding
8. Complete Phase 8: US5 — Data Sync & Contribution
9. **STOP and VALIDATE**: Full MVP — login, hierarchy, binding, sync, contribution all working end-to-end
10. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation
2. US1 (Auth) → Users can log in
3. + US4 (Hierarchy) → Admin can manage org structure
4. + US2 (Qualifications) → Promoters can upload qualifications
5. + US10 (Promotion Codes) → Promoters get QR codes
6. + US3 (Binding) → Doctors can bind customers ✨ CORE LOOP WORKS
7. + US5 (Sync+Contrib) → Automatic data sync and contribution calc ✨ BUSINESS ENGINE WORKS
8. + US7 (Sharing) → Admin configures sharing rules
9. + US6 (Viewing) → Promoters see their contributions
10. + US8 (Reports) → Finance can generate reports
11. + US9 (Content) → Health articles live

Each increment adds value without breaking previous.

### Parallel Team Strategy

With multiple developers after Foundational (Phase 2):

- Developer A: US1 (Auth) → US4 (Hierarchy) → US2 (Qual)
- Developer B: US9 (Content) — completely independent, can start immediately
- Developer C: US7 (Sharing Rules) — needs only US1 + US4, can start after Phase 4
- Then converge: US10 → US3 → US5 in sequence (these have strong dependencies)
- Then parallel: US6 + US8 (both depend on US5 but are independent of each other)

---

## Notes

- [P] tasks = different files, no dependencies — can truly run in parallel
- [Story] label maps task to specific user story for traceability
- TDD enforced: tests FAIL first, then implement, then refactor
- Each user story should be independently completable and testable
- Commit after each task or logical group (1-3 tasks)
- Stop at any checkpoint to validate story independently
- Contract tests verify API behavior against contracts/
- Integration tests verify full user journeys with mocked external dependencies
- Unit tests verify business logic with edge cases
- Admin frontend uses Axios interceptor for JWT auto-refresh — always test with expired tokens
