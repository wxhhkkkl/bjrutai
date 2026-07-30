# Data Model: 北京儒泰分销管理后端与API

**Branch**: `001-distribution-management-api` | **Date**: 2026-07-30
**Database**: MySQL 8.0 (InnoDB, utf8mb4)
**ORM**: SQLAlchemy 2.0+ (async)

---

## 1. Entity-Relationship Diagram

### 1.1 High-Level Domain View

```
+====================================================================================================+
|                              AUTH & IDENTITY DOMAIN                                                |
|                                                                                                    |
|  +------------------+       +---------------------+       +------------------+                     |
|  |     users        |       |   admin_accounts    | M---N |     roles        |                     |
|  |------------------|       |---------------------|       |------------------|                     |
|  | id (PK)          |       | id (PK)             |       | id (PK)          |                     |
|  | openid (U)       |       | username (U)        |       | name (U)         |                     |
|  | user_type        |       | password_hash       |       | permissions (JSON)|                    |
|  | name, phone...   |       | status, locked_until|       +------------------+                     |
|  +--------+---------+       +----------+----------+              |                                |
|           |                            |                admin_account_roles                       |
|           | 1                          | 1              (junction table)                           |
|           |                            |                                                          |
+===========|============================|==========================================================+
            |                            |
+===========|============================|==========================================================+
|           |           HIERARCHY & PROMOTION DOMAIN              |                                   |
|           |                                                     |                                   |
|  +--------v---------+    +-------------------+                 |                                   |
|  |    promoters     |    | hierarchy_nodes   |                 |                                   |
|  |------------------|    |-------------------|                 |                                   |
|  | id (PK)          |    | id (PK)           |                 |                                   |
|  | user_id (U,FK)   |--->| parent_id (FK:self|                 |                                   |
|  | node_id (U,FK)   |----| level (1-6)       |                 |                                   |
|  | qualification    |    | node_type         |                 |                                   |
|  |   _status        |    +--------+----------+                 |                                   |
|  +----+------+------+             |                            |                                   |
|       |      |                    | tree (self-ref)            |                                   |
|       |      |         +----------v----------+                 |                                   |
|       |      |         | hierarchy_snapshots |                 |                                   |
|       |      |         | (audit trail)       |                 |                                   |
|       |      |         +---------------------+                 |                                   |
|       |      |                                                 |                                   |
|       |      +----> +------------------+                       |                                   |
|       |             | qualifications   |                       |                                   |
|       |             +------------------+                       |                                   |
|       |                                                        |                                   |
|       +------------> +------------------+                      |                                   |
|                      | promotion_codes  |                      |                                   |
|                      +------------------+                      |                                   |
+====================================================================================================+

+====================================================================================================+
|                              CUSTOMER & BINDING DOMAIN                                             |
|                                                                                                    |
|  +------------------+       +---------------------+       +-------------------------+              |
|  |    customers     |       |  binding_requests   |       |  binding_change_logs    |              |
|  |------------------|       |---------------------|       |-------------------------|              |
|  | id (PK)          |<------| customer_id (FK)    |       | binding_request_id (FK) |              |
|  | promoter_id (FK) |       | promoter_id (FK)    |       | from/to_status          |              |
|  | node_id (FK)     |       | submitted_by (FK)   |--+    | operator_id             |              |
|  | name, phone...   |       | idempotency_key (U) |  |    +-------------------------+              |
|  | hrb_user_id      |       | status              |  |                                             |
|  +-------+----------+       +---------------------+  |    (submitted_by -> users)                   |
|          |                                            |                                             |
|          | 1:N                                        |                                             |
|          |                                            |                                             |
|  +-------v----------+       +------------------+     |                                             |
|  | followup_records |       | consent_records  |     |                                             |
|  |------------------|       |------------------|     |                                             |
|  | doctor_id (FK)   |       | user_id (FK)     |     |                                             |
|  | customer_id (FK) |       | customer_id (FK) |     |                                             |
|  +------------------+       +------------------+     |                                             |
+====================================================================================================+

+====================================================================================================+
|                              BILLING & CONTRIBUTION DOMAIN                                         |
|                                                                                                    |
|  +------------------+       +------------------------+      +------------------+                   |
|  |      bills       |       | contribution_records   |      |  sharing_rules   |                   |
|  |------------------|       |------------------------|      |------------------|                   |
|  | id (PK)          |------>| bill_id (FK)           |      | applicable_level |                   |
|  | transaction_id(U)|       | promoter_id (FK)       |      | rule_type        |                   |
|  | customer_id (FK) |       | points (DECIMAL)       |      | base, value      |                   |
|  | paid_amount      |       | status                 |      | effective_from   |                   |
|  | refund_amount    |       | source_type            |      | status           |                   |
|  | status           |       | conversion_rate        |      +--------+---------+                   |
|  +------------------+       | sharing_rule_id (FK)   |               |                             |
|                             | settlement_log_id (FK) |               |                             |
|                             +------------+-----------+               |                             |
|                                          |                           |                             |
|                                          | N:1                       |                             |
|                                          v                           v                             |
|                             +------------------+       +-------------------------+                 |
|                             | settlement_logs  |       | sharing_rule_change_logs|                 |
|                             |------------------|       |-------------------------|                 |
|                             | period (U)       |       | sharing_rule_id (FK)    |                 |
|                             | status           |       | changed_by (FK->admin)  |                 |
|                             +------------------+       +-------------------------+                 |
+====================================================================================================+

+====================================================================================================+
|                              CONTENT & SYSTEM DOMAIN                                               |
|                                                                                                    |
|  +------------------+       +------------------------+      +------------------+                   |
|  |    articles      |       | reconciliation_reports|      |  notifications   |                   |
|  |------------------|       |------------------------|      |------------------|                   |
|  | title, body      |       | report_type            |      | category         |                   |
|  | category, status |       | time_range             |      | recipient info   |                   |
|  | created_by (FK)  |       | report_data (JSON)     |      | is_read          |                   |
|  +------------------+       | generated_by (FK)      |      +------------------+                   |
|                             +------------------------+                                             |
|                                                                                                    |
|  +---------------------+                                                                           |
|  |    api_call_logs    |     (partitioned by YEAR)                                                 |
|  |---------------------|                                                                           |
|  | interface_name      |                                                                           |
|  | request/response    |                                                                           |
|  | duration_ms         |                                                                           |
|  +---------------------+                                                                           |
+====================================================================================================+
```

### 1.2 Legend

```
PK  = Primary Key
FK  = Foreign Key
U   = Unique constraint
(U) = Unique constraint
---> = Foreign key relationship (many-to-one direction)
M--N = Many-to-many (via junction table)
```

---

## 2. Entity Definitions

### 2.1 users (用户)

WeChat mini-program users. Covers promoters (L2-L5) and doctors. Admin users are managed
separately via `admin_accounts`.

