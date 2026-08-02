# Data Model: 组织人员管理（组织架构 + 分销员 + 组织管理员业绩视图）

**Branch**: `004-org-personnel-management` | **Date**: 2026-08-02
**Database**: MySQL 8.0 (InnoDB, utf8mb4)
**ORM**: SQLAlchemy 2.0+ (async)

**定位**: 本模型以**演进 + 迁移**方式替换 001 的层级/拓展人模型。新增 `organizations`、`distributors`、`org_qualifications` 三张主表，复用 `users` 作为统一账户表；`customers`、`promotion_codes`、`contribution_records`、`binding_requests` 等表的外键由 `promoters.id` 迁移为 `distributors.id`。旧表 `hierarchy_nodes`、`promoters`、`qualifications` 在迁移完成后废弃。

---

## 1. Entity-Relationship Overview

```
+------------------+         +-------------------------+
|    users         | 1 ---- 1|  distributors           |   N ---- 1   +------------------+
|  id (PK)         |         |  id (PK)                |              | organizations    |
|  phone (U)       |         |  user_id (U, FK)        |              |  id (PK)         |
|  password_hash   |         |  org_id (FK)            |              |  parent_id (FK)  |
|  openid (U)      |         |  org_role member/admin  |              |  name            |
|  user_type       |         |  status active/disabled |              |  org_type        |
+------------------+         +-------------------------+              |  level           |
                                                                       |  sort_order      |
                                                                       |  status          |
                                                                       +-----------------+
                                                                              |
                                                                              | parent_id (self-ref, 任意深度)
                                                                              v
+------------------+         +-------------------------+
| org_qualifications |   N ---| 1  organizations        |
|  id (PK)          |         |                          |
|  org_id (FK)      |         |  1 ---- N  distributors  |--- customers/promotion_codes/
|  file_urls        |         +-------------------------+    contribution_records/binding_requests
|  valid_until      |
|  status           |
+------------------+
```

**关键约束**:
- `distributors.user_id` UNIQUE → 一个用户至多一个分销员身份；`distributors.org_id` 单值 → **单组织归属**（spec Q1-A）。
- `organizations.parent_id` 自引用邻接表，任意深度（不沿用 MAX_LEVEL=6），环路由服务层递归检测。
- 组织资质为组织级唯一业务准入口；分销员无个人资质（spec Q2-A）。

---

## 2. Entity Definitions

### 2.1 organizations (组织)

任意深度通用组织树节点，取代 `hierarchy_nodes`。

