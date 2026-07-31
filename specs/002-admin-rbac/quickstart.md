# Quickstart: 后台管理 RBAC 权限管理

**Feature**: 002-admin-rbac
**Date**: 2026-07-31

## Prerequisites

- Backend: Python 3.12, MySQL 8.0 (Tencent Cloud), venv activated
- Frontend: Node.js 18+, npm

## Backend Setup

```bash
cd backend
# Apply migration for is_system field
alembic upgrade head

# Start server (auto-seeds system admin role + admin assignment on first run)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**What the seed does on first startup**:
1. Checks if a role with `is_system = TRUE` exists
2. If not: creates "系统管理员" role with all 22 permissions (see contracts)
3. Finds admin account (username = "admin") and assigns the system admin role

## Frontend Setup

```bash
cd manageSystem
npm install
npm run dev
```

Open `http://localhost:5173` and login.

## Verification Checklist

After startup, verify:

1. **Login**: `admin` / `change-me-immediately` → should succeed and return `permissions: [...]` in user data
2. **Menu**: Left sidebar shows "账户管理" with submenu "管理员列表" and "角色管理"
3. **Admin List** (`/accounts/admins`): Shows admin account with "系统管理员" role badge
4. **Role List** (`/accounts/roles`): Shows "系统管理员" role, no delete button visible
5. **Role Edit**: Open "系统管理员" → permission tree is fully checked, name field is disabled
6. **Create Role**: Create new role "测试角色" with selective permissions → appears in list
7. **Delete Role**: Try to delete "系统管理员" via API → returns error
8. **Create Admin**: Create new admin with "测试角色" → login succeeds with restricted permissions
