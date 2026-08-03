# Research: 客户管理模块

**Branch**: `005-customer-management` | **Date**: 2026-08-03
**目的**: 解决 Technical Context 中的技术决策/未知项，供 Phase 1 设计与 Phase 2 任务分解依据。

## 决策清单

### D1: 后台客户管理独立 API + 服务层
- **Decision**: 新增 `/admin/customers` 路由（`admin_customers.py`）+ 服务层 `customer_admin_service.py`；权限用 `require_permission("customers.read")`（读）/ `require_permission("customers.write")`（写）
- **Rationale**: 后台操作（组织维度列表、手工录入+医院匹配、敏感字段编辑、推广员变更）与分销员侧 `/customers`（小程序端个人客户列表）语义不同；遵循既有 `admin_organizations.py`/`admin_distributors.py` 模式
- **Alternatives considered**: 扩展现有 `/customers` 端点 → 权限与角色语义混杂；把逻辑塞进 `binding_service` → 职责不清（客户档案管理 ≠ 绑定请求）

### D2: 推广员变更记录独立表 `customer_change_logs`
- **Decision**: 新增表，operation_type ∈ {created, transfer}，记录 previous/new distributor_id、operator_id、reason、created_at；customer_id FK ON DELETE CASCADE
- **Rationale**: `BindingChangeLog.binding_request_id` 为非空 FK，手工录入客户可能没有绑定请求，无法复用；FR-012 要求完整可追溯
- **Alternatives considered**: 放宽 `BindingChangeLog` 约束 → 破坏既有审计语义；伪造 `BindingRequest` → 引入无意义数据，违反宪法 V

### D3: 手工录入 = 建客户档案 + 建 BindingRequest + 调医院匹配
- **Decision**: `create_manual_customer` 流程：① 校验身份证唯一 → ② 创建 `Customer`（distributor_id=推广员）→ ③ 创建 `BindingRequest`（source_type=manual，customer_id 关联，submitted_by=管理员）→ ④ 调 `rutai.bind_bj_user` → ⑤ matched → Customer 置 BOUND + rutai_user_id + bound_at，BindingRequest 置 bound；否则 Customer 保持 PENDING，失败原因写入 `BindingRequest.failure_reason`
- **Rationale**: 匹配结果与失败原因复用现有模型存储，无需给 customers 加列；客户详情"绑定历史"天然可查该次匹配；RUTAI_MOCK=true 时恒 matched（hrb_user_id=hrb_mock_{request_id}）
- **Alternatives considered**: 给 `customers` 加 `failure_reason` 列 → 与 BindingRequest 重复存储，破坏既有表结构

### D4: 推广员变更只更新 Customer，不碰 BindingRequest
- **Decision**: `transfer_customer`（新）：校验目标分销员存在且 `is_distributor_selectable` → 更新 `customer.distributor_id` → 写 `customer_change_logs`(transfer) + `AuditLog`
- **Rationale**: 推广员=业绩归属主体，绑定=医院绑定；推广员变更不影响医院绑定状态（spec 已确认）。不再沿用旧的"绑定请求转移"语义
- **Alternatives considered**: 沿用 `/admin/bindings/{id}/transfer` → 仅对已绑定客户、依赖 binding_request_id、与解绑耦合（解绑已移除）

### D5: 移除 `/admin/bindings` 解绑/转移
- **Decision**: 删除 `admin.py` 中 `/admin/bindings/{id}/unbind` 与 `/admin/bindings/{id}/transfer` 两个端点及其契约测试；`binding_service.unbind_customer`/`transfer_customer` 若无其他引用则一并移除
- **Rationale**: 解绑已由用户确认移除；转移迁移到客户级端点。保留即死代码，违反宪法 V
- **Alternatives considered**: 保留端点 → 两套解绑/转移入口，双轨维护

### D6: 分销员端绑定流程按身份证去重
- **Decision**: 修改 `binding_service.submit_binding_request`：医院匹配成功后，先按 `Customer.id_card_encrypted == id_card` 查重；已存在 → 更新该档案（binding_status=BOUND、rutai_user_id、bound_at；若 distributor_id 变化则同时更新并写 `customer_change_logs`(transfer)）；不存在 → 新建（现状）
- **Rationale**: 手工录入的待绑定客户由分销员端完成匹配时不得产生重复档案（FR-007）
- **Alternatives considered**: 不处理 → 同身份证重复建档，违反 FR-007

### D7: 敏感字段编辑强制原因 + 审计
- **Decision**: `PATCH /admin/customers/{id}` 对身份证/医保账户/手机号修改强制 `changeReason`，写入 `AuditLog`（action=update_customer_sensitive）
- **Rationale**: FR-010；宪法 IV 的"敏感数据修改审计"要求
- **Alternatives considered**: 不审计 → 无法追溯，违反宪法

### D8: 脱敏展示（明文存储）
- **Decision**: 身份证/医保账户/手机号明文存储，所有接口响应一律脱敏（如 `110***********1234`）；无解密端点
- **Rationale**: spec 澄清 Q1 用户确认"仅脱敏展示，不加密"；现有系统即此模式
- **Alternatives considered**: 真实加密 → 用户明确不做；宪法 IV 已于 2026-08-03 修订为"前后台脱敏"（v2.0.0），与本决策一致

### D9: 组织维度客户列表
- **Decision**: `GET /admin/customers?orgId=` 用 `customers JOIN distributors ON customer.distributor_id=distributors.id`，`WHERE distributors.org_id IN (选中组织子树全部 org_id)`；复用 `organization_service.get_subtree` + `_collect_org_ids` 获取子树
- **Rationale**: 客户所属组织由推广员（分销员）所属组织推导（spec 假设）；子树范围与组织人员模块一致
- **Alternatives considered**: 客户表存 org_id 冗余字段 → 双份事实，数据不一致风险

## 未知项状态

所有 NEEDS CLARIFICATION 已在上轮 `/speckit-clarify` 解决（录入即匹配、仅脱敏不加密、移除解绑、分销员端去重）。本轮无新增未知项。

## 依赖与风险

- **Rutai 医院接口**: 生产环境为外部依赖，已具备超时/重试/熔断（30s、3 次、熔断阈值 5）；手工录入在医院不可用时仍建档（PENDING + 失败原因），不阻断（spec 边界条件）
- **RUTAI_MOCK**: 当前 `RUTAI_MOCK=true`，医院匹配恒为 matched，去重/失败路径需靠单测覆盖
- **既有测试影响**: 移除 `/admin/bindings` 会删改 `tests/contract/test_binding.py` 中的解绑/转移契约用例
