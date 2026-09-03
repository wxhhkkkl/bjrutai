# Tasks: 后台消费录入

**Input**: Design documents from `/specs/016-admin-consumption-entry/`  
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: 项目宪章要求严格 TDD。每个用户故事必须先写测试、确认失败，再编写最小实现并回归。

**Organization**: 任务按用户故事分组。US1 完成单笔录入，US2 打通统计展示，US3 完成权限与审计闭环。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可以与同阶段其他标记任务并行，且不修改同一文件。
- **[Story]**: 对应规格中的用户故事。
- 每个任务均包含明确文件路径。

## Phase 1: Setup（现有项目基线）

**Purpose**: 在修改前确认现有消费统计与管理后台构建基线，避免把历史问题误判为本功能回归。

- [x] T001 运行现有消费后端基线测试 `backend/tests/contract/test_admin_contribution_dashboard.py`、`backend/tests/integration/test_contribution_calc.py`、`backend/tests/unit/test_contribution_dashboard_service.py`，并把任何既有失败记录到 `specs/016-admin-consumption-entry/quickstart.md`
- [x] T002 [P] 运行 `manageSystem/package.json` 中的 Vitest 和 Vite build 基线命令，并把任何既有失败记录到 `specs/016-admin-consumption-entry/quickstart.md`

---

## Phase 2: Foundational（所有故事的阻塞基础）

**Purpose**: 建立人工账单数据结构、请求模型和测试数据能力；本阶段完成前不得实现用户故事。

**⚠️ CRITICAL**: 先完成失败测试，再实施迁移和模型变更。

- [x] T003 [P] 在 `backend/tests/integration/test_migration_consistency.py` 增加迁移 016 的失败测试，覆盖人工录入字段、既有账单 `rutai_sync` 回填、幂等唯一约束及 015→016→015 往返
- [x] T004 实现 `backend/migrations/versions/016_manual_consumption_entry.py` 并同步扩展 `backend/src/models/bill.py`，使 T003 通过且不改变既有账单金额、状态和交易号
- [x] T005 [P] 在 `backend/src/schemas/admin_contribution.py` 定义客户搜索结果、人工消费创建请求及响应模型，落实整数分、带时区时间、版本号和备注长度校验
- [x] T006 [P] 在 `backend/tests/conftest.py` 增加管理员权限、有效绑定客户、停用人员/组织和人工账单所需的可复用测试辅助方法
- [x] T007 [P] 在 `backend/src/services/seed_service.py` 和 `manageSystem/src/constants/permissions.js` 增加 `contributions.write`，保留 `contributions.read` 为独立只读权限并确保系统管理员默认获得写权限

**Checkpoint**: 模型、迁移、schema、测试夹具和权限键准备完成；现有消费测试保持通过。

---

## Phase 3: User Story 1 - 录入单笔客户消费（Priority: P1）🎯 Functional MVP

**Goal**: 有写权限的管理员可以搜索有效绑定客户，确认只读归属并创建一条已支付人工消费；非法输入、客户变化和重复提交不会产生错误数据。

**Independent Test**: 使用一个有效绑定客户提交当前时间和 `12880` 分，返回唯一人工记录；无效金额、未来时间、解绑/停用客户、版本冲突被中文错误拦截；相同请求重试只存在一条账单。

### Tests for User Story 1（先写并确认失败）

- [x] T008 [P] [US1] 在 `backend/tests/unit/test_manual_consumption_service.py` 编写失败测试，覆盖客户搜索脱敏、金额/时间校验、客户资格与版本冲突、归属快照、交易号生成、幂等重放和幂等键内容冲突
- [x] T009 [P] [US1] 在 `backend/tests/contract/test_admin_manual_consumption.py` 编写失败契约测试，覆盖 `GET /admin/contributions/customers`、`POST /admin/contributions/manual` 的统一响应、字段、中文错误和 `Idempotency-Key`
- [x] T010 [P] [US1] 在 `manageSystem/src/components/contributions/__tests__/ManualConsumptionDialog.spec.js` 编写失败组件测试，覆盖远程客户搜索、脱敏展示、只读归属、金额转分、未来时间、最终确认、提交锁和失败保留表单

### Implementation for User Story 1

