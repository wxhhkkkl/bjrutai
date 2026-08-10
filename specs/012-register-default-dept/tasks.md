# Tasks: 小程序注册自动挂载默认组织顶级部门

**Input**: Design documents from `/specs/012-register-default-dept/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api.md ✅, quickstart.md ✅

**Tests**: REQUIRED (Constitution Principle I — TDD is NON-NEGOTIABLE)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- All tasks include exact file paths

## Path Conventions

- **Backend**: `backend/src/`, `backend/tests/`, `backend/migrations/`
- **MiniProgram**: `miniProgram/pages/`, `miniProgram/services/`, `miniProgram/models/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database migration and model update for new `source_channel` field

- [x] T001 Create Alembic migration to add `source_channel` column to `distributors` table in `backend/migrations/versions/014_add_distributor_source_channel.py`
- [x] T002 [P] Add `source_channel` field to Distributor model in `backend/src/models/distributor.py`
- [x] T003 Run migration and verify column exists: `alembic upgrade head`

**Checkpoint**: `distributors` table has `source_channel` column with default `'admin_create'`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core service functions that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Write unit test for `get_default_org()` in `backend/tests/unit/test_organization_service.py`
- [x] T005 [P] Write unit test for `register_distributor()` in `backend/tests/unit/test_distributor_service.py`
- [x] T006 Implement `get_default_org(db)` — query root org with min `sort_order` — in `backend/src/services/organization_service.py`
- [x] T007 Implement `register_distributor(db, user_id, org_id, source_channel)` — create Distributor with org_role=MEMBER, status=ACTIVE — in `backend/src/services/distributor_service.py`
- [x] T008 Run T004 and T005 tests to confirm they pass after T006/T007 implementation

**Checkpoint**: Foundation ready — default org lookup and distributor registration can be called from any auth flow

---

## Phase 3: User Story 1 - 新用户注册自动加入组织 (Priority: P1) 🎯 MVP

**Goal**: 新用户通过微信授权登录或手机号+密码注册后，自动创建 Distributor 并挂载到默认组织根节点，直接进入首页（可选完善信息）

**Independent Test**: 用全新微信账号授权登录 → 检查数据库 `distributors` 表有新记录且 `source_channel = 'wechat_register'`、`org_id` 指向默认组织根节点 → 小程序直接进入首页

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T009 [P] [US1] Integration test for WeChat login auto-mount in `backend/tests/integration/test_auth_api.py` — test_wechat_register_creates_distributor
- [x] T010 [P] [US1] Integration test for phone register auto-mount in `backend/tests/integration/test_auth_api.py` — test_phone_register_creates_distributor
- [x] T011 [P] [US1] Unit test for wechat_login with default org exists in `backend/tests/unit/test_auth_service.py` — test_wechat_login_auto_creates_distributor
- [x] T012 [P] [US1] Unit test for wechat_login with NO default org (graceful fallback) in `backend/tests/unit/test_auth_service.py` — test_wechat_login_no_default_org

### Backend Implementation for User Story 1

- [x] T013 [US1] Modify `AuthService.wechat_login()` — after User creation, call `register_distributor()` with `source_channel='wechat_register'` — in `backend/src/services/auth_service.py`
- [x] T014 [US1] Handle edge case: no default org → still create User but skip Distributor, return warning — in `backend/src/services/auth_service.py`
- [x] T015 [US1] Add phone + password self-registration endpoint `POST /api/v1/auth/distributor-register` in `backend/src/api/v1/auth.py`
- [x] T016 [US1] Create `DistributorRegisterRequest` and `DistributorRegisterResponse` schemas in `backend/src/schemas/auth.py`
- [x] T017 [US1] Modify `AuthService.get_session()` — include distributor info (distributorId, orgNodeId, orgNodeName, orgRole, sourceChannel) in session response — in `backend/src/services/auth_service.py`
- [ ] T018 [US1] Verify T009-T012 tests pass; run full test suite `pytest backend/tests/ -k "register or wechat" -v`

