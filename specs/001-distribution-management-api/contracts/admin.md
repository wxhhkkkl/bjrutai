# Admin API Contracts

All endpoints under `/api/v1/admin/`. Unified response envelope: `{ code, message, data, requestId, serverTime }`.

All admin endpoints require an authenticated admin session with appropriate role-based permissions.

---

## List Admin Accounts

**Method**: GET
**Path**: /api/v1/admin/accounts
**Auth**: Required (admin)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| status | string | no | Enum: `active`, `disabled` | Filter by status |
| roleId | string | no | Length 1-64 | Filter by role |
| keyword | string | no | Max 100 chars | Search by account name or display name |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "accountId": "u_admin001",
        "account": "admin001",
        "displayName": "管理员张三",
        "role": {
          "roleId": "role_admin",
          "roleName": "超级管理员"
        },
        "orgNodeId": "org_001",
        "orgNodeName": "北京总部",
        "status": "active",
        "statusLabel": "正常",
        "lastLoginAt": "2026-07-29T08:30:00+08:00",
        "createdAt": "2025-01-01T00:00:00+08:00"
      }
    ],
    "nextCursor": "cursor_admin_accts",
    "hasMore": false
  },
  "requestId": "req_20260730120000036",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Visibility scoped to the admin's own org node and its descendants.
- Passwords are never returned in any response.
- `lastLoginAt` is null if the account has never logged in.

---

## Create Admin Account

