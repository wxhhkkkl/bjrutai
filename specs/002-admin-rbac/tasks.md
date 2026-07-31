# Tasks: 后台管理 RBAC 权限管理

**Input**: Design documents from `/specs/002-admin-rbac/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/admin-rbac.md

**Tests**: Included per constitution Principle I (TDD is non-negotiable). Backend tasks follow Red→Green→Refactor cycle.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US3 = 系统管理员播种, US1 = 管理员账户管理, US2 = 角色管理与权限配置)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/src/`, `backend/tests/`
- **Frontend**: `manageSystem/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the codebase for RBAC feature implementation

- [x] T001 [P] Create permissions constants file with 22 permissions across 12 modules in manageSystem/src/constants/permissions.js per contracts/admin-rbac.md
- [x] T002 [P] Generate Alembic migration to add `is_system` BOOLEAN NOT NULL DEFAULT FALSE column to roles table in backend/migrations/

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core backend protections and reusable frontend component — MUST complete before any user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Backend: Role model update

- [x] T003 Add `is_system` Mapped[bool] field to Role model in backend/src/models/role.py

### Backend: Delete role protections (TDD)

- [x] T004 [P] Write unit test: delete system role returns error in backend/tests/unit/test_role_service.py
- [x] T005 [P] Write unit test: delete role with assigned admins returns error in backend/tests/unit/test_role_service.py
- [x] T006 Update delete_role endpoint: reject system roles (is_system=True) in backend/src/api/v1/admin_accounts.py
- [x] T007 Update delete_role endpoint: reject roles assigned to admin accounts in backend/src/api/v1/admin_accounts.py
- [x] T008 [P] Write unit test: update system role name returns error in backend/tests/unit/test_role_service.py
- [x] T009 Protect system role name from modification in update_role endpoint in backend/src/api/v1/admin_accounts.py

### Backend: Admin account protections (TDD)

- [x] T010 [P] Write unit test: disable admin account "admin" returns error in backend/tests/unit/test_admin_service.py
- [x] T011 Protect default admin (username="admin") from being disabled in disable_admin_account endpoint in backend/src/api/v1/admin_accounts.py
- [x] T012 Protect default admin (username="admin") from being deleted (if delete endpoint exists) in backend/src/api/v1/admin_accounts.py

### Frontend: Permission Tree reusable component

- [x] T013 [P] Write unit test: PermissionTree renders modules and checkboxes in manageSystem/tests/components/PermissionTree.test.js
- [x] T014 Create PermissionTree.vue component (el-tree, checkbox mode, module grouping, select-all per module) in manageSystem/src/components/PermissionTree.vue

**Checkpoint**: Foundation ready — `is_system` field in place, role/admin protections active, PermissionTree component reusable

---

## Phase 3: User Story 3 - 系统管理员默认角色播种 (Priority: P1) 🎯 MVP

**Goal**: System auto-creates "系统管理员" role with all permissions on first startup; default admin assigned to this role

**Independent Test**: Start backend on fresh DB → roles table has "系统管理员" with is_system=true and 22 permissions → admin_account_roles links admin to this role → delete role API returns error → admin login returns all 22 permissions

### Tests for User Story 4

> **Write these FIRST, ensure they FAIL before implementation**

- [x] T015 [P] [US3] Write integration test: seed creates system admin role when none exists in backend/tests/integration/test_seed.py
- [x] T016 [P] [US3] Write integration test: seed is idempotent (second run does not duplicate) in backend/tests/integration/test_seed.py
- [x] T017 [P] [US3] Write integration test: seed assigns system admin role to admin account in backend/tests/integration/test_seed.py

### Implementation for User Story 4

- [x] T018 [US3] Create seed_service.py with `seed_system_admin_role()` function (idempotent, uses SELECT FOR is_system=True to check existence) in backend/src/services/seed_service.py
- [x] T019 [US3] Integrate seed_service call into lifespan startup (after admin account seeding, before scheduler start) in backend/src/main.py
- [x] T020 [US3] Ensure seed assigns admin account (username="admin") to system admin role if not already assigned in backend/src/services/seed_service.py

**Checkpoint**: Fresh backend startup → system admin role exists, admin has full permissions, delete protected

---

## Phase 4: User Story 1 - 管理员账户管理 (Priority: P1)

**Goal**: Admin list page with submenu navigation showing all admin accounts; create, edit, enable/disable functionality

**Independent Test**: Login → navigate to 账户管理 → 管理员列表 → see admins → create new admin → edit their roles → disable → re-enable → admin account "admin" has no disable option

### Frontend Route & Menu

- [x] T02- [ ] T021 [US1] Update router: restructure `/accounts` route with children (`/accounts/admins`, `/accounts/roles`) and redirect in manageSystem/src/router/index.js
- [x] T02- [ ] T022 [US1] Update sidebar menu: replace flat "账户管理" with el-sub-menu containing "管理员列表" and "角色管理" children in manageSystem/src/App.vue

### Tests for User Story 1

- [x] T02- [ ] T023 [P] [US1] Write component test: AdminList renders account table with mock data in manageSystem/tests/pages/AdminList.test.js
- [x] T02- [ ] T024 [P] [US1] Write component test: Create/Edit admin dialog validates required fields in manageSystem/tests/pages/AdminList.test.js

### Implementation for User Story 1

- [x] T02- [ ] T025 [P] [US1] Create rbac store (Pinia): admin list fetching, CRUD actions, state management in manageSystem/src/stores/rbac.js
- [x] T02- [ ] T026 [US1] Rewrite accounts/index.vue: admin list table (username, status tag, roles, created_at), pagination, search in manageSystem/src/pages/accounts/index.vue
- [x] T02- [ ] T027 [US1] Build create admin dialog: username, password fields, role multi-select, form validation in manageSystem/src/pages/accounts/index.vue
- [x] T02- [ ] T028 [US1] Build edit admin dialog: password reset field, role reassignment in manageSystem/src/pages/accounts/index.vue
- [x] T02- [ ] T029 [US1] Implement enable/disable buttons with confirmation dialogs in manageSystem/src/pages/accounts/index.vue
- [x] T03- [ ] T030 [US1] Hide disable/delete buttons for admin account (username="admin") row in manageSystem/src/pages/accounts/index.vue

**Checkpoint**: Admin account management fully functional — list, create, edit roles, disable/enable, admin protection

---

## Phase 5: User Story 2 + 3 - 角色管理与权限配置 (Priority: P2)

**Goal**: Role list page with create/edit/delete; permission checkbox tree in role edit dialog; system role protected from deletion and name change

**Independent Test**: Navigate to 角色管理 → see roles → create role with selective permissions → edit role permissions → system admin role has no delete button and name field disabled → delete unused role succeeds → delete assigned role fails with error

### Tests for User Story 2

- [x] T03- [ ] T031 [P] [US2] Write component test: RoleList renders roles with system badge and delete protection in manageSystem/tests/pages/RoleList.test.js
- [x] T03- [ ] T032 [P] [US2] Write component test: PermissionTree emits selected permissions on change in manageSystem/tests/pages/RoleList.test.js

### Implementation for User Story 2

- [x] T03- [ ] T033 [US2] Rewrite accounts/roles.vue: role list table (name, permission count badge, is_system indicator, created_at) in manageSystem/src/pages/accounts/roles.vue
- [x] T03- [ ] T034 [US2] Build create role dialog: name input + PermissionTree component integration in manageSystem/src/pages/accounts/roles.vue
- [x] T03- [ ] T035 [US2] Build edit role dialog: pre-fill existing permissions in PermissionTree, disable name field for system roles in manageSystem/src/pages/accounts/roles.vue
- [x] T03- [ ] T036 [US2] Implement delete role button with pre-check (show error if assigned or system) in manageSystem/src/pages/accounts/roles.vue
- [x] T03- [ ] T037 [US2] Hide delete button and disable name editing for system roles (is_system=true) in manageSystem/src/pages/accounts/roles.vue
- [x] T03- [ ] T038 [US2] Connect rbac store to role CRUD endpoints (list, create, update, delete) in manageSystem/src/stores/rbac.js

**Checkpoint**: Role management fully functional — list, create with permissions, edit, delete protection, system role badge

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final integration validation and cleanup

- [ ] T039 [P] Run backend test suite and verify all tests pass: `cd backend && pytest`
- [x] T04- [ ] T040 [P] Run frontend test suite and verify all tests pass: `cd manageSystem && npm run test`
- [x] T04- [ ] T041 Run quickstart.md verification checklist end-to-end (login → submenus → admin CRUD → role CRUD → system role protection)
- [x] T04- [ ] T042 [P] Ensure rbac store permissions are returned and accessible via auth store for future UI permission gating in manageSystem/src/stores/rbac.js
- [x] T04- [ ] T043 Verify SC-001: time creating a new admin account via the UI — target under 2 minutes from login to completion

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — BLOCKS all user stories
- **US3 (Phase 3)**: Depends on Foundational (Phase 2) — backend seed logic
- **US1 (Phase 4)**: Depends on Foundational (Phase 2) — frontend admin list page
- **US2 (Phase 5)**: Depends on Foundational (Phase 2) — frontend role list page (can parallel with US1)
- **Polish (Phase 6)**: Depends on US3 + US1 + US2 complete

### User Story Dependencies

- **US3 (系统管理员播种)**: Depends on Phase 2 (is_system field, protections). No dependency on frontend stories.
- **US1 (管理员账户管理)**: Depends on Phase 2. No dependency on US3 or US2.
- **US2 (角色管理)**: Depends on Phase 2. Uses PermissionTree from Phase 2. No dependency on US1 or US3.

### Parallel Opportunities

- Phase 1: T001 and T002 can run in parallel
- Phase 2: T004, T005, T008, T010 can run in parallel (write tests first)
- After Phase 2: US3 (backend), US1 (frontend), US2 (frontend) can ALL run in parallel
- Phase 4 (US1): T023, T024, T025 can run in parallel
- Phase 5 (US2): T031, T032 can run in parallel

---

## Parallel Example: After Foundational Phase

```bash
# All three user stories can start in parallel:
# Developer A: Phase 3 (US3) - Backend seed + tests
Task: "T015 [P] [US3] Integration test: seed creates system admin role"
Task: "T016 [P] [US3] Integration test: seed is idempotent"
Task: "T017 [P] [US3] Integration test: seed assigns to admin"
Task: "T018 [US3] Create seed_service.py"
Task: "T019 [US3] Integrate into main.py lifespan"

