# Data Model: 小程序注册自动挂载默认组织顶级部门

**Feature**: 012-register-default-dept
**Date**: 2026-08-08

## Schema Changes

### `distributors` 表 — 新增字段

| Column | Type | Constraints | Default | Description |
|--------|------|------------|---------|-------------|
| `source_channel` | VARCHAR(32) | NOT NULL | `'admin_create'` | 人员来源渠道：`wechat_register`、`phone_register`、`admin_create` |

**Migration**: `012_add_distributor_source_channel.py`

```sql
ALTER TABLE distributors
ADD COLUMN source_channel VARCHAR(32) NOT NULL DEFAULT 'admin_create'
AFTER status;
```

### 现有表（无变更）

| Table | Role |
|-------|------|
| `users` | 用户账号（openid, phone, name, user_type 等）— 无 schema 变更 |
| `organizations` | 组织树（parent_id, name, sort_order 等）— 无 schema 变更，通过查询规则确定默认组织 |
| `distributors` | 人员记录（user_id, org_id, org_role, status）— 新增 source_channel |

## 实体关系

```
┌──────────┐         ┌──────────────┐         ┌──────────────┐
│   users   │ 1 ── 1 │ distributors │ N ── 1  │ organizations │
│           │        │              │         │              │
│ id (PK)   │◄──────│ user_id (FK) │────────►│ id (PK)      │
│ openid    │        │ org_id (FK)  │         │ parent_id     │
│ phone     │        │ org_role     │         │ name          │
│ name      │        │ status       │         │ sort_order    │
│ user_type │        │ source_channel│        │ level         │
└──────────┘        └──────────────┘         └──────────────┘
                                                    │
                                                    │ parent_id (self-ref)
                                                    ▼
                                            ┌──────────────┐
                                            │ organizations │
                                            │  (child node) │
                                            └──────────────┘
```

## 状态转换

### 新用户注册流程

```
[用户发起注册]
      │
      ▼
[微信授权 / 手机号+密码]
      │
      ▼
[创建 User 记录] ──► user_type=PROMOTER, wechat_bound=true
      │
      ▼
[手机号去重检查] ──► 已存在? → 仅绑定微信 (FR-004)
      │                    └── 不存在? ↓
      ▼
[查找默认组织]  ──► 根节点不存在? → 创建 User 但 org_id=NULL (FR-005)
      │                    └── 存在? ↓
      ▼
[创建 Distributor] ──► org_id=默认组织ID, org_role=member
                      source_channel=wechat_register|phone_register
                      status=active
      │
      ▼
[返回 session + distributor info]
      │
      ▼
[小程序跳转] ──► profile-setup (可选完善信息) → 首页
```

### Distributor 生命周期

```
[admin_create] ──► active ──► disabled ──► (可重新启用 → active)
[wechat_register] ──► active ──► disabled ──► (可重新启用 → active)
[phone_register] ──► active ──► disabled ──► (可重新启用 → active)

注：org_id 可由管理员通过现有 update_distributor 接口调整
```

## 数据约束

- **手机号唯一性**：同一 `phone` 在 `users` 表中只能对应一条记录（FR-004 去重依据）
- **Distributor 唯一性**：同一 `user_id` 在 `distributors` 表中只能有一条记录（unique FK）
- **单组织归属**：每个 Distributor 只能属于一个 Organization（现有约束，不变）
- **默认组织规则**：`parent_id IS NULL ORDER BY sort_order ASC LIMIT 1`
- **source_channel 值域**：`wechat_register`, `phone_register`, `admin_create`