```sql
CREATE TABLE users (
    id              BIGINT UNSIGNED    NOT NULL AUTO_INCREMENT,
    openid          VARCHAR(64)        NOT NULL,
    unionid         VARCHAR(64)        NULL,
    user_type       ENUM('promoter','doctor') NOT NULL,
    is_active       TINYINT(1)         NOT NULL DEFAULT 1,
    name            VARCHAR(64)        NULL,
    phone           VARCHAR(20)        NULL,
    organization    VARCHAR(128)       NULL,
    avatar_url      VARCHAR(512)       NULL,
    created_at      DATETIME(3)        NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)        NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at      DATETIME(3)        NULL,

    PRIMARY KEY (id),
    UNIQUE INDEX idx_users_openid (openid),
    INDEX idx_users_user_type (user_type),
    INDEX idx_users_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `openid` is the stable WeChat identity per mini-program. Unique.
- `unionid` is nullable -- available only when the mini-program is bound to an Open Platform account.
- `user_type` distinguishes promoters from doctors. Admins are in `admin_accounts`.
- `phone` is the verified WeChat phone number, stored as plaintext at the DB layer (encrypted/masked
  at API layer per FR-061).
- Soft-delete via `deleted_at`; GDPR/right-to-deletion handled at application layer.
- `organization` is free-text; no FK to a formal organization table (YAGNI -- no organization
  management feature in scope).

### 2.2 user_tokens (用户令牌)

Manages the dual-token mechanism (access token + refresh token) for WeChat users per FR-003.

```sql
CREATE TABLE user_tokens (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id             BIGINT UNSIGNED  NOT NULL,
    access_token_hash   VARCHAR(256)     NOT NULL,
    refresh_token_hash  VARCHAR(256)     NOT NULL,
    access_expires_at   DATETIME(3)      NOT NULL,
    refresh_expires_at  DATETIME(3)      NOT NULL,
    is_revoked          TINYINT(1)       NOT NULL DEFAULT 0,
    revoked_at          DATETIME(3)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_ut_access_hash (access_token_hash),
    UNIQUE INDEX idx_ut_refresh_hash (refresh_token_hash),
    INDEX idx_ut_user_id (user_id),
    INDEX idx_ut_refresh_expires (refresh_expires_at),
    CONSTRAINT fk_ut_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- Hashed tokens stored, never plaintext. Lookup by hash, return token once on creation.
- `is_revoked` bulk-set on logout (FR-005: "使当前所有令牌失效").
- Separate table (not columns on `users`) because a user may have multiple concurrent sessions
  or a refresh token rotation window.

### 2.3 admin_accounts (后台账号)

Admin panel login accounts. Password-based auth with JWT (FR-005a), lockout on repeated
failures (FR-005b), RBAC via roles (FR-005c).

```sql
CREATE TABLE admin_accounts (
    id                    BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    username              VARCHAR(64)      NOT NULL,
    password_hash         VARCHAR(256)     NOT NULL,
    display_name          VARCHAR(64)      NOT NULL,
    status                ENUM('active','disabled','locked') NOT NULL DEFAULT 'active',
    failed_login_attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until          DATETIME(3)      NULL,
    last_login_at         DATETIME(3)      NULL,
    last_login_ip          VARCHAR(45)      NULL,
    created_by            BIGINT UNSIGNED  NULL,
    created_at            DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at            DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at            DATETIME(3)      NULL,

    PRIMARY KEY (id),
    UNIQUE INDEX idx_aa_username (username),
    INDEX idx_aa_status (status),
    CONSTRAINT fk_aa_created_by FOREIGN KEY (created_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `password_hash` uses bcrypt via passlib (Python); 256 chars to accommodate future algorithm
  upgrades.
- `locked_until`: set to `NOW() + 15 minutes` after the 5th consecutive failure. Login checks
  clear it if the lock period has elapsed.
- `failed_login_attempts` resets to 0 on successful login.
- `deleted_at` soft-delete (super-admin action); system audit logs prevent hard deletion.
- `created_by` self-ref: the super-admin who created this account.

### 2.4 roles (角色)

RBAC role definitions (FR-005c). A role contains a set of permission strings.

```sql
CREATE TABLE roles (
    id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    name            VARCHAR(64)      NOT NULL,
    display_name    VARCHAR(64)      NOT NULL,
    permissions     JSON             NOT NULL,
    description     VARCHAR(256)     NULL,
    is_system       TINYINT(1)       NOT NULL DEFAULT 0,
    created_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_roles_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `permissions` is a JSON array of strings, e.g.:
  `["qualification:review", "customer:unbind", "customer:transfer", "reports:view"]`.
- `is_system = 1` prevents deletion of built-in roles (admin, finance, ops).
- Using JSON instead of a normalized `role_permissions` junction table because:
  - Permissions are always loaded as a unit with the role.
  - No need to query "which roles have permission X" independently.
  - The set is small (tens, not thousands).

### 2.5 admin_account_roles (后台账号-角色关联)

M:N junction between `admin_accounts` and `roles`.

```sql
CREATE TABLE admin_account_roles (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    admin_account_id    BIGINT UNSIGNED  NOT NULL,
    role_id             BIGINT UNSIGNED  NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_aar_pair (admin_account_id, role_id),
    CONSTRAINT fk_aar_account FOREIGN KEY (admin_account_id) REFERENCES admin_accounts(id),
    CONSTRAINT fk_aar_role FOREIGN KEY (role_id) REFERENCES roles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.6 hierarchy_nodes (层级节点)

The 6-level tree structure (L1 company root -> L2-L5 promoters -> L6 end customers). This is
the authoritative hierarchy; `promoters` and `customers` reference their nodes here.

```sql
CREATE TABLE hierarchy_nodes (
    id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    parent_id       BIGINT UNSIGNED  NULL,
    level           TINYINT UNSIGNED NOT NULL,
    node_type       ENUM('root','promoter','customer') NOT NULL,
    name            VARCHAR(128)     NOT NULL,
    sort_order      INT              NOT NULL DEFAULT 0,
    created_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_hn_parent (parent_id),
    INDEX idx_hn_level (level),
    INDEX idx_hn_node_type (node_type),
    CONSTRAINT fk_hn_parent FOREIGN KEY (parent_id) REFERENCES hierarchy_nodes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `parent_id` IS NULL only for the single L1 root node (北京总部).
- `level` is derived from tree depth but stored as a column for efficient querying
  ("all L3 nodes", "all nodes at a level"). Updated when a subtree is moved.
- `node_type`: L1=`root`, L2-L5=`promoter`, L6=`customer`.
- Adjacency list model (parent_id) chosen over nested sets or materialized path because:
  - Tree depth is bounded at 6 (small).
  - Moves are subtree operations that are straightforward with FK updates.
  - Common query is "all children of node X" (direct children only).
  - Full-tree reads are cached at the application layer.
- Circular reference detection (FR-020) is enforced at the application/service layer
  via a recursive lookup before accepting parent changes.

### 2.7 hierarchy_snapshots (层级快照)

Audit trail for hierarchy changes (FR-021: "保留历史层级快照").

```sql
CREATE TABLE hierarchy_snapshots (
    id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    node_id         BIGINT UNSIGNED  NOT NULL,
    old_parent_id   BIGINT UNSIGNED  NULL,
    new_parent_id   BIGINT UNSIGNED  NULL,
    old_level       TINYINT UNSIGNED NOT NULL,
    new_level       TINYINT UNSIGNED NOT NULL,
    action          ENUM('created','moved','deleted') NOT NULL,
    operator_id     BIGINT UNSIGNED  NULL,
    created_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_hs_node (node_id),
    INDEX idx_hs_created (created_at),
    CONSTRAINT fk_hs_operator FOREIGN KEY (operator_id) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.8 promoters (拓展人)

Extension table for users of type `promoter`. Links a WeChat user to their hierarchy node,
tracks qualification status (denormalized for fast checks), and points to their active
promotion code.

```sql
CREATE TABLE promoters (
    id                      BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id                 BIGINT UNSIGNED  NOT NULL,
    node_id                 BIGINT UNSIGNED  NOT NULL,
    current_promotion_code_id BIGINT UNSIGNED NULL,
    qualification_status    ENUM('none','reviewing','approved','rejected','expiring','expired') NOT NULL DEFAULT 'none',
    created_at              DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at              DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_pr_user (user_id),
    UNIQUE INDEX idx_pr_node (node_id),
    INDEX idx_pr_qual_status (qualification_status),
    CONSTRAINT fk_pr_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_pr_node FOREIGN KEY (node_id) REFERENCES hierarchy_nodes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `qualification_status` is denormalized from the `qualifications` table for fast access in
  auth middleware (block promotion code generation / contribution calc without a join).
  Updated transactionally when qualification state changes.
- `current_promotion_code_id` is nullable -- only set after qualification is approved
  and the promoter has generated a code.
- `node_id` is UNIQUE: one promoter per hierarchy node. Created when the admin places a
  promoter into the tree.

### 2.9 qualifications (资质)

Promoter qualification submissions. A promoter submits company qualification documents
(营业执照, 法人证书, 医疗机构许可证). Admin reviews and approves/rejects.

```sql
CREATE TABLE qualifications (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    promoter_id         BIGINT UNSIGNED  NOT NULL,
    legal_entity_name   VARCHAR(256)     NOT NULL,
    qualification_types JSON             NOT NULL,
    credit_code         VARCHAR(64)      NOT NULL,
    file_urls           JSON             NOT NULL,
    valid_from          DATE             NULL,
    valid_until         DATE             NOT NULL,
    status              ENUM('reviewing','approved','rejected') NOT NULL DEFAULT 'reviewing',
    review_comment      TEXT             NULL,
    reviewed_by         BIGINT UNSIGNED  NULL,
    reviewed_at         DATETIME(3)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_qual_promoter (promoter_id),
    INDEX idx_qual_status (status),
    INDEX idx_qual_valid_until (valid_until),
    CONSTRAINT fk_qual_promoter FOREIGN KEY (promoter_id) REFERENCES promoters(id),
    CONSTRAINT fk_qual_reviewer FOREIGN KEY (reviewed_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `qualification_types` is a JSON array, e.g. `["business_license", "medical_institution_permit"]`.
  A single submission can cover multiple types.
- `file_urls` is a JSON array of objects: `[{"url": "...", "type": "pdf", "size": 12345}]`.
  Files are uploaded via cloud storage (short-term upload credential), and only URLs are stored.
- A promoter may have multiple `qualifications` rows (re-submission after rejection, or
  renewal after expiry). Only the most recent (by `created_at`) is authoritative.
- `valid_until` is the expiry date of the qualification certificate. System cron checks
  approaching expiry (FR-008: 30-day warning).
- `review_comment` is TEXT rather than VARCHAR to accommodate detailed rejection reasons
  (can be multi-paragraph in practice).

### 2.10 promotion_codes (推广码)

A promoter's unique promotion QR code. Each code contains a `refToken` that identifies
the promoter when a customer scans the QR code.

```sql
CREATE TABLE promotion_codes (
    id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    promoter_id     BIGINT UNSIGNED  NOT NULL,
    ref_token       VARCHAR(64)      NOT NULL,
    qr_image_url    VARCHAR(512)     NULL,
    status          ENUM('active','disabled','expired') NOT NULL DEFAULT 'active',
    expires_at      DATETIME(3)      NULL,
    scan_count      INT UNSIGNED     NOT NULL DEFAULT 0,
    lead_count      INT UNSIGNED     NOT NULL DEFAULT 0,
    bind_count      INT UNSIGNED     NOT NULL DEFAULT 0,
    created_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    disabled_at     DATETIME(3)      NULL,

    PRIMARY KEY (id),
    UNIQUE INDEX idx_pc_ref_token (ref_token),
    INDEX idx_pc_promoter (promoter_id),
    INDEX idx_pc_status (status),
    CONSTRAINT fk_pc_promoter FOREIGN KEY (promoter_id) REFERENCES promoters(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `ref_token` is a unique short token (e.g. base64-encoded random bytes) embedded in the
  QR code URL with `?src=BJTR&refToken=xxx`.
- When a promoter refreshes their code (FR-025), the old record gets `status='disabled'`
  and a new record is inserted. `promoters.current_promotion_code_id` is updated atomically.
- `scan_count`, `lead_count`, `bind_count` are denormalized counters for the analytics
  dashboard (FR-026). Updated incrementally from `binding_requests` and QR scan events.
- `qr_image_url` stores the URL to the generated QR image in cloud storage.
- `expires_at` is optional -- null means never expires. Set on creation for codes with
  a fixed validity period.

### 2.11 customers (客户)

End users bound to a promoter. Represents patients/consumers in the Rutai system.

```sql
CREATE TABLE customers (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    promoter_id         BIGINT UNSIGNED  NULL,
    node_id             BIGINT UNSIGNED  NULL,
    name                VARCHAR(64)      NOT NULL,
    phone               VARCHAR(20)      NULL,
    id_card             VARCHAR(32)      NULL,
    medical_account     VARCHAR(64)      NULL,
    family_phone        VARCHAR(20)      NULL,
    hrb_user_id         VARCHAR(64)      NULL,
    binding_status      ENUM('pending_match','matched','bound','unbound','transferred') NOT NULL DEFAULT 'pending_match',
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_cust_promoter (promoter_id),
    INDEX idx_cust_hrb_user_id (hrb_user_id),
    INDEX idx_cust_phone (phone),
    INDEX idx_cust_binding_status (binding_status),
    INDEX idx_cust_node (node_id),
    CONSTRAINT fk_cust_promoter FOREIGN KEY (promoter_id) REFERENCES promoters(id),
    CONSTRAINT fk_cust_node FOREIGN KEY (node_id) REFERENCES hierarchy_nodes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `promoter_id` is the current bound promoter (NULL until matched/bound).
- `node_id` is the L6 hierarchy node for this customer. Created when the customer is first
  recorded.
- `hrb_user_id` is the user ID in the Harbin Rutai system. Populated after successful
  matching via `bindBjUser`. NULL for pending-match records.
- `id_card` and `phone` stored plaintext at DB level; masked at API layer (FR-061).
- The constraint "one customer cannot be simultaneously bound to multiple promoters"
  (FR-014) is enforced at the application layer because MySQL does not support partial
  unique indexes (UNIQUE on `phone` WHERE `binding_status='bound'`).
- `binding_status` is maintained in sync with the latest `binding_requests` status for
  this customer. Denormalized for list queries.

### 2.12 binding_requests (绑定申请)

A doctor-submitted record to bind a customer to a promoter. Tracks the full lifecycle
from submission through matching to binding/unbinding/transfer.

```sql
CREATE TABLE binding_requests (
    id                      BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    customer_id             BIGINT UNSIGNED  NULL,
    promoter_id             BIGINT UNSIGNED  NOT NULL,
    submitted_by            BIGINT UNSIGNED  NOT NULL,
    source_type             ENUM('manual','scan','rutai_marked') NOT NULL,
    status                  ENUM('pending_match','matching','bound','unbound','transferred','error') NOT NULL DEFAULT 'pending_match',
    hrb_user_id             VARCHAR(64)      NULL,
    idempotency_key         VARCHAR(64)      NULL,
    customer_name           VARCHAR(64)      NOT NULL,
    customer_phone          VARCHAR(20)      NULL,
    customer_id_card        VARCHAR(32)      NULL,
    customer_medical_account VARCHAR(64)     NULL,
    customer_family_phone   VARCHAR(20)      NULL,
    bind_time               DATETIME(3)      NULL,
    unbind_reason           VARCHAR(512)     NULL,
    unbind_by               BIGINT UNSIGNED  NULL,
    transfer_from_promoter_id BIGINT UNSIGNED NULL,
    transfer_to_promoter_id   BIGINT UNSIGNED NULL,
    retry_count             TINYINT UNSIGNED NOT NULL DEFAULT 0,
    max_retries             TINYINT UNSIGNED NOT NULL DEFAULT 3,
    last_retry_at           DATETIME(3)      NULL,
    created_at              DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at              DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_br_customer (customer_id),
    INDEX idx_br_promoter (promoter_id),
    INDEX idx_br_submitted_by (submitted_by),
    INDEX idx_br_status (status),
    INDEX idx_br_hrb_user (hrb_user_id),
    UNIQUE INDEX idx_br_idempotency (idempotency_key),
    INDEX idx_br_created (created_at),
    CONSTRAINT fk_br_customer FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT fk_br_promoter FOREIGN KEY (promoter_id) REFERENCES promoters(id),
    CONSTRAINT fk_br_submitted_by FOREIGN KEY (submitted_by) REFERENCES users(id),
    CONSTRAINT fk_br_unbind_by FOREIGN KEY (unbind_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `customer_id` is NULL initially; created after matching or on first submission.
- Customer info fields (`customer_name`, etc.) are a snapshot at submission time, even if the
  customer record is later updated.
- `idempotency_key`: unique per submission to prevent duplicate bindings (FR-066). Set by
  the client; if the same key arrives again, return the existing result.
- `retry_count` and `max_retries` track the `bindBjUser` retry policy (FR-017: retry every
  10 min, max 3 times). When `retry_count >= max_retries` and status is still not `bound`,
  status becomes `error`.
- `unbind_reason` and `unbind_by` record admin-initiated unbinding (FR-015).
- Transfer fields (`transfer_from/to_promoter_id`) capture the from/to promoters when
  status is `transferred`.

### 2.13 binding_change_logs (绑定变更日志)

Full audit trail for binding lifecycle changes (FR-016). One record per status transition.

```sql
CREATE TABLE binding_change_logs (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    binding_request_id  BIGINT UNSIGNED  NOT NULL,
    from_status         VARCHAR(32)      NULL,
    to_status           VARCHAR(32)      NOT NULL,
    operator_id         BIGINT UNSIGNED  NULL,
    operator_type       ENUM('doctor','admin','system') NOT NULL,
    reason              VARCHAR(512)     NULL,
    snapshot_data       JSON             NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_bcl_binding (binding_request_id),
    INDEX idx_bcl_created (created_at),
    CONSTRAINT fk_bcl_binding FOREIGN KEY (binding_request_id) REFERENCES binding_requests(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `snapshot_data` is a JSON copy of the `binding_requests` row at the time of the transition.
  Preserves historical state even if the main row is updated.
- `operator_id` is a polymorphic reference depending on `operator_type` (doctor -> `users.id`,
  admin -> `admin_accounts.id`, system -> NULL). No FK constraint due to polymorphism.
- Note: `from_status`/`to_status` use VARCHAR instead of ENUM to avoid ALTER TABLE when new
  statuses are added. The application layer validates against the current set.

### 2.14 bills (账单)

Customer billing records synced from Harbin Rutai via `getUserBill`/`getAllUsersBill`.
Transaction-IDs serve as idempotency keys (FR-031).

```sql
CREATE TABLE bills (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    transaction_id      VARCHAR(64)      NOT NULL,
    customer_id         BIGINT UNSIGNED  NULL,
    hrb_user_id         VARCHAR(64)      NULL,
    transaction_time    DATETIME(3)      NOT NULL,
    consultation_fee    BIGINT           NOT NULL DEFAULT 0,
    medicine_fee        BIGINT           NOT NULL DEFAULT 0,
    total_amount        BIGINT           NOT NULL DEFAULT 0,
    discount_amount     BIGINT           NOT NULL DEFAULT 0,
    paid_amount         BIGINT           NOT NULL DEFAULT 0,
    refund_amount       BIGINT           NOT NULL DEFAULT 0,
    status              ENUM('normal','partial_refund','full_refund') NOT NULL DEFAULT 'normal',
    raw_data            JSON             NULL,
    synced_at           DATETIME(3)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_bills_txn (transaction_id),
    INDEX idx_bills_customer (customer_id),
    INDEX idx_bills_hrb_user (hrb_user_id),
    INDEX idx_bills_txn_time (transaction_time),
    INDEX idx_bills_status (status),
    INDEX idx_bills_synced (synced_at),
    CONSTRAINT fk_bills_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- All monetary amounts in **cents** (BIGINT) per FR-068. Example: 100.50 CNY = 10050.
- `transaction_id` from Rutai is the unique idempotency key -- INSERT IGNORE or ON DUPLICATE KEY
  used during sync to prevent duplicates.
- `raw_data` stores the complete Rutai API response as JSON for debugging/audit.
- `customer_id` may be NULL if the Rutai record does not match a local customer yet.
- `refund_amount` is non-zero when the Rutai system processes a refund/partial refund. When
  a refund occurs, `status` transitions and the associated `contribution_records` are reversed
  (FR-041).

### 2.15 contribution_records (贡献值记录)

Contribution points calculated from bills. One record per contribution event, aggregated
up the hierarchy tree.

```sql
CREATE TABLE contribution_records (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    promoter_id         BIGINT UNSIGNED  NOT NULL,
    bill_id             BIGINT UNSIGNED  NULL,
    source_type         ENUM('binding','service','followup','bill','adjustment') NOT NULL,
    source_id           BIGINT UNSIGNED  NULL,
    points              DECIMAL(18,2)    NOT NULL,
    status              ENUM('pending','settled','reversed','cancelled') NOT NULL DEFAULT 'pending',
    sharing_rule_id     BIGINT UNSIGNED  NULL,
    conversion_rate     DECIMAL(10,4)    NOT NULL,
    is_team_aggregate   TINYINT(1)       NOT NULL DEFAULT 0,
    settled_at          DATETIME(3)      NULL,
    settlement_log_id   BIGINT UNSIGNED  NULL,
    adjustment_reason   VARCHAR(512)     NULL,
    adjusted_by         BIGINT UNSIGNED  NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_cr_promoter (promoter_id),
    INDEX idx_cr_bill (bill_id),
    INDEX idx_cr_status (status),
    INDEX idx_cr_source_type (source_type),
    INDEX idx_cr_created (created_at),
    INDEX idx_cr_settlement_log (settlement_log_id),
    INDEX idx_cr_promoter_status (promoter_id, status),
    CONSTRAINT fk_cr_promoter FOREIGN KEY (promoter_id) REFERENCES promoters(id),
    CONSTRAINT fk_cr_bill FOREIGN KEY (bill_id) REFERENCES bills(id),
    CONSTRAINT fk_cr_sharing_rule FOREIGN KEY (sharing_rule_id) REFERENCES sharing_rules(id),
    CONSTRAINT fk_cr_settlement_log FOREIGN KEY (settlement_log_id) REFERENCES settlement_logs(id),
    CONSTRAINT fk_cr_adjusted_by FOREIGN KEY (adjusted_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `points` uses `DECIMAL(18,2)` for precision. Max value: 99,999,999,999,999,999.99.
  API layer returns as string per FR-068 (JSON number precision issue).
- `source_type` values per FR-046: `binding` (绑定), `service` (服务), `followup` (跟进),
  `bill` (账单), `adjustment` (调整).
- `is_team_aggregate`: 0 = promoter's own contribution from a specific event; 1 = aggregated
  from subordinate team members (FR-038). Aggregate records are recalculated when subordinates
  change.
- `conversion_rate` stores the specific rate used when this record was calculated (e.g. 1.0000
  for "1 CNY = 1 point"). Critical for audit: rules may change, but historical records keep
  their original rate.
- `sharing_rule_id` references the rule version used for calculation.
- `settlement_log_id` populated during the monthly batch settlement (FR-039).
- Composite index on `(promoter_id, status)` for the fast "pending points for promoter X"
  lookups during settlement.

### 2.16 sharing_rules (分账规则)

Admin-configured distribution rules, one active per level per time period. Rules define how
contribution points are calculated for each hierarchy level.

```sql
CREATE TABLE sharing_rules (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    applicable_level    TINYINT UNSIGNED NOT NULL,
    rule_type           ENUM('fixed_ratio','fixed_amount','tiered') NOT NULL,
    base                ENUM('paid_amount','total_amount') NOT NULL,
    rule_value          DECIMAL(10,4)    NOT NULL,
    tier_config         JSON             NULL,
    effective_from      DATETIME(3)      NOT NULL,
    effective_until     DATETIME(3)      NULL,
    status              ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_by          BIGINT UNSIGNED  NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_sr_level (applicable_level),
    INDEX idx_sr_status (status),
    INDEX idx_sr_effective (effective_from),
    INDEX idx_sr_level_active (applicable_level, status),
    CONSTRAINT fk_sr_created_by FOREIGN KEY (created_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `tier_config` is populated only when `rule_type='tiered'`. Example JSON:
  `[{"min": 0, "max": 10000, "value": 0.10}, {"min": 10001, "max": 50000, "value": 0.15}, ...]`.
  For `fixed_ratio` and `fixed_amount`, the single value goes in `rule_value`.
- `effective_until` is NULL for the currently active rule; set to the `effective_from` of the
  replacement rule when a new rule supersedes it.
- FR-049 (one active rule per level at a time) is enforced at the application layer. Before
  activating a new rule, the service queries for active rules at the same level.
- `base`: `paid_amount` = 实付金额, `total_amount` = 合计金额 (before discount).
- Composite index `(applicable_level, status)` optimizes the common lookup: "get the active
  rule for level X".

### 2.17 sharing_rule_change_logs (分账规则变更日志)

Audit trail for all sharing rule changes (FR-050).

```sql
CREATE TABLE sharing_rule_change_logs (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    sharing_rule_id     BIGINT UNSIGNED  NOT NULL,
    changed_by          BIGINT UNSIGNED  NOT NULL,
    change_type         ENUM('created','updated','deactivated','reactivated') NOT NULL,
    before_data         JSON             NULL,
    after_data          JSON             NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_srcl_rule (sharing_rule_id),
    INDEX idx_srcl_created (created_at),
    CONSTRAINT fk_srcl_rule FOREIGN KEY (sharing_rule_id) REFERENCES sharing_rules(id),
    CONSTRAINT fk_srcl_changed_by FOREIGN KEY (changed_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.18 settlement_logs (结算日志)

Records of monthly automatic settlement runs (FR-039). One record per month.

```sql
CREATE TABLE settlement_logs (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    period              VARCHAR(7)       NOT NULL,
    status              ENUM('pending','processing','completed','failed') NOT NULL DEFAULT 'pending',
    total_records       INT UNSIGNED     NOT NULL DEFAULT 0,
    total_points        DECIMAL(18,2)    NULL,
    started_at          DATETIME(3)      NULL,
    completed_at        DATETIME(3)      NULL,
    error_message       TEXT             NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_sl_period (period),
    INDEX idx_sl_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `period` format: 'YYYY-MM' (e.g., '2026-07'). UNIQUE: one settlement run per month.
- Settlement is triggered at 00:00 on the 1st of each month by APScheduler.
- Flow: `pending` -> `processing` (update all pending contribution_records for the period to
  `settled`) -> `completed`. On error -> `failed` with `error_message`.
- Idempotent: if the cron fires and a `processing` or `completed` record exists for this
  period, skip.

### 2.19 reconciliation_reports (对账报表)

Admin-generated reconciliation reports. Stored as JSON data with optional Excel export.

```sql
CREATE TABLE reconciliation_reports (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    report_type         ENUM('customer_summary','payment_summary','discount_summary','allocation_detail') NOT NULL,
    time_range_start    DATE             NOT NULL,
    time_range_end      DATE             NOT NULL,
    dimensions          JSON             NOT NULL,
    report_data         JSON             NOT NULL,
    excel_file_url      VARCHAR(512)     NULL,
    generated_by        BIGINT UNSIGNED  NOT NULL,
    generated_at        DATETIME(3)      NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_rr_type (report_type),
    INDEX idx_rr_time_range (time_range_start, time_range_end),
    INDEX idx_rr_generated_by (generated_by),
    CONSTRAINT fk_rr_generated_by FOREIGN KEY (generated_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `dimensions` is a JSON array of dimension names selected by the user, e.g.
  `["promoter_level", "time_month"]`.
- `report_data` is the full aggregated result set as JSON (denormalized for fast retrieval).
  Excel export converts this to .xlsx format.
- Reports are "generate and cache" rather than live queries. Generating a report stores the
  result; subsequent requests for the same params can reuse.
- Excel file is generated server-side (openpyxl or xlsxwriter) and uploaded to cloud storage;
  `excel_file_url` is the download link.

### 2.20 articles (文章)

CMS-managed health/科普 articles (FR-055 through FR-058).

```sql
CREATE TABLE articles (
    id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    title           VARCHAR(256)     NOT NULL,
    body            LONGTEXT         NOT NULL,
    cover_image_url VARCHAR(512)     NULL,
    summary         VARCHAR(512)     NULL,
    category        VARCHAR(64)      NOT NULL,
    status          ENUM('draft','published','unpublished') NOT NULL DEFAULT 'draft',
    published_at    DATETIME(3)      NULL,
    created_by      BIGINT UNSIGNED  NOT NULL,
    updated_by      BIGINT UNSIGNED  NULL,
    created_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at      DATETIME(3)      NULL,

    PRIMARY KEY (id),
    INDEX idx_art_category (category),
    INDEX idx_art_status (status),
    INDEX idx_art_published (published_at),
    FULLTEXT INDEX idx_art_search (title, body),
    CONSTRAINT fk_art_created_by FOREIGN KEY (created_by) REFERENCES admin_accounts(id),
    CONSTRAINT fk_art_updated_by FOREIGN KEY (updated_by) REFERENCES admin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `body` is `LONGTEXT` (max 4GB) because rich-text HTML articles with embedded base64 images
  can exceed the 64KB `TEXT` limit. `MEDIUMTEXT` (16MB) would also work; `LONGTEXT` is chosen
  for safety.
- `FULLTEXT INDEX` on `(title, body)` supports the search feature (FR-057). MySQL's built-in
  full-text with ngram parser for Chinese. For production at scale, consider Elasticsearch.
- `status='unpublished'` means previously published but now taken down (FR-058: "已下架文章
  不得在小程序前端展示").
- `deleted_at` soft-delete. Unpublishing is distinct from deletion.

### 2.21 followup_records (跟进记录)

Doctor follow-up records for customers (FR specification entity #13).

```sql
CREATE TABLE followup_records (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    doctor_id           BIGINT UNSIGNED  NOT NULL,
    customer_id         BIGINT UNSIGNED  NOT NULL,
    method              VARCHAR(32)      NOT NULL,
    result              VARCHAR(32)      NULL,
    content             TEXT             NOT NULL,
    next_reminder_at    DATETIME(3)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_fr_doctor (doctor_id),
    INDEX idx_fr_customer (customer_id),
    INDEX idx_fr_next_reminder (next_reminder_at),
    INDEX idx_fr_created (created_at),
    CONSTRAINT fk_fr_doctor FOREIGN KEY (doctor_id) REFERENCES users(id),
    CONSTRAINT fk_fr_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `method`: free-text values like `phone`, `visit`, `wechat`, `sms` (VARCHAR used instead of
  ENUM because new follow-up methods may be introduced without schema changes).
- `result`: free-text values like `success`, `no_answer`, `refused`, `follow_up_needed`.
- `next_reminder_at` is indexed for the scheduled task that sends reminder notifications.
- `content` is `TEXT` (64KB) for longer follow-up notes.

### 2.22 consent_records (授权记录)

Privacy consent records (FR-059, FR-060). Required before customer binding or data sharing.

```sql
CREATE TABLE consent_records (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id             BIGINT UNSIGNED  NULL,
    customer_id         BIGINT UNSIGNED  NULL,
    scene               VARCHAR(64)      NOT NULL,
    agreed_version      VARCHAR(32)      NOT NULL,
    scope               VARCHAR(256)     NULL,
    consented_at        DATETIME(3)      NOT NULL,
    ip_address          VARCHAR(45)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_cr_user (user_id),
    INDEX idx_cr_customer (customer_id),
    INDEX idx_cr_scene (scene),
    INDEX idx_cr_consented_at (consented_at),
    CONSTRAINT fk_cr_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_cr_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- Polymorphic: `user_id` for mini-program user consent, `customer_id` for end-customer consent
  (via doctor-submitted binding flow). At least one must be non-NULL (CHECK constraint or app
  validation).
- `scene`: e.g. `binding`, `privacy_policy`, `data_sharing`.
- `scope`: description of what data is shared, e.g. "与哈尔滨儒泰互联网医院共享姓名、手机号".
- `agreed_version` tracks which version of the privacy policy was agreed to. Version string
  format managed by operations.

### 2.23 notifications (消息通知)

System notification center (FR-008a). Supports both promoter-facing and admin-facing
notifications with read/unread tracking.

```sql
CREATE TABLE notifications (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    category            ENUM('qualification','binding','sync','system','settlement') NOT NULL,
    title               VARCHAR(256)     NOT NULL,
    summary             TEXT             NULL,
    target_type         VARCHAR(32)      NULL,
    target_id           BIGINT UNSIGNED  NULL,
    recipient_type      ENUM('promoter','admin','all_admins','specific_admin') NOT NULL,
    recipient_id        BIGINT UNSIGNED  NULL,
    is_read             TINYINT(1)       NOT NULL DEFAULT 0,
    read_at             DATETIME(3)      NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    INDEX idx_notif_recipient (recipient_type, recipient_id),
    INDEX idx_notif_read (is_read),
    INDEX idx_notif_category (category),
    INDEX idx_notif_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `recipient_type` + `recipient_id`: discriminates between promoter notifications
  (`recipient_id` -> `promoters.id`), admin notifications (-> `admin_accounts.id`),
  broadcast-to-all-admins (`all_admins`, `recipient_id` is NULL), or specific admin.
  No FK due to polymorphic target.
- `target_type` + `target_id`: where clicking the notification leads (e.g.
  `qualification:123`, `binding:456`). Resolved by the frontend.
- `category` maps to notification types:
  - `qualification`: review results, expiry warnings (FR-008)
  - `binding`: binding exceptions (FR-033)
  - `sync`: data sync failures (FR-033, FR-034)
  - `system`: account lockouts, configuration changes
  - `settlement`: monthly settlement results
- Soft-delete is not needed; notifications are compact and can be bulk-cleared periodically
  if needed (though the system values permanent retention, notification cleanup is a UX
  concern, not audit).

### 2.24 api_call_logs (接口调用日志)

External API call audit log (FR-035). Records every call to Harbin Rutai and WeChat APIs.
**Partitioned by year.**

```sql
CREATE TABLE api_call_logs (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    interface_name      VARCHAR(128)     NOT NULL,
    request_url         VARCHAR(512)     NULL,
    request_method      VARCHAR(10)      NULL,
    request_params      JSON             NULL,
    request_headers     JSON             NULL,
    response_status     SMALLINT         NULL,
    response_body       JSON             NULL,
    response_time_ms    INT UNSIGNED     NULL,
    is_success          TINYINT(1)       NOT NULL DEFAULT 0,
    error_message       TEXT             NULL,
    retry_count         TINYINT UNSIGNED NOT NULL DEFAULT 0,
    called_at           DATETIME(3)      NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id, called_at),
    INDEX idx_acl_interface (interface_name),
    INDEX idx_acl_called (called_at),
    INDEX idx_acl_success (is_success),
    INDEX idx_acl_duration (response_time_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
PARTITION BY RANGE (YEAR(called_at)) (
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p2028 VALUES LESS THAN (2029),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

**Design Notes:**
- Primary key includes `called_at` to satisfy MySQL's requirement that the partition key be
  part of all unique indexes (including PK).
- Partitioned by `YEAR(called_at)` to manage table growth (FR-063a: permanent retention).
  New partitions are added annually via a scheduled DDL or manually.
- `request_params` and `response_body` are JSON for flexible schema (different APIs return
  different shapes).
- `is_success` is derived: 1 for HTTP 2xx with no application-level error, 0 otherwise.
  Enables fast queries for "failure rate over time window".
- `response_time_ms` is indexed for performance monitoring queries.

### 2.25 idempotency_keys (幂等键)

Tracks idempotency keys for write operations (FR-066) to prevent duplicate processing.

```sql
CREATE TABLE idempotency_keys (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    idempotency_key     VARCHAR(64)      NOT NULL,
    response_data       JSON             NOT NULL,
    expires_at          DATETIME(3)      NOT NULL,
    created_at          DATETIME(3)      NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),
    UNIQUE INDEX idx_ik_key (idempotency_key),
    INDEX idx_ik_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Design Notes:**
- `response_data` stores the original API response. If a duplicate request arrives with the
  same key, the stored response is returned without re-processing.
- `expires_at`: keys expire after a configurable window (default 24 hours). A scheduled task
  purges expired keys.
- Separate table (not cached in Redis) because idempotency must survive server restarts and
  Redis is not in the current architecture.

---

## 3. State Machines

### 3.1 Binding Status (`binding_requests.status`)

```
                    +----------+
                    |  Manual  |
                    |   Scan   |------+
                    |HRB Marked|      |
                    +----------+      |
                          |           |
                          v           v
                    +--------------+  (auto from Rutai sync)
                    | pending_match|----------------------------+
                    +------+-------+                            |
                           |                                    |
                           | (bindBjUser API call)              |
                           v                                    |
                    +----------+                                |
                    | matching |---(fail > 3 retries)--+        |
                    +----+-----+                        |        |
                         |                              |        |
                         | (match success)              |        |
                         v                              v        |
                    +---------+                    +-------+     |
                    |  bound  |                    | error |     |
                    +----+----+                    +-------+     |
                         |                                      |
              +----------+----------+                           |
              |                     |                           |
              v                     v                           |
        +----------+         +-------------+                   |
        | unbound  |         | transferred |                   |
        |(admin)   |         | (admin)     |                   |
        +----------+         +-------------+                   |
              |                     |                           |
              | (re-bind)           | (can re-bind              |
              v                     |  or unbind)               |
        +----------+               v                           |
        |  bound   |         +----------+                      |
        | (new)    |         | unbound  |                      |
        +----------+         +----------+                      |
                                                                |
        +-------------------------------------------------------+
        | (Rutai auto-matches previously unmatched customer)
        v
  (goes directly to 'bound' via updateBindUser callback)
```

**Transition Rules:**
1. `pending_match` -> `matching`: When the system calls `bindBjUser`.
2. `pending_match` -> `bound`: Direct match from Rutai-side marking (auto-sync).
3. `matching` -> `bound`: Rutai returns `hrb_user_id` successfully.
4. `matching` -> `error`: After `retry_count >= max_retries` without success (FR-017).
5. `bound` -> `unbound`: Admin unbinds with reason (FR-015). Historical contributions preserved.
6. `bound` -> `transferred`: Admin transfers customer to a different promoter (FR-015).
7. `transferred` -> `bound`: Re-binding after transfer (to new promoter).
8. `transferred` -> `unbound`: Admin unbinds a transferred customer.
9. `error` -> `matching`: Admin manually retries the binding.

### 3.2 Qualification Status (`promoters.qualification_status`)

```
                    +------+
                    | none |  (new promoter, not yet submitted)
                    +--+---+
                       |
                       | (promoter submits qualification)
                       v
                  +-----------+
                  | reviewing |<-------------------+
                  +-----+-----+                    |
                        |                          |
              +---------+---------+                |
              |                   |                |
              v                   v                |
        +----------+        +----------+           |
        | approved |        | rejected |----(re-submit)---+
        +----+-----+        +----------+           |
             |                                     |
             | (system detects 30 days to expiry)  |
             v                                     |
        +-----------+                              |
        | expiring  |                              |
        +-----+-----+                              |
              |                                    |
              | (system detects expiry date past)  |
              v                                    |
        +---------+                                |
        | expired |---(re-submit qualification)----+
        +---------+
              |
              | (system auto-action: disable promotion code,
              |  pause contribution calculation per FR-009)
              v
        (promotion code disabled, contributions paused)
```

**Transition Rules:**
1. `none` -> `reviewing`: Promoter submits qualification documents.
2. `reviewing` -> `approved`: Admin approves (FR-007).
3. `reviewing` -> `rejected`: Admin rejects with reason (FR-007).
4. `rejected` -> `reviewing`: Promoter re-submits after addressing issues.
5. `approved` -> `expiring`: System cron detects `valid_until - 30 days` (FR-008).
6. `expiring` -> `expired`: System cron detects `valid_until < NOW()` (FR-009).
7. `expired` -> `reviewing`: Promoter submits new qualification.
8. On `approved` -> `expired`: System automatically disables the active promotion code
   and pauses contribution calculation for this promoter.

### 3.3 Contribution Status (`contribution_records.status`)

```
                    +---------+
                    | pending |  (newly calculated contribution)
                    +----+----+
                         |
            +------------+------------+
            |            |            |
            v            v            v
      +----------+ +----------+ +----------+
      | settled  | | reversed | |cancelled |
      | (monthly | | (refund) | | (admin   |
      |  batch)  | |          | |  adjust) |
      +----------+ +----------+ +----------+
           |
           | (IMMUTABLE after settlement per FR-039)
           v
      (no further transitions allowed)
```

**Transition Rules:**
1. `pending` -> `settled`: Monthly batch on the 1st at 00:00 (FR-039). Irreversible.
2. `pending` -> `reversed`: Rutai returns a `partial_refund` or `full_refund` on the
   associated bill (FR-041). Points are reversed (negative record created).
3. `pending` -> `cancelled`: Admin manually adjusts a contribution before settlement
   (FR-039: "支持管理员对单个待结算贡献值进行人工调整"). Cancelled records are excluded
   from settlement.
4. Once `settled`, no transitions are permitted. Attempts to modify are rejected at the
   service layer (FR-039: "已结算后禁止修改").

### 3.4 Admin Account Status (`admin_accounts.status`)

```
                    +--------+
                    | active |
                    +---+----+
                        |
           +------------+------------+
           |            |            |
           v            v            v
     +----------+ +----------+  (manual unlock
     | disabled | |  locked  |   or 15-min expiry)
     | (admin   | |  (5      |----------> back to 'active'
     |  action) | |  failed  |
     +----------+ |  logins) |
           |      +----------+
           |
           v
     (admin re-enables)
     back to 'active'
```

**Transition Rules:**
1. `active` -> `locked`: 5 consecutive failed login attempts (FR-005b). `locked_until`
   set to `NOW() + 15 minutes`. Login API re-checks: if `NOW() > locked_until`, reverts
   to `active` and resets `failed_login_attempts` to 0 before processing.
2. `active` -> `disabled`: Admin manually disables the account.
3. `disabled` -> `active`: Admin manually re-enables.
4. Successful login resets `failed_login_attempts` to 0.

### 3.5 Settlement Log Status (`settlement_logs.status`)

```
                    +---------+
                    | pending |
                    +----+----+
                         |
                         | (cron triggers at 00:00 on 1st)
                         v
                   +------------+
                   | processing |
                   +-----+------+
                         |
               +---------+---------+
               |                   |
               v                   v
         +-----------+       +--------+
         | completed |       | failed |
         +-----------+       +--------+
                                 |
                                 | (manual retry or next month's run)
                                 v
                           back to 'pending' (new attempt)
```

---

## 4. Enum Definitions

### 4.1 Application-Level Enums

These are used in the codebase and correspond to MySQL ENUM columns or VARCHAR fields.

```python
# users
class UserType(str, enum.Enum):
    PROMOTER = "promoter"
    DOCTOR   = "doctor"

# hierarchy_nodes
class NodeType(str, enum.Enum):
    ROOT     = "root"      # L1
    PROMOTER = "promoter"  # L2-L5
    CUSTOMER = "customer"  # L6

# promoters (denormalized, synced from qualifications)
class QualificationStatus(str, enum.Enum):
    NONE      = "none"
    REVIEWING = "reviewing"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    EXPIRING  = "expiring"
    EXPIRED   = "expired"

# qualifications
class QualificationReviewStatus(str, enum.Enum):
    REVIEWING = "reviewing"
    APPROVED  = "approved"
    REJECTED  = "rejected"

# promotion_codes
class PromotionCodeStatus(str, enum.Enum):
    ACTIVE   = "active"
    DISABLED = "disabled"
    EXPIRED  = "expired"

# customers / binding_requests
class BindingStatus(str, enum.Enum):
    PENDING_MATCH = "pending_match"
    MATCHING      = "matching"
    BOUND         = "bound"
    UNBOUND       = "unbound"
    TRANSFERRED   = "transferred"
    ERROR         = "error"

# binding_requests
class BindingSourceType(str, enum.Enum):
    MANUAL       = "manual"
    SCAN         = "scan"
    RUTAI_MARKED = "rutai_marked"

# binding_change_logs
class BindingOperatorType(str, enum.Enum):
    DOCTOR = "doctor"
    ADMIN  = "admin"
    SYSTEM = "system"

# bills
class BillStatus(str, enum.Enum):
    NORMAL        = "normal"
    PARTIAL_REFUND = "partial_refund"
    FULL_REFUND   = "full_refund"

# contribution_records
class ContributionStatus(str, enum.Enum):
    PENDING   = "pending"
    SETTLED   = "settled"
    REVERSED  = "reversed"
    CANCELLED = "cancelled"

class ContributionSourceType(str, enum.Enum):
    BINDING     = "binding"
    SERVICE     = "service"
    FOLLOWUP    = "followup"
    BILL        = "bill"
    ADJUSTMENT  = "adjustment"

# sharing_rules
class RuleType(str, enum.Enum):
    FIXED_RATIO  = "fixed_ratio"
    FIXED_AMOUNT = "fixed_amount"
    TIERED       = "tiered"

class RuleBase(str, enum.Enum):
    PAID_AMOUNT  = "paid_amount"
    TOTAL_AMOUNT = "total_amount"

class RuleStatus(str, enum.Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"

# sharing_rule_change_logs
class RuleChangeType(str, enum.Enum):
    CREATED      = "created"
    UPDATED      = "updated"
    DEACTIVATED  = "deactivated"
    REACTIVATED  = "reactivated"

# settlement_logs
class SettlementStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"

# reconciliation_reports
class ReportType(str, enum.Enum):
    CUSTOMER_SUMMARY   = "customer_summary"
    PAYMENT_SUMMARY    = "payment_summary"
    DISCOUNT_SUMMARY   = "discount_summary"
    ALLOCATION_DETAIL  = "allocation_detail"

# articles
class ArticleStatus(str, enum.Enum):
    DRAFT       = "draft"
    PUBLISHED   = "published"
    UNPUBLISHED = "unpublished"

# admin_accounts
class AdminAccountStatus(str, enum.Enum):
    ACTIVE   = "active"
    DISABLED = "disabled"
    LOCKED   = "locked"

# notifications
class NotificationCategory(str, enum.Enum):
    QUALIFICATION = "qualification"
    BINDING       = "binding"
    SYNC          = "sync"
    SYSTEM        = "system"
    SETTLEMENT    = "settlement"

class NotificationRecipientType(str, enum.Enum):
    PROMOTER        = "promoter"
    ADMIN           = "admin"
    ALL_ADMINS      = "all_admins"
    SPECIFIC_ADMIN  = "specific_admin"

# hierarchy_snapshots
class HierarchyAction(str, enum.Enum):
    CREATED = "created"
    MOVED   = "moved"
    DELETED = "deleted"
```

### 4.2 Permission Matrix (RBAC)

Pre-seeded `roles.permissions` for built-in roles per FR-005c:

| Permission                  | Super Admin | Admin | Finance | Ops  |
|-----------------------------|:-----------:|:-----:|:-------:|:----:|
| `account:create`            | Y           |       |         |      |
| `account:manage`            | Y           | Y     |         |      |
| `role:manage`               | Y           |       |         |      |
| `qualification:review`      | Y           | Y     |         |      |
| `hierarchy:manage`          | Y           | Y     |         |      |
| `customer:view`             | Y           | Y     | Y       | Y    |
| `customer:unbind`           | Y           | Y     |         |      |
| `customer:transfer`         | Y           | Y     |         |      |
| `contribution:view`         | Y           | Y     | Y       |      |
| `contribution:adjust`       | Y           | Y     |         |      |
| `sharing_rule:manage`       | Y           |       | Y       |      |
| `settlement:manage`         | Y           |       | Y       |      |
| `reports:view`              | Y           | Y     | Y       |      |
| `reports:export`            | Y           | Y     | Y       |      |
| `article:manage`            | Y           |       |         | Y    |
| `notification:view`         | Y           | Y     | Y       | Y    |
| `notification:manage`       | Y           | Y     |         |      |
| `system:config`             | Y           |       |         |      |

---

## 5. Index Strategy

### 5.1 Index Design Principles

1. **Every FK gets an index** -- all foreign key columns (`*_id`) have a dedicated or
   leading-column index for join performance and referential integrity checks.
2. **Queried ENUMs get indexes** -- status columns that appear in WHERE clauses or are
   used for filtering lists get dedicated indexes.
3. **Time-range queries get composite indexes** -- reports and sync operations query by
   time range; composite indexes lead with the relevant time column.
4. **No over-indexing** -- indexes on low-cardinality boolean columns or columns only
   used in occasional admin queries are omitted.
5. **Full-text for search** -- only `articles.title` and `articles.body` have `FULLTEXT`
   indexes. Other search-like queries use LIKE with existing B-tree indexes on VARCHAR
   columns.

### 5.2 Critical Query Paths and Their Indexes

| Query Pattern                                        | Index Used                                       |
|------------------------------------------------------|--------------------------------------------------|
| "Find user by WeChat openid"                         | `idx_users_openid (openid)` UNIQUE               |
| "Get promoter by user_id"                            | `idx_pr_user (user_id)` UNIQUE                   |
| "Get children of hierarchy node X"                   | `idx_hn_parent (parent_id)`                      |
| "Get all nodes at level 3"                           | `idx_hn_level (level)`                           |
| "Get pending qualifications for review"              | `idx_qual_status (status)`                       |
| "Find qualifications expiring within 30 days"        | `idx_qual_valid_until (valid_until)`             |
| "Get customer's binding history"                     | `idx_br_customer (customer_id)`                  |
| "Check duplicate binding by phone"                   | `idx_cust_phone (phone)` + app-level check       |
| "Get bill by Rutai transaction_id"                   | `idx_bills_txn (transaction_id)` UNIQUE          |
| "Get bills synced in time range"                     | `idx_bills_txn_time (transaction_time)`          |
| "Get pending contributions for promoter X"           | `idx_cr_promoter_status (promoter_id, status)`   |
| "Get contributions by settlement batch"              | `idx_cr_settlement_log (settlement_log_id)`      |
| "Get active sharing rule for level X"                | `idx_sr_level_active (applicable_level, status)` |
| "Get admin notifications (unread, ordered by time)"  | `idx_notif_recipient (recipient_type, recipient_id)` + `idx_notif_read` |
| "Search articles by keyword"                         | `FULLTEXT idx_art_search (title, body)`          |
| "Get published articles (category + time)"           | `idx_art_status (status)` + `idx_art_published`  |
| "Get API call failures in last hour"                 | `idx_acl_called (called_at)` + `idx_acl_success` |
| "Get follow-up reminders due"                        | `idx_fr_next_reminder (next_reminder_at)`        |

### 5.3 Full-Text Search Configuration

```sql
-- MySQL ngram parser for Chinese text search
ALTER TABLE articles ADD FULLTEXT INDEX idx_art_search (title, body) WITH PARSER ngram;
```

The ngram parser tokenizes Chinese text into bigrams (`ngram_token_size=2` default).
For production, set `innodb_ft_min_token_size=1` and `ngram_token_size=2` in `my.cnf`.

---

## 6. Partitioning Strategy

### 6.1 Scope

Only **append-only audit/log tables** that grow unboundedly are partitioned. Core business
tables (`users`, `promoters`, `customers`, etc.) are not partitioned -- their growth is
proportional to business scale (tens of thousands of rows), not time.

### 6.2 Partitioned Tables

| Table               | Partition Key     | Granularity | Retention        |
|----------------------|-------------------|-------------|------------------|
| `api_call_logs`      | YEAR(called_at)   | Annual      | Permanent (FR-063a) |
| `binding_change_logs`| YEAR(created_at)  | Annual      | Permanent        |
| `hierarchy_snapshots`| YEAR(created_at)  | Annual      | Permanent        |
| `settlement_logs`    | Not partitioned   | N/A         | One row per month; negligible growth |

**Rationale:**
- `api_call_logs`: 60-second polling + per-user bill queries = thousands of rows per day.
  Without partitioning, the table reaches millions of rows within months.
- `binding_change_logs`: One row per status transition per binding. Moderate growth
  but should be partitioned for long-term query performance.
- `hierarchy_snapshots`: Low volume (hierarchy changes are infrequent admin operations).
  Partitioned for consistency with audit table policy; partition pruning still helps
  even at low volumes.

### 6.3 Partition Management

```sql
-- Add a new partition before the year rolls over (run in December):
ALTER TABLE api_call_logs REORGANIZE PARTITION p_future INTO (
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- Query examples that leverage partition pruning:
SELECT * FROM api_call_logs WHERE called_at >= '2026-06-01' AND called_at < '2026-07-01';
-- MySQL scans only partition p2026.
```

**Automation:** A pre-December CRON job (or Alembic migration) should add the next year's
partition. If it fails, data writes into `p_future` still work -- the partition just
isn't pruned as efficiently.

### 6.4 Tables Explicitly NOT Partitioned

- **`bills`**: Growth is bounded by Rutai-side transaction volume. Partitioning adds
  complexity (all unique keys must include the partition key) without proportional benefit.
- **`contribution_records`**: Growth is proportional to bills + hierarchy width. The
  composite index `(promoter_id, status)` handles the primary query pattern efficiently.
- **`notifications`**: Can be periodically archived/bulk-cleared rather than partitioned.

---

## 7. Table Summary

| # | Table Name                  | MySQL Name              | Primary Key        | Approx. Growth   |
|---|-----------------------------|-------------------------|--------------------|------------------|
| 1 | 用户                         | users                   | id                 | Linear (users)   |
| 2 | 用户令牌                      | user_tokens             | id                 | Linear x sessions|
| 3 | 后台账号                      | admin_accounts          | id                 | ~constant (<100) |
| 4 | 角色                         | roles                   | id                 | ~constant (<20)  |
| 5 | 账号-角色关联                  | admin_account_roles     | id                 | Linear x roles   |
| 6 | 层级节点                      | hierarchy_nodes         | id                 | Linear (tree)    |
| 7 | 层级快照                      | hierarchy_snapshots     | id                 | Low              |
| 8 | 拓展人                        | promoters               | id                 | Linear (<= nodes)|
| 9 | 资质                         | qualifications          | id                 | Linear x submits |
|10 | 推广码                        | promotion_codes         | id                 | Linear x refreshes|
|11 | 客户                         | customers               | id                 | Linear (10k+)    |
|12 | 绑定申请                      | binding_requests        | id                 | Linear           |
|13 | 绑定变更日志                   | binding_change_logs     | id                 | Linear x states  |
|14 | 账单                         | bills                   | id                 | Linear (high)    |
|15 | 贡献值记录                    | contribution_records    | id                 | Linear x tree width|
|16 | 分账规则                      | sharing_rules           | id                 | ~constant        |
|17 | 分账规则变更日志               | sharing_rule_change_logs| id                 | Low              |
|18 | 结算日志                      | settlement_logs         | id                 | 12/year          |
|19 | 对账报表                      | reconciliation_reports  | id                 | Low (on-demand)  |
|20 | 文章                         | articles                | id                 | Low              |
|21 | 跟进记录                      | followup_records        | id                 | Linear           |
|22 | 授权记录                      | consent_records         | id                 | Linear           |
|23 | 消息通知                      | notifications           | id                 | Linear (moderate)|
|24 | 接口调用日志                   | api_call_logs           | id, called_at      | High (partitioned)|
|25 | 幂等键                       | idempotency_keys        | id                 | Transient (purged)|

**Total: 25 tables** (19 core entities + 6 supporting tables for M:N junctions, audit logs,
and infrastructure).

---

## 8. SQLAlchemy Mapping Notes

- **Async engine**: All models use SQLAlchemy 2.0 async style (`AsyncAttrs`, `async_sessionmaker`).
- **Declarative base**: `Base = declarative_base()` in `backend/src/models/base.py`.
- **Naming convention**: Python class names use PascalCase matching the table purpose
  (e.g., `User`, `Promoter`, `BindingRequest`). Table names use snake_case matching
  the logical entity name (e.g., `users`, `promoters`, `binding_requests`).
- **UUID alternative**: IDs use `BIGINT UNSIGNED AUTO_INCREMENT` rather than UUIDs for
  performance (sequential PKs benefit InnoDB clustered indexes) and human readability
  in admin screens. External-facing IDs use opaque tokens (e.g., `ref_token` for
  promotion codes) where needed.
- **JSON columns**: Mapped to Python `dict`/`list` via `sqlalchemy.JSON`. MySQL stores
  JSON natively (binary JSON type) since 5.7.
- **ENUM columns**: Mapped to Python `enum.Enum` subclasses via `sqlalchemy.Enum`. MySQL
  native ENUM used for storage efficiency and CHECK-like constraint.
- **DECIMAL columns**: Mapped to Python `decimal.Decimal` for exact arithmetic. Never use
  `float`/`double` for monetary or points values.
- **Timestamp precision**: `DATETIME(3)` provides millisecond precision. Sufficient for
  ordering idempotent operations and audit trails.
- **Soft delete**: `deleted_at` columns use SQLAlchemy's `@declared_attr` or a mixin
  to add `.where(deleted_at.is_(None))` to default queries.
- **Polymorphic references**: Where a column can reference different tables (e.g.,
  `notifications.recipient_id`), use a discriminator column (`recipient_type`) and
  skip the FK constraint. Type safety is enforced at the Pydantic/service layer.
