# API Contracts: Admin RBAC

**Feature**: 002-admin-rbac
**Date**: 2026-07-31

All endpoints under `/api/v1` prefix. All responses use unified envelope `{code, message, data, requestId, serverTime}`.

## Admin Accounts (`/admin/accounts`)

### GET /admin/accounts — List accounts

**Query**: `?cursor=&page_size=20&status=active`

**Response data**:
```json
{
  "items": [{
    "id": 1,
    "username": "admin",
    "status": "active",
    "roles": [{"id": 1, "name": "系统管理员"}],
    "created_at": "2026-07-31T00:00:00Z"
  }],
  "next_cursor": null,
  "has_more": false
}
```

### POST /admin/accounts — Create account

**Request**:
```json
{
  "username": "new_admin",
  "password": "min-length-8",
  "roleIds": [2]
}
```

**Validation**: username unique, password ≥ 8 chars.

### PUT /admin/accounts/{id} — Update account

**Request**:
```json
{
  "password": "new-password",
  "roleIds": [2, 3]
}
```

### POST /admin/accounts/{id}/disable — Disable account

**Constraint**: Cannot disable account with `username = "admin"` (default admin).

### POST /admin/accounts/{id}/enable — Enable account

No additional constraints.

---

## Roles (`/admin/roles`)

### GET /admin/roles — List roles

**Response data**:
```json
{
  "items": [{
    "id": 1,
    "name": "系统管理员",
    "permissions": {"permissions": ["accounts.read", "accounts.write", "..."]},
    "is_system": true,
    "created_at": "2026-07-31T00:00:00Z"
  }]
}
```

### POST /admin/roles — Create role

**Request**:
```json
{
  "name": "运营编辑",
  "permissions": {"permissions": ["articles.read", "articles.write", "notifications.read"]}
}
```

**Validation**: name unique.

### PUT /admin/roles/{id} — Update role

**Constraint**: System roles (`is_system = true`) cannot have their name changed.

**Request**:
```json
{
  "name": "运营编辑 v2",
  "permissions": {"permissions": ["articles.read", "articles.write"]}
}
```

### DELETE /admin/roles/{id} — Delete role

**Pre-checks** (return error if either fails):
1. Role `is_system = true` → 403 "系统管理员角色不可删除"
2. Role assigned to any admin account (check `admin_account_roles`) → 409 "该角色已被 N 个管理员使用，请先取消分配"

---

## Permission Definitions (Frontend Constant)

The following permission list is defined in `manageSystem/src/constants/permissions.js`:

```javascript
export const PERMISSION_MODULES = [
  {
    module: 'accounts',
    label: '账户管理',
    permissions: [
      { key: 'accounts.read', label: '查看管理员列表' },
      { key: 'accounts.write', label: '创建/编辑管理员' },
    ],
  },
  {
    module: 'roles',
    label: '角色管理',
    permissions: [
      { key: 'roles.read', label: '查看角色列表' },
      { key: 'roles.write', label: '创建/编辑/删除角色' },
    ],
  },
  {
    module: 'customers',
    label: '客户管理',
    permissions: [
      { key: 'customers.read', label: '查看客户列表及详情' },
      { key: 'customers.write', label: '编辑客户信息' },
    ],
  },
  {
    module: 'qualifications',
    label: '资质审核',
    permissions: [
      { key: 'qualifications.read', label: '查看资质申请' },
      { key: 'qualifications.write', label: '审核资质申请' },
    ],
  },
  {
    module: 'contributions',
    label: '业绩贡献',
    permissions: [
      { key: 'contributions.read', label: '查看业绩数据' },
    ],
  },
  {
    module: 'reports',
    label: '数据报表',
    permissions: [
      { key: 'reports.read', label: '查看报表' },
    ],
  },
  {
    module: 'articles',
    label: '文章管理',
    permissions: [
      { key: 'articles.read', label: '查看文章列表' },
      { key: 'articles.write', label: '创建/编辑/删除文章' },
    ],
  },
  {
    module: 'promotions',
    label: '推广码管理',
    permissions: [
      { key: 'promotions.read', label: '查看推广码' },
      { key: 'promotions.write', label: '创建/编辑推广码' },
    ],
  },
  {
    module: 'notifications',
    label: '消息通知',
    permissions: [
      { key: 'notifications.read', label: '查看通知' },
      { key: 'notifications.write', label: '发送通知' },
    ],
  },
  {
    module: 'hierarchy',
    label: '层级管理',
    permissions: [
      { key: 'hierarchy.read', label: '查看层级结构' },
      { key: 'hierarchy.write', label: '编辑层级结构' },
    ],
  },
  {
    module: 'sharing_rules',
    label: '分成规则',
    permissions: [
      { key: 'sharing_rules.read', label: '查看分成规则' },
      { key: 'sharing_rules.write', label: '编辑分成规则' },
    ],
  },
  {
    module: 'sync',
    label: '数据同步',
    permissions: [
      { key: 'sync.read', label: '查看同步状态' },
      { key: 'sync.write', label: '手动触发同步' },
    ],
  },
]
```

**Note**: The set of `read`/`write` permissions per module follows the principle that some modules are read-only (reports, contributions). The full list of 22 permission keys serves as the seed data for the "系统管理员" role.
