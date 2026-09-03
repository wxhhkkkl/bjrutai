# Implementation Plan: 后台消费录入

**Branch**: `016-admin-consumption-entry` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/016-admin-consumption-entry/spec.md`

## Summary

在现有管理后台“消费业绩”页面增加单笔消费录入。后台通过新增的管理员接口搜索有效绑定客户并创建人工账单；归属人员和组织由后端在提交时重新校验并保存快照，前端不可修改。人工账单继续进入现有 `bills` 统一统计链路，同时通过数据库唯一约束实现跨进程幂等，并写入安全审计日志。

## Technical Context

**Language/Version**: Python 3.11+；JavaScript（Vue 3.5）  
**Primary Dependencies**: FastAPI 0.115、SQLAlchemy 2.0 async、Pydantic v2、Alembic；Vue 3、Vite 5、Element Plus、Pinia、Axios  
**Storage**: MySQL 8.0（生产）；SQLite（自动化测试）；`bills` 表新增人工录入元数据  
**Testing**: pytest 8 + pytest-asyncio（单元、契约、集成）；Vitest 2 + Vue Test Utils；Vite 生产构建  
**Target Platform**: Linux 后端服务；现代桌面浏览器管理后台  
**Project Type**: Web service + admin SPA  
**Performance Goals**: 正常网络下 95% 录入请求 3 秒内返回；客户搜索首屏最多 20 条；录入成功后看板刷新即可反映数据  
**Constraints**: 金额全程使用整数分；仅有效绑定客户；人工记录只能为已支付；不得回传儒泰；敏感字段全程脱敏；同一次提交只能生成一条记录  
**Scale/Scope**: 单笔人工录入、单页弹窗交互；复用现有消费看板、统计和排行，不建设完整账务管理模块

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Pre-design | Post-design | Evidence |
|---|---|---|---|
| I. Test-Driven Development | PASS | PASS | 先增加服务单元测试、接口契约测试和完整录入集成测试，再实现后端与前端；前端补充组件测试和构建校验。 |
| II. API-First Design | PASS | PASS | [API contract](./contracts/api.md) 先定义客户搜索、人工录入、错误码与统一响应封装。 |
| III. Separation of Concerns | PASS | PASS | 后端负责权限、客户状态、归属、金额、幂等和审计；Vue 仅负责输入、确认和展示。 |
| IV. Database Integrity | PASS | PASS | Alembic 版本化迁移；金额存整数分；手机号和身份证号仅返回脱敏值；写入与 AuditLog 在同一事务中完成。 |
| V. Simplicity (YAGNI) | PASS | PASS | 复用 `Bill` 与现有统计服务，只增加两条接口和一个弹窗；不引入批量、编辑、删除、退款或外部回传。 |

Gate status: PASS。不存在需要豁免的宪章违规，也没有未解决的 `NEEDS CLARIFICATION`。

## Project Structure

### Documentation (this feature)

```text
specs/016-admin-consumption-entry/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md
│   └── admin-ui.md
├── checklists/
│   └── requirements.md
└── tasks.md                 # 后续 /speckit-tasks 生成，本阶段不创建
```

### Source Code (repository root)

```text
backend/
├── migrations/versions/
│   └── 016_manual_consumption_entry.py
├── src/
│   ├── api/v1/admin_contributions.py
│   ├── models/bill.py
│   ├── schemas/admin_contribution.py
│   ├── services/
│   │   ├── contribution_dashboard_service.py
│   │   ├── consumption_service.py
│   │   ├── manual_consumption_service.py
│   │   └── seed_service.py
│   └── main.py
└── tests/
    ├── contract/test_admin_manual_consumption.py
    ├── integration/test_admin_manual_consumption_flow.py
    └── unit/test_manual_consumption_service.py

manageSystem/
├── src/
│   ├── api/contributions.js
│   ├── components/contributions/ManualConsumptionDialog.vue
│   ├── constants/permissions.js
│   └── pages/contributions/
│       ├── index.vue
│       └── __tests__/index.spec.js
└── package.json
```

**Structure Decision**: 沿用现有 FastAPI 服务层和 Vue 管理后台分层。人工消费创建逻辑放入独立的 `manual_consumption_service.py`，现有只读看板路由中增加客户搜索与创建端点；弹窗拆成局部组件，页面负责成功后的看板刷新，不新增跨页面 Pinia 状态。

## Implementation Design

### Backend flow

1. `GET /api/v1/admin/contributions/customers` 使用 `contributions.write` 权限搜索已绑定客户，只返回脱敏信息、当前有效归属和客户版本号。
2. `POST /api/v1/admin/contributions/manual` 强制接收 `Idempotency-Key`，校验金额、时区时间和请求长度。
3. 服务在事务中重新读取客户、分销人员和组织，检查绑定状态、启用状态及客户版本；版本变化返回冲突，要求管理员重新确认。
4. 服务创建 `Bill`：生成 `MANUAL-...` 唯一交易号，设置 `paid` 状态、人民币整数分、`manual` 来源以及人员/组织历史快照。
5. 同一事务写入 `AuditLog(action=manual_consumption_create)`；审计详情仅保存必要标识、金额和脱敏/快照信息，不复制手机号、身份证号或备注正文。
6. `(created_by_admin_id, idempotency_key)` 唯一约束保证多进程和服务重启后仍不重复；请求指纹用于识别同一键对应不同内容。
7. 消费聚合以人工账单的归属快照为准，其他存量账单继续使用客户当前归属；看板最新明细增加客户和来源字段。

### Admin flow

1. 页面依据 `contributions.write` 展示“录入消费”按钮。
2. 弹窗远程搜索已绑定客户，选中后展示脱敏手机号/身份证号、人员和组织只读信息。
3. 表单使用日期时间、人民币金额和备注；前端金额转换为整数分，消费时间发送带时区的 ISO 8601 字符串。
4. 提交前展示客户、归属、时间和金额确认；提交期间锁定按钮。
5. 打开表单生成幂等键；失败重试相同内容复用该键，内容变化后生成新键；成功后关闭弹窗并刷新看板与当前排行。

### Test order (TDD)

1. 后端契约测试先覆盖权限、请求响应、中文错误、脱敏和错误码。
2. 服务单元测试覆盖金额/时间校验、客户状态、版本冲突、归属快照、请求指纹和幂等重放。
3. 集成测试覆盖“搜索客户 → 录入 → 明细/总额/趋势/个人与组织排行更新”，以及客户转移后历史归属不变。
4. 前端组件测试覆盖按钮权限、客户只读归属、金额转换、二次确认、重复点击和失败保留表单。
5. 实现最小代码使测试通过，最后运行全量后端测试、前端测试、迁移校验及生产构建。

## Complexity Tracking

无宪章违规，不需要复杂度豁免。