- [x] T011 [US1] 在 `backend/src/services/manual_consumption_service.py` 实现有效客户搜索、提交时重新校验、规范化请求指纹、唯一人工交易号、账单创建及数据库并发幂等处理，使 T008 通过
- [x] T012 [US1] 在 `backend/src/api/v1/admin_contributions.py` 增加客户搜索和人工消费创建端点，强制管理员会话、`contributions.write`、`Idempotency-Key` 和契约化中文错误，使 T009 通过
- [x] T013 [US1] 在 `backend/src/main.py` 的 `IdempotencyMiddleware` 中仅为人工消费创建路径绕过进程内缓存，让 `backend/src/services/manual_consumption_service.py` 的持久化幂等成为唯一业务判定
- [x] T014 [P] [US1] 在 `manageSystem/src/api/contributions.js` 增加客户搜索与人工消费创建封装，并显式发送 `Idempotency-Key`
- [x] T015 [US1] 在 `manageSystem/src/components/contributions/ManualConsumptionDialog.vue` 实现单弹窗录入表单、客户远程搜索、只读归属、人民币校验、带时区时间、备注、确认摘要和幂等键生命周期，使 T010 通过
- [x] T016 [US1] 在 `manageSystem/src/pages/contributions/index.vue` 按 `contributions.write` 接入“录入消费”按钮和弹窗，并在成功后刷新看板与当前排行
- [x] T017 [US1] 运行 `backend/tests/unit/test_manual_consumption_service.py`、`backend/tests/contract/test_admin_manual_consumption.py` 和 `manageSystem/src/components/contributions/__tests__/ManualConsumptionDialog.spec.js`，确认 US1 全部通过并把结果记录到 `specs/016-admin-consumption-entry/quickstart.md`

**Checkpoint**: US1 可独立演示完整单笔录入和防重复，但在完成 US3 审计验证前不得上线。

---

## Phase 4: User Story 2 - 消费记录进入统一统计（Priority: P1）

**Goal**: 人工消费使用录入时归属进入现有总额、趋势、组织/人员排行和最新明细，并清楚标记“人工录入”。

**Independent Test**: 录入一笔消费后，消费明细、当月总额、趋势、人员排行和组织排行均增加相同金额；随后转移客户，历史人工消费仍保留原人员和组织归属。

### Tests for User Story 2（先写并确认失败）

- [x] T018 [P] [US2] 在 `backend/tests/unit/test_consumption_service.py` 增加失败测试，覆盖人工账单优先使用归属快照、同步账单继续使用客户当前归属及退款/取消排除规则
- [x] T019 [P] [US2] 在 `backend/tests/integration/test_admin_manual_consumption_flow.py` 编写失败的端到端测试，覆盖“搜索→录入→总额/趋势/人员排行/组织排行更新”和客户转移后历史归属不变
- [x] T020 [P] [US2] 在 `backend/tests/contract/test_admin_contribution_dashboard.py` 增加失败契约测试，覆盖最新明细的客户、脱敏手机号、来源字段和存量 `rutai_sync` 默认值
- [x] T021 [P] [US2] 在 `manageSystem/src/pages/contributions/__tests__/index.spec.js` 编写失败页面测试，覆盖最新明细客户列、“人工录入/儒泰同步”标签及成功录入后的看板和排行刷新

### Implementation for User Story 2

- [x] T022 [US2] 修改 `backend/src/services/consumption_service.py`，以人工账单归属快照和同步账单当前客户归属形成统一有效归属聚合，使 T018 的所有口径测试通过
- [x] T023 [US2] 修改 `backend/src/services/contribution_dashboard_service.py`，让统计、趋势、组织/人员排行和最新明细使用统一有效归属，并返回客户脱敏信息及来源，使 T019、T020 通过
- [x] T024 [P] [US2] 修改 `manageSystem/src/pages/contributions/index.vue`，在最新消费明细中展示客户和中文来源标签，同时保持现有金额、状态、组织、人员和时间格式，使 T021 通过
- [x] T025 [US2] 运行 `backend/tests/unit/test_consumption_service.py`、`backend/tests/integration/test_admin_manual_consumption_flow.py`、`backend/tests/contract/test_admin_contribution_dashboard.py` 和 `manageSystem/src/pages/contributions/__tests__/index.spec.js`，确认 US2 独立验收并记录到 `specs/016-admin-consumption-entry/quickstart.md`

**Checkpoint**: US1 和 US2 构成完整业务链路，人工消费已进入所有本规格要求的统计展示。

---

## Phase 5: User Story 3 - 权限控制与操作追溯（Priority: P2）

**Goal**: 只允许有写权限的管理员录入，并为每笔成功人工消费留下与账单同事务的最小化安全审计证据。

**Independent Test**: 只读账号看不到入口且接口返回 403；有写权限账号成功录入后仅产生一条 AuditLog，包含操作人和业务标识但不包含原始敏感信息或备注正文；账单失败时审计也回滚。

### Tests for User Story 3（先写并确认失败）

- [x] T026 [P] [US3] 在 `backend/tests/contract/test_admin_manual_consumption.py` 增加失败测试，覆盖只读权限 403、写权限成功、系统管理员 seed 权限和重复重放不重复写审计
- [x] T027 [P] [US3] 在 `backend/tests/unit/test_manual_consumption_service.py` 增加失败测试，覆盖 AuditLog 字段最小化、管理员用户名快照、客户端 IP、账单与审计同事务提交/回滚
- [x] T028 [P] [US3] 在 `manageSystem/src/pages/contributions/__tests__/index.spec.js` 增加失败测试，覆盖只读账号隐藏按钮、有写权限显示按钮及后端拒绝消息保留表单

### Implementation for User Story 3

