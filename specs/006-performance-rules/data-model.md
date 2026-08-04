# Data Model: 绩效规则模块

**Branch**: `006-performance-rules` | **Date**: 2026-08-03
**Database**: MySQL 8.0 (InnoDB, utf8mb4)
**ORM**: SQLAlchemy 2.0+ (async)

**定位**: 新增三张表承载"按组织配置的绩效提成方式 + 变更历史 + 月度提成结果"。旧的按层级 `sharing_rules` / `contribution_coefficient` 表**保留但废弃**（不再参与计算，不迁移数据）。

---

## 1. Entity-Relationship Overview

```
organizations 1 ---- N performance_rules         commission_results
   org_id (FK)          id (PK)                   id (PK)
                        org_id (FK)               period (YYYY-MM)
                        rule_type                 distributor_id (FK)
                        tiers (JSON)              org_id
                        status                    rule_type
                        version                   base_cent
                        created_by                ratio
                        updated_at                commission_cent
                                                    computed_at
performance_rules 1 ---- N performance_rule_change_logs
   rule_id (FK)              id (PK), rule_id (FK, CASCADE)
                             changed_by (FK users), old_value/new_value (JSON), created_at
```

**关键约束**:
- `performance_rules(org_id, rule_type)` UNIQUE → 每组织每类型至多一条配置（组织内 `intra_org` / 组织管理 `org_management`）。
- 金额一律以**分**（整数 `cent`）存储，避免浮点误差；比率 `ratio` 为小数（0-1）。
- 提成结果 `commission_results(period, distributor_id, rule_type)` UNIQUE → 每人每周期每类型一条结果（幂等重算覆盖）。

---

## 2. Entity Definitions

### 2.1 performance_rules（绩效提成方式）

```sql
CREATE TABLE performance_rules (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    org_id      BIGINT UNSIGNED NOT NULL,
    rule_type   ENUM('intra_org','org_management') NOT NULL,
    tiers       JSON NOT NULL,                 -- [{minCent, maxCent, ratio}]
    status      ENUM('active','inactive') NOT NULL DEFAULT 'active',
    version     INT NOT NULL DEFAULT 1,
    created_by  BIGINT UNSIGNED NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_rule_org_type (org_id, rule_type),
    CONSTRAINT fk_pr_org FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `tiers` JSON 示例：`[{"minCent":0,"maxCent":1000000,"ratio":0.05},{"minCent":1000000,"maxCent":null,"ratio":0.08}]`
> （`maxCent=null` 表示上不封顶；区间含下限、不含上限，服务层校验）

### 2.2 performance_rule_change_logs（变更历史）

```sql
CREATE TABLE performance_rule_change_logs (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    rule_id     BIGINT UNSIGNED NOT NULL,
    changed_by  BIGINT UNSIGNED NOT NULL,
    old_value   JSON NULL,
    new_value   JSON NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_prcl_rule (rule_id),
    CONSTRAINT fk_prcl_rule FOREIGN KEY (rule_id) REFERENCES performance_rules(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.3 commission_results（月度提成结果）

```sql
CREATE TABLE commission_results (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    period           VARCHAR(7) NOT NULL,       -- 'YYYY-MM'
    distributor_id   BIGINT UNSIGNED NOT NULL,
    org_id           BIGINT UNSIGNED NOT NULL,
    rule_type        ENUM('intra_org','org_management') NOT NULL,
    base_cent        BIGINT NOT NULL,           -- 消费金额基数（分）
    ratio            DECIMAL(10,6) NOT NULL,    -- 命中阶梯比率
    commission_cent  BIGINT NOT NULL,           -- 提成金额（分）
    computed_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_comm_period_dist_type (period, distributor_id, rule_type),
    KEY idx_comm_org_period (org_id, period),
    CONSTRAINT fk_comm_dist FOREIGN KEY (distributor_id) REFERENCES distributors(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 3. State Transitions

**performance_rules.status**: `active` ↔ `inactive`（停用；版本号递增记录修改）。
- 新规则创建即 `active`；同 `(org_id, rule_type)` 再次配置即覆盖（版本 +1，写变更日志）。

**commission_results**: 月度结算幂等生成——同 `(period, distributor_id, rule_type)` 已存在则覆盖更新（支持重算）。

**distributor.org_role**: 收紧为**每组织至多一名 `admin`**（`set_role` 强制 + 迁移 010 清理存量）。

---

## 4. Key Queries

- **组织两种提成方式**（FR-003）:
  ```sql
  SELECT * FROM performance_rules WHERE org_id = ? ORDER BY rule_type
  ```
- **成员消费金额（组织内提成基数）**（FR-011）:
  ```sql
  SELECT c.distributor_id, SUM(b.paid_amount_cent)
  FROM bills b JOIN customers c ON b.customer_id = c.id
  WHERE c.distributor_id IN (组织成员)
    AND b.transaction_status NOT IN ('refunded','cancelled')
    AND b.transaction_time BETWEEN 周期起止
  GROUP BY c.distributor_id
  ```
- **子树消费总额（组织管理提成基数）**（FR-011）:
  ```sql
  SELECT SUM(b.paid_amount_cent)
  FROM bills b JOIN customers c ON b.customer_id = c.id
  WHERE c.distributor_id IN (组织及全部下级组织的所有成员 id)
    AND b.transaction_status NOT IN ('refunded','cancelled')
    AND b.transaction_time BETWEEN 周期起止
  ```

---

## 5. Migration Plan

- `009_performance_rules`：创建 3 张表（SQL 见上）。
- `010_demote_duplicate_admins`：将每组织多管理员中的额外管理员（保留 `id` 最小者）降为 `member`（FR-008 存量清理）。
- 无存量数据迁移到新表（新规则从空开始配置）。