```sql
CREATE TABLE organizations (
    id          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    parent_id   BIGINT UNSIGNED  NULL,
    name        VARCHAR(128)     NOT NULL,
    org_type    VARCHAR(50)      NOT NULL,
    level       SMALLINT UNSIGNED NOT NULL,
    sort_order  INT              NOT NULL DEFAULT 0,
    status      ENUM('active','disabled') NOT NULL DEFAULT 'active',
    created_at  DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_org_parent (parent_id),
    INDEX idx_org_type (org_type),
    INDEX idx_org_level (level),
    CONSTRAINT fk_org_parent FOREIGN KEY (parent_id) REFERENCES organizations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `parent_id` 仅根组织为 NULL；`level` 由树深度派生并维护（用于"某层级组织"查询）。
- `org_type` 为后台可配置字符串（seed: `headquarters`/`region`/`branch`…），满足"层级类型由后台定义"（FR-005）。
- `status`：`active`/`disabled`。组织业务可用性由资质派生（见 2.3 状态机），与 `status` 相互独立。
- 邻接表 + 应用层/SQL 递归 CTE；环路检测与最大深度校验在 `organization_service` 层。

### 2.2 distributors (分销员)

组织内人员账户，取代 `promoters`。账户（登录/绑定）字段复用 `users`。

```sql
CREATE TABLE distributors (
    id             BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id        BIGINT UNSIGNED  NOT NULL,
    org_id         BIGINT UNSIGNED  NOT NULL,
    org_role       ENUM('member','admin') NOT NULL DEFAULT 'member',
    status         ENUM('active','disabled') NOT NULL DEFAULT 'active',
    created_at     DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at     DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_dst_user (user_id),
    INDEX idx_dst_org (org_id),
    INDEX idx_dst_org_role (org_id, org_role),
    CONSTRAINT fk_dst_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_dst_org  FOREIGN KEY (org_id)  REFERENCES organizations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `user_id` UNIQUE + 单值 `org_id` → 单组织归属（FR-019）；调整归属 = 更新 `org_id`，新业绩计入新组织。
- `org_role = 'admin'` 表示该分销员是所属组织管理员（FR-013/026），由后台授权维护；设置/撤销即时生效。
- `status`：`active`/`disabled`；停用后无法登录，历史业绩保留在组织下。
- 手机号唯一性由 `users.phone` UNIQUE 保证（FR-012）。

### 2.3 users (用户) — 变更

`users` 保留为统一账户表，新增登录字段，支持手机号+密码登录与微信绑定。

```sql
ALTER TABLE users
    ADD COLUMN password_hash VARCHAR(255) NULL AFTER phone;
-- phone 用作登录标识（现有 UNIQUE 索引保留）
-- openid 用作微信绑定（现有字段，UNIQUE 索引保留）
```

**Design Notes:**
- `password_hash` nullable：兼容纯微信老用户；后台新建分销员时写入初始密码哈希。
- 首登强制绑定微信 = 写入 `users.openid`（FR-027）；绑定后微信授权可快速登录。
- `user_type` 保留（distributor 等），`distributors` 表标识分销员身份。

### 2.4 org_qualifications (组织资质)

组织级资质文件，取代 `qualifications`（个人资质）。

```sql
CREATE TABLE org_qualifications (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    org_id              BIGINT UNSIGNED NOT NULL,
    legal_entity_name   VARCHAR(256)    NOT NULL,
    qualification_types JSON            NOT NULL,
    credit_code         VARCHAR(64)     NOT NULL,
    file_urls           JSON            NOT NULL,
    valid_from          DATE            NULL,
    valid_until         DATE            NOT NULL,
    status              ENUM('reviewing','approved','rejected') NOT NULL DEFAULT 'reviewing',
    review_comment      TEXT            NULL,
    reviewed_by         BIGINT UNSIGNED NULL,
    reviewed_at         DATETIME(3)     NULL,
    created_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_oq_org (org_id),
    INDEX idx_oq_status (status),
    INDEX idx_oq_valid_until (valid_until),
    CONSTRAINT fk_oq_org      FOREIGN KEY (org_id)      REFERENCES organizations(id),
    CONSTRAINT fk_oq_reviewer FOREIGN KEY (reviewed_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `qualification_types` / `file_urls` 为 JSON 数组，沿用 001 语义；文件存 COS，仅存 URL。
- 一个组织可有多条资质记录（驳回后重提、到期续期），以 `created_at` 最新一条为当前有效记录。
- `valid_until` 为到期日；系统 cron 到期前 30 天提醒（FR-007）。

### 2.5 roles (角色) — 变更

权限 JSON 新增/替换细分权限点（Q3-B）。

```text
org:manage           取代 hierarchy:manage（组织树管理）
distributor:manage   新增（分销员账户管理）
org_admin:assign     新增（组织管理员设置）
qualification:review 复用（组织资质审核）
```

---

## 3. State Machines

### 3.1 Organization Status (`organizations.status`)

```
active ──(停用)──▶ disabled ──(启用)──▶ active
```

- 与组织资质独立：`status` 为管理员维护的组织生命周期；业务可用性由资质派生。
- 停用组织：其下分销员登录与业务按规则受限（规则细化见 tasks）。

### 3.2 Distributor Status & Role

```
status: active ──(停用)──▶ disabled ──(启用)──▶ active
role:   member ──(后台授权)──▶ admin ──(撤销)──▶ member
```

- `disabled` 分销员无法登录；历史业绩保留。
- `admin` 分销员在小程序可见组织业绩入口；撤销后入口即时消失（FR-014/FR-026）。

### 3.3 Organization Qualification Status (`org_qualifications.status`)

```
reviewing ──(通过)──▶ approved ──(过期检测)──▶ [expired 派生状态]
        └──(驳回)──▶ rejected ──(重新上传)──▶ reviewing
```

- 派生状态：`valid_until` 前 30 天 → `expiring`（提醒）；到期 → `expired`（暂停组织业务，历史业绩不受影响）。
- 组织业务可用性 = 最新一条资质 `approved` 且未过期 → 组织及其下分销员可开展业务（FR-008）。

---

## 4. Migration Mapping (001 → 004)

| 旧表/字段 | 新表/字段 | 迁移规则 |
|-----------|-----------|----------|
| `hierarchy_nodes` | `organizations` | 树结构原样迁移（parent_id/level/name）；`node_type` 映射到 `org_type`；`status` 默认 active |
| `promoters` | `distributors` | `user_id` 保留；`node_id` → `org_id`（对应迁移后的组织）；`org_role` 默认 member；`status` 默认 active |
| `qualifications` (promoter_id) | `org_qualifications` (org_id) | 每组织取其下拓展人 `created_at` 最新一条资质，状态保持原状；无资质则组织不建资质 |
| `customers.promoter_id` | `customers.distributor_id` | 外键切换 |
| `promotion_codes.promoter_id` | `promotion_codes.distributor_id` | 外键切换 |
| `contribution_records.promoter_id` | `contribution_records.distributor_id` | 外键切换 |
| `binding_requests.promoter_id` | `binding_requests.distributor_id` | 外键切换 |
| `roles.permissions['hierarchy:manage']` | `roles.permissions['org:manage']` | seed/迁移脚本更新 |

**迁移约束**: 单事务内完成建表 + 数据迁移 + 外键切换；迁移前备份；迁移后一致性校验（行数、贡献值求和、客户绑定数、推广码数），通过后废弃旧表（SC-009/010）。

---

## 5. RBAC Permission Matrix（变更后）

| Permission | Super Admin | Admin | Finance | Ops |
|-----------|:-----------:|:-----:|:-------:|:---:|
| `org:manage` | Y | Y | | |
| `distributor:manage` | Y | Y | | |
| `org_admin:assign` | Y | Y | | |
| `qualification:review` | Y | Y | | |
| `customer:view` | Y | Y | Y | Y |
| `contribution:view` | Y | Y | Y | |
| `sharing_rule:manage` | Y | | Y | |
| `reports:view` / `reports:export` | Y | Y | Y | |
| …（其余沿用 001 矩阵） | | | | |

---

## 6. Index Strategy

1. **组织树**: `organizations.parent_id` 索引用作子树查询；`org_type`/`level` 供层级筛选。
2. **分销员**: `distributors.user_id` UNIQUE（身份唯一）；`(org_id, org_role)` 复合索引支撑"组织内成员/管理员"查询与组织业绩成员列表。
3. **组织资质**: `org_qualifications.org_id`、`status`、`valid_until` 索引（到期检测/列表）。
4. **业绩聚合**: `contribution_records.distributor_id` + `month` 索引支撑组织业绩按月份聚合（沿用 001 索引策略，外键迁移后重建）。