# Developer B: Phase 4 (US1) - Frontend admin list
Task: "T021 [US1] Update router with accounts children"
Task: "T022 [US1] Update sidebar with el-sub-menu"
Task: "T025 [P] [US1] Create rbac store"
Task: "T026 [US1] Rewrite accounts/index.vue"

# Developer C: Phase 5 (US2) - Frontend role list
Task: "T033 [US2] Rewrite accounts/roles.vue"
Task: "T034 [US2] Build create role dialog with PermissionTree"
```

---

## Implementation Strategy

### MVP First (Backend Seed + Minimum Admin Management)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US3 (System admin seed + protections)
4. **STOP and VALIDATE**: Fresh startup → system admin role exists, admin has permissions
5. Deploy backend if ready

### Full Delivery

1. Complete Phases 1-2 → Foundation ready
2. Complete Phase 3 (US3) → Backend RBAC infrastructure
3. Complete Phase 4 (US1) → Admin account management page
4. Complete Phase 5 (US2) → Role management page with permission tree
5. Phase 6 → Validation and polish

### Suggested MVP Scope

Phase 1 + Phase 2 + Phase 3 = Backend RBAC seed + protections (backend-only MVP).
Add Phase 4 = Usable admin account management (first frontend page).

---

## Notes

- [P] tasks = different files, no dependencies on other in-progress tasks
- [Story] label maps task to specific user story for traceability
- Each user story phase is independently completable and testable
- Constitution Principle I (TDD) enforced: tests written first, verified to fail, then implementation
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