- [x] T029 [US3] 修改 `backend/src/services/manual_consumption_service.py`，在首次创建账单的同一事务写入 `AuditLog(action=manual_consumption_create)`，只保存管理员、客户、归属、金额和来源等必要信息且不复制敏感值或备注正文
- [x] T030 [US3] 修改 `backend/src/api/v1/admin_contributions.py`，将管理员 ID、用户名和可用客户端 IP 传入审计流程，并确保只读与无权限请求在服务执行前被拒绝
- [x] T031 [US3] 运行 `backend/tests/contract/test_admin_manual_consumption.py`、`backend/tests/unit/test_manual_consumption_service.py` 和 `manageSystem/src/pages/contributions/__tests__/index.spec.js`，确认 US3 权限与审计闭环通过并记录到 `specs/016-admin-consumption-entry/quickstart.md`

**Checkpoint**: 三个用户故事全部完成；功能达到可上线的权限、幂等、审计和数据一致性要求。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 完成全量回归、迁移安全、隐私复核和人工验收。

- [x] T032 运行完整后端测试 `backend/tests/` 并修复本功能引入的回归，确保新增代码覆盖率超过 80%，把最终命令与结果更新到 `specs/016-admin-consumption-entry/quickstart.md`
- [x] T033 使用临时数据库验证 `backend/migrations/versions/016_manual_consumption_entry.py` 从 015 升级、降级、再次升级，确认既有账单与幂等约束安全，并更新 `specs/016-admin-consumption-entry/quickstart.md`
- [x] T034 [P] 审核 `backend/src/services/manual_consumption_service.py`、`backend/src/api/v1/admin_contributions.py`、`manageSystem/src/components/contributions/ManualConsumptionDialog.vue` 和 `manageSystem/src/pages/contributions/index.vue`，确认日志、响应和 DOM 不泄露原始手机号、身份证号、医保账户或备注正文
- [ ] T035 按 `specs/016-admin-consumption-entry/quickstart.md` 完成管理后台人工冒烟测试，并运行 `manageSystem/package.json` 的完整 Vitest、lint 和生产 build 命令

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 无依赖，可立即执行；T001 与 T002 可并行。
- **Phase 2 Foundational**: 依赖 Phase 1；T003 必须先失败，T004 才能实现迁移；T005、T006、T007 可并行。
- **Phase 3 US1**: 依赖 Phase 2；是人工消费创建的功能基础。
- **Phase 4 US2**: 依赖 US1 已能创建人工账单；统计测试可独立运行。
- **Phase 5 US3**: 依赖 US1 的创建服务；可与 US2 并行推进，但同一开发者顺序执行可减少 `manual_consumption_service.py` 冲突。
- **Phase 6 Polish**: 依赖计划上线的所有用户故事完成。

### User Story Dependency Graph

```text
Setup
  -> Foundational
       -> US1 单笔录入
            -> US2 统一统计
            -> US3 权限与审计
                 \        /
                   Polish
```

### Within Each User Story

- 测试任务必须先完成并确认失败。
- 数据模型和 schema 先于服务；服务先于端点；端点契约先于前端接入。
- 每个故事的验证任务通过后才能标记该故事完成。
- 相同文件上的任务不得并行修改。

## Parallel Opportunities

### Setup and foundation

```text
T001 后端基线  ||  T002 管理后台基线
T003 迁移测试  ||  T005 schema  ||  T006 测试夹具  ||  T007 权限定义
```

### User Story 1

```text
T008 服务单元测试  ||  T009 API 契约测试  ||  T010 Vue 组件测试
T014 API 客户端可在 T011-T013 后端实现期间独立完成
```

### User Story 2

```text
T018 聚合单测  ||  T019 集成测试  ||  T020 看板契约测试  ||  T021 页面测试
T024 前端明细展示可在 T022-T023 后端实现期间基于契约推进
```

### User Story 3

```text
T026 权限契约测试  ||  T027 审计单测  ||  T028 前端权限测试
```

## Implementation Strategy

### Functional MVP

1. 完成 Phase 1 和 Phase 2。
2. 完成 US1，验证管理员能够安全创建单笔人工消费。
3. 停止并独立验证 US1，不立即部署。

### Deployable MVP

1. 在 Functional MVP 基础上完成 US2，确保数据进入统一统计。
2. 完成 US3，确保权限和审计闭环。
3. 完成 Phase 6 全量回归和迁移验证后才可部署。

### Incremental Delivery

1. Setup + Foundational → 数据结构和权限基础就绪。
2. US1 → 单笔录入可用且具备持久化幂等。
3. US2 → 看板、趋势和排行数据闭环。
4. US3 → 安全审计闭环，达到上线条件。
5. Polish → 全量测试、迁移、隐私和人工验收。

## Notes

- `[P]` 仅表示文件不冲突且前置依赖相同，不代表可以跳过 TDD 顺序。
- 所有金额在接口和数据库中使用整数分，前端只在输入/展示时使用元。
- 人工消费不允许编辑、删除、退款或回传儒泰；不得在实施中扩展这些能力。
- 每个用户故事通过独立测试后再形成原子提交；本任务生成阶段不自动提交。