### MiniProgram Implementation for User Story 1

- [x] T019 [P] [US1] Update `auth-service.js` `establishSession()` — handle new `distributor` field in wechatLogin/distributorRegister response, pass to session builder — in `miniProgram/services/auth-service.js`
- [x] T020 [US1] Update `session-service.js` `getEntry()` — allow users with `profileCompleted=false` to enter home (skip mandatory redirect to profile-setup) — in `miniProgram/services/session-service.js`
- [x] T021 [US1] Update `session-service.js` `buildDistributorSession()` — populate distributor fields (orgId, orgName, distributorId, sourceChannel) from login response — in `miniProgram/services/session-service.js`
- [x] T022 [US1] Update `auth/login/index.js` `completeLogin()` — after successful auto-mount, route to profile-setup as optional page (not mandatory; user can skip) — in `miniProgram/pages/auth/login/index.js`
- [x] T023 [US1] Update `auth/profile-setup/index.js` — remove "请联系管理员创建账号" blocking modal; add "跳过" button → go to home; keep "提交" button for info collection — in `miniProgram/pages/auth/profile-setup/index.js`

**Checkpoint**: 全新微信用户注册 → 自动挂载 → 进入首页，全程无阻断。已有管理员创建的用户登录不受影响。

---

## Phase 4: User Story 2 - 已有账号绑定微信不重复创建 (Priority: P2)

**Goal**: 管理员已创建的人员记录在绑定微信时不被覆盖，不创建重复 Distributor

**Independent Test**: 管理员先创建人员（phone=13800000001）→ 该人员微信授权登录并绑定此手机号 → 检查 `distributors` 表仍只有1条记录，org_id 不变

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T024 [P] [US2] Unit test for existing user WeChat bind — no duplicate distributor — in `backend/tests/unit/test_auth_service.py` — test_existing_user_wechat_bind_no_duplicate
- [x] T025 [P] [US2] Integration test for existing phone match → WeChat bind → org unchanged — in `backend/tests/integration/test_auth_api.py` — test_existing_distributor_wechat_bind_preserves_org

### Backend Implementation for User Story 2

- [x] T026 [US2] Add phone-based Distributor lookup to `wechat_login()` — before auto-creating, check if `phone` from WeChat auth matches existing Distributor; if yes, only bind WeChat (set `user.openid`, `user.wechat_bound = True`) without creating/updating Distributor — in `backend/src/services/auth_service.py`
- [x] T027 [US2] Add phone-based Distributor lookup to `distributor_register()` — reject with `40901 该手机号已注册` if phone already linked to a Distributor — in `backend/src/services/auth_service.py`

### MiniProgram Implementation for User Story 2

- [x] T028 [US2] Update `auth/login/index.js` — when WeChat login response returns `isNewUser: false` with existing distributor info, skip profile-setup entirely and go directly to home — in `miniProgram/pages/auth/login/index.js`

**Checkpoint**: 已有人员绑定微信 → 组织不变；重复注册被正确拒绝

---

## Phase 5: User Story 3 - 管理员查看和管理自动挂载的人员 (Priority: P3)

**Goal**: 管理员在人员列表中看到 `source_channel` 标记，能区分微信注册人员和手动创建人员，并能调整其部门

**Independent Test**: 完成一次微信注册后 → 管理员登录管理后台 → 人员列表中出现新人员，`source_channel = 'wechat_register'` → 将其移动到子部门 → 验证成功

### Tests for User Story 3 ⚠️

- [x] T029 [P] [US3] Unit test for distributor list includes source_channel in `backend/tests/unit/test_distributor_service.py` — test_list_distributors_includes_source_channel

### Backend Implementation for User Story 3

- [x] T030 [US3] Update `distributor_service.py` `_to_dict()` — include `sourceChannel` in distributor response — in `backend/src/services/distributor_service.py`
- [x] T031 [US3] Update admin distributor list API response schema to include `sourceChannel` field — in `backend/src/schemas/distributor.py`

