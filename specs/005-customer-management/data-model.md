# Data Model: 客户管理模块

**Branch**: `005-customer-management` | **Date**: 2026-08-03
**Database**: MySQL 8.0 (InnoDB, utf8mb4)
**ORM**: SQLAlchemy 2.0+ (async)

**定位**: 在既有 `customers` / `binding_requests` / `binding_change_logs` 基础上，**新增一张表** `customer_change_logs` 承载"推广员变更记录"（建档初始归属 + 变更）。`customers` 表**无结构变更**（身份证/医保账户继续明文存储、界面脱敏，spec 澄清 Q1）。

---

## 1. Entity-Relationship Overview

```
+------------------+         +-------------------------+
|    users         | 1 ---- 1|  distributors           |
|  id (PK)         |         |  id (PK)                |---- 1
|  phone (U)       |         |  user_id (U, FK)        |     |
|  user_type       |         |  org_id (FK)            |     | N
+------------------+         +-------------------------+     |
                                                              | distributor_id（推广员，单值）
                                                              v
+------------------+  1 ----- N   +----------------------+
|   customers      |               | customer_change_logs|
|  id (PK)         |               |  id (PK)            |
|  distributor_id  |               |  customer_id (FK)   |
|  name            |               |  operation_type     |
|  phone           |               |  previous_distributor_id |
|  id_card         | (明文存储)     |  new_distributor_id |
|  medical_account | (明文存储)     |  operator_id (FK→users) |
|  family_phone    |               |  reason             |
|  rutai_user_id   |               |  created_at         |
|  binding_status  |               +----------------------+
+------------------+
```

**关键约束**:
- `customers.distributor_id` 单值 → 客户同一时间仅归属一个推广员（分销员）；客户所属组织由 `distributors.org_id` 推导，不冗余存储。
- `customer_change_logs.operation_type` ∈ {`created`, `transfer`}；`customer_id` FK **ON DELETE CASCADE**。
- 身份证号作为客户唯一标识（查重键）；`id_card_encrypted` 列实际存储明文（现状，spec 澄清 Q1）。

---

## 2. Entity Definitions

### 2.1 customers（客户，既有表，无变更）

```sql
CREATE TABLE customers (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    distributor_id          BIGINT UNSIGNED NOT NULL,           -- FK distributors.id
    name                    VARCHAR(100) NULL,
    phone                   VARCHAR(20)  NULL,
    phone_masked            VARCHAR(20)  NULL,
    id_card_encrypted       TEXT         NULL,                  -- 明文存身份证
    id_card_masked          VARCHAR(50)  NULL,
    medical_account_encrypted TEXT       NULL,                  -- 明文存医保账户
    family_phone            VARCHAR(20)  NULL,
    rutai_user_id           VARCHAR(100) NULL,
    note                    TEXT         NULL,
    binding_status          ENUM('pending','bound','unbound') NOT NULL DEFAULT 'pending',
    bound_at                DATETIME     NULL,
    version                 INT          NOT NULL DEFAULT 1,
    created_at              DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at              DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_customer_distributor (distributor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 身份证查重键：`id_card_encrypted`（明文值）。手工录入与分销员端绑定去重均以此为唯一键（FR-007）。

### 2.2 customer_change_logs（推广员变更记录，新增）

```sql
CREATE TABLE customer_change_logs (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id             BIGINT UNSIGNED NOT NULL,
    operation_type          ENUM('created','transfer') NOT NULL,
    previous_distributor_id BIGINT UNSIGNED NULL,
    new_distributor_id      BIGINT UNSIGNED NULL,
    operator_id             BIGINT UNSIGNED NOT NULL,           -- FK users.id
    reason                  VARCHAR(500) NULL,
    created_at              DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_ccl_customer (customer_id),
    CONSTRAINT fk_ccl_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `operator_id` 为后台管理员 user id（来自 JWT `sub`）。`previous_distributor_id` 在 `created` 时为空。

### 2.3 binding_requests（既有表，复用）

手工录入时创建 `source_type='manual'`、`customer_id` 关联的绑定请求，用于存储匹配结果与失败原因（`status`/`failure_reason`/`match_level`）。分销员端绑定继续复用该表。**无结构变更**。

---

## 3. State Transitions

**customer.binding_status**（= 与哈尔滨互联网医院绑定关系）:
```
pending ──医院匹配成功──> bound      （手工录入 / 分销员端绑定去重）
  │
  └── 匹配失败/接口异常 ──> 保持 pending（失败原因存 BindingRequest.failure_reason）
```
- 推广员变更（created/transfer）**不改变** `binding_status`（绑定=医院绑定，推广员=业绩归属，spec 已确认）。
- 本迭代无解绑操作（spec 澄清 Q2）。

**customer_change_logs.operation_type**:
- `created`：建档时记录初始推广员。
- `transfer`：管理员变更推广员 / 分销员端去重时推广员变化。

---

## 4. Key Queries

- **组织维度客户列表**（FR-003）:
  ```
  SELECT c.* FROM customers c
  JOIN distributors d ON c.distributor_id = d.id
  WHERE d.org_id IN (子树 org_id 集合)   -- 复用 organization_service.get_subtree + _collect_org_ids
  ```
- **推广员变更记录**（FR-012）:
  ```
  SELECT * FROM customer_change_logs WHERE customer_id = ? ORDER BY created_at DESC
  ```
- **身份证去重**（FR-007）:
  ```
  SELECT id FROM customers WHERE id_card_encrypted = ? LIMIT 1
  ```

---

## 5. Migration Plan

- `008_customer_change_logs`：新建 `customer_change_logs` 表（SQL 见 2.2）。
- 无存量数据迁移（新表为空）。
