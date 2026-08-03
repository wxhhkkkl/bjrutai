# Tasks: 客户管理模块

**Input**: Design documents from `/specs/005-customer-management/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/customers.md](./contracts/customers.md), [quickstart.md](./quickstart.md)

**Tests**: 本项目宪法（`.specify/memory/constitution.md` 原则 I）强制 TDD——所有生产代码先写测试、每个 API 端点必须有契约测试。因此每个用户故事均含测试任务，按 TDD 先红后绿执行。

**Organization**: 任务按用户故事分组，支持独立实现与独立验收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

## Path Conventions

Web app 三独立层：`backend/src/`（FastAPI）、`manageSystem/src/`（Vue 3 admin）、`miniProgram/`（微信小程序，本迭代仅涉及后端绑定流程去重）。

---

## Phase 1: Setup（基线校验）

**Purpose**: 在改动前确认既有代码库基线可用

- [X] T001 Verify baseline: run full backend test suite green（`cd backend && ./venv/Scripts/python.exe -m pytest -q`）before any changes
- [X] T002 [P] Verify baseline: manageSystem build passes（`cd manageSystem && npm run build`）before any changes

---

## Phase 2: Foundational（阻塞性前置）

**Purpose**: 所有用户故事共用的数据层/服务层/API 骨架。本阶段完成前不得开始任何用户故事。

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create `CustomerChangeLog` model in `backend/src/models/customer_change_log.py`（operation_type enum `created`/`transfer`，customer_id FK→customers ON DELETE CASCADE，previous_distributor_id/new_distributor_id，operator_id，reason，created_at；str-enum 用 `values_callable` 对齐迁移列）
- [X] T004 Create migration `008_customer_change_logs` in `backend/migrations/versions/008_customer_change_logs.py`（CREATE TABLE `customer_change_logs`，见 [data-model.md §2.2](data-model.md)）
- [X] T005 [P] Create request schemas in `backend/src/schemas/customer_admin.py`（`CustomerCreateRequest` name/phone/idCard 必填 + medicalAccount/familyPhone/note/distributorId；`CustomerUpdateRequest` 可选字段 + `changeReason` 条件必填；`CustomerTransferRequest` newDistributorId/reason 必填）
- [X] T006 [P] Create `backend/src/services/customer_admin_service.py` with shared helpers: masking `_mask_phone`/`_mask_id_card`/`_mask_medical_account`，change-log serialization `_log_distributor_change(db, customer, operation_type, prev, new, operator_id, reason)`，change-log→dict 序列化
- [X] T007 Create `backend/src/api/v1/admin_customers.py` router scaffold（`prefix="/admin/customers"`，`get_admin_user` + `require_permission("customers.read"/"customers.write")` 依赖）and register in `backend/src/api/v1/app.py`（import + include_router）
- [X] T008 [P] Create `manageSystem/src/api/customers.js` with admin customer API methods（list/create/detail/update/transfer/changeLogs，复用 [org.js](manageSystem/src/api/org.js) 的 payload 解包模式）

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 组织维度客户视图 (Priority: P1) 🎯 MVP

**Goal**: 客户管理页改为"左组织树 + 右客户列表"，默认选中根组织；选中组织展示该组织及全部下级组织范围内推广员名下客户。

**Independent Test**: 后台客户管理 → 默认展示根组织子树客户 → 切换组织 → 列表按组织范围变化（含下级组织）；状态筛选/关键词搜索/分页正常。

### Tests for User Story 1（TDD：先写、先红）⚠️

- [X] T009 [P] [US1] Contract test `GET /admin/customers` in `backend/tests/contract/test_admin_customers.py`（组织子树范围、脱敏字段、status/keyword 过滤、分页、无 `customers.read` 权限返回 40300）
- [X] T010 [P] [US1] Unit test `list_customers_by_org` in `backend/tests/unit/test_customer_admin_service.py`

### Implementation for User Story 1

- [X] T011 [US1] Implement `list_customers_by_org` in `backend/src/services/customer_admin_service.py`（`customers JOIN distributors ON customer.distributor_id=distributors.id WHERE distributors.org_id IN (子树 org_id 集合)`，复用 `organization_service.get_subtree` + `distributor_service._collect_org_ids`；返回 `{items,total,page,pageSize,hasMore}`，输出统一脱敏）
- [X] T012 [US1] Implement `GET /admin/customers` endpoint in `backend/src/api/v1/admin_customers.py`（orgId 必填，require `customers.read`）
- [X] T013 [US1] Implement org tree + default-root selection + list wiring in `manageSystem/src/pages/customers/index.vue`（复用 [org-tree.vue](manageSystem/src/pages/org/org-tree.vue) 的左树布局与默认选中根逻辑；右侧表格数据源切换为 `GET /admin/customers?orgId=`，保留状态筛选/搜索/加载更多）

**Checkpoint**: US1 独立可用——切换组织客户列表随之更新

---

## Phase 4: User Story 2 - 后台手工录入客户 (Priority: P1)

**Goal**: 管理员在选中组织下手工录入客户（必填姓名/手机号/身份证，选填医保账户/家属电话/备注，指定推广员），录入即调哈尔滨互联网医院接口匹配。

**Independent Test**: 选中组织 → 新建客户 → 填资料选推广员 → 提交 → 列表出现新客户；mock 匹配成功 status=已绑定；身份证重复被拒。

### Tests for User Story 2（TDD：先写、先红）⚠️

- [X] T014 [P] [US2] Contract test `POST /admin/customers` in `backend/tests/contract/test_admin_customers.py`（创建成功 matched/pending、必填校验 40000、身份证重复 40900、推广员不可用 40020、生成 `created` 变更记录、无 `customers.write` 权限返回 40300）
- [X] T015 [P] [US2] Unit test `create_manual_customer` in `backend/tests/unit/test_customer_admin_service.py`（注入 mock RutaiClient：matched→bound + pending→pended；医院异常仍建档）

### Implementation for User Story 2

- [X] T016 [US2] Implement `create_manual_customer` in `backend/src/services/customer_admin_service.py`（① 身份证唯一查重 → ② 创建 `Customer`（distributor_id=推广员）→ ③ 创建 `BindingRequest`（source_type=manual、customer_id 关联、submitted_by=管理员）→ ④ 调 `rutai.bind_bj_user` → ⑤ matched：Customer 置 bound + rutai_user_id + bound_at，BindingRequest 置 bound；否则 Customer 保持 pending、失败原因写 `BindingRequest.failure_reason` → ⑥ `_log_distributor_change` 写 created 记录；服务允许注入 mock client）
- [X] T017 [US2] Implement `POST /admin/customers` endpoint in `backend/src/api/v1/admin_customers.py`（require `customers.write`）
- [X] T018 [US2] Create `manageSystem/src/components/customers/CreateCustomerDialog.vue`（表单：姓名/手机号/身份证/医保账户/家属电话/备注 + 推广员下拉，推广员列表用 `distributorApi.list(orgId)` 取当前组织及子树分销员，默认选第一个）
- [X] T019 [US2] Wire 新建客户 button + dialog + reload in `manageSystem/src/pages/customers/index.vue`

**Checkpoint**: US1 + US2 均独立可用

---

## Phase 5: User Story 3 - 客户详情敏感字段维护 (Priority: P1)

**Goal**: 客户详情展示并维护身份证号/医保账户（脱敏），编辑敏感字段强制填写修改原因并留审计。

**Independent Test**: 详情页展示脱敏身份证/医保账户；编辑敏感字段不填原因被拦截；填原因保存后审计可查。

### Tests for User Story 3（TDD：先写、先红）⚠️

- [X] T020 [P] [US3] Contract test `GET/PATCH /admin/customers/{id}` in `backend/tests/contract/test_admin_customers.py`（详情脱敏字段、PATCH 敏感字段无 changeReason 返回 40000、审计落 AuditLog、无 `customers.write` 权限 PATCH 返回 40300）
- [X] T021 [P] [US3] Unit test `get_customer_detail` + `update_customer_profile` in `backend/tests/unit/test_customer_admin_service.py`

### Implementation for User Story 3

- [X] T022 [US3] Implement `get_customer_detail` + `update_customer_profile` in `backend/src/services/customer_admin_service.py`（详情返回脱敏 idCardMasked/medicalAccountMasked + promoter/org 信息 + 统计；更新时 phone/idCard/medicalAccount 任一修改必须带 `changeReason` 否则拒绝，写 `AuditLog` action=`update_customer_sensitive`，idCard 变更重新查重并刷新 masked）
- [X] T023 [US3] Implement `GET` + `PATCH /admin/customers/{id}` endpoints in `backend/src/api/v1/admin_customers.py`（GET require `customers.read`；PATCH require `customers.write`）
- [X] T024 [US3] Add idCard/medicalAccount masked editable fields (with changeReason input) to `manageSystem/src/pages/customers/detail.vue`（切换为 `/admin/customers/{id}` 数据源）

**Checkpoint**: US1-US3 均独立可用

---

## Phase 6: User Story 4 - 推广员变更与详细变更记录 (Priority: P1)

**Goal**: 管理员更改客户推广员（填原因），每次变更生成完整审计记录并在详情可追溯。

**Independent Test**: 更改推广员 → 填原因 → 成功且详情"推广员变更记录"显示操作人/时间/变更前后推广员/原因；目标推广员不可用被拒。

### Tests for User Story 4（TDD：先写、先红）⚠️

- [X] T025 [P] [US4] Contract test `POST /admin/customers/{id}/transfer` + `GET /admin/customers/{id}/change-logs` in `backend/tests/contract/test_admin_customers.py`（新推广员不可用 40020、同推广员 40000、transfer 记录与 created 记录齐全、无 `customers.write` 权限 transfer 返回 40300）
- [X] T026 [P] [US4] Unit test `transfer_customer` in `backend/tests/unit/test_customer_admin_service.py`

### Implementation for User Story 4

- [X] T027 [US4] Implement `transfer_customer` + `get_change_logs` in `backend/src/services/customer_admin_service.py`（校验目标分销员 `is_distributor_selectable`、不可更改为当前推广员；更新 `customer.distributor_id`；`_log_distributor_change` 写 transfer + `AuditLog`；**不改 binding_status**；get_change_logs 返回完整记录含推广员姓名/操作人姓名）
- [X] T028 [US4] Implement `POST /admin/customers/{id}/transfer` + `GET /admin/customers/{id}/change-logs` endpoints in `backend/src/api/v1/admin_customers.py`（transfer require `customers.write`；change-logs require `customers.read`）
- [X] T029 [US4] Create `manageSystem/src/components/customers/TransferPromoterDialog.vue` + 推广员变更记录 display in `manageSystem/src/pages/customers/detail.vue`（转移弹窗 + "推广员变更记录"列表）

**Checkpoint**: US1-US4 均独立可用

---

## Phase 7: User Story 5 - 移除"绑定管理"菜单并合并能力 (Priority: P2)

**Goal**: 后台不再出现"绑定管理"菜单/页面；解绑能力移除；推广员转移已由 US4 承接。

**Independent Test**: 登录后台确认菜单无"绑定管理"；直接访问旧地址不白屏；客户管理内仍可完成推广员变更。

### Implementation for User Story 5

- [X] T030 [US5] Remove `/customers/binding` route from `manageSystem/src/router/index.js` and add a `/customers/binding` → `/customers` redirect（或全局 catch-all），确保直接访问旧地址不出现空白页（spec US5-AC4）
- [X] T031 [US5] Delete `manageSystem/src/pages/customers/binding.vue` and orphaned `manageSystem/src/components/customers/UnbindDialog.vue` + `TransferDialog.vue`（确认无其他引用后删除）
- [X] T032 [US5] Remove `/admin/bindings` unbind/transfer endpoints from `backend/src/api/v1/admin.py`
- [X] T033 [US5] Remove unbind/transfer contract tests from `backend/tests/contract/test_binding.py` and orphaned `binding_service.unbind_customer`/`transfer_customer` methods in `backend/src/services/binding_service.py`（确认无其他引用后移除）
- [X] T034 [US5] Verify manageSystem build passes after route/component removal（`cd manageSystem && npm run build`）

**Checkpoint**: 导航与后端均无"绑定管理"残留

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 影响多用户故事的横切行为（FR-007 分销员端去重）与全量回归

- [X] T035 [P] Implement binding dedup in `backend/src/services/binding_service.py`（`submit_binding_request` 医院匹配成功后按 `Customer.id_card_encrypted == id_card` 查重：已存在→复用/更新该档案（binding_status=bound、rutai_user_id、bound_at；distributor_id 变化则更新并 `_log_distributor_change` 写 transfer），不新建重复档案；不存在→维持新建）
- [X] T036 [P] Contract test binding dedup in `backend/tests/contract/test_binding.py`（同身份证已存在待绑定客户时，分销员端匹配成功不产生第二档案）
- [X] T037 Run full backend pytest suite（`cd backend && ./venv/Scripts/python.exe -m pytest -q`）; fix regressions
- [ ] T038 Run manageSystem build + manual verification per [quickstart.md](./quickstart.md)（SC-001~SC-009）
- [X] T039 Update `specs/005-customer-management/quickstart.md` / `contracts/customers.md` if behavior drifted during implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify baseline first
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational
  - US1→US2→US3→US4 共享 `admin_customers.py` / `customer_admin_service.py`，单实现者按序推进；前端组件（Create/TransferDialog、detail.vue）可部分并行
  - US5（移除绑定管理）依赖 US4 完成（转移能力已迁至客户级后再删旧端点）
- **Polish (Phase 8)**: Depends on all desired user stories（T035/T036 分销员端去重可独立于 US1-US5 并行）

### User Story Dependencies

- **US1 (P1)**: Foundational 后可开始 - 无其他故事依赖（MVP）
- **US2 (P1)**: Foundational 后可开始；依赖 US1 的列表用于回显，但可独立测试
- **US3 (P1)**: Foundational 后可开始 - 独立
- **US4 (P1)**: Foundational 后可开始；依赖 T006 `_log_distributor_change`；前端变更记录依赖 US3 的 detail.vue 骨架
- **US5 (P2)**: 依赖 US4（转移已迁移）后执行

### Within Each User Story

- 测试先写并确认 FAIL（Red），再实现使其 PASS（Green）
- Models/schemas → services → endpoints → 前端集成
- 每个 checkpoint 独立验证后进入下一故事

### Parallel Opportunities

- Setup：T001/T002 并行
- Foundational：T003/T005/T006/T008 并行（不同文件）；T004 依赖 T003；T007 依赖 T006
- US1-US4 后端均共享 `admin_customers.py` + `customer_admin_service.py`——同一实现者不并行；跨故事的前端组件（T018/T029）与后端不同文件可并行
- 每个故事内测试任务 [P] 并行
- T035/T036（分销员端去重）与 US1-US5 完全独立，可并行

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test GET /admin/customers in backend/tests/contract/test_admin_customers.py"
Task: "Unit test list_customers_by_org in backend/tests/unit/test_customer_admin_service.py"

# Implementation tasks (sequential, same service+router files):
Task: "Implement list_customers_by_org in backend/src/services/customer_admin_service.py"
Task: "Implement GET /admin/customers in backend/src/api/v1/admin_customers.py"
Task: "Wire org tree + list in manageSystem/src/pages/customers/index.vue"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: 基线校验
2. Phase 2: Foundational（模型/迁移/schemas/服务助手/路由/api 模块）
3. Phase 3: US1 组织维度客户视图
4. **STOP and VALIDATE**: 客户管理左树右表 + 默认根组织 + 组织切换

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. US1 组织维度客户视图 → 独立验证（MVP）
3. US2 手工录入（+医院匹配）→ 独立验证
4. US3 敏感字段维护 → 独立验证
5. US4 推广员变更 + 变更记录 → 独立验证
6. US5 移除绑定管理 → 验证导航
7. Polish：分销员端去重 + 全量回归

### Parallel Team Strategy

后端（US1-US4 顺序）与前端组件开发（T018/T029）可并行；T035/T036 分销员端去重可独立分配。

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- 每个用户故事独立可完成、独立可验收
- 每个端点契约测试遵循宪法原则 I（TDD）
- 测试确认 FAIL 后再实现；每个故事 checkpoint 独立验证
- 提交粒度：每个故事完成后建议一次 checkpoint commit
- 敏感信息输出统一脱敏（宪法 IV v2.0.0：前后台脱敏）