**Checkpoint**: 管理员能在人员列表中看到 `sourceChannel` 字段，区分注册来源

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, cleanup, and edge case hardening

- [ ] T032 Run quickstart.md manual verification: WeChat register flow end-to-end
- [ ] T033 Run quickstart.md manual verification: Phone register flow end-to-end
- [x] T034 [P] Edge case: verify concurrent registration (same phone, rapid requests) → only 1 Distributor created (phone uniqueness check in distributor_register)
- [x] T035 [P] Edge case: verify deleted default org → auto-selects next root org (or graceful fallback) (get_default_org returns sort_order min; graceful None fallback exists)
- [ ] T036 [P] Edge case: verify disabled user re-registration → reuses original record per spec
- [x] T037 Code review: verify all backend changes have corresponding tests (Constitution Principle I)
- [ ] T038 Run full test suite: `cd backend && pytest -v` — all tests must pass (requires Python venv)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T003) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — 🎯 MVP
- **User Story 2 (Phase 4)**: Depends on Foundational + US1 (shares `wechat_login` code path)
- **User Story 3 (Phase 5)**: Depends on Foundational — Independent of US1/US2
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

```
Phase 1: Setup
    │
    ▼
Phase 2: Foundational
    │
    ├──► Phase 3: US1 (P1) 🎯 MVP ──► Phase 4: US2 (P2) ──► Phase 6: Polish
    │                                        │
    └──► Phase 5: US3 (P3) ─────────────────┘
```

- **US1 (P1)**: No dependencies on other stories — can implement immediately after Foundational
- **US2 (P2)**: Depends on US1 (modifies same `wechat_login()` code path) — should be done after US1
- **US3 (P3)**: Independent of US1/US2 — can be done in parallel with US1

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Backend before MiniProgram (API contract must be ready)
- Core implementation before edge cases
- Story complete before moving to next priority

### Parallel Opportunities

- **Phase 1**: T001, T002 can run together
- **Phase 2**: T004, T005 (tests) can run in parallel
- **Phase 3 US1**: T009-T012 (all US1 tests) can run in parallel; T019 (frontend) can run in parallel with T013-T018 (backend)
- **Phase 4 US2**: T024, T025 (tests) can run in parallel
- **Phase 5 US3**: Can run in parallel with US1 (different files, independent)
- **Phase 6**: T034-T036 (edge cases) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Step 1: Write all US1 tests in parallel (they FAIL initially)
Task: "T009 [P] [US1] Integration test for WeChat login auto-mount"
Task: "T010 [P] [US1] Integration test for phone register auto-mount"
Task: "T011 [P] [US1] Unit test for wechat_login with default org"
Task: "T012 [P] [US1] Unit test for wechat_login without default org"

# Step 2: Backend and MiniProgram implementation can run in parallel
# Backend dev:
Task: "T013-T018 Backend: wechat_login, distributor-register, get_session"
# MiniProgram dev:
Task: "T019-T023 MiniProgram: auth-service, session-service, login, profile-setup"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008)
3. Complete Phase 3: User Story 1 (T009-T023)
4. **STOP and VALIDATE**: 用新微信账号测试注册流程
5. Deploy demo if ready — 核心价值已交付

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → 新用户可自主注册并直接使用小程序 (MVP!)
3. Add US2 → 已有用户绑定微信时数据安全有保障
4. Add US3 → 管理员可区分和管理自动注册人员
5. Polish → 边缘场景加固、全量测试

### Suggested MVP Scope

**Phase 1 + 2 + 3 = 23 tasks** — delivers the core value: users can self-register and use the app.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Constitution Principle I (TDD) is enforced — tests written BEFORE implementation
- Each user story checkpoint is independently testable
- Commit after each task or logical group
- Backend and MiniProgram tasks within a story can be done in parallel by different team members
