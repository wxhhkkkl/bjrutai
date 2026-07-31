# Implementation Plan: 后台管理 RBAC 权限管理

**Branch**: `002-admin-rbac` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-admin-rbac/spec.md`

## Summary

为管理后台 (manageSystem) 实现完整的 RBAC 权限管理体系：重构"账户管理"菜单为两个子菜单（管理员列表 + 角色管理），角色创建/编辑时通过权限勾选树配置权限；后端新增 `is_system` 字段保护系统管理员角色不可删除，首次启动自动播种系统管理员角色并关联 admin 账户。

## Technical Context

**Language/Version**: Python 3.12 (backend), JavaScript (Vue 3 frontend)
**Primary Dependencies**: FastAPI + SQLAlchemy (backend), Vue 3 + Pinia + Element Plus + Axios (frontend)
**Storage**: MySQL 8.0 (Tencent Cloud), JSON column for role permissions
**Testing**: pytest + pytest-asyncio (backend), Vitest + Vue Test Utils (frontend)
**Target Platform**: Web browser (admin SPA), Linux server (backend API)
**Project Type**: Web application (frontend SPA + backend REST API)
**Performance Goals**: 管理员列表分页加载 < 1s，角色编辑权限树渲染 < 500ms
**Constraints**: 前后端通过 REST API 通信，遵循 `{code, message, data, requestId, serverTime}` 统一响应格式
**Scale/Scope**: 管理员账户 < 100，角色 < 50，权限项 < 100

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TDD | ✅ PASS | 后端播种逻辑、API 保护、前端组件均需先写测试 |
| II. API-First | ✅ PASS | 后端 API 已就绪 (`/api/v1/admin/accounts`, `/api/v1/admin/roles`)，仅需增加 `is_system` 保护逻辑，不需新端点 |
| III. Separation of Concerns | ✅ PASS | 前端在 `manageSystem/`，后端在 `backend/`，通过 API 通信 |
| IV. Database Integrity | ✅ PASS | `is_system` 字段通过 Alembic 迁移添加，播种逻辑幂等 |
| V. Simplicity (YAGNI) | ✅ PASS | 不新建独立权限实体，权限以 JSON 存在 Role 上；权限列表由前端常量定义 |

## Project Structure

### Documentation (this feature)

```text
specs/002-admin-rbac/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── admin-rbac.md    # RBAC API contract summary
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   │   ├── role.py              # ADD is_system field
│   │   └── user.py              # AdminAccount (existing)
│   ├── api/v1/
│   │   └── admin_accounts.py    # UPDATE delete_role: protect system role + assigned check
│   ├── services/
│   │   └── seed_service.py      # NEW: seed default system admin role + assign to admin
│   └── main.py                  # UPDATE lifespan: call seed_service
└── migrations/                   # Alembic migration for is_system

manageSystem/
└── src/
    ├── router/index.js           # UPDATE: accounts routes with submenu meta
    ├── pages/accounts/
    │   ├── index.vue             # REWRITE: admin account list + CRUD
    │   └── roles.vue             # REWRITE: role list + CRUD + permission tree dialog
    ├── components/
    │   └── PermissionTree.vue    # NEW: reusable permission checkbox tree
    ├── constants/
    │   └── permissions.js        # NEW: permission definitions by module
    └── stores/
        └── rbac.js               # NEW: RBAC state management (or extend auth.js)
```

**Structure Decision**: 选用 Web application 结构。前端 `manageSystem/`（用户已将 admin 代码移至此目录），后端 `backend/`。权限配置不新建数据库表，复用现有 `roles.permissions` JSON 字段。

## Complexity Tracking

> No violations — all changes align with constitution principles.