**Method**: POST
**Path**: /api/v1/admin/accounts
**Auth**: Required (admin, permission: `admin.accounts.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| account | string | yes | Length 4-64, alphanumeric + underscore | Login account name |
| displayName | string | yes | Length 2-50 | Display name |
| password | string | yes | Length 8-128 | Initial password |
| roleId | string | yes | Length 1-64 | Role ID to assign |
| orgNodeId | string | yes | Length 1-64 | Org node assignment |
| phone | string | no | Length 11 | Phone number |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accountId": "u_admin002",
    "account": "admin002",
    "displayName": "管理员李四",
    "role": {
      "roleId": "role_ops",
      "roleName": "运营人员"
    },
    "orgNodeId": "org_002",
    "orgNodeName": "华东大区",
    "status": "active",
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000037",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40050 | Account name already exists | No |
| 40051 | Role not found | No |
| 40052 | Org node not found | No |
| 40053 | Password does not meet complexity requirements | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Account name must be unique across all admin accounts.
- Password must contain at least 8 characters with at least one letter and one digit.
- The creator must have authority over the target `orgNodeId` (must be same org node or a descendant).
- The creator cannot assign a role with higher privilege than their own.

---

## Update Admin Account

**Method**: PUT
**Path**: /api/v1/admin/accounts/{id}
**Auth**: Required (admin, permission: `admin.accounts.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Admin account ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| displayName | string | no | Length 2-50 | Display name |
| roleId | string | no | Length 1-64 | New role ID |
| orgNodeId | string | no | Length 1-64 | New org node assignment |
| phone | string | no | Length 11 | Phone number |
| password | string | no | Length 8-128 | New password (resets on next login if set) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accountId": "u_admin002",
    "account": "admin002",
    "displayName": "管理员李四(已更新)",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000038",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Account not found | No |
| 40051 | Role not found | No |
| 40052 | Org node not found | No |
| 40054 | Cannot modify a super admin account | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Cannot modify accounts with higher privilege than the caller.
- Cannot modify super admin accounts (built-in system accounts).
- If `password` is set, the existing refresh tokens for that account are revoked.

---

## Disable Admin Account

**Method**: POST
**Path**: /api/v1/admin/accounts/{id}/disable
**Auth**: Required (admin, permission: `admin.accounts.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Admin account ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| reason | string | no | Max 500 chars | Disable reason |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accountId": "u_admin002",
    "status": "disabled",
    "statusLabel": "已禁用",
    "disabledAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000039",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Account not found | No |
| 40055 | Cannot disable your own account | No |
| 40054 | Cannot disable a super admin account | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Disabled accounts cannot log in. All existing sessions are revoked.
- Does not delete the account; it can be re-enabled via the update endpoint.
- An admin cannot disable their own account.

---

## List Roles

**Method**: GET
**Path**: /api/v1/admin/roles
**Auth**: Required (admin, permission: `admin.roles.read`)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "roleId": "role_admin",
        "roleName": "超级管理员",
        "description": "系统最高权限角色",
        "permissions": [
          "admin.*",
          "qualification.*",
          "binding.*",
          "customer.*",
          "contribution.*"
        ],
        "isSystemRole": true,
        "accountCount": 2,
        "createdAt": "2025-01-01T00:00:00+08:00"
      }
    ]
  },
  "requestId": "req_20260730120000040",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- `isSystemRole: true` means the role cannot be modified or deleted.
- `permissions` uses glob-style wildcards (e.g., `qualification.*` grants all qualification permissions).
- Results sorted by role priority (highest first).

---

## Create Role

**Method**: POST
**Path**: /api/v1/admin/roles
**Auth**: Required (admin, permission: `admin.roles.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| roleName | string | yes | Length 2-50, unique | Role display name |
| description | string | no | Max 200 chars | Role description |
| permissions | array[string] | yes | Min 1 item | List of permission strings |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "roleId": "role_custom_001",
    "roleName": "区域管理员",
    "description": "管理指定区域的业务",
    "permissions": [
      "qualification.review",
      "binding.transfer",
      "customer.read",
      "contribution.read"
    ],
    "isSystemRole": false,
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000041",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40056 | Role name already exists | No |
| 40057 | Invalid permission string(s) | No |
| 40058 | Cannot assign permissions you do not have | No |
| 50001 | Internal server error | Yes |

### Business Rules
- The creator can only assign permissions they themselves possess.
- `roleName` must be unique among non-system roles.
- Permission strings follow the format `resource.action` (e.g., `qualification.review`).

---

## Get Hierarchy Tree

**Method**: GET
**Path**: /api/v1/admin/hierarchy
**Auth**: Required (admin)
**Idempotency**: Not applicable

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "tree": {
      "nodeId": "org_001",
      "nodeName": "北京总部",
      "nodeType": "headquarters",
      "nodeTypeLabel": "总部",
      "managerId": "u_admin001",
      "managerName": "管理员张三",
      "sortOrder": 0,
      "children": [
        {
          "nodeId": "org_002",
          "nodeName": "华东大区",
          "nodeType": "region",
          "nodeTypeLabel": "大区",
          "managerId": "u_admin002",
          "managerName": "管理员李四",
          "sortOrder": 1,
          "children": [
            {
              "nodeId": "org_003",
              "nodeName": "上海分部",
              "nodeType": "branch",
              "nodeTypeLabel": "分部",
              "managerId": null,
              "managerName": null,
              "sortOrder": 0,
              "children": []
            }
          ]
        }
      ]
    },
    "statistics": {
      "totalNodes": 5,
      "totalAdmins": 8,
      "totalPromoters": 150
    }
  },
  "requestId": "req_20260730120000042",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Returns the full hierarchy tree from the admin's assigned org node downward.
- `nodeType` enum: `headquarters`, `region`, `branch`, `team`.
- Empty `children` array indicates a leaf node.

---

## Create Hierarchy Node

**Method**: POST
**Path**: /api/v1/admin/hierarchy/nodes
**Auth**: Required (admin, permission: `admin.hierarchy.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| nodeName | string | yes | Length 2-50 | Node name |
| nodeType | string | yes | Enum: `region`, `branch`, `team` | Node type |
| parentNodeId | string | yes | Length 1-64 | Parent node ID |
| sortOrder | integer | no | >= 0, default 0 | Display order among siblings |
| managerId | string | no | Length 1-64 | Admin account ID to assign as manager |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "nodeId": "org_004",
    "nodeName": "浙江分部",
    "nodeType": "branch",
    "parentNodeId": "org_002",
    "parentNodeName": "华东大区",
    "sortOrder": 1,
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000043",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Parent node not found | No |
| 40059 | Node name already exists under this parent | No |
| 40060 | Invalid manager ID | No |
| 40061 | Cannot create child under a leaf-type node | No |
| 50001 | Internal server error | Yes |

### Business Rules
- A node name must be unique among sibling nodes.
- The admin must have authority over the parent node.
- `managerId` is optional; if omitted, the node has no assigned manager.

---

## Update Hierarchy Node

**Method**: PUT
**Path**: /api/v1/admin/hierarchy/nodes/{id}
**Auth**: Required (admin, permission: `admin.hierarchy.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Node ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| nodeName | string | no | Length 2-50 | New node name |
| nodeType | string | no | Enum | New node type |
| sortOrder | integer | no | >= 0 | New display order |
| managerId | string | no | Length 1-64 or empty string to clear | New manager assignment |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "nodeId": "org_003",
    "nodeName": "上海分部（已更名）",
    "nodeType": "branch",
    "sortOrder": 5,
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000044",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Node not found | No |
| 40059 | Node name already exists under this parent | No |
| 40062 | Cannot change type of a node with children | No |
| 50001 | Internal server error | Yes |

### Business Rules
- The admin must have authority over the node being updated.
- `nodeType` cannot be changed if the node has children (conflicting hierarchy).
- Send empty string `""` for `managerId` to remove the current manager.

---

## Delete Hierarchy Node

**Method**: DELETE
**Path**: /api/v1/admin/hierarchy/nodes/{id}
**Auth**: Required (admin, permission: `admin.hierarchy.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Node ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": null,
  "requestId": "req_20260730120000045",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Node not found | No |
| 40063 | Cannot delete node with child nodes (migrate first) | No |
| 40064 | Cannot delete node with active admins or promoters | No |
| 40065 | Cannot delete root node | No |
| 50001 | Internal server error | Yes |

### Business Rules
- A node can only be deleted if it has no children, no assigned admins, and no assigned promoters.
- For nodes with children, use the migrate endpoint first to reassign them.
- Root node (headquarters) cannot be deleted.

---

## Migrate Hierarchy Branch

**Method**: POST
**Path**: /api/v1/admin/hierarchy/nodes/{id}/migrate
**Auth**: Required (admin, permission: `admin.hierarchy.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Node ID to migrate (including all descendants) |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| targetParentNodeId | string | yes | Length 1-64 | New parent node ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "migratedNodeId": "org_003",
    "migratedNodeName": "上海分部",
    "fromParentNodeId": "org_002",
    "fromParentNodeName": "华东大区",
    "toParentNodeId": "org_005",
    "toParentNodeName": "华南大区",
    "affectedAccounts": 3,
    "affectedPromoters": 25,
    "migratedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000046",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Source or target node not found | No |
| 40066 | Cannot migrate a node to its own descendant (circular) | No |
| 40067 | Target parent cannot accept children of this type | No |
| 50001 | Internal server error | Yes |

### Business Rules
- The entire sub-tree (the node and all its descendants) is moved to the new parent.
- All admins and promoters under the migrated sub-tree retain their assignments but now fall under the new parent hierarchy.
- Circular migration is blocked (cannot move a node to be a child of one of its own descendants).

---

## Review Qualification

**Method**: POST
**Path**: /api/v1/admin/qualifications/{id}/review
**Auth**: Required (admin, permission: `qualification.review`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Qualification record ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| action | string | yes | Enum: `approve`, `reject`, `return_for_amend` | Review decision |
| comment | string | no | Max 1000 chars | Review comment (required for reject/return) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "qualificationId": "qual_001",
    "action": "approve",
    "actionLabel": "通过",
    "comment": "资料齐全，审核通过",
    "reviewedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000047",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Qualification not found | No |
| 40068 | Qualification is not in pending_review status | No |
| 40069 | Comment is required for reject or return_for_amend | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only qualifications in `pending_review` status can be reviewed.
- `approve`: sets status to `approved`; the user becomes an active promoter.
- `reject`: sets status to `rejected`; the user must resubmit.
- `return_for_amend`: sets status to `draft`; the user can edit and resubmit without the full review queue.

---

## Unbind

**Method**: POST
**Path**: /api/v1/admin/bindings/{id}/unbind
**Auth**: Required (admin, permission: `binding.manage`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Binding ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| reason | string | yes | Max 500 chars | Unbind reason (audited) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "bindingId": "bind_001",
    "status": "unbound",
    "unboundAt": "2026-07-30T12:00:00+08:00",
    "reason": "推广员申请解除绑定"
  },
  "requestId": "req_20260730120000048",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Binding not found | No |
| 40070 | Binding is not active | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only active bindings can be unbound.
- After unbinding, the customer's `bindingInfo` becomes the previous one in history (if any) or null.
- Pending contributions from the unbound promoter remain in their accounts.
- The unbind is permanent; a new binding request must be submitted to re-establish.

---

## Transfer Binding

**Method**: POST
**Path**: /api/v1/admin/bindings/{id}/transfer
**Auth**: Required (admin, permission: `binding.manage`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Binding ID to transfer from |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| targetPromoterId | string | yes | Length 1-64 | Promoter to transfer the customer to |
| reason | string | yes | Max 500 chars | Transfer reason (audited) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "oldBindingId": "bind_001",
    "newBindingId": "bind_002",
    "customerId": "cust_001",
    "customerName": "王五",
    "fromPromoter": {
      "promoterId": "u_prom001",
      "promoterName": "李四"
    },
    "toPromoter": {
      "promoterId": "u_prom003",
      "promoterName": "赵六"
    },
    "transferredAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000049",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Source binding or target promoter not found | No |
| 40071 | Target promoter is not qualified | No |
| 40072 | Target promoter has reached maximum bindings | No |
| 40073 | Cannot transfer to the same promoter | No |
| 40070 | Source binding is not active | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Transfer creates a new binding with the target promoter and terminates the old binding.
- Historical contributions remain with the old promoter. Only new contributions accrue to the new promoter.
- The old binding's `unboundAt` is set; the new binding's `boundAt` is the transfer time.

---

## List Sharing Rules

**Method**: GET
**Path**: /api/v1/admin/sharing-rules
**Auth**: Required (admin, permission: `admin.sharing.read`)
**Idempotency**: Not applicable

### Query Parameters
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| status | string | no | Enum: `active`, `inactive` | Filter by status |
| cursor | string | no | Max 256 chars | Cursor for pagination |
| limit | integer | no | 1-100, default 20 | Page size |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "ruleId": "rule_001",
        "ruleName": "默认分配规则",
        "targetType": "promoter",
        "targetId": "u_prom001",
        "targetName": "李四",
        "percentage": 70,
        "status": "active",
        "statusLabel": "生效中",
        "effectiveFrom": "2026-01-01T00:00:00+08:00",
        "effectiveTo": null
      }
    ],
    "nextCursor": "cursor_rules",
    "hasMore": false
  },
  "requestId": "req_20260730120000050",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Sharing rules define how contribution amounts split across promoters and org nodes.
- `targetType`: `promoter` or `org_node`.
- All active rules for a given scope must sum to 100%.

---

## Create Sharing Rule

**Method**: POST
**Path**: /api/v1/admin/sharing-rules
**Auth**: Required (admin, permission: `admin.sharing.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| ruleName | string | yes | Length 2-100 | Rule display name |
| targetType | string | yes | Enum: `promoter`, `org_node` | Sharing target type |
| targetId | string | yes | Length 1-64 | Target promoter or org node ID |
| percentage | integer | yes | 1-100 | Share percentage |
| effectiveFrom | string | yes | ISO 8601 datetime | When the rule takes effect |
| effectiveTo | string | no | ISO 8601 datetime | When the rule expires (null = indefinite) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "ruleId": "rule_002",
    "ruleName": "华东大区提成规则",
    "targetType": "promoter",
    "targetId": "u_prom003",
    "targetName": "赵六",
    "percentage": 80,
    "status": "active",
    "effectiveFrom": "2026-08-01T00:00:00+08:00",
    "effectiveTo": null,
    "createdAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000051",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Target promoter or org node not found | No |
| 40074 | Active rule percentages for this scope exceed 100% | No |
| 40075 | Rule with same target already exists | No |
| 50001 | Internal server error | Yes |

### Business Rules
- The sum of all active sharing rule percentages must not exceed 100%.
- `effectiveFrom` can be a future date, in which case the rule is created with status `active` but only applies from that date.
- A target (promoter or org node) can only have one active rule at a time.

---

## Update Sharing Rule

**Method**: PUT
**Path**: /api/v1/admin/sharing-rules/{id}
**Auth**: Required (admin, permission: `admin.sharing.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Rule ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| ruleName | string | no | Length 2-100 | New rule name |
| percentage | integer | no | 1-100 | New share percentage |
| effectiveFrom | string | no | ISO 8601 datetime | New effective date |
| effectiveTo | string | no | ISO 8601 datetime or empty string | New expiry date |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "ruleId": "rule_002",
    "ruleName": "华东大区提成规则(已调整)",
    "percentage": 75,
    "effectiveFrom": "2026-08-01T00:00:00+08:00",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000052",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Rule not found | No |
| 40074 | Active rule percentages for this scope exceed 100% | No |
| 40076 | Cannot modify an inactive rule | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Only active rules can be modified. To change an inactive rule, create a new one.
- Changing `percentage` triggers a recalculation of pending contributions.

---

## Deactivate Sharing Rule

**Method**: POST
**Path**: /api/v1/admin/sharing-rules/{id}/deactivate
**Auth**: Required (admin, permission: `admin.sharing.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Rule ID |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "ruleId": "rule_002",
    "status": "inactive",
    "statusLabel": "已失效",
    "deactivatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000053",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Rule not found | No |
| 40077 | Rule is already inactive | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Deactivation does not retroactively affect settled contributions.
- Pending contributions are recalculated without the deactivated rule.

---

## Set Contribution Coefficient

**Method**: PUT
**Path**: /api/v1/admin/contribution-coefficient
**Auth**: Required (admin, permission: `admin.contribution.write`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| coefficient | string | yes | Decimal string, e.g. "0.33" (0 < x <= 1) | Global contribution coefficient |
| effectiveFrom | string | yes | ISO 8601 datetime | Effective date |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "coefficient": "0.33",
    "coefficientPercent": "33%",
    "effectiveFrom": "2026-08-01T00:00:00+08:00",
    "previousCoefficient": "0.30",
    "updatedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000054",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40078 | Coefficient must be between 0 and 1 (exclusive of 0) | No |
| 40079 | Effective date must be in the future | No |
| 50001 | Internal server error | Yes |

### Business Rules
- The coefficient is applied to order amounts to compute contribution.
- `contribution = orderAmount * coefficient * sharingPercentage`.
- Historical settled contributions are not affected by coefficient changes.
- Only one active coefficient at a time; the new one replaces the current one.

---

## Adjust Contribution

**Method**: POST
**Path**: /api/v1/admin/contributions/{id}/adjust
**Auth**: Required (admin, permission: `admin.contribution.write`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | yes | Contribution ID |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| adjustmentAmount | integer | yes | Can be negative (deduction) | Adjustment amount in 分 |
| reason | string | yes | Max 1000 chars | Adjustment reason (audited) |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "adjustmentId": "adj_002",
    "contributionId": "ctrb_001",
    "originalAmount": "500000",
    "adjustmentAmount": "50000",
    "adjustedAmount": "550000",
    "reason": "季度奖励",
    "adjustedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000055",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | Contribution not found | No |
| 40080 | Adjusted amount cannot be negative | No |
| 40081 | Can only adjust settled contributions | No |
| 50001 | Internal server error | Yes |

### Business Rules
- Adjustments can only be applied to `settled` contributions.
- Negative `adjustmentAmount` denotes a deduction. The result (`adjustedAmount`) must not go below 0.
- All adjustments are audited with operator ID and timestamp.
- Multiple adjustments on the same contribution are cumulative.

---

## Retry BindUser Sync

**Method**: POST
**Path**: /api/v1/admin/sync/retry-binduser
**Auth**: Required (admin, permission: `admin.sync.manage`)
**Idempotency**: Required (Idempotency-Key header)

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| userId | string | no | Length 1-64 | Specific user to retry (syncs all if omitted) |
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Sync from this date |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "syncTaskId": "sync_001",
    "status": "queued",
    "queuedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000056",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40082 | A sync task is already running | Yes |
| 50001 | Internal server error | Yes |

### Business Rules
- Triggers a background sync of user-to-customer binding data from the ERP/order system.
- If `userId` is omitted, retries all failed syncs in the specified date range.
- Only one sync task can run at a time. Returns `40082` if another is still in progress.

---

## Retry Bill Sync

**Method**: POST
**Path**: /api/v1/admin/sync/retry-bill/{userId}
**Auth**: Required (admin, permission: `admin.sync.manage`)
**Idempotency**: Required (Idempotency-Key header)

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| userId | string | yes | User ID whose bill data to re-sync |

### Request Body
| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| startDate | string | no | ISO 8601 date (YYYY-MM-DD) | Sync from this date (default: last 90 days) |
| billIds | array[string] | no | Max 100 items | Specific bill IDs to retry |

### Response (Success)
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "syncTaskId": "sync_bill_001",
    "userId": "u_abc123",
    "status": "queued",
    "queuedAt": "2026-07-30T12:00:00+08:00"
  },
  "requestId": "req_20260730120000057",
  "serverTime": "2026-07-30T12:00:00+08:00"
}
```

### Error Codes
| Code | Message | Retryable |
|------|---------|-----------|
| 40300 | Insufficient permissions | No |
| 40400 | User not found | No |
| 40082 | A sync task for this user is already running | Yes |
| 50001 | Internal server error | Yes |

### Business Rules
- Re-fetches bill/order data from the external ERP system and recalculates contributions.
- If `billIds` is provided, only those specific bills are re-synced.
- Historical contributions from re-synced bills are updated; settled contributions may be adjusted.
