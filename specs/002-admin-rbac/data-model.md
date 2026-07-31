# Data Model: 后台管理 RBAC 权限管理

**Feature**: 002-admin-rbac
**Date**: 2026-07-31

## Entity Changes

### Role (`roles`)

| Field | Type | Change | Description |
|-------|------|--------|-------------|
| `id` | INT PK | Existing | Auto-increment |
| `name` | VARCHAR(100) UNIQUE NOT NULL | Existing | Role display name |
| `permissions` | JSON NOT NULL DEFAULT '{}' | Existing | Permission dict, format: `{"permissions": ["scope.action", ...]}` |
| `is_system` | BOOLEAN NOT NULL DEFAULT FALSE | **NEW** | System-reserved flag; system roles cannot be deleted or renamed |
| `created_at` | DATETIME | Existing | Creation timestamp |

**State transitions**: N/A — roles have no lifecycle state beyond creation/deletion.

### AdminAccount (`admin_accounts`)

| Field | Type | Change | Description |
|-------|------|--------|-------------|
| `id` | INT PK | Existing | Auto-increment |
| `username` | VARCHAR(100) UNIQUE NOT NULL | Existing | Login username |
| `password_hash` | VARCHAR(255) NOT NULL | Existing | bcrypt hash |
| `status` | ENUM(active, disabled, locked) | Existing | Account status |
| `locked_until` | DATETIME NULL | Existing | Auto-unlock time |
| `created_at` | DATETIME | Existing | |
| `updated_at` | DATETIME | Existing | |

**State transitions**:
```
active → disabled (admin action: disable)
disabled → active (admin action: enable)
active → locked (5 failed login attempts)
locked → active (auto after lockout period or manual reset)
```

### Junction: admin_account_roles

| Field | Type | Change | Description |
|-------|------|--------|-------------|
| `admin_account_id` | INT FK → admin_accounts.id | Existing | |
| `role_id` | INT FK → roles.id | Existing | |

No changes needed. CASCADE delete on both FKs.

### Seed Data

**System Admin Role** (created on first startup if not exists):

```json
{
  "name": "系统管理员",
  "is_system": true,
  "permissions": {
    "permissions": [
      "accounts.read", "accounts.write",
      "roles.read", "roles.write",
      "customers.read", "customers.write",
      "qualifications.read", "qualifications.write",
      "contributions.read",
      "reports.read",
      "articles.read", "articles.write",
      "promotions.read", "promotions.write",
      "notifications.read", "notifications.write",
      "hierarchy.read", "hierarchy.write",
      "sharing_rules.read", "sharing_rules.write",
      "sync.read", "sync.write"
    ]
  }
}
```

**Default admin ↔ System Admin role** (if not already assigned):
- Admin account `username = admin` gets `role_id = <system_admin_role.id>` inserted into `admin_account_roles`
