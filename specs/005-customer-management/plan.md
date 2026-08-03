# Implementation Plan: 客户管理模块

**Branch**: `005-customer-management` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-customer-management/spec.md`

## Summary

客户管理模块重构：管理后台"客户管理"改为 **组织结构树（左）+ 组织维度客户列表（右）**，默认选中根组织；管理员可**手工录入客户**（录入即调用哈尔滨互联网医院接口尝试绑定匹配）；客户详情支持维护**身份证/医保账户**（明文存储、界面脱敏）；管理员可**更改客户推广员**且每次变更生成完整审计记录；移除"绑定管理"菜单；分销员端绑定流程按**身份证去重**，复用已有档案而非新建重复档案。

技术要点：新增后台客户管理 API 层（`/admin/customers`）+ 服务层；新增 `customer_change_logs` 变更记录表；复用 `RutaiClient.bind_bj_user` 做医院匹配（`RUTAI_MOCK=true` 下恒为 matched）；改造 `binding_service.submit_binding_request` 做去重；移除 `/admin/bindings` 解绑/转移端点。

## Technical Context

**Language/Version**: Python 3.11+（后端）；Vue 3 + Vite（管理后台）
**Primary Dependencies**: FastAPI、SQLAlchemy 2.0 async、Pydantic v2、httpx；Element Plus、Pinia、Axios
**Storage**: MySQL 8.0（Tencent Cloud，Alembic 迁移）
**Testing**: pytest + pytest-asyncio（后端 TDD：契约 + 单元）；manageSystem 构建校验
**Target Platform**: Linux 服务器（后端）；浏览器（管理后台）
**Project Type**: web-service + admin-spa + mini-program
**Performance Goals**: 切换组织后客户列表 2 秒内展示（SC-002）
**Constraints**: 复用现有权限点 `customers.read` / `customers.write`（不新增）；敏感信息明文存储 + 界面统一脱敏（用户已确认）；身份证号作为客户唯一标识
**Scale/Scope**: 组织 ~10 个、客户千级以内；页分页加载

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Test-Driven Development | ✅ PASS | 所有新端点/服务先写测试；契约测试强制（`test_admin_customers.py`） |
| II. API-First Design | ✅ PASS | 新增 `/admin/customers` 契约（contracts/customers.md），统一响应封装 |
| III. Separation of Concerns | ✅ PASS | 业务逻辑入 `customer_admin_service.py`，API 层薄，前端只做展示/表单校验 |
| IV. Database Integrity | ✅ PASS | 宪法 IV 已于 2026-08-03 修订为"前后台脱敏"（v2.0.0，原则再定义），与本 spec 澄清 Q1 一致：敏感数据明文存储、前后台输出统一脱敏、审计日志（FR-010 → AuditLog）仍满足 |
| V. Simplicity (YAGNI) | ✅ PASS | 新增独立 `customer_change_logs` 表而非强行复用 `BindingChangeLog`（见 Complexity Tracking） |

Gate 状态：全部 PASS（宪法 IV 已修订对齐）。继续 Phase 0。

## Project Structure

### Documentation (this feature)

```text
specs/005-customer-management/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output（技术决策）
├── data-model.md        # Phase 1 output（新增表）
├── quickstart.md        # Phase 1 output（运行/验证）
├── contracts/           # Phase 1 output（接口契约）
│   └── customers.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   │   └── customer_change_log.py     # 新增：推广员变更记录（created/transfer）
│   ├── schemas/
│   │   └── customer_admin.py           # 新增：后台客户管理请求/响应模型
│   ├── services/
│   │   └── customer_admin_service.py   # 新增：组织维度列表/手工录入+匹配/敏感字段/变更推广员
│   ├── api/v1/
│   │   ├── admin_customers.py          # 新增：/admin/customers 路由（customers.read/write 权限）
│   │   └── admin.py                    # 移除 /admin/bindings 的 unbind/transfer 端点
│   └── services/binding_service.py     # 改：submit_binding_request 按身份证去重
├── migrations/versions/
│   └── 008_customer_change_logs.py     # 新增 customer_change_logs 表
└── tests/
    ├── contract/test_admin_customers.py  # 新增契约测试
    ├── unit/test_customer_admin_service.py
    └── contract/test_binding.py          # 改：去重契约用例

manageSystem/
├── src/
│   ├── api/customers.js                 # 新增：后台客户管理 API 封装
│   ├── pages/customers/
│   │   ├── index.vue                    # 重构：左组织树 + 右客户列表（复用 org-tree.vue 树模式）
│   │   ├── detail.vue                   # 增强：身份证/医保账户编辑+变更记录+更改推广员
│   │   └── binding.vue                  # 删除（绑定管理菜单移除）
│   ├── components/customers/
│   │   ├── CreateCustomerDialog.vue     # 新增：手工录入表单（含推广员下拉）
│   │   └── TransferPromoterDialog.vue   # 新增：更改推广员（填原因）
│   └── router/index.js                  # 移除 /customers/binding 路由
```

**Structure Decision**: 沿用现有前后端分离结构（backend/manageSystem/miniProgram 三独立层）。业务逻辑统一放 `services/`，API 层薄。前端客户页参照 `pages/org/org-tree.vue` 已落地的"左树右表"布局与默认选中根组织逻辑。

## Complexity Tracking

> 复杂度说明（设计决策理由）。宪法检查无违规：宪法 IV 已修订为"前后台脱敏"（v2.0.0），与本 spec 一致。

| Design Choice | Why Needed | Simpler Alternative Rejected Because |
|---------------|------------|-------------------------------------|
| 新增 `customer_change_logs` 表（非复用 `BindingChangeLog`） | 手工录入客户可能无 `binding_request`，而 `BindingChangeLog.binding_request_id` 为非空 FK；推广员变更需独立完整追溯（FR-012） | 为每个客户伪造 `BindingRequest` 或放宽 FK 会引入脏数据与耦合，比新增一张轻量表更复杂 |
